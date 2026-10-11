#!/usr/bin/env python3
"""v5.9 research-only cross-sectional OHLCV candidate triage; no live buy approval."""
import argparse,csv,json,math
from pathlib import Path

def read(path):
 with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def number(s):
 try:
  x=float(s)
  return x if math.isfinite(x) else None
 except (ValueError,TypeError):return None

def main():
 p=argparse.ArgumentParser();p.add_argument('--outdir',default='reports');a=p.parse_args();out=Path(a.outdir)
 audit=json.loads((out/'market_data_v56_merge_audit.json').read_text(encoding='utf-8'))
 if audit.get('status') not in ('ALL_SHARDS_COLLECTED_WITH_FAILURES','ALL_SHARDS_COLLECTED_OHLCV_ONLY_NO_BUY') or audit.get('shards_collected')!=audit.get('shard_count') or audit.get('live_buy_approved')!=0:raise ValueError('MERGE_NOT_SAFE_FOR_RESEARCH')
 rows=read(out/'market_data_v56_merged.csv');session=audit['batch_date'];results=[];skipped={}
 for r in rows:
  try:
   if r['snapshot_date']!=session or r['dated_ohlcv_valid'].lower()!='true':raise ValueError('INVALID_DATE')
   o,h,l,c,v=[number(r[k]) for k in ('open','high','low','close','volume')]
   if any(x is None for x in (o,h,l,c,v)) or not (0<l<=o<=h and l<=c<=h and v>0):raise ValueError('INVALID_BAR')
   # One-day candle, NOT trend, RS, institutional flow, or verified exchange turnover.
   proxy=c*v;day_return=100*(c/o-1);position=(c-l)/(h-l) if h>l else 0.5;range_pct=100*(h-l)/c
   if proxy<1_000_000_000:raise ValueError('LOW_PROXY_LIQUIDITY')
   if range_pct>18:raise ValueError('EXCESSIVE_INTRADAY_RANGE')
   if day_return>15:raise ValueError('OVEREXTENDED_DAY')
   if position<0.55:raise ValueError('WEAK_CLOSE_LOCATION')
   score=round(35*position+min(25,max(0,day_return)*4)+min(20,math.log10(max(1,proxy)/1e9)*12)+max(0,20-range_pct*1.5),2)
   results.append(dict(ticker=r['ticker'],name=r['name'],market=r['market'],snapshot_date=session,close=int(c),day_return_pct=round(day_return,2),close_location=round(position,3),range_pct=round(range_pct,2),close_times_volume_proxy_krw=int(proxy),preliminary_score=score,status='WATCH_ONLY_NOT_BUY',missing_checks='MULTIDAY_TREND|RS|RVOL|FOREIGN_INSTITUTION_FLOW|CATALYST|INSTRUMENT_TYPE|VERIFIED_TURNOVER|LIVE_PRICE|CAPITAL_GATE'))
  except ValueError as e:skipped[str(e)]=skipped.get(str(e),0)+1
 results.sort(key=lambda x:(-x['preliminary_score'],-x['close_times_volume_proxy_krw'],x['ticker']))
 out.mkdir(exist_ok=True,parents=True)
 fields=['ticker','name','market','snapshot_date','close','day_return_pct','close_location','range_pct','close_times_volume_proxy_krw','preliminary_score','status','missing_checks']
 with (out/'v59_preliminary_watchlist.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(results)
 report={'version':'v5.9','status':'PRELIMINARY_WATCH_ONLY','research_only':True,'live_buy_approved':0,'batch_date':session,'input_rows':len(rows),'screened_watch_count':len(results),'top_10':results[:10],'excluded':skipped,'caveats':['Single-date OHLCV cannot verify weekly/daily trends, relative strength, RVOL, or fund flows.','Close times volume is an UNVERIFIED liquidity proxy, not independently verified exchange turnover.','Do not use preliminary scores for trading or position sizing.']}
 (out/'v59_preliminary_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
