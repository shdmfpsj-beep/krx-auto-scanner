#!/usr/bin/env python3
"""v6.1: research-only entry geometry for already history-validated v6.0 candidates.
Not a full-market TOP3; no orders or actionable current-day recommendations.
"""
import argparse, csv, json, math
from datetime import date, timedelta
from pathlib import Path

COLS=['rank','ticker','name','market','asof','strategy','setup','score','reference_close','ideal_buy_low','ideal_buy_high','max_buy_no_chase','structural_stop','target_1','target_2','reward_risk_1','atr14','risk_pct','status','limitations']

def val(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else 0
    except (TypeError, ValueError): return 0

def make_levels(df, r):
    h=df['High']; l=df['Low']; c=df['Close']; p=c.shift(1)
    tr=(h-l).combine((h-p).abs(),max).combine((l-p).abs(),max)
    atr=float(tr.tail(14).mean()); close=float(c.iloc[-1]); ma20=float(c.tail(20).mean())
    low10=float(l.tail(10).min()); high20=float(h.tail(20).max())
    # Research plan: conditional limit-buy zone near MA20, never market chase.
    upper=min(close,ma20+0.45*atr)
    lower=max(0,ma20-0.55*atr)
    stop=min(low10-0.3*atr,lower-1.0*atr)
    if not (atr>0 and lower>stop>0 and upper>=lower): return None
    risk=upper-stop
    risk_pct=100*risk/upper
    if risk_pct>12 or risk_pct<1.0: return None
    # Reject if reference close already far above planned entry.
    if close>upper+1.25*atr: return None
    # Breakout resistance is a context input, not a claimed target guarantee.
    target1=max(high20,upper+1.8*risk)
    target2=upper+2.8*risk
    return dict(reference_close=round(close),ideal_buy_low=round(lower),ideal_buy_high=round(upper),max_buy_no_chase=round(upper),structural_stop=round(stop),target_1=round(target1),target_2=round(target2),reward_risk_1=round((target1-upper)/risk,2),atr14=round(atr,1),risk_pct=round(risk_pct,2))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',default='reports/v60_history_validation.csv')
    ap.add_argument('--outdir',default='reports')
    ap.add_argument('--limit',type=int,default=30)
    args=ap.parse_args()
    if not 1<=args.limit<=60: ap.error('limit 1..60')
    import FinanceDataReader as fdr
    import pandas as pd
    with open(args.input,encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    rows=[r for r in rows if r.get('status')=='HISTORY_VALIDATED_RESEARCH_ONLY'][:args.limit]
    if not rows: raise SystemExit('No validated v6.0 rows; do not backfill automatically')
    dates={r['snapshot_date'] for r in rows}
    if len(dates)!=1: raise SystemExit('Mixed snapshot dates')
    asof=date.fromisoformat(dates.pop())
    if asof>date.today(): raise SystemExit('Future snapshot date')
    results=[]; failures=[]
    for r in rows:
        ticker=r['ticker'].zfill(6)
        try:
            df=fdr.DataReader(ticker,(asof-timedelta(days=300)).isoformat(),(asof+timedelta(days=1)).isoformat())
            if df is None or df.empty: raise ValueError('empty history')
            df=df.copy();df.index=pd.to_datetime(df.index).normalize();df=df[~df.index.duplicated(keep='last')].sort_index();df=df[df.index.date<=asof].tail(121)
            if len(df)<121 or df.index[-1].date()!=asof: raise ValueError('insufficient/stale history')
            for k in ('Open','High','Low','Close','Volume'): df[k]=pd.to_numeric(df[k],errors='coerce')
            if df[['Open','High','Low','Close','Volume']].isna().any().any(): raise ValueError('null OHLCV')
            if (df[['Open','High','Low','Close','Volume']]<=0).any().any(): raise ValueError('nonpositive OHLCV')
            if ((df['High']<df[['Open','Close','Low']].max(axis=1)) | (df['Low']>df[['Open','Close','High']].min(axis=1))).any(): raise ValueError('invalid geometry')
            if abs(float(df['Close'].iloc[-1])/val(r['close'])-1)>0.03: raise ValueError('close mismatch')
            levels=make_levels(df,r)
            if not levels: continue
            close=levels['reference_close']; ma20=val(r['ma20']);ma60=val(r['ma60']);ma120=val(r['ma120']);ret20=val(r['ret20_pct']);rvol=val(r['rvol20'])
            # Trend + no chase + bounded risk are mandatory for both research tracks.
            if not (close>ma20>ma60 and ret20>0 and rvol>=0.6): continue
            for strategy in ('C3','K100_NEW_TOP3'):
                if strategy=='C3' and not close>ma120: continue
                if strategy=='K100_NEW_TOP3' and not (ma60>ma120 and val(r['ret60_pct'])>0): continue
                score=(25 if close>ma20>ma60>ma120 else 15)+(20 if 0<ret20<25 else 10)+(15 if 0.8<=rvol<=3 else 5)+(20 if levels['risk_pct']<=6 else 10)+(20 if levels['reward_risk_1']>=2 else 10)
                results.append(dict(rank='',ticker=ticker,name=r['name'],market=r['market'],asof=asof.isoformat(),strategy=strategy,setup='PULLBACK_LIMIT_PLAN',score=score,**levels,status='HISTORICAL_CONDITIONAL_WATCH_ONLY',limitations='30_OF_157|NOT_FULL_MARKET|NO_CURRENT_PRICE|NO_FLOW|NO_FUNDAMENTALS|NO_EXECUTION'))
        except Exception as e: failures.append({'ticker':ticker,'error':str(e)[:120]})
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    for strategy,file in [('C3','v61_c3_conditional_top3.csv'),('K100_NEW_TOP3','v61_new_top3_conditional.csv')]:
        items=sorted((x for x in results if x['strategy']==strategy),key=lambda x:(-x['score'],-x['reward_risk_1'],x['risk_pct']))[:3]
        for i,x in enumerate(items,1): x['rank']=i
        with (out/file).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=COLS);w.writeheader();w.writerows(items)
    audit={'version':'6.1','asof':asof.isoformat(),'input_validated_rows':len(rows),'scope':'ONLY_PREVIOUSLY_VALIDATED_TOP_30_NOT_FULL_MARKET','historical_conditional_only':True,'not_current_trade_levels':True,'failures':failures,'plans_by_strategy':{s:sum(x['strategy']==s for x in results) for s in ('C3','K100_NEW_TOP3')},'next_required':'expand historical coverage to full universe and time-split backtest before claiming daily market TOP3 precision'}
    (out/'v61_entry_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in audit.items() if k!='failures'},ensure_ascii=False))
if __name__=='__main__': main()
