#!/usr/bin/env python3
"""v8.8 research-only, as-of evidence audit for v8.7 pre-ignition signals.

No live recommendations. Requires the preserved v8.7 reports and underlying
v36 daily OHLCV cache. Does NOT refit, revise, or overwrite v8.7 outcomes.
Only uses bars on or before each signal date to compute audit features.
"""
from __future__ import annotations
import argparse, csv, io, json, math, zipfile
from pathlib import Path
from collections import Counter, defaultdict

VERSION='V8.8_PREIGNITION_CAUSAL_QUALITY_AUDIT_NOT_LIVE'
FEATURE_COLUMNS=['ticker','signal_date','subtype','score','resistance','recent4_max_high','purity_class','prebreakout_clean','prior3_breached','signal_day_probed','updown_turnover_20','cmf_20','flow_ratio_ge_1p2','cmf_ge_0p10','data_status']
SUMMARY_COLUMNS=['mode','cohort','split','signal_count','closed_trades','win_rate_pct','avg_net_pct','avg_net_R','profit_factor','unique_signal_dates','note']
COHORTS=('ALL','CLEAN_PREBREAKOUT','PRIOR_BREACH','SIGNAL_DAY_PROBE','UPDOWN_GE_1P2','CMF_GE_0P10','CLEAN_AND_CMF_GE_0P10')
MODES=('E1_LIMIT_2D','E2_NEXT_OPEN','E3_NEXT_CLOSE_AUCTION_PROXY')

def parse_csv(b):
    return list(csv.DictReader(io.StringIO(b.decode('utf-8-sig'))))

def f(v):
    try:
        v=float(v)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError):return None

def avg(a):return sum(a)/len(a) if a else 0

def features(b,i,res):
    """Call with signal bar index i; all windows end at or before i."""
    if i<20:return None
    recent=b[i-3:i+1]
    prev=b[i-3:i]
    prior=any(q['h']>=res for q in prev)
    probe=b[i]['h']>=res
    kind='PRIOR_BREACH' if prior else ('SIGNAL_DAY_PROBE' if probe else 'CLEAN_PREBREAKOUT')
    hist=b[i-19:i+1]
    priorhist=b[i-20:i]
    up=down=totalvol=mfmvol=0.0
    for cur,last in zip(hist,priorhist):
        turn=cur['v']*cur['c']
        if cur['c']>last['c']:up+=turn
        elif cur['c']<last['c']:down+=turn
        rng=cur['h']-cur['l']
        mult=(2*cur['c']-cur['h']-cur['l'])/rng if rng>0 else 0.0
        mfmvol+=mult*cur['v']
        totalvol+=cur['v']
    ratio=up/down if down>0 else None
    cmf=mfmvol/totalvol if totalvol>0 else None
    return {'recent4_max_high':round(max(q['h'] for q in recent),6),
            'purity_class':kind,'prebreakout_clean':int(kind=='CLEAN_PREBREAKOUT'),
            'prior3_breached':int(prior),'signal_day_probed':int(probe),
            'updown_turnover_20':round(ratio,6) if ratio is not None else '',
            'cmf_20':round(cmf,6) if cmf is not None else '',
            'flow_ratio_ge_1p2':int(ratio is not None and ratio>=1.2),
            'cmf_ge_0p10':int(cmf is not None and cmf>=.10)}

def belongs(feature, cohort):
    if cohort=='ALL':return True
    if cohort=='CLEAN_PREBREAKOUT':return feature['prebreakout_clean']==1
    if cohort=='PRIOR_BREACH':return feature['purity_class']=='PRIOR_BREACH'
    if cohort=='SIGNAL_DAY_PROBE':return feature['purity_class']=='SIGNAL_DAY_PROBE'
    if cohort=='UPDOWN_GE_1P2':return feature['flow_ratio_ge_1p2']==1
    if cohort=='CMF_GE_0P10':return feature['cmf_ge_0p10']==1
    if cohort=='CLEAN_AND_CMF_GE_0P10':return feature['prebreakout_clean']==1 and feature['cmf_ge_0p10']==1
    raise ValueError('unknown cohort')

def clean_rows(raw,ticker):
    bars=[]
    for x in parse_csv(raw):
        try:
            o,h,l,c,v=(f(x.get(col)) for col in ('Open','High','Low','Close','Volume'))
            d=x['Date'][:10]
            if any(n is None for n in (o,h,l,c,v)) or min(o,h,l,c)<=0 or v<0 or h<max(o,c,l) or l>min(o,c,h):return None
        except (TypeError,ValueError,KeyError):return None
        bars.append({'date':d,'o':o,'h':h,'l':l,'c':c,'v':v})
    if any(bars[j]['date']<=bars[j-1]['date'] for j in range(1,len(bars))):return None
    return bars

def make_audit(signals,trades,bars_lookup):
    by_ticker=defaultdict(list)
    for s in signals:by_ticker[s['ticker'].zfill(6)].append(s)
    details=[];features_map={};errors=[]
    for ticker,rows in by_ticker.items():
        raw=bars_lookup(ticker)
        if raw is None:
            errors.append(f'MISSING_CACHE:{ticker}');continue
        b=clean_rows(raw,ticker)
        if b is None:
            errors.append(f'INVALID_CACHE:{ticker}');continue
        ix={x['date']:i for i,x in enumerate(b)}
        for s in rows:
            d=s['signal_date'];key=(ticker,d)
            i=ix.get(d)
            if i is None or i<20:
                errors.append(f'MISSING_SIGNAL_DATE:{ticker}:{d}');continue
            resistance=f(s['resistance'])
            if resistance is None or resistance<=0:
                errors.append(f'INVALID_RESISTANCE:{ticker}:{d}');continue
            obj=features(b,i,resistance)
            if obj is None:errors.append(f'NO_FEATURE:{ticker}:{d}');continue
            rec={'ticker':ticker,'signal_date':d,'subtype':s['subtype'],'score':s['score'],'resistance':s['resistance'],**obj,'data_status':'ASOF_ONLY'}
            if key in features_map:errors.append(f'DUPLICATE_SIGNAL:{ticker}:{d}');continue
            details.append(rec);features_map[key]=rec
    if errors:raise ValueError('audit invalid: '+str(errors[:10]))
    end_dates=sorted({s['signal_date'] for s in signals});boundary=end_dates[int(len(end_dates)*.7)] if end_dates else '9999-12-31'
    matched=[];missing_trade=[]
    for t in trades:
        key=(t['ticker'].zfill(6),t['signal_date'])
        feature=features_map.get(key)
        if feature is None:missing_trade.append(key);continue
        if t['mode'] not in MODES:continue
        matched.append((t,feature))
    if missing_trade:raise ValueError('trade missing signal: '+str(missing_trade[:10]))
    scores=[]
    for mode in MODES:
        for cohort in COHORTS:
            signals_here=[s for s in details if belongs(s,cohort)]
            for phase in ('EARLY','LATE','ALL'):
                sg=[s for s in signals_here if phase=='ALL' or ('EARLY' if s['signal_date']<boundary else 'LATE')==phase]
                tt=[t for t,v in matched if t['mode']==mode and belongs(v,cohort) and (phase=='ALL' or ('EARLY' if t['signal_date']<boundary else 'LATE')==phase)]
                vals=[f(t['net_pct']) for t in tt]
                netR=[f(t.get('net_R')) for t in tt]
                if any(v is None for v in vals) or any(v is None for v in netR):raise ValueError('invalid outcomes')
                pos=sum(max(0,n) for n in vals); neg=-sum(min(0,n) for n in vals)
                scores.append({'mode':mode,'cohort':cohort,'split':phase,'signal_count':len(sg),'closed_trades':len(tt),
                               'win_rate_pct':round(sum(v>0 for v in vals)*100/len(vals),2) if vals else '',
                               'avg_net_pct':round(avg(vals),4) if vals else '',
                               'avg_net_R':round(avg(netR),4) if netR else '',
                               'profit_factor':round(pos/neg,4) if neg else ('INF' if pos else ''),
                               'unique_signal_dates':len({t['signal_date'] for t in tt}),
                               'note':'NO_TRADES' if not tt else ('SMALL_N_NOT_ACTIONABLE' if len(tt)<30 else 'EXPLORATORY_ONLY')})
    counts=Counter(d['purity_class'] for d in details)
    status={'version':VERSION,'signals_input':len(signals),'signals_audited':len(details),'trades_input':len(trades),'trades_matched':len(matched),
            'purity_classes':dict(counts),'time_split_boundary':boundary,'historical_winner_selection_possible':True,
            'BUY_APPROVED':False,'method':'As-of last-4-bar resistance-breach classification plus 20d turnover direction and CMF. No past rows edited.',
            'caveats':['Purity excludes prior breaches but does not claim a predictive filter; recent breach may be valid retest.',
                       'CMF and up/down turnover are unverified proxies, not broker order-flow or institutional net purchases.',
                       'Same stock and signal date are repeated across three modes and are NOT independent observations.',
                       'No historical sector RS, catalysts, revised fundamentals, or intraday quote data.',
                       'Reports are selected-ticker research and not point-in-time broad-market results.',
                       'Next-close entry proxy cannot validate actual closing auction execution; final closing price is not knowable pre-order.',
                       'Results are in-sample diagnostics; do not choose a winner from this test alone.']}
    return details,scores,status

def save_csv(p,rows,columns):
    with open(p,'w',newline='',encoding='utf-8-sig') as f0:
        w=csv.DictWriter(f0,columns,extrasaction='ignore');w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sources=ap.add_mutually_exclusive_group(required=True)
    sources.add_argument('--report-dir');sources.add_argument('--report-zip')
    ap.add_argument('--outdir',default='reports')
    args=ap.parse_args()
    if args.report_zip:
        with zipfile.ZipFile(args.report_zip) as z:
            names=set(z.namelist())
            signals=parse_csv(z.read('v87_preignition_signals.csv'))
            trades=parse_csv(z.read('v87_entry_trades.csv'))
            def look(t):
                n='v36_ohlcv_cache/'+t+'.csv'
                return z.read(n) if n in names else None
            details,scores,status=make_audit(signals,trades,look)
    else:
        p=Path(args.report_dir)
        signals=parse_csv((p/'v87_preignition_signals.csv').read_bytes())
        trades=parse_csv((p/'v87_entry_trades.csv').read_bytes())
        def look(t):
            n=p/'v36_ohlcv_cache'/(t+'.csv')
            return n.read_bytes() if n.exists() else None
        details,scores,status=make_audit(signals,trades,look)
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    save_csv(out/'v88_preignition_purity.csv',details,FEATURE_COLUMNS)
    save_csv(out/'v88_purity_scorecard.csv',scores,SUMMARY_COLUMNS)
    (out/'v88_quality_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(status,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
