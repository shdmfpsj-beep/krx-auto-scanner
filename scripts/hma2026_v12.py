#!/usr/bin/env python3
"""HMA60/volume flow 2026 dated cohort. RESEARCH ONLY, NOT LIVE ORDERS.

Input: new, unspliced, ticker-specific OHLCV histories fetched as a consistent
source from 2025-01-01 through an explicit as-of. 2026-10-08 *current*
sector assignments are NOT valid point-in-time classifications in earlier dates.

Commands:
  prepare --source reports/v36_ohlcv_cache --mapping reports/v65_sector_stock_map.csv
  fetch --manifest work/manifest.csv --shard 0 --shards 6 --outdir work/shard0
  study --manifest work/manifest.csv --prices work/all/prices --asof 2026-10-13
"""
from __future__ import annotations
import argparse, csv, io, json, math, time, statistics, sys
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta

import bottom_upturn_v10 as base
import hma60_first_pullback_v11 as hm

USER_FOUR={'036930':('주성엔지니어링','KOSDAQ','2026-09-03'),
 '034020':('두산에너빌리티','KOSPI','2026-08-24'),
 '006400':('삼성SDI','KOSPI','2026-08-11'),
 '131970':('두산테스나','KOSDAQ','2026-09-15')}


def read_csv(path):
 p=Path(path)
 if not p.exists():return []
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def save_csv(path, rows, fields):base.csv_out(path,rows,fields)


def ticker_set(source):
 source=Path(source)
 if not source.exists():raise FileNotFoundError(f'Cache missing: {source}')
 result=set()
 for ticker,_ in base.iter_source(source):
  if len(ticker)==6 and ticker.isdigit():result.add(ticker)
 return result


def prepare(args):
 chosen=ticker_set(args.source)
 mappings={}
 for r in read_csv(args.mapping):
  code=(r.get('ticker') or '').strip().zfill(6)
  if not code.isdigit() or len(code)!=6:continue
  market=(r.get('market') or '').strip().upper()
  if market not in ('KOSPI','KOSDAQ'):continue
  # Dated snapshot ONLY for discovery and labels, never assume old membership.
  mappings[code]=r
 if args.universe_mode=='all_snapshot':chosen=set(mappings)
 chosen.update(USER_FOUR)
 manifest=[];skipped=[]
 for tk in sorted(chosen):
  if tk in USER_FOUR:
   nm,mkt,_=USER_FOUR[tk]
  else:
   r=mappings.get(tk,{})
   nm=r.get('name','');mkt=r.get('market','')
  if mkt not in ('KOSPI','KOSDAQ'):
   skipped.append(dict(ticker=tk,reason='NO_CONFIRMED_MARKET',snapshot_source=args.mapping));continue
  ref=mappings.get(tk,{})
  manifest.append(dict(ticker=tk,name=nm,market=mkt,suffix='.KS' if mkt=='KOSPI' else '.KQ',user_example=tk in USER_FOUR,
      sector_snapshot=ref.get('sector',''),snapshot_date=ref.get('snapshot_date',''),
      sector_historical_pit_verified='False'))
 p=Path(args.outdir);p.mkdir(parents=True,exist_ok=True)
 fields=['ticker','name','market','suffix','user_example','sector_snapshot','snapshot_date','sector_historical_pit_verified']
 save_csv(p/'manifest.csv',manifest,fields)
 save_csv(p/'prepare_skipped.csv',skipped,['ticker','reason','snapshot_source'])
 audit=dict(version='12.0',mode=args.universe_mode,original_cache_symbols=len(ticker_set(args.source)),
            current_snapshot_symbols=len(mappings),output_symbols=len(manifest),unverified_market_skipped=len(skipped),
            user_four_present=all(t in {r['ticker'] for r in manifest} for t in USER_FOUR),
            sector_membership_pit_verified=False,source_snapshot=args.mapping,
            limitation='2026-10-08 sector labels are retrospective descriptions, NEVER an as-of sector backtest filter.')
 (p/'prepare_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(audit,ensure_ascii=False))
 return manifest


def parse_yfinance(frame):
 import pandas as pd
 if frame is None or frame.empty:return []
 if isinstance(frame.columns,pd.MultiIndex):frame.columns=frame.columns.get_level_values(0)
 out=[]
 for d,r in frame.iterrows():
  try:
   dt=str(d.date()); vals=[float(r[k]) for k in ('Open','High','Low','Close','Volume')]
   if not all(math.isfinite(x) for x in vals):continue
   o,h,l,c,v=vals
   if min(o,h,l,c)<=0 or v<=0 or h<max(o,c) or l>min(o,c):continue
   out.append(dict(Date=dt,Open=round(o,6),High=round(h,6),Low=round(l,6),Close=round(c,6),Volume=int(v)))
  except (KeyError,TypeError,ValueError,AttributeError):continue
 return out


def has_big_gaps(rows,max_days=35):
 ds=[date.fromisoformat(r['Date']) for r in rows]
 return [(str(a),str(b),(b-a).days) for a,b in zip(ds,ds[1:]) if (b-a).days>max_days]


def validate_rows(rows,start,end):
 if not rows:return 'EMPTY',[]
 if len(rows)<220:return 'INSUFFICIENT_220_BARS',[]
 if rows[-1]['Date']>=end:return 'DATE_AFTER_REQUESTED_CUTOFF',[]
 if (date.fromisoformat(end)-timedelta(days=1)-date.fromisoformat(rows[-1]['Date'])).days>7:return 'STALE_MORE_THAN_7_CAL_DAYS',[]
 if rows[0]['Date']>='2025-08-01':return 'MISSING_PRE_2025_AUG',[]
 if rows[-1]['Date']<'2026-10-01':return 'MISSING_OCT_2026',[]
 if has_big_gaps(rows):return 'LONG_GAP_GT35_CAL_DAYS',[]
 payload=io.StringIO();writer=csv.DictWriter(payload,fieldnames=['Date','Open','High','Low','Close','Volume']);writer.writeheader();writer.writerows(rows)
 bars,status=base.read_bars(payload.getvalue().encode())
 return ('OK' if status=='OK' else status),bars


def fetch(args):
 import yfinance as yf
 all_rows=read_csv(args.manifest)
 shard=[r for i,r in enumerate(all_rows) if i%args.shards==args.shard]
 p=Path(args.outdir);(p/'prices').mkdir(parents=True,exist_ok=True)
 status=[];last_seen=[]
 for count,row in enumerate(shard):
  tk=row['ticker'];symbol=tk+row['suffix'];bars=[];reason='';rows=[]
  for attempt in range(1,args.retries+1):
   try:
    frame=yf.download(symbol,start=args.start,end=args.end_exclusive,auto_adjust=False,progress=False,threads=False)
    rows=parse_yfinance(frame)
    if not rows:reason='EMPTY_DOWNLOAD'
    else:reason,_bars=validate_rows(rows,args.start,args.end_exclusive)
    if rows:break
   except Exception as ex:reason='ERROR_'+type(ex).__name__
   if attempt<args.retries:time.sleep(attempt*2)
  # Store valid data only; prevents silently splicing short/inconsistent caches.
  if reason=='OK':
   save_csv(p/'prices'/f'{tk}.csv',rows,['Date','Open','High','Low','Close','Volume'])
  status.append(dict(ticker=tk,symbol=symbol,status=reason,bars=len(rows),first=rows[0]['Date'] if rows else '',last=rows[-1]['Date'] if rows else '',shard=args.shard))
  if (count+1)%10==0:print(json.dumps(dict(shard=args.shard,done=count+1,total=len(shard),ok=sum(x['status']=='OK' for x in status)),ensure_ascii=False),flush=True)
  time.sleep(args.pause)
 save_csv(p/f'fetch_shard_{args.shard}.csv',status,['ticker','symbol','status','bars','first','last','shard'])
 summary=dict(shard=args.shard,requested=len(shard),valid=sum(r['status']=='OK' for r in status),status=dict(Counter(r['status'] for r in status)),start=args.start,end_exclusive=args.end_exclusive,
 source='Yahoo Finance/yfinance unofficial prices, auto_adjust=False', downloaded_at_utc=datetime.now().astimezone().isoformat(),research_only=True)
 (p/f'fetch_shard_{args.shard}.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False))


def money_features(b,signal_index):
 i=signal_index
 if i<40:return dict(tv_ratio_10_vs_prior20=None,upday_turnover_share_10=None,tv_ratio_5_vs_prior20=None,price_5d_pct=None)
 tv=[x['close']*x['volume'] for x in b]
 old20=sum(tv[i-29:i-9])/20
 v10=sum(tv[i-9:i+1])/10
 old20_5=sum(tv[i-24:i-4])/20
 v5=sum(tv[i-4:i+1])/5
 uptv=sum(b[j]['close']*b[j]['volume'] for j in range(i-9,i+1) if b[j]['close']>b[j]['open'])
 return dict(tv_ratio_10_vs_prior20=round(v10/old20,6) if old20>0 else None,
  tv_ratio_5_vs_prior20=round(v5/old20_5,6) if old20_5>0 else None,
  upday_turnover_share_10=round(uptv/(10*v10),6) if v10 else None,
  price_5d_pct=round((b[i]['close']/b[i-5]['close']-1)*100,4))


def market_calendar_daily_flow(dates_to_bars, man):
 """Sampled universe only; 2026-10-08 sector labels = retrospective, not PIT."""
 groups=defaultdict(lambda:defaultdict(lambda:{'turnover':0.0,'n':0,'up':0}))
 for tk,b in dates_to_bars.items():
  sector=man.get(tk,{}).get('sector_snapshot','').strip() or 'UNKNOWN'
  for r in b:
   if not ('2026-01-01'<=r['date']):continue
   val=r['close']*r['volume']
   z=groups[r['date']][sector]
   z['turnover']+=val;z['n']+=1;z['up']+=int(r['close']>r['open'])
 out=[]
 for dt,sectors in sorted(groups.items()):
  daytotal=sum(v['turnover'] for v in sectors.values())
  for sector,v in sectors.items():
   out.append(dict(date=dt,sector_snapshot=sector,n_sample_stocks=v['n'],turnover_sample_billion=round(v['turnover']/1e9,4),
      turnover_sample_share_pct=round(v['turnover']/daytotal*100,3) if daytotal else None,
      rising_candle_share_pct=round(v['up']/v['n']*100,3) if v['n'] else None,
      sector_historical_pit_verified='False'))
 return out


def study(args):
 p=Path(args.outdir);p.mkdir(parents=True,exist_ok=True)
 m={r['ticker']:r for r in read_csv(args.manifest)}
 prices=Path(args.prices)
 statuses=Counter();reports=[];entryrows=[];traderows=[];illustrative_trades=[];caserows=[];validated={};turns_rows=[]
 for tk,row in sorted(m.items()):
  file=prices/f'{tk}.csv'
  if not file.exists():
   statuses['NO_VALID_PRICE_FILE']+=1
   reports.append(dict(ticker=tk,market=row['market'],status='NO_VALID_PRICE_FILE',bars=0,first='',last=''))
   continue
  b,q=base.read_bars(file.read_bytes());statuses[q]+=1
  # Recheck exact asof and continuity; no future dates may enter signals or outcomes.
  b=[x for x in b if x['date']<=args.asof]
  if q!='OK' or len(b)<220 or not b or b[0]['date']>='2025-08-01' or (date.fromisoformat(args.asof)-date.fromisoformat(b[-1]['date'])).days>7 or b[-1]['date']<'2026-10-01' or has_big_gaps([dict(Date=r['date']) for r in b]):
   reports.append(dict(ticker=tk,market=row['market'],status='FAILED_ASOF_OR_HISTORY',bars=len(b),first=b[0]['date'] if b else '',last=b[-1]['date'] if b else ''))
   continue
  validated[tk]=b
  reports.append(dict(ticker=tk,market=row['market'],status='USABLE_2026',bars=len(b),first=b[0]['date'],last=b[-1]['date']))
  entries,turns,h=hm.hma_entries(b,args.min_turnover)
  for j in turns:
   if b[j]['date'].startswith('2026'):
    turns_rows.append(dict(ticker=tk,turn_date=b[j]['date'],hma60=round(h[j],6),sector_snapshot=row.get('sector_snapshot',''),
      sector_historical_pit_verified=False))
  for e in entries:
   if not e['entry_date'].startswith('2026'):continue
   ix=next((i for i,r in enumerate(b) if r['date']==e['signal_date']),None)
   feature=money_features(b,ix) if ix is not None else {}
   common=dict(ticker=tk,name=row['name'],market=row['market'],sector_snapshot=row.get('sector_snapshot',''),
      snapshot_date=row.get('snapshot_date',''),sector_pit_verified=False,
      user_nominated_example=tk in USER_FOUR,**e,**feature)
   if tk not in USER_FOUR:entryrows.append(common)
   for variant in base.VARIANTS:
    r=base.run_exit(b,e,variant,args.max_hold,args.cost_bps)
    record=dict(**common,variant=variant,**r)
    if tk in USER_FOUR:illustrative_trades.append(record)
    else:traderows.append(record)
 # Four user examples are hindsight-selected and cannot count as random validation cohort.
 for tk,(name,mkt,ref) in USER_FOUR.items():
  b=validated.get(tk)
  if not b:
   caserows.append(dict(ticker=tk,name=name,reference_date=ref,data_status='NOT_VERIFIED',nearest_turn_date='',nearest_turn_delta_sessions='',
      first_entry_date='',first_entry_signal_date='',trade_result='NOT_VERIFIED'))
   continue
  ht=hm.hma([x['close'] for x in b]);ts=list(hm.turn_dates(b,ht));idx=next((i for i,r in enumerate(b) if r['date']>=ref),len(b)-1)
  near=min(ts,key=lambda k:abs(k-idx)) if ts else None
  selected=[r for r in illustrative_trades if r['ticker']==tk and r['variant']=='A_10_ALL' and abs((date.fromisoformat(r['turn_date'])-date.fromisoformat(ref)).days)<=40]
  best=min(selected,key=lambda x:abs((date.fromisoformat(x['turn_date'])-date.fromisoformat(ref)).days)) if selected else None
  caserows.append(dict(ticker=tk,name=name,reference_date=ref,data_status='AVAILABLE' if b else 'NOT_VERIFIED',
    nearest_turn_date=b[near]['date'] if near is not None else '',nearest_turn_delta_sessions=(near-idx) if near is not None else '',
    first_entry_date=best['entry_date'] if best else '',first_entry_signal_date=best['signal_date'] if best else '',
    trade_result='EXAMPLE_ONLY_NOT_IN_INDEPENDENT_VALIDATION'))
 # 2026 outcomes: censor whenever no exit is completed, do not impute +10/-stop.
 sums=[]
 for v in base.VARIANTS:
  sub=[t for t in traderows if t['variant']==v]
  complete=[t for t in sub if t['status']=='COMPLETE']
  wins=sum('TP10' in t.get('exit_reason','') for t in complete)
  stops=sum('STOP' in t.get('exit_reason','') for t in complete)
  censor=len(sub)-len(complete)
  rets=[float(t['net_return_pct']) for t in complete]
  sums.append(dict(variant=v,signals=len(sub),completed=len(complete),censored=censor,completed_tp10=wins,completed_stop=stops,
       tp10_over_completed_pct=round(wins/len(complete)*100,2) if complete else None,
       mean_net_completed_pct=round(statistics.mean(rets),3) if rets else None,
       caveat='Incomplete outcomes and selected universe: no unbiased hit rate'))
 bins=[]
 a=[t for t in traderows if t['variant']=='A_10_ALL' and t['status']=='COMPLETE']
 for lo,hi in [(0,1),(1,1.5),(1.5,2),(2,1e9)]:
  v=[r for r in a if r.get('tv_ratio_10_vs_prior20') is not None and lo<=r['tv_ratio_10_vs_prior20']<hi]
  bins.append(dict(turnover_ratio_bin=f'[{lo},{hi})',completed=len(v),tp10=sum('TP10' in r.get('exit_reason','') for r in v),
    average_net_pct=round(statistics.mean(float(r['net_return_pct']) for r in v),3) if v else None,
    observational_only=True))
 sectors=market_calendar_daily_flow(validated,m)
 save_csv(p/'v12_price_quality.csv',reports,['ticker','market','status','bars','first','last'])
 save_csv(p/'v12_2026_turn_events.csv',turns_rows,['ticker','turn_date','hma60','sector_snapshot','sector_historical_pit_verified'])
 common_fields=['ticker','name','market','sector_snapshot','snapshot_date','sector_pit_verified','user_nominated_example','turn_date','impulse_date','pullback_start','signal_date','entry_date','entry_price','stop','risk_pct','tv_ratio_10_vs_prior20','tv_ratio_5_vs_prior20','upday_turnover_share_10','price_5d_pct']
 save_csv(p/'v12_2026_signal_features.csv',entryrows,common_fields)
 save_csv(p/'v12_2026_trades.csv',traderows,common_fields+['variant','status','exit_date','exit_reason','days_held','net_return_pct','gross_return_pct'])
 save_csv(p/'v12_four_illustrative_trades_excluded.csv',illustrative_trades,common_fields+['variant','status','exit_date','exit_reason','days_held','net_return_pct','gross_return_pct'])
 save_csv(p/'v12_2026_summary.csv',sums,['variant','signals','completed','censored','completed_tp10','completed_stop','tp10_over_completed_pct','mean_net_completed_pct','caveat'])
 save_csv(p/'v12_turnover_groups.csv',bins,['turnover_ratio_bin','completed','tp10','average_net_pct','observational_only'])
 save_csv(p/'v12_sector_sample_proxy.csv',sectors,['date','sector_snapshot','n_sample_stocks','turnover_sample_billion','turnover_sample_share_pct','rising_candle_share_pct','sector_historical_pit_verified'])
 save_csv(p/'v12_four_cases.csv',caserows,['ticker','name','reference_date','data_status','nearest_turn_date','nearest_turn_delta_sessions','first_entry_date','first_entry_signal_date','trade_result'])
 coverage=len(validated)/len(m) if m else 0
 audit=dict(version='12.0',asof=args.asof,research_only=True,live_trade_authorized=False,
      requested_tickers=len(m),full_asof_2026_history=len(validated),coverage_ratio=round(coverage,4),
      preliminary_quality_states=dict(statuses),turn_events_2026=len(turns_rows),entries_2026=len(entryrows),
      nominated_cases_covered=sum(bool(r['data_status']=='AVAILABLE') for r in caserows), user_four_excluded_from_performance_cohort=True, illustrative_trade_rows=len(illustrative_trades),
      no_hindsight_selection_verified=False,sector_pit_verified=False,sector_flow_is_true_net_buy=False,
      caveats=['Data provider unofficial; Yahoo adjusted/unadjusted corporate actions not fully independently verified',
       'Tickers selected from a 2026-10-08 present-day sample; survivorship, selection and coverage biases remain',
       '2026-10-08 snapshot sector labels are retrospective only, never verified as of older 2026 dates',
       'Turnover proxy close*volume is activity, not buyer net capital inflow',
       'Sector share denominator is coverage of valid sample ONLY, not full KRX',
       'Right-censored positions are excluded from completed statistics but explicitly reported',
       'HMA first-pullback v1.1 thresholds previously examined on 2023-25; truly held-out test not established',
       'Intrabar stop-first and fills are model assumptions, gaps not guaranteed executable'],
      status='DATA_PENDING' if len(validated)<args.min_valid else 'EXPLORATORY_WITH_BIAS',
      prerequisites_for_strict=['historical listed/unlisted KRX universe', 'dated sector membership', 'source reconciliation', 'slippage and execution auditing'])
 (p/'v12_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'audit':audit,'summary':sums,'turnover_groups':bins,'cases':caserows},ensure_ascii=False))
 return audit


def main():
 ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
 a=sub.add_parser('prepare');a.add_argument('--source',required=True);a.add_argument('--mapping',required=True);a.add_argument('--outdir',default='work/v12');a.add_argument('--universe-mode',choices=['v36','all_snapshot'],default='v36')
 a=sub.add_parser('fetch');a.add_argument('--manifest',required=True);a.add_argument('--outdir',required=True);a.add_argument('--shard',type=int,required=True);a.add_argument('--shards',type=int,default=6);a.add_argument('--start',default='2025-01-01');a.add_argument('--end-exclusive',default='2026-10-14');a.add_argument('--retries',type=int,default=2);a.add_argument('--pause',type=float,default=.6)
 a=sub.add_parser('study');a.add_argument('--manifest',required=True);a.add_argument('--prices',required=True);a.add_argument('--outdir',default='reports/hma_v12');a.add_argument('--asof',default='2026-10-13');a.add_argument('--max-hold',type=int,default=60);a.add_argument('--cost-bps',type=float,default=35);a.add_argument('--min-turnover',type=float,default=500_000_000);a.add_argument('--min-valid',type=int,default=50)
 args=ap.parse_args()
 if args.command=='prepare':prepare(args)
 elif args.command=='fetch':
  if args.shards<1 or args.shard<0 or args.shard>=args.shards:ap.error('Invalid shard')
  fetch(args)
 else:study(args)
if __name__=='__main__':main()
