#!/usr/bin/env python3
"""HMA60 first-pullback, research only. Daily-close confirmation, next-open proxy.

Compare on identical usable source and identical exits to bottom_upturn_v10.py.
All entry decisions are formed using dates at/before the signal date; next-session
OPEN is a modeled, gap-gated fill, not an executable order. Not PIT KRX universe.
"""
from __future__ import annotations
import argparse,csv,json,math,statistics,sys
from pathlib import Path
from collections import Counter

try:
 import bottom_upturn_v10 as base
except ImportError as ex:
 raise SystemExit('Missing scripts/bottom_upturn_v10.py (copy from previous release)') from ex

HMA_PERIOD=60
VARIANTS=base.VARIANTS

def wma(values,period):
 if period<1:raise ValueError('period must be positive')
 out=[None]*len(values);den=period*(period+1)/2
 for i in range(period-1,len(values)):
  window=values[i-period+1:i+1]
  if all(v is not None and math.isfinite(v) for v in window):
   out[i]=sum(v*(j+1) for j,v in enumerate(window))/den
 return out

def hma(closes,period=60):
 """Exact user formula: wavg(2*wavg(C,n/2)-wavg(C,n), floor(sqrt(n))).
 This matches the formula for even n=60; intermediate WMA starts at n-1.
 """
 fast=wma(closes,period//2);slow=wma(closes,period)
 delta=[2*a-b if a is not None and b is not None else None for a,b in zip(fast,slow)]
 return wma(delta,math.isqrt(period))

def turn_dates(b,h):
 """Reversal after declines. Confirmed only after two positive close-to-close HMA slopes."""
 for i in range(82,len(b)-1):
  if any(h[z] is None for z in (i-10,i-3,i-2,i-1,i)):continue
  if not (h[i-3]>=h[i-2] and h[i-1]>h[i-2] and h[i]>h[i-1]):continue
  prior=sum(h[k]<h[k-1] for k in range(i-9,i-1))
  if prior<4:continue
  if not (b[i]['close']>h[i]*0.985):continue
  yield i

def recognize_first_pullback(b,h,t,turn_window=15,pullback_window=9,min_turnover=0):
 """Locate earliest qualifying impulse and *first* material retracement.
 No lookahead for entry: all confirmation criteria use <=p; execution uses p+1 open.
 """
 if t+3>=len(b):return None
 turn_close=b[t]['close'];imp=None
 for k in range(t+1,min(t+turn_window+1,len(b)-1)):
  q=b[k];res=max(x['close'] for x in b[k-12:k]);avgvol=sum(x['volume'] for x in b[k-20:k])/20
  if (q['close']>=turn_close*1.025 and q['close']>=res*1.001
      and q['close']>=h[k]*1.005 and q['volume']>=avgvol*1.1
      and q['close']<=turn_close*1.20 and q['close']*q['volume']>=min_turnover):
   imp=k;break
 if imp is None:return None
 # Seek earliest negative day after impulse. First pullback only.
 start=None
 for k in range(imp+1,min(imp+pullback_window+2,len(b)-1)):
  if b[k]['close']<b[k-1]['close']*.995 or b[k]['close']<b[k]['open']*.998:
   start=k;break
 if start is None:return None
 for p in range(start+1,min(start+pullback_window+1,len(b)-1)):
  q=b[p];prev=b[p-1];leg=b[start:p]
  if not leg:continue
  impulse_peak=max(x['high'] for x in b[imp:p])
  low=min(x['low'] for x in leg)
  # First retracement should be meaningful, but not destroy the new base.
  if low>impulse_peak*.980:continue
  if low<min(h[start:p+1])*.940:return None
  if low < b[t]['close']*.92:return None
  if any(x['close']<h[start+j]*.96 for j,x in enumerate(b[start:p],start=0)):return None
  if not (q['close']>prev['high']*.999 and q['close']>q['open'] and q['close']>prev['close']*1.003):continue
  if not (h[p]>h[p-2] and q['close']>=h[p]):continue
  # Pullback volume must soften compared with first expansion bar.
  if statistics.mean(x['volume'] for x in leg)>b[imp]['volume']*.95:continue
  if q['close']>impulse_peak*1.055:continue
  e=p+1;op=b[e]['open']
  if op>q['close']*1.025 or op<q['close']*.94:return None
  stop=min(x['low'] for x in b[start:p+1])*.985
  risk=1-stop/op
  if not(.025<=risk<=.05):return None
  # first +10% objective must supply at least 2R before cost
  if .10/risk<2:return None
  return dict(turn_date=b[t]['date'],impulse_date=b[imp]['date'],pullback_start=b[start]['date'],signal_date=b[p]['date'],entry_date=b[e]['date'],entry_idx=e,entry_price=op,stop=stop,risk_pct=100*risk,pullback_bars=p-start+1,turn_hma=h[t],signal_hma=h[p],impulse_high=impulse_peak,impulse_rvol=b[imp]['volume']/(sum(x['volume'] for x in b[imp-20:imp])/20))
 return None

def hma_entries(b,min_turnover=500_000_000):
 h=hma([r['close'] for r in b]);turns=list(turn_dates(b,h))
 # Candidate events are produced at their actual confirmed rebound date. Select
 # chronologically by executable entry date, not by older turn date: choosing an
 # older turn using a later-confirmed entry would retroactively block an earlier
 # executable entry from a newer turn (subtle selection lookahead).
 proposed=[]
 for t in turns:
  e=recognize_first_pullback(b,h,t,min_turnover=min_turnover)
  if e:proposed.append(e)
 signals=[];cooldown=-1
 for e in sorted(proposed,key=lambda x:(x['entry_idx'],x['turn_date'])):
  if e['entry_idx']<cooldown:continue
  signals.append(e);cooldown=e['entry_idx']+70
 return signals,turns,h

def result_summary(rows):
 a=[x for x in rows if x.get('status')=='COMPLETE']
 out=base.summary(a)
 out['censored']=len(rows)-len(a)
 return out

def run(args):
 output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
 quality=Counter();quality_rows=[];all_trades=[];all_entries=[];baseline=[];turn_rows=[];case_audit=[]
 watch={'036930':'주성엔지니어링','034020':'두산에너빌리티','006400':'삼성SDI','131970':'두산테스나'}
 found=set()
 for ticker,raw in base.iter_source(Path(args.input)):
  found.add(ticker);bars,status=base.read_bars(raw);quality[status]+=1
  raw_lines=raw.decode('utf-8-sig',errors='replace').splitlines()
  raw_n=max(0,len(raw_lines)-1);raw_first=raw_lines[1].split(',')[0] if raw_n else '';raw_last=raw_lines[-1].split(',')[0] if raw_n else ''
  quality_rows.append(dict(ticker=ticker,status=status,bars=len(bars),raw_bars=raw_n,first_date=bars[0]['date'] if bars else raw_first,last_date=bars[-1]['date'] if bars else raw_last))
  if ticker in watch:
   case_audit.append(dict(ticker=ticker,name=watch[ticker],status=status,bars=len(bars) if bars else raw_n,first_date=bars[0]['date'] if bars else raw_first,last_date=bars[-1]['date'] if bars else raw_last,user_reference_date={'036930':'2026-09-03','034020':'2026-08-24','006400':'2026-08-11','131970':'2026-09-15'}[ticker],verified_signal_date='NOT_VERIFIED'))
  if status!='OK':continue
  entries,turns,h=hma_entries(bars,args.min_turnover)
  for t in turns:
   turn_rows.append(dict(ticker=ticker,turn_date=bars[t]['date'],turn_hma=round(h[t],5),close=bars[t]['close'],followed_by_valid_entry=any(e['turn_date']==bars[t]['date'] for e in entries)))
  for e in entries:
   all_entries.append(dict(ticker=ticker,**e))
   for mode in VARIANTS:
    trade=base.run_exit(bars,e,mode,args.max_hold,args.cost_bps)
    all_trades.append(dict(ticker=ticker,method='HMA60',variant=mode,**e,**trade))
  if args.baseline:
   for be in base.get_entries(bars,args.min_turnover):
    for mode in VARIANTS:
     trade=base.run_exit(bars,be,mode,args.max_hold,args.cost_bps)
     baseline.append(dict(ticker=ticker,method='v10_ORIGINAL',variant=mode,**be,**trade))
 for ticker,name in watch.items():
  if ticker not in found:
   case_audit.append(dict(ticker=ticker,name=name,status='NOT_IN_CACHE',bars=0,first_date='',last_date='',user_reference_date={'036930':'2026-09-03','034020':'2026-08-24','006400':'2026-08-11','131970':'2026-09-15'}[ticker],verified_signal_date='NOT_VERIFIED'))
 summary_rows=[];yearly=[]
 for method,trades in [('HMA60',all_trades),('v10_ORIGINAL',baseline)]:
  if not trades and method=='v10_ORIGINAL' and not args.baseline:continue
  for v in VARIANTS:
   cohort=[x for x in trades if x['variant']==v and x['entry_date']<'2026-01-01']
   summary_rows.append(dict(method=method,variant=v,**result_summary(cohort)))
   for year in ('2023','2024','2025','2026'):
    r=[x for x in trades if x['variant']==v and x['entry_date'].startswith(year)]
    yearly.append(dict(method=method,year=year,variant=v,**result_summary(r)))
 base.csv_out(output/'v11_data_quality.csv',quality_rows,['ticker','status','bars','raw_bars','first_date','last_date'])
 base.csv_out(output/'v11_user_four_coverage.csv',case_audit,['ticker','name','user_reference_date','status','bars','first_date','last_date','verified_signal_date'])
 base.csv_out(output/'v11_turn_events.csv',turn_rows,['ticker','turn_date','turn_hma','close','followed_by_valid_entry'])
 entry_cols=['ticker','turn_date','impulse_date','pullback_start','signal_date','entry_date','entry_price','stop','risk_pct','pullback_bars','turn_hma','signal_hma','impulse_high','impulse_rvol']
 base.csv_out(output/'v11_entries.csv',all_entries,entry_cols)
 trade_cols=['ticker','method','variant','turn_date','impulse_date','pullback_start','signal_date','entry_date','entry_price','stop','risk_pct','pullback_bars','status','exit_date','exit_reason','days_held','net_return_pct','gross_return_pct']
 base.csv_out(output/'v11_hma_trades.csv',all_trades,trade_cols)
 base.csv_out(output/'v11_baseline_v10_trades.csv',baseline,['ticker','method','variant','signal_date','entry_date','entry_price','stop','risk_pct','status','exit_date','exit_reason','days_held','net_return_pct','gross_return_pct'])
 sums=['method','variant','n','censored','mean_net_pct','median_net_pct','win_rate_pct','tp10_pct','tp20_pct','avg_hold']
 base.csv_out(output/'v11_comparison_2023_2025.csv',summary_rows,sums)
 base.csv_out(output/'v11_yearly.csv',yearly,['method','year','variant','n','censored','mean_net_pct','median_net_pct','win_rate_pct','tp10_pct','tp20_pct','avg_hold'])
 audit=dict(version='HMA60_First_Pullback_v1.1',research_only=True,buy_approval=False,code_origin='user exact HMA= WMA(2*WMA(close,30)-WMA(close,60),7)',time_rule='confirmed closing bars through signal date; next-session open fill assumption, 2.5% max opening gap',source=args.input,source_tickers=sum(quality.values()),usable_tickers=quality['OK'],quality=dict(quality),hma_turn_events=len(turn_rows),hma_entries=len(all_entries),hma_entry_tickers=len(set(x['ticker'] for x in all_entries)),max_hold=args.max_hold,one_position_portfolio_tested=False,entry_rules='Two rising HMA60 closes following negative HMA slope, minimum four previous downward slopes; first +2.5% up impulse with new 12-day close high, RVOL>=1.1 within 15 bars; first red/down day within 9 bars; 2%-plus shallow retracement with reduced volume, HMA support and bullish confirmation; next bar gap gate; 2.5%-5% risk and target +10% >=2R',roundtrip_cost_bps=args.cost_bps,min_impulse_trade_value_krw=args.min_turnover,strict_pit_approved=False,missing_historical_universe=True,survivorship_bias=True,limitations=['Subset of selected historical ticker cache, not all KRX listed on each historical date','OHLCV integrity filters do not include split/rights/merger verification','Cannot verify all four user-nominated Sep/Aug 2026 dates (short history or ticker absent)','HMA reversal and first pullback confirmed at close, next day open proxy; not executable orders','Daily stop/target time ordering assumed conservatively stop first; no tick-level fill, bid/ask or slippage validation','HMA setup thresholds preregistered research hypotheses, not statistically optimized; baseline and HMA signal cohorts differ','v10 outcomes and HMA outcomes comparable on same available tickers/exit methods, but different trade counts and market-date exposures','No CVD auxiliary filter and no sector, global, corporate fundamentals used in pure HMA test','Small sample; 2026 outside sample insufficient for independent walk-forward validation'])
 (output/'v11_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'audit':audit,'comparison':summary_rows,'yearly':yearly,'case_coverage':case_audit},ensure_ascii=False,indent=2))
 return audit,summary_rows

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--input',default='reports/v36_ohlcv_cache')
 p.add_argument('--output',default='reports/hma_v11')
 p.add_argument('--baseline',action='store_true')
 p.add_argument('--min-turnover',type=float,default=500_000_000)
 p.add_argument('--max-hold',type=int,default=60)
 p.add_argument('--cost-bps',type=float,default=35)
 a=p.parse_args()
 if a.max_hold<10 or a.cost_bps<0: p.error('Invalid settings')
 run(a)

if __name__=='__main__':main()
