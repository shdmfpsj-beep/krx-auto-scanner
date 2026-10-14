#!/usr/bin/env python3
"""v1.4: compare four first-pullback *hypotheses* and daily rolling ETF sector proxies.

No investment orders, no look-ahead outcomes in entry qualification. 2026 snapshot
stock universe is NOT historical KRX point-in-time universe. Sector-link comparison
is forbidden without verified point-in-time sector memberships.
"""
from __future__ import annotations
import argparse,csv,json,math,statistics
from datetime import date
from pathlib import Path
from collections import Counter,defaultdict

import bottom_upturn_v10 as base
import hma60_first_pullback_v11 as hma
import hma_rotation_v13 as upstream

MODELS=('HMA60_PULLBACK','HMA40_PULLBACK','HMA60_EMA20_RECLAIM','DONCHIAN20_RETEST')
HANDPICK={'036930','034020','006400','131970'}
BASELINE_ETF='069500'


def ema(xs,n):
    alpha=2/(n+1);value=None;out=[]
    for x in xs:
        value=x if value is None else alpha*x+(1-alpha)*value
        out.append(value)
    return out


def turn_indices(b,h):
    """Turn confirmed at the current close; past >=4 declining slopes/8."""
    ans=[]
    for i in range(85,len(b)-1):
        if any(h[j] is None for j in range(i-9,i+1)):continue
        if not (h[i]>h[i-1] and h[i-1]<=h[i-2]):continue
        if sum(h[j]<h[j-1] for j in range(i-9,i-1))<4:continue
        if b[i]['close']<h[i]*.97:continue
        ans.append(i)
    return ans


def mk_entry(b,p,start,turn,imp,model,stop):
    """Entry uses next open for fill/stop distance; signal uses <=p only."""
    if p+1>=len(b):return None
    nxt=b[p+1];today=b[p]
    op=nxt['open'];gap=op/today['close']-1
    if gap>.025 or gap<-.06 or op<=stop:return None
    risk=1-stop/op
    if not(.02<=risk<=.08):return None
    return {'model':model,'turn_date':b[turn]['date'] if turn is not None else '',
            'impulse_date':b[imp]['date'],'pullback_start':b[start]['date'],
            'signal_idx':p,'signal_date':today['date'],'entry_idx':p+1,
            'entry_date':nxt['date'],'entry_price':op,'stop':stop,
            'risk_pct':round(risk*100,4),'risk_gate_10pct_2r':risk<=.05,
            'gap_pct':round(gap*100,4),'setup':'FIRST_PULLBACK'}


def turn_pullback(b,h,period):
    """First corrective sequence after confirmed HMA turning and 12-day close breakout."""
    proposed=[]
    for t in turn_indices(b,h):
        impulse=None
        for j in range(t,min(t+13,len(b)-1)):
            if j<25 or h[j] is None:continue
            prev=max(x['close'] for x in b[j-12:j]);q=b[j]
            if (q['close']>=prev*1.002 and q['close']>h[j]*.995 and
                q['close']>=b[t]['close']*1.015 and q['close']/b[t]['close']<=1.22):
                impulse=j;break
        if impulse is None:continue
        start=None
        for j in range(impulse+1,min(impulse+11,len(b)-1)):
            if b[j]['close']<b[j-1]['close']*.997 or b[j]['close']<b[j]['open']*.995:
                start=j;break
        if start is None:continue
        peak=max(x['high'] for x in b[impulse:start+1])
        for p in range(start+1,min(start+9,len(b)-1)):
            q=b[p];prev=b[p-1];leg=b[start:p]
            if not leg:continue
            low=min(x['low'] for x in leg)
            if low>peak*.987:continue
            if h[p] is None or q['close']<h[p]*.985:continue
            if low<h[p]*.91:break
            if low<b[t]['close']*.91:break
            if not (q['close']>prev['high']*.993 and q['close']>q['open'] and q['close']>prev['close']*1.002):continue
            stop=min(x['low'] for x in b[start:p+1])*.985
            e=mk_entry(b,p,start,t,impulse,f'HMA{period}_PULLBACK',stop)
            if e:proposed.append(e)
            break
    return proposed


def price_breaks(b,lookback=20):
    return [i for i in range(105,len(b)-1)
            if b[i]['close']>max(x['high'] for x in b[i-lookback:i])*1.002
            and b[i]['close']>b[i]['open']]


def ema_reclaim(b,h60,em20):
    """HMA60 flat/up and breakout; first low near EMA20 followed by price reclaim."""
    proposed=[]
    for imp in price_breaks(b,15):
        if imp<85 or any(h60[j] is None for j in (imp,imp-5)):continue
        if h60[imp]<h60[imp-5]*.992:continue
        start=None
        for j in range(imp+1,min(imp+12,len(b)-1)):
            if b[j]['low']<=em20[j]*1.01 and b[j]['close']<=b[imp]['close']*.99:
                start=j;break
        if start is None:continue
        for p in range(start+1,min(start+8,len(b)-1)):
            q=b[p]
            if min(x['low'] for x in b[start:p])<em20[p]*.91:break
            if not (q['close']>=em20[p] and q['close']>q['open'] and q['close']>b[p-1]['high']*.994):continue
            if q['close']<h60[p]*.988:continue
            stop=min(x['low'] for x in b[start:p+1])*.985
            e=mk_entry(b,p,start,None,imp,'HMA60_EMA20_RECLAIM',stop)
            if e:proposed.append(e)
            break
    return proposed


def donchian_retest(b,em50):
    """Close through 20-day HIGH, first retest of former resistance, bullish reclaim."""
    proposed=[]
    for imp in price_breaks(b,20):
        if em50[imp]<=em50[imp-5]:continue
        resistance=max(x['high'] for x in b[imp-20:imp])
        start=None
        for j in range(imp+1,min(imp+11,len(b)-1)):
            if b[j]['low']<=resistance*1.02 and b[j]['close']<=b[imp]['close']*.995:
                start=j;break
        if start is None:continue
        for p in range(start+1,min(start+8,len(b)-1)):
            q=b[p]
            low=min(x['low'] for x in b[start:p])
            if low<resistance*.91:break
            if not (q['close']>resistance*.992 and q['close']>q['open'] and q['close']>b[p-1]['high']*.994):continue
            stop=min(x['low'] for x in b[start:p+1])*.985
            e=mk_entry(b,p,start,None,imp,'DONCHIAN20_RETEST',stop)
            if e:proposed.append(e)
            break
    return proposed


def select_chronological(entries,cooldown=60):
    # Signals with same stock close together are competing entries; don't use future exits
    # to decide which one to select. Earliest confirmed entry wins.
    out=[];until=-1
    for e in sorted(entries,key=lambda x:(x['entry_idx'],x['signal_idx'])):
        if e['entry_idx']<=until:continue
        out.append(e);until=e['entry_idx']+cooldown
    return out


def entry_models(b):
    closes=[x['close'] for x in b]
    h60=hma.hma(closes,60);h40=hma.hma(closes,40)
    em20=ema(closes,20);em50=ema(closes,50)
    return {m:select_chronological(proposed) for m,proposed in (
        ('HMA60_PULLBACK',turn_pullback(b,h60,60)),
        ('HMA40_PULLBACK',turn_pullback(b,h40,40)),
        ('HMA60_EMA20_RECLAIM',ema_reclaim(b,h60,em20)),
        ('DONCHIAN20_RETEST',donchian_retest(b,em50)))}


def _ratio(a,b):return (a/b-1)*100 if b>0 else None


def rolling_sector_bars(b,benchmark):
    """Each date uses only already CLOSED ETF/benchmark bars, NEVER semester winners."""
    bm={x['date']:x['close'] for x in benchmark}
    val=lambda x:x['close']*x['volume']
    out={}
    for i in range(80,len(b)):
        d=b[i]['date']
        # Different trading calendars or stale benchmark rows: skip rather than forward-fill.
        if d not in bm or any(b[i-n]['date'] not in bm for n in (5,10,20,60)):continue
        sector_r={n:_ratio(b[i]['close'],b[i-n]['close']) for n in (5,10,20,60)}
        rs={n:sector_r[n]-_ratio(bm[d],bm[b[i-n]['date']]) for n in (5,10,20,60)}
        prev20=sum(val(x) for x in b[i-29:i-9])/20
        tv10=sum(val(x) for x in b[i-9:i+1])/10
        prev5=sum(val(x) for x in b[i-10:i-5])/5
        cur5=sum(val(x) for x in b[i-4:i+1])/5
        tv_ratio=tv10/prev20 if prev20 else None
        tv5=cur5/prev5 if prev5 else None
        accel=rs[5] - (rs[20]/4)
        # A stated descriptive rule, not a fitted optimal classifier.
        if rs[5]>1 and accel>0 and tv_ratio is not None and tv_ratio>1.2:
            phase='NEW_IGNITION' if rs[20]<=2 else 'EXPANSION'
        elif rs[20]>2 and rs[5]>0:phase='LEADING'
        elif rs[20]>2 and rs[5]<=0:phase='COOLING'
        elif rs[5]<-1 and rs[20]<0:phase='WEAK'
        else:phase='NEUTRAL'
        out[d]={'date':d,'rs5_pct':round(rs[5],3),'rs10_pct':round(rs[10],3),
                'rs20_pct':round(rs[20],3),'rs60_pct':round(rs[60],3),
                'rs_accel_5_vs_20':round(accel,3),
                'etf_tv10_vs_prev20':round(tv_ratio,3) if tv_ratio else None,
                'etf_tv5_vs_prev5':round(tv5,3) if tv5 else None,
                'phase':phase,'data_kind':'ETF_PRICE_TURNOVER_PROXY_NOT_NET_BUY'}
    return out


def stock_turnover(b,signal_i):
    if signal_i<30:return (None,None)
    val=[x['close']*x['volume'] for x in b]
    recent=sum(val[signal_i-9:signal_i+1])/10
    past=sum(val[signal_i-29:signal_i-9])/20
    up=sum(val[k] for k in range(signal_i-9,signal_i+1) if b[k]['close']>b[k]['open'])
    return (round(recent/past,3) if past else None,
            round(up/(recent*10),3) if recent else None)


def period_month(d):return d[:7]
def period_half(d):return d[:4]+'H'+('1' if int(d[5:7])<=6 else '2')

def safe_mean(xs):return round(statistics.mean(xs),3) if xs else None

def write_csv(path,rows,fields):upstream.write(path,rows,fields)

def build(args):
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    manifest=upstream.rows_csv(args.manifest)
    sector_cfg=upstream.rows_csv(args.sectors)
    membership=upstream.rows_csv(args.membership)
    etfs={};benchmark=[];fail_etf={}
    etf_ids=sorted({r['etf_ticker'] for r in sector_cfg}|{BASELINE_ETF})
    for ticker in etf_ids:
        b,status=upstream.price_load(Path(args.etf_prices)/f'{ticker}.csv',args.asof)
        fail_etf[ticker]=status
        if status=='OK':etfs[ticker]=b
    benchmark=etfs.get(BASELINE_ETF,[])
    rolling={tk:rolling_sector_bars(b,benchmark) for tk,b in etfs.items() if tk!=BASELINE_ETF and benchmark}
    sector_daily=[]
    for sector in sector_cfg:
        tk=sector['etf_ticker']
        for d,vals in rolling.get(tk,{}).items():
            if d>args.asof or d<'2023-01-01':continue
            sector_daily.append({'sector_id':sector['sector_id'],'sector_etf':tk,**vals})
    # As-of ranks: use only same day known ETFs
    by_date=defaultdict(list)
    for r in sector_daily:by_date[r['date']].append(r)
    for day,records in by_date.items():
        for i,r in enumerate(sorted(records,key=lambda z:(z['rs5_pct']+z['rs20_pct']*.4,z['etf_tv10_vs_prev20'] or 0),reverse=True),1):r['asof_rank']=i
    sectorcols=['date','sector_id','sector_etf','asof_rank','phase','rs5_pct','rs10_pct','rs20_pct','rs60_pct','rs_accel_5_vs_20','etf_tv10_vs_prev20','etf_tv5_vs_prev5','data_kind']
    write_csv(out/'v14_daily_rolling_sectors.csv',sector_daily,sectorcols)

    all_signals=[];trades=[];data_quality=Counter();good=0
    signal_cols=['ticker','name','model','signal_date','entry_date','turn_date','impulse_date','pullback_start','entry_price','stop','risk_pct','risk_gate_10pct_2r','stock_tv10_ratio','stock_upday_tv_share10','sector_membership_pit','sector_id_pit','sector_phase','sector_rs5_pct','sector_rs20_pct','sector_rank_asof','sector_tv10_ratio','actual_investor_net_buy','excluded_handpicked','period_month','period_half']
    trade_cols=['ticker','model','period_month','period_half','signal_date','entry_date','entry_price','stop','risk_pct','risk_gate_10pct_2r','excluded_handpicked','stock_tv10_ratio','sector_phase','sector_rs5_pct','variant','status','exit_date','exit_reason','days_held','gross_return_pct','net_return_pct']
    sector_by_id={r['sector_id']:r for r in sector_cfg}
    for row in manifest:
        tk=row['ticker'];b,status=upstream.price_load(Path(args.prices)/f'{tk}.csv',args.asof)
        data_quality[status]+=1
        if status!='OK':continue
        # Reconstructed price histories must not have silent multi-month missing spans.
        if any((date.fromisoformat(b[j]['date'])-date.fromisoformat(b[j-1]['date'])).days>25 for j in range(1,len(b))):
            data_quality['GAP_GT25_DAYS']+=1
            good-=1
            continue
        good+=1
        model_entries=entry_models(b)
        for model,entries in model_entries.items():
            for e in entries:
                d=e['signal_date'];i=e['signal_idx']
                if not('2023-01-01'<=d<=args.asof):continue
                m=upstream.strict_membership(membership,tk,d)
                sid=sector_by_id.get(m,{}).get('etf_ticker') if m else None
                sector=rolling.get(sid,{}).get(d) if sid else None
                ratio,upshare=stock_turnover(b,i)
                sig={'ticker':tk,'name':row.get('name',''),'model':model,
                     'signal_date':d,'entry_date':e['entry_date'],'turn_date':e['turn_date'],
                     'impulse_date':e['impulse_date'],'pullback_start':e['pullback_start'],
                     'entry_price':e['entry_price'],'stop':e['stop'],'risk_pct':e['risk_pct'],
                     'risk_gate_10pct_2r':e['risk_gate_10pct_2r'],
                     'stock_tv10_ratio':ratio,'stock_upday_tv_share10':upshare,
                     'sector_membership_pit':'VERIFIED' if m else 'UNVERIFIED',
                     'sector_id_pit':m or '','sector_phase':sector['phase'] if sector else 'NOT_EVALUABLE',
                     'sector_rs5_pct':sector['rs5_pct'] if sector else None,
                     'sector_rs20_pct':sector['rs20_pct'] if sector else None,
                     'sector_rank_asof':next((r['asof_rank'] for r in by_date.get(d,[]) if r['sector_id']==m),None),
                     'sector_tv10_ratio':sector['etf_tv10_vs_prev20'] if sector else None,
                     'actual_investor_net_buy':'NOT_COLLECTED',
                     'excluded_handpicked':tk in HANDPICK,
                     'period_month':period_month(d),'period_half':period_half(d)}
                all_signals.append(sig)
                # Four named success examples should not be counted as independent performance.
                if tk in HANDPICK or not e['risk_gate_10pct_2r']:continue
                for mode in base.VARIANTS:
                    outcome=base.run_exit(b,e,mode,args.max_hold,args.cost_bps)
                    trades.append({k:sig.get(k) for k in ('ticker','model','period_month','period_half','signal_date','entry_date','entry_price','stop','risk_pct','risk_gate_10pct_2r','excluded_handpicked','stock_tv10_ratio','sector_phase','sector_rs5_pct')}
                                  |{'variant':mode}|outcome)
    write_csv(out/'v14_entries.csv',all_signals,signal_cols)
    write_csv(out/'v14_trades.csv',trades,trade_cols)
    # show each period, including periods with no trades; all models share same data and exits
    summ=[]
    periods=[f'{y}H{h}' for y in range(2023,2027) for h in (1,2)]
    for period in periods:
        for model in MODELS:
            for variant in base.VARIANTS:
                rr=[x for x in trades if x['period_half']==period and x['model']==model and x['variant']==variant]
                completed=[x for x in rr if x['status']=='COMPLETE']
                gains=[x['net_return_pct'] for x in completed]
                summ.append({'period_half':period,'model':model,'variant':variant,'entries':len(rr),
                             'completed':len(completed),'censored':len(rr)-len(completed),
                             'tp10':sum('TP10' in x.get('exit_reason','') for x in completed),
                             'stops':sum('STOP' in x.get('exit_reason','') for x in completed),
                             'mean_net_pct':safe_mean(gains),
                             'win_rate_pct':round(100*sum(v>0 for v in gains)/len(gains),2) if gains else None,
                             'research_only':True})
    write_csv(out/'v14_models_by_halfyear.csv',summ,['period_half','model','variant','entries','completed','censored','tp10','stops','mean_net_pct','win_rate_pct','research_only'])
    monthly=[]
    for month in sorted(set(x['period_month'] for x in trades)):
        for model in MODELS:
            rr=[x for x in trades if x['period_month']==month and x['model']==model and x['variant']=='A_10_ALL']
            completed=[x for x in rr if x['status']=='COMPLETE']
            gains=[x['net_return_pct'] for x in completed]
            monthly.append({'month':month,'model':model,'entries':len(rr),'completed':len(completed),
                            'mean_net_pct':safe_mean(gains), 'tp10':sum('TP10' in x.get('exit_reason','') for x in completed)})
    write_csv(out/'v14_models_by_month.csv',monthly,['month','model','entries','completed','mean_net_pct','tp10'])
    # raw model & money flow stratification on same timeframe; not optimized thresholds.
    strat=[]
    for model in MODELS:
        for flow in ('STRONGER_TURNOVER','WEAKER_TURNOVER','UNKNOWN'):
            co=[x for x in trades if x['model']==model and x['variant']=='A_10_ALL'
                and (('STRONGER_TURNOVER' if x['stock_tv10_ratio'] is not None and x['stock_tv10_ratio']>=1.5 else 'WEAKER_TURNOVER' if x['stock_tv10_ratio'] is not None else 'UNKNOWN')==flow)]
            cc=[x for x in co if x['status']=='COMPLETE'];rr=[x['net_return_pct'] for x in cc]
            strat.append({'model':model,'flow_cohort':flow,'entries':len(co),'completed':len(cc),
                          'mean_net_pct':safe_mean(rr),'tp10':sum('TP10' in x.get('exit_reason','') for x in cc)})
    write_csv(out/'v14_turnover_hypotheses.csv',strat,['model','flow_cohort','entries','completed','mean_net_pct','tp10'])
    # Sector effects may be evaluated ONLY for ex-ante dated/PIT stock membership.
    linked=[]
    sigidx={(z['ticker'],z['model'],z['signal_date']):z for z in all_signals}
    for model in MODELS:
        for phase in ('NEW_IGNITION','EXPANSION','LEADING','COOLING','WEAK','NEUTRAL'):
            cc=[t for t in trades if t['variant']=='A_10_ALL' and t['model']==model
                and (z:=sigidx.get((t['ticker'],t['model'],t['signal_date'])))
                and z['sector_membership_pit']=='VERIFIED' and z['sector_phase']==phase]
            done=[t for t in cc if t['status']=='COMPLETE']
            gains=[t['net_return_pct'] for t in done]
            linked.append({'model':model,'sector_phase':phase,'status':'EVALUABLE' if cc else 'NO_PIT_LINKED_TRADES',
                           'entries':len(cc),'completed':len(done),'mean_net_pct':safe_mean(gains),
                           'tp10':sum('TP10' in x.get('exit_reason','') for x in done)})
    write_csv(out/'v14_pit_sector_model_comparison.csv',linked,
              ['model','sector_phase','status','entries','completed','mean_net_pct','tp10'])
    audit={'asof':args.asof,'requested_tickers':len(manifest),'usable_tickers':good,'quality':dict(data_quality),
           'models':list(MODELS),'entries_by_model':dict(Counter(x['model'] for x in all_signals)),
           'independent_trade_entries_by_model':dict(Counter(x['model'] for x in trades if x['variant']=='A_10_ALL')),
           'sector_etfs_requested':len(sector_cfg),'sector_etfs_usable':len(rolling),
           'sector_daily_rows':len(sector_daily),
           'historic_membership_records':len(membership),
           'sector_linked_entries':sum(x['sector_membership_pit']=='VERIFIED' for x in all_signals),
           'investor_net_buy_observed':False,'universe_pit':False,'four_examples_ex_post_excluded_from_trade_cohort':sorted(HANDPICK),
           'cost_bps':args.cost_bps,'risk_gate':'Only entry stops <=5% of next-open modeled fill (10% gross target >=2R); raw candidates with 5-8% risk shown but not traded', 'hold_days':args.max_hold,'status':'EXPLORATORY' if good>=50 else 'DATA_PENDING',
           'warnings':['HMA40, EMA20 reclaim, Donchian20 are hypotheses; no proof any model outperforms HMA60.',
                       'Sector ETFs represent price strength and turnover, NOT sector net buying or underlying stock sector trading share.',
                       'PIT mapping is required before claiming trade-level money flow/sector alpha.',
                       'Historical cohort is based on 2026 snapshot: survivor and selection bias.',
                       'No real fills: next open market fill assumption, no order-book or corporate action ledger.',
                       'Four user-picked 2026 examples shown as signals but excluded from independent trade P&L.',
                       'No capital/portfolio overlap simulation. Unfinished positions excluded from completed outcomes.',
                       'No automatic adoption of the in-sample best model; requires out-of-sample validation.']}
    (out/'v14_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':audit['status'],'usable_tickers':good,'entries_by_model':audit['entries_by_model'],'sector_etfs_usable':len(rolling),'sector_linked_entries':audit['sector_linked_entries']},ensure_ascii=False))
    return audit


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--manifest',required=True)
    p.add_argument('--prices',required=True)
    p.add_argument('--etf-prices',required=True)
    p.add_argument('--sectors',required=True)
    p.add_argument('--membership',required=True)
    p.add_argument('--outdir',required=True)
    p.add_argument('--asof',default='2026-10-13')
    p.add_argument('--max-hold',type=int,default=60)
    p.add_argument('--cost-bps',type=float,default=35)
    build(p.parse_args())

if __name__=='__main__':main()
