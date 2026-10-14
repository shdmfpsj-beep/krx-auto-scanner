#!/usr/bin/env python3
"""HMA60 first-pullback & historical half-year rotation (2023 H1 -- 2026 H2).
Research only. Sector ETF historic returns are illustrative proxies, not stock fund flows.
PIT stock-sector memberships are optional and mandatory for combined M3 measurement.
"""
from __future__ import annotations
import argparse,csv,json,math,statistics,sys,time
from collections import Counter,defaultdict
from datetime import date,timedelta
from pathlib import Path
import bottom_upturn_v10 as base
import hma60_first_pullback_v11 as hma

FOUR={'036930','034020','006400','131970'}
BENCH={'069500':'KODEX 200','229200':'KODEX 코스닥150'}


def rows_csv(path):
 p=Path(path)
 if not p.exists():return []
 with p.open('r',encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def write(path,rows,fields):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def semester(d):
 return f'{d[:4]}-H{1 if int(d[5:7])<=6 else 2}'

def mean_safe(a):return round(statistics.mean(a),4) if a else None

def med_safe(a):return round(statistics.median(a),4) if a else None

def symbol_map(mapping):
 out={}
 for r in rows_csv(mapping):
  t=r.get('ticker','').strip().zfill(6);m=r.get('market','').strip().upper()
  if t.isdigit() and len(t)==6 and m in ('KOSPI','KOSDAQ'):out[t]=r
 return out

def prepare(args):
 m=symbol_map(args.universe)
 # This is a 2026-10-08 research cohort (not a historical KRX universe).
 selected=sorted(m)
 manifest=[{'ticker':t,'name':m[t].get('name',''),'market':m[t]['market'],
  'symbol':t+('.KS' if m[t]['market']=='KOSPI' else '.KQ'),
  'user_selected_ex_post':str(t in FOUR),'selection_snapshot':'2026-10-08',
  'not_pit_universe':'True'} for t in selected]
 write(Path(args.outdir)/'manifest.csv',manifest, list(manifest[0]) if manifest else ['ticker'])
 audit={'n':len(selected),'kospi':sum(r['market']=='KOSPI' for r in manifest),
 'kosdaq':sum(r['market']=='KOSDAQ' for r in manifest),'user_four':sorted(FOUR.intersection(m)),
 'limitation':'Only present-day 2026-10-08 cohort. No historical surviving/delisted universe.'}
 (Path(args.outdir)/'prepare_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
 print(json.dumps(audit,ensure_ascii=False))


def parse_yf(df):
 import pandas as pd
 if df is None or df.empty:return []
 if isinstance(df.columns,pd.MultiIndex):df.columns=df.columns.get_level_values(0)
 arr=[]
 for day,x in df.iterrows():
  try:
   o,h,l,c,v=[float(x[q]) for q in ['Open','High','Low','Close','Volume']]
   if not all(math.isfinite(i) for i in [o,h,l,c,v]) or min(o,h,l,c)<=0 or v<=0 or h<max(o,c) or l>min(o,c):continue
   arr.append({'Date':str(day.date()),'Open':round(o,6),'High':round(h,6),
               'Low':round(l,6),'Close':round(c,6),'Volume':int(v)})
  except (ValueError,KeyError,AttributeError,TypeError):continue
 return arr

def price_rows_ok(rows):
 if len(rows)<90:return False,'LT90_BARS'
 payload=[];last=None
 for r in rows:
  d=date.fromisoformat(r['Date'])
  if last and (d-last).days>35:return False,'GAP_GT35_DAYS'
  last=d
  payload.append(r)
 return True,'OK'

def fetch(args):
 import yfinance as yf
 manifest=rows_csv(args.manifest)
 selected=[r for i,r in enumerate(manifest) if i%args.shards==args.shard]
 p=Path(args.outdir);(p/'prices').mkdir(parents=True,exist_ok=True)
 statuses=[]
 for n,r in enumerate(selected,1):
  reason='FAILED';bars=[]
  for att in range(1,args.retries+1):
   try:
    frame=yf.download(r['symbol'],start=args.start,end=args.end_exclusive,auto_adjust=False,progress=False,threads=False)
    bars=parse_yf(frame)
    ok,reason=price_rows_ok(bars)
    if ok:break
   except Exception as ex:reason='EXCEPTION_'+type(ex).__name__
   if att<args.retries:time.sleep(1.5*att)
  if reason=='OK':write(p/'prices'/f"{r['ticker']}.csv",bars,['Date','Open','High','Low','Close','Volume'])
  statuses.append({'ticker':r['ticker'],'status':reason,'bars':len(bars),
                   'first_date':bars[0]['Date'] if bars else '',
                   'last_date':bars[-1]['Date'] if bars else ''})
  if n%10==0:print('shard',args.shard,n,'/',len(selected),'valid',sum(z['status']=='OK' for z in statuses),flush=True)
  time.sleep(args.pause)
 write(p/f'fetch_shard_{args.shard}.csv',statuses,['ticker','status','bars','first_date','last_date'])
 print('FETCH_SUMMARY',args.shard,Counter(r['status'] for r in statuses))


def fetch_etfs(args):
 import yfinance as yf
 conf=rows_csv(args.sectors);p=Path(args.outdir);(p/'prices').mkdir(parents=True,exist_ok=True)
 tickers=sorted(set([r['etf_ticker'] for r in conf])|set(BENCH))
 statuses=[]
 for ticker in tickers:
  reason='FAILED';bars=[]
  for at in range(1,args.retries+1):
   try:
    frame=yf.download(ticker+'.KS',start=args.start,end=args.end_exclusive,auto_adjust=False,progress=False,threads=False)
    bars=parse_yf(frame);ok,reason=price_rows_ok(bars)
    if ok:break
   except Exception as ex:reason='EXCEPTION_'+type(ex).__name__
   if at<args.retries:time.sleep(at)
  if reason=='OK':write(p/'prices'/ticker+'.csv',bars,['Date','Open','High','Low','Close','Volume'])
  statuses.append({'ticker':ticker,'status':reason,'bars':len(bars),
                   'first_date':bars[0]['Date'] if bars else '',
                   'last_date':bars[-1]['Date'] if bars else ''})
  time.sleep(args.pause)
 write(p/'etf_fetch_status.csv',statuses,['ticker','status','bars','first_date','last_date'])
 print('ETF_FETCH',Counter(r['status'] for r in statuses))


def cash_flow(b,i):
 """Turnover participation PROXY, not directional net buy; all data through i."""
 if i<30:return {'tv10_ratio':None,'upday_tv_share10':None,'tv5_ratio':None}
 tv=[x['close']*x['volume'] for x in b]
 d20=sum(tv[i-29:i-9])/20
 d10=sum(tv[i-9:i+1])/10
 d20_5=sum(tv[i-24:i-4])/20
 d5=sum(tv[i-4:i+1])/5
 up=sum(tv[j] for j in range(i-9,i+1) if b[j]['close']>b[j]['open'])
 return {'tv10_ratio':round(d10/d20,4) if d20>0 else None,
         'upday_tv_share10':round(up/(10*d10),4) if d10>0 else None,
         'tv5_ratio':round(d5/d20_5,4) if d20_5>0 else None}


def strict_membership(membership,ticker,asof):
 """Only historical membership rows whose *availability* date was <= signal date."""
 matches=[]
 for r in membership:
  if r.get('ticker','').strip().zfill(6)!=ticker:continue
  if not r.get('sector_id') or not r.get('source') or not r.get('known_from'):continue
  if r.get('known_from')>asof:continue
  if r.get('valid_from','9999-12-31')>asof:continue
  if r.get('valid_to') and r['valid_to']<asof:continue
  matches.append(r)
 # Ambiguous mappings are not evidence.
 return matches[0]['sector_id'] if len(matches)==1 else None


def price_load(p,cutoff):
 if not Path(p).exists():return [],'MISSING'
 b,status=base.read_bars(Path(p).read_bytes())
 if status!='OK':return [],status
 b=[r for r in b if r['date']<=cutoff]
 if len(b)<90:return [],'LT90_BARS'
 return b,'OK'


def rolling_etf_features(bar_list,benchmark):
 """Compute per-date RS and turnover using only historical bars up to that close."""
 ans={};bm={r['date']:r['close'] for r in benchmark}
 for i in range(30,len(bar_list)):
  d=bar_list[i]['date']
  past=bar_list[i-20]['date']
  if past not in bm or d not in bm or bm[d]<=0 or bm[past]<=0:continue
  etf=bar_list[i]['close']/bar_list[i-20]['close']-1
  bmr=bm[d]/bm[past]-1
  turnover=lambda z:z['close']*z['volume']
  val10=statistics.mean(turnover(z) for z in bar_list[i-9:i+1]);prev20=statistics.mean(turnover(z) for z in bar_list[i-29:i-9])
  ans[d]={'rs20_pct':round((etf-bmr)*100,4),'tv_ratio':round(val10/prev20,4) if prev20>0 else None,
          'ret20_pct':round(etf*100,4)}
 return ans


def tech_confirm(b,i):
 """Research hypothesis M2: 20-day EMA rising for last 3 sessions, close above."""
 if i<30:return False
 closes=[x['close'] for x in b[:i+1]]
 alpha=2/(20+1);ema=closes[0];seq=[]
 for c in closes:
  ema=alpha*c+(1-alpha)*ema
  seq.append(ema)
 return b[i]['close']>seq[i] and seq[i]>seq[i-3]


def output_stats(rows):
 completed=[x for x in rows if x['status']=='COMPLETE']
 values=[float(x['net_return_pct']) for x in completed if x.get('net_return_pct') not in ('',None)]
 return {'entries':len(rows),'completed':len(completed),'censored':len(rows)-len(completed),
         'win_rate_pct':round(100*sum(v>0 for v in values)/len(values),2) if values else None,
         'mean_net_pct':mean_safe(values),
         'tp10_count':sum('TP10' in x.get('exit_reason','') for x in completed),
         'stops':sum('STOP' in x.get('exit_reason','') for x in completed)}


def analyze(args):
 end=args.asof;out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
 manifest=rows_csv(args.manifest);conf=rows_csv(args.sectors)
 membership=rows_csv(args.membership)
 etf_bars={};etf_quality={}
 for ticker in sorted(set([r['etf_ticker'] for r in conf])|set(BENCH)):
  b,s=price_load(Path(args.etf_prices)/f'{ticker}.csv',end);etf_quality[ticker]=s
  if s=='OK':etf_bars[ticker]=b
 benchmark=etf_bars.get('069500',[])
 etf_signal_features={t:rolling_etf_features(b,benchmark) for t,b in etf_bars.items() if t not in BENCH and benchmark}
 etf_metadata={r['sector_id']:r for r in conf}
 # Daily sector ETF momentum/turnover state: point-in-time through each CLOSE.
 sector_daily=[]
 for r in conf:
  for d,z in sorted(etf_signal_features.get(r['etf_ticker'],{}).items()):
   if '2023-01-01'<=d<=end:
    sector_daily.append({'date':d,'semester':semester(d),'sector_id':r['sector_id'],
      'etf_ticker':r['etf_ticker'],'rs20_pct':z['rs20_pct'],
      'etf_tv_ratio_10_vs_prior20':z['tv_ratio'],
      'ret20_pct':z['ret20_pct'],'source':'ETF_OHLCV_PROXY_NOT_NET_FLOWS'})
 daily_by_date=defaultdict(list)
 for z in sector_daily:daily_by_date[z['date']].append(z)
 for day,rws in daily_by_date.items():
  for rank,z in enumerate(sorted(rws,key=lambda x:(x['rs20_pct'],x['etf_tv_ratio_10_vs_prior20'] or 0),reverse=True),1):
   z['rs_rank_at_close']=rank
 write(out/'v13_sector_state_daily.csv',sector_daily,
    ['date','semester','rs_rank_at_close','sector_id','etf_ticker','rs20_pct',
     'etf_tv_ratio_10_vs_prior20','ret20_pct','source'])
 # Semester full-period performance is retrospective DESCRIPTIVE ONLY.
 etf_sem=[]
 for r in conf:
  t=r['etf_ticker'];b=etf_bars.get(t,[])
  if not b:continue
  grouped=defaultdict(list)
  for item in b:
   if '2023-01-01'<=item['date']<=end:grouped[semester(item['date'])].append(item)
  for half,seq in sorted(grouped.items()):
   if len(seq)<30:continue
   ret=(seq[-1]['close']/seq[0]['close']-1)*100
   rs=etf_signal_features.get(t,{}).get(seq[-1]['date'],{}).get('rs20_pct')
   val=[x['close']*x['volume'] for x in seq]
   etf_sem.append({'semester':half,'sector_id':r['sector_id'],'etf':r['etf_name'],'ticker':t,
          'days_available':len(seq),'first':seq[0]['date'],'last':seq[-1]['date'],
          'return_pct_ex_post':round(ret,3), 'end_20d_rs_vs_kodex200_pct':rs,
          'avg_daily_etf_turnover_bn':round(statistics.mean(val)/1e9,3),
          'interpretation':'RETROSPECTIVE ETF PROXY; not historical fund net inflows'})
 for sem in set(x['semester'] for x in etf_sem):
  ordered=sorted([x for x in etf_sem if x['semester']==sem],key=lambda x:x['return_pct_ex_post'],reverse=True)
  for rank,item in enumerate(ordered,1):item['ex_post_rank']=rank
 write(out/'v13_sector_etf_halfyear.csv',etf_sem,
       ['semester','ex_post_rank','sector_id','etf','ticker','days_available','first','last','return_pct_ex_post','end_20d_rs_vs_kodex200_pct','avg_daily_etf_turnover_bn','interpretation'])
 all_signals=[];all_trades=[];quality=Counter();good=0
 for r in manifest:
  tk=r['ticker'];b,s=price_load(Path(args.prices)/f'{tk}.csv',end)
  quality[s]+=1
  if s!='OK':continue
  good+=1
  hs,ts,h=hma.hma_entries(b,args.min_turnover)
  idx={v['date']:j for j,v in enumerate(b)}
  for sig in hs:
   d=sig['signal_date']
   if d<'2023-01-01' or d>end:continue
   i=idx[d];f=cash_flow(b,i)
   tech=tech_confirm(b,i)
   sec_id=strict_membership(membership,tk,d)
   sec=etf_metadata.get(sec_id) if sec_id else None
   ef=etf_signal_features.get(sec['etf_ticker'],{}).get(d) if sec else None
   sector_ok=ef is not None and ef['rs20_pct']>0 and ef['tv_ratio'] is not None and ef['tv_ratio']>1.2
   # Unknown sector membership -> M3 cannot be evaluated at all.
   m3='PASS' if tech and sector_ok else ('REJECT' if tech and ef is not None else 'UNVERIFIED_PIT_SECTOR')
   siginfo={'ticker':tk,'name':r.get('name',''),'semester':semester(d),
      'user_selected_ex_post':str(tk in FOUR),'signal_date':d,'entry_date':sig['entry_date'],
      'turn_date':sig['turn_date'],'model_M1':True,'model_M2':tech,'model_M3':m3,
      'sector_id_pit':sec_id or '',
      'sector_rs20_pct':ef['rs20_pct'] if ef else None,
      'sector_etf_tv_ratio':ef['tv_ratio'] if ef else None,**f}
   all_signals.append(siginfo)
   # Independent cohort excludes hand-picked four, remains present-day survivor selection.
   if tk in FOUR:continue
   for model,on in [('M1',True),('M2',tech),('M3',m3=='PASS')]:
    if not on:continue
    for variant in base.VARIANTS:
     res=base.run_exit(b,sig,variant,args.max_hold,args.cost_bps)
     all_trades.append({'ticker':tk,'semester':semester(d),'model':model,'variant':variant,
       'signal_date':d,'entry_date':sig['entry_date'], 'sector_id_pit':sec_id or '',
       'tv10_ratio':f['tv10_ratio'],'upday_tv_share10':f['upday_tv_share10'],
       'sector_rs20_pct':ef['rs20_pct'] if ef else None,
       'sector_etf_tv_ratio':ef['tv_ratio'] if ef else None,**res})
 write(out/'v13_signals.csv',all_signals,['ticker','name','semester','user_selected_ex_post','signal_date','entry_date','turn_date','model_M1','model_M2','model_M3','sector_id_pit','sector_rs20_pct','sector_etf_tv_ratio','tv10_ratio','upday_tv_share10','tv5_ratio'])
 write(out/'v13_trades.csv',all_trades,
       ['ticker','semester','model','variant','signal_date','entry_date','sector_id_pit','tv10_ratio','upday_tv_share10',
        'sector_rs20_pct','sector_etf_tv_ratio','status','exit_date','exit_reason','days_held','net_return_pct','gross_return_pct'])
 all_halves=[f'{year}-H{half}' for year in range(2023,2027) for half in (1,2)]
 sums=[]
 for sem in all_halves:
  for model in ['M1','M2','M3']:
   for variant in base.VARIANTS:
    cohort=[t for t in all_trades if t['semester']==sem and t['model']==model and t['variant']==variant]
    state='NOT_EVALUABLE_NO_PIT_MEMBERSHIP' if model=='M3' and not membership else ('NO_ENTRIES' if not cohort else 'EXPLORATORY')
    sums.append({'semester':sem,'model':model,'variant':variant,'status':state,**output_stats(cohort)})
 write(out/'v13_model_by_halfyear.csv',sums,['semester','model','variant','status','entries','completed','censored','win_rate_pct','mean_net_pct','tp10_count','stops'])
 coverage={'requested_tickers':len(manifest),'usable_tickers':good,'quality':dict(quality),
  'sector_etfs_requested':len(set(x['etf_ticker'] for x in conf)),
  'sector_etfs_usable':len([e for e in conf if e['etf_ticker'] in etf_bars]),
  'etf_status':etf_quality,'stock_signals':len(all_signals),
  'pit_sector_mapping_rows':len(membership),
  'pit_sector_linked_signals':sum(bool(z['sector_id_pit']) for z in all_signals),
  'm3_evaluable':bool(membership and etf_signal_features),
  'asof':end,'periods':all_halves,'historical_universe_pit':False,
  'historical_sector_membership_pit':'ONLY if a verifiable dated mapping file is supplied',
  'net_fund_flow_confirmed':False,'sector_daily_rows':len(sector_daily),
  'warnings':['Current 2026 stock cohort creates survivorship and selection bias in 2023-25.',
              'ETF volume*price is turnover, NEVER stock/sector net inflow.',
              'Half-year ETF top returns are retrospective, not available as rankings at entry.',
              'At trade entry only RS/turnover calculated through preceding/current confirmed close.',
              'M3 not claimable when PIT historical sector membership absent.',
              'Missing and censored trades are not assumed successful or unsuccessful.',
              'No verified institutional/foreign net buys, no transactions.']}
 (out/'v13_audit.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'usable':good,'signals':len(all_signals),'etfs':coverage['sector_etfs_usable'],'m3':coverage['m3_evaluable'],'quality':dict(quality)},ensure_ascii=False))


def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True)
 a=sub.add_parser('prepare');a.add_argument('--universe',required=True);a.add_argument('--outdir',required=True)
 b=sub.add_parser('fetch');b.add_argument('--manifest',required=True);b.add_argument('--outdir',required=True)
 b.add_argument('--shard',type=int,default=0);b.add_argument('--shards',type=int,default=6)
 c=sub.add_parser('fetch-etfs');c.add_argument('--sectors',required=True);c.add_argument('--outdir',required=True)
 for subp in [b,c]:
  subp.add_argument('--start',default='2022-08-01');subp.add_argument('--end-exclusive',required=True)
  subp.add_argument('--retries',type=int,default=2);subp.add_argument('--pause',type=float,default=.5)
 d=sub.add_parser('analyze');d.add_argument('--manifest',required=True);d.add_argument('--prices',required=True)
 d.add_argument('--etf-prices',required=True);d.add_argument('--sectors',required=True)
 d.add_argument('--membership',required=True);d.add_argument('--asof',required=True)
 d.add_argument('--outdir',required=True);d.add_argument('--max-hold',type=int,default=60)
 d.add_argument('--cost-bps',type=float,default=35);d.add_argument('--min-turnover',type=float,default=500_000_000)
 args=p.parse_args()
 if args.cmd=='prepare':prepare(args)
 elif args.cmd=='fetch':fetch(args)
 elif args.cmd=='fetch-etfs':fetch_etfs(args)
 else:analyze(args)
if __name__=='__main__':main()
