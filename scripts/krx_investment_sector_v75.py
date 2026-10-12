#!/usr/bin/env python3
"""v7.5: compare validated independent histories with sector watchlist; historical research only."""
import argparse,csv,json,math,statistics
from pathlib import Path

def load(p):
 with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def save(p,rows,cols):
 with open(p,'w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)
def num(v):
 try:
  x=float(v);return x if math.isfinite(x) else None
 except (ValueError,TypeError):return None

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--queue',default='reports/v73_independent_research_queue.csv')
 p.add_argument('--validation',default='reports/v74_independent_history_validation.csv')
 p.add_argument('--sector-watch',default='reports/v72_historical_watchlist.csv')
 p.add_argument('--market',default='reports/market_data_v56_merged.csv')
 p.add_argument('--cache',default='reports/v36_ohlcv_cache')
 p.add_argument('--outdir',default='reports')
 a=p.parse_args();out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
 queue=load(a.queue);valid=load(a.validation);sector=load(a.sector_watch);market=load(a.market)
 dates={x['snapshot_date'] for x in queue}|{x['snapshot_date'] for x in market}|{x['asof'] for x in sector}
 if len(dates)!=1:raise SystemExit('Historical snapshot dates do not match')
 asof=dates.pop();marketby={x['ticker'].zfill(6):x for x in market};validation={x['ticker'].zfill(6):x for x in valid}
 if len(queue)!=30 or len(validation)!=30:raise SystemExit('Expected 30 independent research names and validation records')
 fields=['ticker','name','candidate_class','asof','status','setup','close','stock_5d_pct','stock_20d_pct','rvol20','ideal_buy_low','ideal_buy_high','max_buy','no_chase_above','structural_stop','target_1','target_2','technical_score','sector_research_score','trade_authorized','reason']
 rows=[]
 for r in queue:
  t=r['ticker'].zfill(6);v=validation.get(t,{});base=dict(ticker=t,name=r['name'],candidate_class='INDEPENDENT_30_ONLY',asof=asof,status='NO_VALID_HISTORY',setup='NONE',trade_authorized='NO',reason='',sector_research_score='')
  if v.get('status') not in ('COLLECTED_VALID','CACHE_VALID'):
   base['reason']='v7.4 validation failed: '+v.get('reason','missing');rows.append(base);continue
  f=Path(a.cache)/f'{t}.csv'
  try:
   bars=[]
   for d in load(f):
    dt=d.get('Date',d.get('date',''))
    if dt>asof:continue
    values=[num(d.get(k,d.get(k.lower()))) for k in ('Open','High','Low','Close','Volume')]
    if any(x is None for x in values):raise ValueError('Missing numeric OHLCV')
    o,h,l,c,vol=values
    if not (min(o,h,l,c)>0 and vol>=0 and l<=min(o,c)<=max(o,c)<=h):raise ValueError('Invalid OHLCV')
    bars.append((dt,o,h,l,c,vol))
   bars.sort()
   if len(bars)<31 or len({x[0] for x in bars})!=len(bars) or bars[-1][0]!=asof:raise ValueError('Insufficient, duplicate or stale bars')
   o,h,l,c,vol=([x[i] for x in bars] for i in range(1,6))
   snap=num(marketby[t]['close'])
   if snap is None or abs(c[-1]/snap-1)>0.03:raise ValueError('Snapshot close mismatch')
   r5=100*(c[-1]/c[-6]-1);r20=100*(c[-1]/c[-21]-1)
   ma20=statistics.mean(c[-20:]);ma10=statistics.mean(c[-10:]);high20=max(h[-21:-1]);low10=min(l[-10:]);avgvol=statistics.mean(vol[-21:-1]);rvol=vol[-1]/avgvol if avgvol>0 else 0
   uptrend=c[-1]>ma20 and ma10>=ma20 and r20>0
   breakout=c[-1]>high20 and rvol>=1.2
   pullback=uptrend and low10<=ma10*1.025 and ma10*0.98<=c[-1]<=ma10*1.06
   setup='BREAKOUT' if uptrend and breakout else 'FIRST_PULLBACK' if pullback else 'NONE'
   ideal_low=max(low10,ma20*0.98);ideal_high=min(c[-1],ma10*1.02);stop=min(low10,ma20*0.97);maxbuy=min(high20*1.015,c[-1]*1.02)
   if setup=='BREAKOUT':ideal_low=high20;ideal_high=min(c[-1],high20*1.015)
   if not (ideal_low>stop>0 and ideal_high>=ideal_low and maxbuy>=ideal_high):setup='NONE'
   # Independent ranking uses only stock-derived features, never missing sector strength as zero.
   score=0.65*r20+0.35*r5
   base.update(close=c[-1],stock_5d_pct=round(r5,3),stock_20d_pct=round(r20,3),rvol20=round(rvol,3),technical_score=round(score,3),setup=setup)
   if setup=='NONE':base.update(status='NO_SETUP',reason='Common historical technical entry gate not met')
   else:
    risk=ideal_high-stop
    base.update(status='HISTORICAL_WATCH_ONLY',ideal_buy_low=round(ideal_low,2),ideal_buy_high=round(ideal_high,2),max_buy=round(maxbuy,2),no_chase_above=round(maxbuy,2),structural_stop=round(stop,2),target_1=round(ideal_high+1.5*risk,2),target_2=round(ideal_high+2.5*risk,2),reason='Historical technical research; no verified sector mapping, tick size, liquidity or live gate')
  except (ValueError,KeyError,IndexError,ZeroDivisionError,FileNotFoundError) as e:base.update(status='INVALID_HISTORY',reason=str(e)[:160])
  rows.append(base)
 save(out/'v75_independent_entry_geometry.csv',rows,fields)
 # Only stock-return components are directly comparable; sector v7.2 score includes thematic factors.
 combined=[]
 for r in rows:
  if r['status']=='HISTORICAL_WATCH_ONLY':combined.append(dict(r))
 for r in sector:
  if r.get('status')!='HISTORICAL_WATCH_ONLY':continue
  r5=num(r.get('stock_5d_pct'));r20=num(r.get('stock_20d_pct'))
  if r5 is None or r20 is None:continue
  x={k:r.get(k,'') for k in fields};x.update(candidate_class='SECTOR_SAMPLE_124',technical_score=round(.65*r20+.35*r5,3),sector_research_score=r.get('research_score',''),trade_authorized='NO');combined.append(x)
 by={}
 for r in combined:
  t=r['ticker'];old=by.get(t)
  if old is None or (r['candidate_class']=='SECTOR_SAMPLE_124' and old['candidate_class']!='SECTOR_SAMPLE_124'):by[t]=r
 ranked=sorted(by.values(),key=lambda r:float(r['technical_score']),reverse=True)
 save(out/'v75_common_technical_watchlist.csv',ranked,fields)
 top=[]
 for i,r in enumerate(ranked[:3],1):
  x=dict(r);x['research_rank']=i;top.append(x)
 save(out/'v75_provisional_common_top3.csv',top,['research_rank']+fields)
 audit={'version':'7.5','asof':asof,'scope':'30 independent + 124 mapped sector sample, NOT full-market 2568 historical validation','independent_queue':len(queue),'independent_validated':sum(x.get('status') in ('COLLECTED_VALID','CACHE_VALID') for x in valid),'independent_technical_setups':sum(x['status']=='HISTORICAL_WATCH_ONLY' for x in rows),'independent_invalid':sum(x['status'] in ('INVALID_HISTORY','NO_VALID_HISTORY') for x in rows),'sector_technical_setups':len([r for r in sector if r.get('status')=='HISTORICAL_WATCH_ONLY']),'combined_unique_setups':len(ranked),'provisional_top3':[{'ticker':x['ticker'],'name':x['name'],'class':x['candidate_class'],'score':x['technical_score']} for x in top],'trade_authorized':False,'status':'HISTORICAL_RESEARCH_ONLY','limitations':['Stock-return common score is a provisional comparable ranking, not predictive accuracy','Only 30 independent names were selected using same-day information; no unbiased 2568-stock historical validation','Sector mapping unverified and omitted from common technical score','Historical date, no real-time market or executable prices','No 1/3/5/10-session forward returns or realistic paper-trading evidence','Price bands are not exchange tick-rounded']}
 (out/'v75_common_comparison_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(audit,ensure_ascii=False))
if __name__=='__main__':main()
