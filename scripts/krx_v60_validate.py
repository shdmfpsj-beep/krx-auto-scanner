#!/usr/bin/env python3
"""v6.0 research-only, bounded historical verification of v5.9 watchlist.
No orders, no live BUY. Fail closed on missing or stale histories.
"""
import argparse
import csv
import json
import math
import time
from datetime import date, timedelta
from pathlib import Path

FIELDS = ['ticker','name','market','snapshot_date','history_last_date','history_rows','close','ma20','ma60','ma120','ret20_pct','ret60_pct','rvol20','range20_high','range20_low','c3_research_score','k100_tactical_score','k100_core_price_score','c3_setup','status','warnings']

def num(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError):
        return 0.0

def classify(closes, volumes):
    c=closes[-1]; ma20=sum(closes[-20:])/20; ma60=sum(closes[-60:])/60; ma120=sum(closes[-120:])/120
    r20=100*(c/closes[-21]-1); r60=100*(c/closes[-61]-1)
    avgvol=sum(volumes[-21:-1])/20
    rvol=volumes[-1]/avgvol if avgvol>0 else 0
    high20=max(closes[-20:]); low20=min(closes[-20:]);
    trend=c>ma20>ma60>ma120
    extension=100*(c/ma20-1)
    c3=round((30 if trend else 0)+(20 if r20>0 else 0)+(15 if r60>0 else 0)+(15 if 1.2<=rvol<=4 else 0)+(20 if 0<=extension<=8 else 0),1)
    tactical=round((30 if c>ma20>ma60 else 0)+(20 if r20>0 else 0)+(20 if rvol>=1.3 else 0)+(30 if 0<=extension<=7 else 0),1)
    core=round((40 if c>ma60>ma120 else 0)+(30 if r60>0 else 0)+(30 if 0<=extension<=12 else 0),1)
    setup='TREND_PULLBACK_CANDIDATE' if trend and 0<=extension<=5 else ('EXTENDED_NO_CHASE' if extension>8 else 'UNCONFIRMED')
    return dict(close=round(c,2),ma20=round(ma20,2),ma60=round(ma60,2),ma120=round(ma120,2),ret20_pct=round(r20,2),ret60_pct=round(r60,2),rvol20=round(rvol,2),range20_high=round(high20,2),range20_low=round(low20,2),c3_research_score=c3,k100_tactical_score=tactical,k100_core_price_score=core,c3_setup=setup)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',default='reports/v59_preliminary_watchlist.csv')
    p.add_argument('--outdir',default='reports')
    p.add_argument('--limit',type=int,default=30)
    p.add_argument('--pause',type=float,default=0.2)
    args=p.parse_args()
    if not 1<=args.limit<=60: p.error('--limit must be 1..60 (bounded verification)')
    import FinanceDataReader as fdr
    import pandas as pd
    path=Path(args.input)
    if not path.is_file(): raise SystemExit('Missing v5.9 watchlist: '+str(path))
    with path.open(encoding='utf-8-sig',newline='') as f: items=list(csv.DictReader(f))
    if not items: raise SystemExit('Empty v5.9 watchlist')
    batch_dates={r.get('snapshot_date','') for r in items}
    if len(batch_dates)!=1: raise SystemExit('Mixed snapshot dates: stop')
    asof=date.fromisoformat(next(iter(batch_dates)))
    if asof>date.today(): raise SystemExit('Future snapshot date: stop')
    start=(asof-timedelta(days=320)).isoformat(); end=(asof+timedelta(days=1)).isoformat()
    out=[]; errors=[]
    for item in items[:args.limit]:
        ticker=item.get('ticker','').strip().zfill(6)
        record={k:'' for k in FIELDS}
        record.update(ticker=ticker,name=item.get('name',''),market=item.get('market',''),snapshot_date=asof.isoformat(),status='WATCH_ONLY_NOT_BUY')
        warns=['NO_FLOW','NO_FUNDAMENTALS','NO_CATALYST','NO_VERIFIED_TURNOVER','NO_LIVE_PRICE','NO_CAPITAL_GATE','NO_INSTRUMENT_TYPE_VERIFICATION']
        try:
            if len(ticker)!=6 or not ticker.isdigit(): raise ValueError('invalid ticker')
            df=fdr.DataReader(ticker,start,end)
            if df is None or df.empty: raise ValueError('empty history')
            df=df.copy(); df.index=pd.to_datetime(df.index).normalize(); df=df[~df.index.duplicated(keep='last')].sort_index()
            df=df[df.index.date<=asof]
            if len(df)<121: raise ValueError('insufficient historical sessions')
            for col in ('Open','High','Low','Close','Volume'):
                if col not in df: raise ValueError('missing '+col)
                df[col]=pd.to_numeric(df[col],errors='coerce')
            df=df.tail(121)
            if df[['Open','High','Low','Close','Volume']].isna().any().any(): raise ValueError('null OHLCV')
            if ((df[['Open','High','Low','Close']]<=0).any().any() or (df['Volume']<=0).any()): raise ValueError('nonpositive OHLCV')
            if ((df['High']<df[['Open','Close','Low']].max(axis=1)) | (df['Low']>df[['Open','Close','High']].min(axis=1))).any(): raise ValueError('invalid OHLC geometry')
            last=df.index[-1].date(); record['history_last_date']=last.isoformat(); record['history_rows']=len(df)
            if last!=asof: raise ValueError('historical last date differs from snapshot')
            # Adjusted prices may differ from snapshot due to subsequent corporate actions.
            if abs(float(df['Close'].iloc[-1])/num(item.get('close'))-1)>0.03: raise ValueError('history/snapshot close differs >3%')
            record.update(classify(df['Close'].tolist(),df['Volume'].tolist()))
            record['status']='HISTORY_VALIDATED_RESEARCH_ONLY'
        except Exception as exc:
            warns.append('HISTORY_FAILED:'+str(exc)[:100].replace(',',';'))
            errors.append({'ticker':ticker,'error':str(exc)[:150]})
        record['warnings']='|'.join(warns)
        out.append(record)
        if args.pause>0: time.sleep(min(args.pause,2))
    dest=Path(args.outdir); dest.mkdir(parents=True,exist_ok=True)
    for group,filename,key in [('all','v60_history_validation.csv',None),('c3','v60_c3_research.csv','c3_research_score'),('tactical','v60_k100_tactical_research.csv','k100_tactical_score'),('core','v60_k100_core_price_research.csv','k100_core_price_score')]:
        rows=out if key is None else sorted([r for r in out if r['status']=='HISTORY_VALIDATED_RESEARCH_ONLY'],key=lambda r:float(r[key]),reverse=True)
        with (dest/filename).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    audit={'version':'6.0','research_only':True,'asof':asof.isoformat(),'input_rows':len(items),'selected_for_history':len(out),'validated':sum(r['status']=='HISTORY_VALIDATED_RESEARCH_ONLY' for r in out),'failed':len(errors),'coverage_note':'Only top N from v5.9; NOT full-market historical verification','no_buy':True,'errors':errors}
    (dest/'v60_history_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in audit.items() if k!='errors'},ensure_ascii=False))

if __name__=='__main__': main()
