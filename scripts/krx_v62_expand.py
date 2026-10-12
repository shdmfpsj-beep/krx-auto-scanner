#!/usr/bin/env python3
"""v6.2 research-only incremental history expansion. No orders or current-day signals.
Process watchlist in chunks, cache successful histories, skip already examined rows.
"""
import argparse,csv,json,math,time
from pathlib import Path
from datetime import date,timedelta

FIELDS=['ticker','name','market','snapshot_date','history_last_date','history_rows','close','ma20','ma60','ma120','ret20_pct','ret60_pct','rvol20','atr14','ideal_buy_low','ideal_buy_high','no_chase_above','structural_stop','target_1','target_2','rr1','setup','research_score','status','reason']
def n(x):
 try:
  v=float(x);return v if math.isfinite(v) else 0.
 except (ValueError,TypeError):return 0.
def readcsv(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def writecsv(p,rows):
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction='ignore');w.writeheader();w.writerows(rows)
def validate(df,asof,expected_close):
 import pandas as pd
 if df is None or df.empty:raise ValueError('EMPTY_HISTORY')
 df=df.copy();df.index=pd.to_datetime(df.index).normalize();df=df[~df.index.duplicated(keep='last')].sort_index()
 df=df[df.index.date<=asof].tail(121)
 if len(df)<121 or df.index[-1].date()!=asof:raise ValueError('STALE_OR_SHORT_HISTORY')
 for c in ['Open','High','Low','Close','Volume']:
  if c not in df:raise ValueError('MISSING_COLUMN_'+c)
  df[c]=pd.to_numeric(df[c],errors='coerce')
 if df[['Open','High','Low','Close','Volume']].isna().any().any() or (df[['Open','High','Low','Close','Volume']]<=0).any().any():raise ValueError('INVALID_OHLCV')
 if ((df.High<df[['Open','Close','Low']].max(axis=1))|(df.Low>df[['Open','Close','High']].min(axis=1))).any():raise ValueError('INVALID_CANDLE')
 if expected_close<=0 or abs(float(df.Close.iloc[-1])/expected_close-1)>0.03:raise ValueError('SNAPSHOT_CLOSE_MISMATCH')
 return df

def evaluate(df):
 c=df.Close;h=df.High;l=df.Low;v=df.Volume
 close=float(c.iloc[-1]);m20=float(c.tail(20).mean());m60=float(c.tail(60).mean());m120=float(c.tail(120).mean())
 r20=100*(close/float(c.iloc[-21])-1);r60=100*(close/float(c.iloc[-61])-1)
 avgv=float(v.iloc[-21:-1].mean());rv=float(v.iloc[-1])/avgv if avgv>0 else 0
 tr=(h-l).combine((h-c.shift(1)).abs(),max).combine((l-c.shift(1)).abs(),max)
 atr=float(tr.tail(14).mean());lo=float(l.tail(10).min());hi=float(h.tail(20).max())
 result=dict(close=round(close,2),ma20=round(m20,2),ma60=round(m60,2),ma120=round(m120,2),ret20_pct=round(r20,2),ret60_pct=round(r60,2),rvol20=round(rv,2),atr14=round(atr,2))
 if not(close>m20>m60>m120 and r20>0 and r60>0 and atr>0 and rv>=0.6):return dict(**result,status='REJECT_TREND',setup='NONE',reason='TREND_OR_MOMENTUM_FAIL')
 lower=m20-0.55*atr;upper=min(close,m20+0.45*atr);stop=min(lo-0.3*atr,lower-atr)
 if not(0<stop<lower<=upper):return dict(**result,status='REJECT_GEOMETRY',setup='NONE',reason='INVALID_LEVELS')
 risk=upper-stop;riskpct=100*risk/upper
 if not(1<=riskpct<=12) or close>upper+1.25*atr:return dict(**result,status='REJECT_CHASE',setup='NONE',reason='OVEREXTENDED_OR_RISK')
 target1=max(hi,upper+1.8*risk);target2=upper+2.8*risk
 score=round(25+min(20,max(0,r20))*0.8+min(15,max(0,r60))*0.6+(15 if .8<=rv<=3 else 5)+(20 if riskpct<=6 else 10)+(15 if (target1-upper)/risk>=2 else 8),2)
 return dict(**result,ideal_buy_low=round(lower),ideal_buy_high=round(upper),no_chase_above=round(upper),structural_stop=round(stop),target_1=round(target1),target_2=round(target2),rr1=round((target1-upper)/risk,2),setup='TREND_PULLBACK_LIMIT',research_score=score,status='CONDITIONAL_RESEARCH',reason='NO_VERIFIED_FLOW_FUNDAMENTALS_INSTRUMENT_TYPE')

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--input',default='reports/v59_preliminary_watchlist.csv');ap.add_argument('--outdir',default='reports');ap.add_argument('--batch-size',type=int,default=40);ap.add_argument('--pause',type=float,default=.15);args=ap.parse_args()
 if not 1<=args.batch_size<=80:ap.error('batch-size must be 1..80')
 import FinanceDataReader as fdr
 src=Path(args.input);dest=Path(args.outdir);dest.mkdir(parents=True,exist_ok=True)
 if not src.exists():raise SystemExit('Missing watchlist: '+str(src))
 items=readcsv(src);dates={r.get('snapshot_date','') for r in items}
 if not items or len(dates)!=1:raise SystemExit('Empty or mixed-date watchlist')
 asof=date.fromisoformat(dates.pop())
 if asof>date.today():raise SystemExit('Future snapshot')
 cache=dest/'v62_history_expanded.csv';prior=readcsv(cache) if cache.exists() else []
 if prior and {r['snapshot_date'] for r in prior}!={asof.isoformat()}:raise SystemExit('Cache batch mismatch; do not mix dates')
 known={r['ticker']:r for r in prior};todo=[r for r in items if r.get('ticker','').zfill(6) not in known][:args.batch_size]
 start=(asof-timedelta(days=320)).isoformat();end=(asof+timedelta(days=1)).isoformat()
 for r in todo:
  ticker=r.get('ticker','').zfill(6);record={k:'' for k in FIELDS};record.update(ticker=ticker,name=r.get('name',''),market=r.get('market',''),snapshot_date=asof.isoformat(),status='HISTORY_FAILED')
  try:
   if len(ticker)!=6 or not ticker.isdigit():raise ValueError('INVALID_TICKER')
   df=validate(fdr.DataReader(ticker,start,end),asof,n(r.get('close')))
   record.update(history_last_date=asof.isoformat(),history_rows=len(df));record.update(evaluate(df))
  except Exception as e:record['reason']=str(e)[:140]
  known[ticker]=record
  if args.pause>0:time.sleep(min(args.pause,2))
 ordered=[known[r['ticker'].zfill(6)] for r in items if r.get('ticker','').zfill(6) in known]
 writecsv(cache,ordered)
 candidates=sorted((r for r in ordered if r['status']=='CONDITIONAL_RESEARCH'),key=lambda r:(-n(r['research_score']),-n(r['rr1']),r['ticker']))
 writecsv(dest/'v62_conditional_research.csv',candidates)
 audit={'version':'6.2','asof':asof.isoformat(),'universe_scope':'ONLY_157_PRELIMINARY_WATCHLIST_NOT_FULL_KRX','watchlist_count':len(items),'processed_total':len(ordered),'processed_this_run':len(todo),'remaining':len(items)-len(ordered),'historical_valid':sum(r['history_rows']!='' for r in ordered),'conditional_candidates':len(candidates),'top3_provisional':[{'ticker':r['ticker'],'name':r['name'],'score':r['research_score']} for r in candidates[:3]],'research_only':True,'current_trading_signal':False,'performance_backtest_completed':False,'note':'Cached historical snapshot; no independent turnover, flow, earnings, catalysts or execution verification.'}
 (dest/'v62_expansion_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(audit,ensure_ascii=False))
if __name__=='__main__':main()
