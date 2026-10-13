#!/usr/bin/env python3
"""Bottom-to-Upturn Swing v1.0 research-only, offline historical OHLCV.

Strictly uses <= decision bar for setups. Signals at confirmed rebound close,
entry at next day's OPEN (conditional gap gate), exits at future OHLC bars.
Not a KRX-wide/survivorship-free backtest; data source caveats in audit.
"""
from __future__ import annotations
import argparse,csv,io,json,math,statistics,zipfile
from collections import Counter
from datetime import date
from pathlib import Path

COST_ROUNDTRIP_BPS=35 # 0.35%; split equally at entry and each exit
MAX_HOLD=60
FIELDS=['Date','Open','High','Low','Close','Volume']
VARIANTS=['A_10_ALL','B_10_HALF_20_TRAIL','C_TRAIL_ONLY']

def csv_out(path,rows,fields):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def read_bars(data:bytes):
 arr=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
 if len(arr)<170:return [],'INSUFFICIENT_170_BARS'
 records=[]; last=''; priorclose=0
 for r in arr:
  try:
   dt=r['Date'];date.fromisoformat(dt)
   o,h,l,c,v=[float(r[k].replace(',','')) for k in FIELDS[1:]]
   if (not all(math.isfinite(z) for z in [o,h,l,c,v])) or min(o,h,l,c,v)<=0 or h<max(o,c) or l>min(o,c) or dt<=last:return [],'INVALID_OHLCV'
   if priorclose and abs(c/priorclose-1)>0.41:return [],'SUSPICIOUS_CORPORATE_ACTION'
  except (ValueError,KeyError,TypeError,ZeroDivisionError,AttributeError):return [],'INVALID_OHLCV'
  records.append(dict(date=dt,open=o,high=h,low=l,close=c,volume=v))
  last=dt;priorclose=c
 return records,'OK'

def iter_source(path:Path):
 if path.is_file() and path.suffix.lower()=='.zip':
  with zipfile.ZipFile(path) as z:
   for n in z.namelist():
    if n.startswith('v36_ohlcv_cache/') and n.endswith('.csv'):
     yield Path(n).stem,z.read(n)
 elif path.is_dir():
  for p in sorted(path.glob('*.csv')):yield p.stem,p.read_bytes()
 else:raise FileNotFoundError('Expected v36_ohlcv_cache directory or krx-scan-report ZIP')

def ma(bars,i,n):return sum(b['close'] for b in bars[i-n+1:i+1])/n

def potential_breakout(b,i,min_turnover=500_000_000):
 """All measurements depend only on bars through i (after i close)."""
 if i<115:return None
 prev=b[i-25:i];first=prev[:12];second=prev[12:]
 floor=min(q['low'] for q in prev);ceiling=max(q['high'] for q in prev)
 if ceiling/floor>1.32:return None
 if min(q['low'] for q in second)<min(q['low'] for q in first)*.99:return None
 oldpeak=max(q['high'] for q in b[i-105:i-25])
 if oldpeak/floor<1.14:return None
 if ma(b,i,20)<ma(b,i-8,20)*.992:return None
 if ma(b,i,60)<ma(b,i-10,60)*.95:return None
 resistance=max(q['high'] for q in b[i-20:i])
 q=b[i];prevclose=b[i-1]['close'];avgvol=sum(y['volume'] for y in b[i-20:i])/20
 if q['close']<=resistance*1.003 or q['close']>resistance*1.09:return None
 if not (1.25<=q['volume']/avgvol<=15):return None
 if not (q['close']>q['open'] and q['close']/prevclose<1.115):return None
 if (q['close']-q['low'])/(q['high']-q['low'])<.60:return None
 if q['close']*q['volume']<min_turnover:return None
 return dict(breakout_idx=i,breakout_date=q['date'],resistance=resistance,breakout_close=q['close'],breakout_volume=q['volume'],rvol=round(q['volume']/avgvol,2),oldpeak=oldpeak,base_low=floor)

def detect_entry(b,setup):
 """Walk only forward from a breakout; rebound confirmation must precede entry day."""
 i=setup['breakout_idx'];r=setup['resistance'];v0=setup['breakout_volume'];c0=setup['breakout_close']
 for p in range(i+2,min(i+11,len(b)-1)):
  leg=b[i+1:p] # past pullback days before confirmation
  if not leg:continue
  q=b[p];prior=b[p-1]
  minleg=min(t['low'] for t in leg)
  if minleg>c0*.994 or minleg<r*.955:continue
  if max(t['high'] for t in leg)>c0*1.10:continue # breakout already extended
  if sum(x['volume'] for x in leg)/len(leg)>v0*.86:continue
  if not (q['close']>prior['close']*1.004 and q['close']>=q['open'] and q['close']>=prior['high']*.995):continue
  if q['close']/c0>1.09:continue
  entry_i=p+1;entry=b[entry_i]
  if entry['open']>q['close']*1.025 or entry['open']<q['close']*.94:return None
  if entry['open']<=0:return None
  stop=min(x['low'] for x in b[i+1:p+1])*.985
  risk=1-stop/entry['open']
  if not (.025<=risk<=.07):return None
  if .10/risk<2.0:return None
  if entry['open']<=stop:return None
  return dict(signal_date=q['date'],entry_idx=entry_i,entry_date=entry['date'],entry_price=entry['open'],stop=stop,risk_pct=risk*100,pullback_bars=p-i,breakout_date=setup['breakout_date'],rvol=setup['rvol'],resistance=r)
 return None

def get_entries(b,min_turnover=500_000_000):
 """At most one candidate per stock every 70 days, dates decided on signal day."""
 entries=[];cooldown=0
 for i in range(115,len(b)-1):
  if i<cooldown:continue
  setup=potential_breakout(b,i,min_turnover)
  if not setup:continue
  entry=detect_entry(b,setup)
  if entry:
   entries.append(entry);cooldown=entry['entry_idx']+70
 return entries

def run_exit(b,e,mode,max_hold=60,cost_bps=35):
 """Conservative intrabar priority: prior stop, then take profit(s).
 Gap-down stops fill at open, not stop price. Trailing levels use only prior bars.
 Includes price outcomes on entry day because entry at day open.
 """
 j=e['entry_idx'];entry=e['entry_price'];stop=e['stop'];tp10=entry*1.10;tp20=entry*1.20
 first=None;trades=[];trail=stop
 for k in range(j,min(j+max_hold,len(b))):
  q=b[k];o,h,l,c=[q[t] for t in ('open','high','low','close')]
  # Update trailing stop at session start, based on CLOSED bars strictly before k.
  if mode=='C_TRAIL_ONLY' and k>j+1:
   recent=min(x['low'] for x in b[max(j,k-10):k])*.99
   trail=max(trail,recent)
  if mode=='B_10_HALF_20_TRAIL' and first is not None and k>j:
   recent=min(x['low'] for x in b[max(j,k-5):k])*.99
   trail=max(trail,recent)
  exit_stop=trail if mode!='A_10_ALL' else stop
  # Gap through stop always executed at worse opening price. For a newly entered position
  # the OPEN is the entry and cannot itself be a stop breach (prechecked).
  if (k>j and o<=exit_stop) or l<=exit_stop:
   exit_price=min(o,exit_stop) if k>j else exit_stop
   if first is None:trades.append((1.0,exit_price,'STOP'))
   else:trades.append((.5,exit_price,'TRAIL_STOP'))
   break
  if mode=='A_10_ALL' and h>=tp10:
   trades.append((1.,tp10,'TP10'));break
  if mode=='B_10_HALF_20_TRAIL':
   if first is None and h>=tp10:
    # If both TP10 and TP20 occur in same bar, TP10 is achieved first by continuity.
    first=k;trades.append((.5,tp10,'TP10_HALF'))
   if first is not None and h>=tp20:
    trades.append((.5,tp20,'TP20'));break
  if k==j+max_hold-1:
   trades.append((.5 if first is not None else 1.,c,'TIME_60'))
 if not trades:return dict(status='CENSORED_NO_60_BARS')
 if abs(sum(t[0] for t in trades)-1)>1e-8:
  return dict(status='CENSORED_REMAINDER_OPEN',partial_exit_date=b[first]['date'] if first is not None else '',partial_exit_reason='TP10_HALF' if first is not None else '')
 gross=sum(weight*(price/entry-1) for weight,price,_ in trades)*100
 net=gross-cost_bps/100 # round-trip proportional trading cost assumption
 reason='+'.join(t[2] for t in trades)
 return dict(status='COMPLETE',gross_return_pct=round(gross,4),net_return_pct=round(net,4),exit_date=q['date'],exit_reason=reason,days_held=k-j+1,exit_prices=';'.join(str(round(price,2)) for _,price,_ in trades))

def summary(trades):
 a=[t for t in trades if t.get('status')=='COMPLETE'];n=len(a)
 if not n:return dict(n=0,mean_net_pct=None,median_net_pct=None,win_rate_pct=None,tp10_pct=None,tp20_pct=None,avg_hold=None,sum_compound_pct=None)
 returns=[x['net_return_pct'] for x in a]
 return dict(n=n,mean_net_pct=round(statistics.mean(returns),3),median_net_pct=round(statistics.median(returns),3),win_rate_pct=round(100*sum(x>0 for x in returns)/n,1),tp10_pct=round(100*sum('TP10' in x['exit_reason'] for x in a)/n,1),tp20_pct=round(100*sum('TP20' in x['exit_reason'] for x in a)/n,1),avg_hold=round(statistics.mean(x['days_held'] for x in a),1))

def max_drawdown(returns):
 bal=1.0;peak=1.0;dd=0
 for t in returns:
  bal*=1+t['net_return_pct']/100;peak=max(peak,bal);dd=max(dd,1-bal/peak)
 return round(dd*100,2),round((bal-1)*100,2)

def portfolio_select(trades):
 """One concurrent position. Deterministic ordering by entry date and ticker.
 This is 100% position whenever active; scaling/risk allocation NOT modeled.
 """
 trades=sorted([x for x in trades if x.get('status')=='COMPLETE'],key=lambda x:(x['entry_date'],x['ticker']))
 result=[];last_exit=''
 for t in trades:
  if t['entry_date']>last_exit:
   result.append(t);last_exit=t['exit_date']
 return result

def run(args):
 out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
 quality=Counter();data={};date_spans={};selected=[];cohort=[];quality_rows=[]
 for ticker,raw in iter_source(Path(args.input)):
  b,status=read_bars(raw);quality[status]+=1
  rawrows=max(0,raw.count(b'\n')-1)
  quality_rows.append(dict(ticker=ticker,status=status,raw_lines_estimate=rawrows,first_date=b[0]['date'] if b else '',last_date=b[-1]['date'] if b else '',valid_bars=len(b)))
  if status!='OK':continue
  data[ticker]=b;date_spans[ticker]=[b[0]['date'],b[-1]['date'],len(b)]
  entries=get_entries(b,args.min_turnover)
  for e in entries:
   cohort.append(dict(ticker=ticker,**e))
   for v in VARIANTS:
    result=run_exit(b,e,v,args.max_hold,args.cost_bps)
    selected.append(dict(ticker=ticker,variant=v,**e,**result))
 reasons=Counter(x['status'] for x in selected)
 completed=[x for x in selected if x['status']=='COMPLETE']
 csv_out(out/'v10_data_quality.csv',quality_rows,['ticker','status','raw_lines_estimate','first_date','last_date','valid_bars'])
 csv_out(out/'v10_candidates.csv',cohort,['ticker','signal_date','breakout_date','entry_date','entry_price','stop','risk_pct','pullback_bars','rvol','resistance'])
 trade_columns=['ticker','variant','signal_date','entry_date','breakout_date','entry_price','stop','risk_pct','rvol','pullback_bars','status','exit_date','exit_reason','exit_prices','days_held','gross_return_pct','net_return_pct']
 csv_out(out/'v10_trades.csv',selected,trade_columns)
 yearly=[]
 for year in sorted({x['entry_date'][:4] for x in selected}):
  for v in VARIANTS:
   records=[x for x in selected if x['entry_date'].startswith(year) and x['variant']==v]
   yearly.append(dict(year=year,variant=v,**summary(records),censored=sum(x['status']!='COMPLETE' for x in records)))
 csv_out(out/'v10_yearly.csv',yearly,['year','variant','n','censored','mean_net_pct','median_net_pct','win_rate_pct','tp10_pct','tp20_pct','avg_hold'])
 compares=[];port=[]
 for v in VARIANTS:
  t=[x for x in selected if x['variant']==v]
  portfolio=portfolio_select([x for x in t if x['entry_date']<'2026-01-01'])
  md,compound=max_drawdown(portfolio)
  compares.append(dict(variant=v,**summary(t),censored=sum(x['status']!='COMPLETE' for x in t),portfolio_trades=len(portfolio),portfolio_compound_pct=compound,portfolio_max_dd_pct=md))
  port.extend(portfolio)
 csv_out(out/'v10_summary.csv',compares,['variant','n','censored','mean_net_pct','median_net_pct','win_rate_pct','tp10_pct','tp20_pct','avg_hold','portfolio_trades','portfolio_compound_pct','portfolio_max_dd_pct'])
 primary=[]
 for v in VARIANTS:
  subset=[x for x in selected if x['variant']==v and x['entry_date']<'2026-01-01']
  primary.append(dict(variant=v,**summary(subset),censored=sum(x['status']!='COMPLETE' for x in subset)))
 csv_out(out/'v10_primary_2023_2025.csv',primary,['variant','n','censored','mean_net_pct','median_net_pct','win_rate_pct','tp10_pct','tp20_pct','avg_hold'])
 csv_out(out/'v10_one_position_portfolio.csv',port,trade_columns)
 audit=dict(version='Bottom_to_Upturn_v1.0',research_only=True,buy_approval=False,source=args.input,source_tickers=sum(quality.values()),quality_counts=dict(quality),usable_tickers=len(data),usable_date_end_histogram=dict(Counter(q[-1] for q in date_spans.values())),candidate_entries=len(cohort),unique_entry_tickers=len(set(e['ticker'] for e in cohort)),variant_trades=len(selected),completed_by_variant={v:sum(x['variant']==v and x['status']=='COMPLETE' for x in selected) for v in VARIANTS},censor_reasons=dict(reasons),max_holding_sessions=args.max_hold,roundtrip_cost_bps=args.cost_bps,selection_rules={'minimum_history':170,'base_days':25,'base_max_width_pct':32,'base_second_half_low_vs_first_half_min_pct':-1,'decline_from_prior_80_high_min_pct':14,'breakout_20_day_high_buffer_pct':0.3,'breakout_volume_vs_20d_average_min':1.25,'maximum_breakout_above_resistance_pct':9,'rebound_confirmation_bars_after_breakout':'2 to 10','pullback_min_volume_contraction_from_breakout_pct':14,'next_open_max_gap_over_rebound_close_pct':2.5,'entry_stop_distance_min_pct':2.5,'entry_stop_distance_max_pct':5.0,'minimum_reward_risk_to_10pct_target':2.0,'same_ticker_cooldown_bars':70,'min_trade_value_krw':args.min_turnover},entry_assumption='Next Korean session OPEN following rebound confirmation; only if gap <=2.5% above confirmation close',entry_order_not_backtested='Market-on-open assumed for eligible gap; no opening auction / order queue liquidity verification',stop_assumption='Previous close trailing reference; gap-through-stop exits at opening price; intraday stop takes precedence over targets',exit_designs={'A':'10% all exit, initial stop, 60-session max','B':'10% 50% exit, 20% remainder or 5-prior-day trailing, 60-session max','C':'10-prior-day trailing stop, no fixed take profit, 60-session max'},limitations=['Existing cached ticker collection only, not full KOSPI/KOSDAQ point-in-time historical universe; survivorship/selection biases and duplicate observations possible','Cache ends for long-history stocks at 2026-02-27 and 2026-10-08 for short-history stocks; 2026 forward holdout not available as independent long history','No independent market index, corporate action ledger, suspension/limit-up tradability audit or bid/ask/slippage implementation','No model-selection separation: parameters are preregistered hypotheses, not proven optimized','Exit liquidity at high/stop level is assumed, not guaranteed: same-bar stop prioritized but daily OHLC cannot prove fill, including limit-up/down','Portfolio simulation uses 2023-25 completed trades only and 100%-allocation illustration, not actual capital- or risk-sized C3 execution','No actual financial statements or sector mapping required; US global sector and disclosures not used'])
 (out/'v10_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'audit':audit,'comparison':compares,'primary_2023_2025':primary,'yearly':yearly},ensure_ascii=False,indent=2))
 return audit,compares

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--input',default='reports/v36_ohlcv_cache')
 p.add_argument('--output',default='reports/bottom_v10')
 p.add_argument('--max-hold',type=int,default=60)
 p.add_argument('--cost-bps',type=float,default=35)
 p.add_argument('--min-turnover',type=float,default=500_000_000)
 a=p.parse_args()
 if a.max_hold<10 or a.cost_bps<0 or a.min_turnover<0:p.error('invalid configuration')
 run(a)
if __name__=='__main__': main()
