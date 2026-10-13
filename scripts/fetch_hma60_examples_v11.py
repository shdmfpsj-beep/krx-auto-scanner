#!/usr/bin/env python3
"""Research-only independent histories for four USER-NOMINATED 2026 chart examples.
NEVER merge these examples into original v11 performance cohorts: they were
picked with hindsight. Yahoo Finance/yfinance is unofficial and may fail.
"""
from __future__ import annotations
import argparse,csv,json,math,sys
from datetime import date,datetime
from zoneinfo import ZoneInfo
from pathlib import Path
try:
 import hma60_first_pullback_v11 as hm
 import bottom_upturn_v10 as base
except ImportError as exc:
 raise SystemExit('Missing hma60_first_pullback_v11.py / bottom_upturn_v10.py') from exc

CASES=[('036930','주성엔지니어링','2026-09-03','.KQ'),('034020','두산에너빌리티','2026-08-24','.KS'),('006400','삼성SDI','2026-08-11','.KS'),('131970','두산테스나','2026-09-15','.KQ')]

def nearest(b,turns,ref_date):
 idx=next((j for j,r in enumerate(b) if r['date']>=ref_date),None)
 if idx is None or not turns:return ('','')
 turns=sorted(turns,key=lambda x:abs(x-idx))
 best=turns[0];dist=best-idx
 return (b[best]['date'],dist)

def fetch_one(ticker,suffix,start,end):
 import yfinance as yf
 import pandas as pd
 frame=yf.download(ticker+suffix,start=start,end=end,auto_adjust=False,progress=False,threads=False)
 if frame is None or frame.empty:return [],'EMPTY_DOWNLOAD'
 if isinstance(frame.columns,pd.MultiIndex):
  frame.columns=frame.columns.get_level_values(0)
 out=[]
 for ts,r in frame.iterrows():
  try:
   record={'date':str(ts.date()),'open':float(r['Open']),'high':float(r['High']),'low':float(r['Low']),'close':float(r['Close']),'volume':float(r['Volume'])}
   if not all(math.isfinite(v) for k,v in record.items() if k!='date'):continue
   out.append(record)
  except (KeyError,ValueError,TypeError):continue
 return out,'DOWNLOADED'

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--outdir',default='reports/hma_v11/examples')
 parser.add_argument('--start',default='2025-06-01')
 parser.add_argument('--end-exclusive',default=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat())
 a=parser.parse_args();date.fromisoformat(a.start);date.fromisoformat(a.end_exclusive)
 out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
 rows=[];log=[]
 for ticker,name,ref,suffix in CASES:
  status='NOT_ATTEMPTED';bars=[];error=''
  try:
   bars,status=fetch_one(ticker,suffix,a.start,a.end_exclusive)
   if status=='DOWNLOADED':
    # Reuse same quality check on round-tripped standard CSV bytes to prevent data misuse.
    payload='Date,Open,High,Low,Close,Volume\n'+'\n'.join(','.join([r['date']]+[str(r[k]) for k in ('open','high','low','close','volume')]) for r in bars)+'\n'
    verified,q=base.read_bars(payload.encode())
    status='VALID_BARS' if q=='OK' else q
    if q=='OK':bars=verified
   if status!='VALID_BARS':bars=[]
  except Exception as exc:
   error=type(exc).__name__+': '+str(exc)[:170]
   status='FETCH_ERROR';bars=[]
  event='';lag='';entry_date='';signal_date='';entry_price='';nturns=0;nentries=0
  if bars:
   h=hm.hma([r['close'] for r in bars]);turns=list(hm.turn_dates(bars,h));entries,_turns,_h=hm.hma_entries(bars)
   nturns=len(turns);nentries=len(entries)
   event,lag=nearest(bars,turns,ref)
   at=[x for x in entries if ref[:7] in (x['turn_date'][:7],x['entry_date'][:7])]
   if at:
    candidate=min(at,key=lambda e:abs((date.fromisoformat(e['turn_date'])-date.fromisoformat(ref)).days))
    entry_date=candidate['entry_date'];signal_date=candidate['signal_date'];entry_price=round(candidate['entry_price'],2)
   base.csv_out(out/(ticker+'_downloaded_ohlcv.csv'),bars,['date','open','high','low','close','volume'])
  row=dict(ticker=ticker,name=name,requested_date=ref,status=status,bars=len(bars),earliest=bars[0]['date'] if bars else '',latest=bars[-1]['date'] if bars else '',nearest_hma_turn_date=event,turn_distance_sessions=lag,confirmed_past_turns=nturns,confirmed_entries=nentries,example_entry_date=entry_date,example_confirmation_date=signal_date,example_entry_price=entry_price,not_in_performance_cohort=True,fetch_error=error)
  rows.append(row);log.append(row)
 fields=list(rows[0]);base.csv_out(out/'v11_four_user_cases_audit.csv',rows,fields)
 (out/'v11_example_fetch_audit.json').write_text(json.dumps({'research_only':True,'not_in_performance_cohort':True,'source':'unofficial Yahoo Finance via yfinance (auto_adjust=False, original Close)','source_start':a.start,'end_exclusive':a.end_exclusive,'cases':rows,'restrictions':['Selection bias: examples explicitly nominated after inspecting winning charts','Raw Yahoo prices may have gaps/corporate action discontinuities; quality filter excludes unusable input','Nearest HMA reversal does not prove user date was entry/turn or causal winner','Close-confirmed signals enter next day open and remain hypothetical']},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(log,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
