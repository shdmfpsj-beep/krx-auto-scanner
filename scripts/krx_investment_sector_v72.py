#!/usr/bin/env python3
"""v7.2: sector-aware historical entry geometry; research-only, no live BUY signals."""
import argparse,csv,json,math,statistics
from pathlib import Path
from collections import defaultdict

def read(p):
 with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def save(p,rows,fields):
 with open(p,'w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def number(x):
 try:
  v=float(x);return v if math.isfinite(v) else None
 except (ValueError,TypeError):return None
def round_tick(x):
 # Historical research geometry; tick-size execution validation required.
 return round(x,2)
def main():
 p=argparse.ArgumentParser()
 p.add_argument('--members',default='reports/v68_investment_sector_members.csv')
 p.add_argument('--sectors',default='reports/v71_sector_strength.csv')
 p.add_argument('--market',default='reports/market_data_v56_merged.csv')
 p.add_argument('--cache',default='reports/v36_ohlcv_cache')
 p.add_argument('--outdir',default='reports')
 a=p.parse_args();out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
 members=read(a.members);sectors=read(a.sectors);market=read(a.market)
 dates={r['snapshot_date'] for r in members}|{r['snapshot_date'] for r in market}
 if len(dates)!=1:raise SystemExit('Snapshot date mismatch')
 asof=dates.pop(); marketby={r['ticker'].zfill(6):r for r in market}
 sectorby={r['investment_sector']:r for r in sectors}
 for s in sectors:
  if s['investment_sector'] not in {r['investment_sector'] for r in members}:raise SystemExit('Unknown sector')
 result=[]; missing=defaultdict(int)
 for r in members:
  t=r['ticker'].zfill(6);s=r['investment_sector'];sec=sectorby.get(s,{})
  base={'ticker':t,'name':r['name'],'investment_sector':s,'subtheme':r.get('subtheme',''),'asof':asof,'mapping_verified':r.get('theme_exposure_verified','false'),'status':'','setup':'','sector_5d_pct':sec.get('median_5d_pct',''),'sector_20d_pct':sec.get('median_20d_pct',''),'stock_5d_pct':'','stock_20d_pct':'','close':'','ideal_buy_low':'','ideal_buy_high':'','max_buy':'','no_chase_above':'','structural_stop':'','target_1':'','target_2':'','reward_risk':'','trade_authorized':'NO','reason':''}
  if sec.get('status')!='RESEARCH_READY':base.update(status='SECTOR_NOT_READY',reason='Sector coverage gate failed');result.append(base);continue
  f=Path(a.cache)/f'{t}.csv'
  if not f.exists():base.update(status='NO_CACHE',reason='Historical OHLCV unavailable');result.append(base);continue
  try:
   data=[]
   for d in read(f):
    date=d.get('Date',d.get('date',''))
    if date>asof:continue
    vals=[number(d.get(k,d.get(k.lower()))) for k in ('Open','High','Low','Close','Volume')]
    if all(v is not None for v in vals) and min(vals[:4])>0 and vals[4]>=0 and vals[2]<=min(vals[0],vals[3])<=max(vals[0],vals[3])<=vals[1]:data.append((date,*vals))
   data.sort(); ds=[x[0] for x in data]
   if len(data)<31 or len(ds)!=len(set(ds)) or ds[-1]!=asof:raise ValueError('Insufficient, duplicate, or stale OHLCV')
   o,h,l,c,v=[x[1] for x in data],[x[2] for x in data],[x[3] for x in data],[x[4] for x in data],[x[5] for x in data]
   snap=number(marketby[t].get('close'))
   if not snap or abs(c[-1]/snap-1)>0.03:raise ValueError('Snapshot close mismatch')
   r5=100*(c[-1]/c[-6]-1);r20=100*(c[-1]/c[-21]-1)
   ma20=statistics.mean(c[-20:]);ma10=statistics.mean(c[-10:]); prior_high=max(h[-21:-1]);low10=min(l[-10:]);low20=min(l[-20:]);vol20=statistics.mean(v[-21:-1]);rvol=v[-1]/vol20 if vol20>0 else 0
   # Technical setup screening; avoid same-day breakout chase and structural downtrends.
   uptrend=c[-1]>ma20 and ma10>=ma20 and r20>0
   breakout=c[-1]>prior_high and rvol>=1.2
   pullback=uptrend and low10<=ma10*1.025 and c[-1]>=ma10*0.98 and c[-1]<=ma10*1.06
   setup='BREAKOUT' if breakout and uptrend else 'FIRST_PULLBACK' if pullback else 'NONE'
   # Indicative entry band from recent MA and 10-session lows; no executable tick rounding.
   ideal_low=max(low10,ma20*0.98);ideal_high=min(c[-1],ma10*1.02)
   stop=min(low10,ma20*0.97);max_buy=min(prior_high*1.015,c[-1]*1.02)
   if setup=='BREAKOUT':ideal_low=prior_high;ideal_high=min(c[-1],prior_high*1.015)
   if not (ideal_low>stop>0 and ideal_high>=ideal_low and max_buy>=ideal_high):setup='NONE'
   risk=ideal_high-stop if setup!='NONE' else 0
   target1=ideal_high+1.5*risk if risk>0 else 0;target2=ideal_high+2.5*risk if risk>0 else 0
   base.update(stock_5d_pct=round(r5,3),stock_20d_pct=round(r20,3),close=c[-1],setup=setup)
   if setup=='NONE':base.update(status='NO_SETUP',reason='Trend, breakout/pullback or risk geometry gate not met')
   else:
    base.update(status='HISTORICAL_WATCH_ONLY',ideal_buy_low=round_tick(ideal_low),ideal_buy_high=round_tick(ideal_high),max_buy=round_tick(max_buy),no_chase_above=round_tick(max_buy),structural_stop=round_tick(stop),target_1=round_tick(target1),target_2=round_tick(target2),reward_risk=1.5,reason='Research-only: historical snapshot; theme mapping unverified; tick-size, liquidity, market benchmark and live gate not validated')
  except (ValueError,KeyError,IndexError,ZeroDivisionError) as exc:base.update(status='INVALID_HISTORY',reason=str(exc)[:140])
  result.append(base)
 # One stock can belong to multiple themes: de-duplicate the candidate ranking by ticker.
 candidates={}
 for row in result:
  if row['status']!='HISTORICAL_WATCH_ONLY':continue
  score=(float(row['sector_20d_pct'] or 0)*0.4+float(row['sector_5d_pct'] or 0)*0.3+float(row['stock_20d_pct'] or 0)*0.2+float(row['stock_5d_pct'] or 0)*0.1)
  row['research_score']=round(score,3)
  if row['ticker'] not in candidates or score>candidates[row['ticker']]['research_score']:candidates[row['ticker']]=row
 watch=sorted(candidates.values(),key=lambda r:r['research_score'],reverse=True)
 fields=['ticker','name','investment_sector','subtheme','asof','mapping_verified','status','setup','sector_5d_pct','sector_20d_pct','stock_5d_pct','stock_20d_pct','close','ideal_buy_low','ideal_buy_high','max_buy','no_chase_above','structural_stop','target_1','target_2','reward_risk','research_score','trade_authorized','reason']
 save(out/'v72_entry_geometry.csv',result,fields);save(out/'v72_historical_watchlist.csv',watch,fields)
 audit={'status':'HISTORICAL_RESEARCH_ONLY','asof':asof,'memberships':len(members),'unique_tickers':len({r['ticker'] for r in members}),'geometry_rows':sum(r['status']=='HISTORICAL_WATCH_ONLY' for r in result),'unique_watchlist':len(watch),'trade_authorized':False,'limitations':['Historical snapshot is not current','Theme exposure mapping is not externally verified','Not full-market screening: 124-stock sector sample only','Independent standalone scanner not integrated','Market index relative strength, liquidity, orderbook, costs and exchange tick size not verified','No automatic BUY, no backtest performance claim']}
 (out/'v72_entry_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(audit,ensure_ascii=False))
if __name__=='__main__':main()
