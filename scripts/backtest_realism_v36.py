"""C3 v3.6 research-only daily OHLCV one-position replay.
Usage: python scripts/backtest_realism_v36.py
Requires reports/entry_v32_paired_trades.csv and FinanceDataReader.
NOT point-in-time universe; never use for live trade approval.
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'
CACHE = REPORTS / 'v36_ohlcv_cache'


def load_signals(path):
    raw = pd.read_csv(path, dtype={'ticker': str, 'signal_id': str})
    needed = {'signal_id','ticker','signal_date','entry_date','entry_open','hold',
              'setup','ma_rising','ret60','distance_ma20','rvol20','ret20'}
    if missing := needed - set(raw.columns):
        raise ValueError(f'Missing columns: {sorted(missing)}')
    x = raw.loc[raw.hold.eq(1)].copy()
    if x.empty:
        raise ValueError('No hold=1 signal rows')
    if x.signal_id.duplicated().any():
        raise ValueError('Duplicate signal ids')
    for col in ('signal_date','entry_date'):
        x[col] = pd.to_datetime(x[col], errors='raise').dt.normalize()
    for col in ('entry_open','ret60','distance_ma20','rvol20','ret20'):
        x[col] = pd.to_numeric(x[col], errors='coerce')
    x['ma_rising'] = x.ma_rising.astype(str).str.lower().eq('true')
    x['improved'] = (x.setup.eq('breakout') & x.ma_rising &
                     x.ret60.lt(.60) & x.distance_ma20.lt(.15))
    x = x.loc[(x.entry_open > 0) & (x.signal_date < x.entry_date)].copy()
    # Ranking inputs only use signal-day factors; no realized outcome is used.
    x['rank_score'] = (np.clip(x.rvol20.fillna(0), 0, 5) * 2 +
                       np.clip(x.ret20.fillna(0), -.5, .5) * 4 -
                       np.clip(x.distance_ma20.fillna(0), -.5, .5) * 2)
    return x.sort_values(['entry_date','signal_id'], kind='stable')


def history(ticker, start, end, refresh=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f'{ticker}.csv'
    if path.exists() and not refresh:
        d = pd.read_csv(path, parse_dates=['Date']).set_index('Date')
    else:
        d = fdr.DataReader(ticker, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
        if d.empty:
            raise ValueError('No OHLCV')
        d.index = pd.to_datetime(d.index).normalize()
        d.index.name = 'Date'
        d.to_csv(path)
        time.sleep(.08)
    for col in ('Open','High','Low','Close','Volume'):
        if col not in d:
            raise ValueError(f'Missing {col}')
        d[col] = pd.to_numeric(d[col], errors='coerce')
    d = d.sort_index()
    return d.loc[(d.index >= start) & (d.index <= end)]


def validate_history(d):
    if d.empty or d.index.has_duplicates:
        return False
    v = d[['Open','High','Low','Close']]
    return bool(v.notna().all().all() and (v > 0).all().all() and
                (d.High >= d[['Open','Close','Low']].max(axis=1)).all() and
                (d.Low <= d[['Open','Close','High']].min(axis=1)).all())


def replay(signals, bars, capital, strategy, hold, selection, stop_pct,
           take_pct, cost_bps, slip_bps):
    eligible = signals if strategy == 'A_baseline' else signals.loc[signals.improved]
    if selection == 'factor_rank':
        eligible = eligible.sort_values(['entry_date','rank_score','ticker'],
                                        ascending=[True,False,True], kind='stable')
    else:
        eligible = eligible.sort_values(['entry_date','ticker'], kind='stable')
    dates = sorted(set().union(*(set(d.index) for d in bars.values())))
    if not dates:
        return None, [], []
    groups = {k:v for k,v in eligible.groupby('entry_date', sort=False)}
    cash = float(capital)
    position = None
    ledger, trades = [], []
    skipped_missing = 0
    buy_mult = 1 + slip_bps / 10000
    sell_mult = 1 - slip_bps / 10000
    fee_rate = cost_bps / 20000  # half the round-trip rate per side
    for dt in dates:
        # Exit before entering new positions, allowing same-day re-entry at open
        # ONLY if an existing position exits at the open (time-exit). Intraday
        # exits cannot free cash for an already-passed opening auction.
        exited_open = False
        if position is not None:
            p = position
            d = bars[p['ticker']]
            if dt in d.index and dt > p['entry_date']:
                candle = d.loc[dt]
                age = d.index.get_loc(dt) - d.index.get_loc(p['entry_date'])
                op, hi, lo = (float(candle[k]) for k in ('Open','High','Low'))
                stop_price = p['entry_fill'] * (1 - stop_pct)
                take_price = p['entry_fill'] * (1 + take_pct)
                exit_price, reason = None, None
                if op <= stop_price:
                    exit_price, reason = op, 'stop_gap'
                elif op >= take_price:
                    exit_price, reason = op, 'take_gap'
                elif age >= hold:
                    exit_price, reason = op, 'time_open'
                elif lo <= stop_price:
                    exit_price, reason = stop_price, 'stop_intraday'
                elif hi >= take_price:
                    exit_price, reason = take_price, 'take_intraday'
                if exit_price is not None:
                    exit_fill = exit_price * sell_mult
                    proceeds = p['shares'] * exit_fill * (1 - fee_rate)
                    cash += proceeds
                    trades.append({'strategy':strategy,'selection':selection,'hold':hold,
                                   'capital':capital,'ticker':p['ticker'],
                                   'signal_id':p['signal_id'],
                                   'entry_date':p['entry_date'].date().isoformat(),
                                   'exit_date':dt.date().isoformat(),
                                   'entry_fill':p['entry_fill'],'exit_fill':exit_fill,
                                   'shares':p['shares'],'exit_reason':reason,
                                   'net_pnl':proceeds-p['total_entry_cost'],
                                   'net_return_pct':100*(proceeds/p['total_entry_cost']-1)})
                    position = None
                    exited_open = reason in ('time_open','stop_gap','take_gap')
        if position is None and (dt in groups) and (not trades or trades[-1]['exit_date'] != dt.date().isoformat() or exited_open):
            # If we just exited intraday, the day's open cannot be traded again.
            for _, sig in groups[dt].iterrows():
                d = bars.get(sig.ticker)
                if d is None or dt not in d.index:
                    skipped_missing += 1
                    continue
                op = float(d.loc[dt,'Open'])
                # Historical adjusted OHLCV may disagree with cached entry-open;
                # refuse mismatched records instead of silently using bad prices.
                if abs(op / float(sig.entry_open) - 1) > .03:
                    skipped_missing += 1
                    continue
                fill = op * buy_mult
                shares = int(cash // (fill * (1 + fee_rate)))
                if shares < 1:
                    continue
                total = shares * fill * (1 + fee_rate)
                cash -= total
                position = {'ticker':sig.ticker,'signal_id':sig.signal_id,
                            'entry_date':dt,'entry_fill':fill,'shares':shares,
                            'total_entry_cost':total}
                break
        if position is None:
            equity = cash
        else:
            d = bars[position['ticker']]
            last = d.loc[:dt]
            px = float(last.iloc[-1]['Close']) if not last.empty else position['entry_fill']
            equity = cash + position['shares'] * px * sell_mult * (1 - fee_rate)
        ledger.append({'date':dt.date().isoformat(),'strategy':strategy,
                       'selection':selection,'hold':hold,'capital':capital,
                       'equity':equity,'cash':cash,
                       'ticker':position['ticker'] if position else ''})
    # Open positions are marked to market, not counted as realized trades.
    vals = np.asarray([a['equity'] for a in ledger], dtype=float)
    peaks = np.maximum.accumulate(vals)
    mdd = 100 * np.min(vals / peaks - 1)
    years = max((dates[-1] - dates[0]).days / 365.25, 1e-9)
    summary = {'strategy':strategy,'selection':selection,'hold':hold,
               'capital':capital,'stop_pct':stop_pct,'take_pct':take_pct,
               'trades_closed':len(trades),'open_position':bool(position),
               'skipped_missing_or_price_mismatch':skipped_missing,
               'total_return_pct':100*(vals[-1]/capital-1),
               'cagr_pct':100*((vals[-1]/capital)**(1/years)-1) if vals[-1]>0 else None,
               'daily_close_mdd_pct':mdd,
               'win_rate_pct':100*np.mean([t['net_pnl']>0 for t in trades]) if trades else None,
               'ending_equity':vals[-1]}
    return summary, trades, ledger


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input',default=str(REPORTS/'entry_v32_paired_trades.csv'))
    p.add_argument('--capitals',default='300000,500000,1000000,3000000,10000000')
    p.add_argument('--holds',default='5,10,15,20')
    p.add_argument('--stop-pct',type=float,default=.07)
    p.add_argument('--take-pct',type=float,default=.15)
    p.add_argument('--cost-bps',type=float,default=15)
    p.add_argument('--slip-bps',type=float,default=10)
    p.add_argument('--refresh-cache',action='store_true')
    p.add_argument('--max-tickers',type=int,default=0,help='Research smoke-test only; 0=all')
    args=p.parse_args()
    if not (0 < args.stop_pct < 1 and 0 < args.take_pct < 5 and
            0 <= args.cost_bps < 1000 and 0 <= args.slip_bps < 1000):
        p.error('Invalid stop/take/cost/slippage')
    capitals=[int(i) for i in args.capitals.split(',')]
    holds=[int(i) for i in args.holds.split(',')]
    if not capitals or min(capitals)<=0 or not holds or min(holds)<=0:
        p.error('Invalid capital/hold')
    x=load_signals(Path(args.input))
    tickers=sorted(x.ticker.unique())
    if args.max_tickers:
        tickers=tickers[:args.max_tickers]
        x=x.loc[x.ticker.isin(tickers)].copy()
    start=x.entry_date.min()-pd.Timedelta(days=10)
    end=x.entry_date.max()+pd.Timedelta(days=max(60,max(holds)*3))
    bars, errors={},[]
    for i,ticker in enumerate(tickers,1):
        try:
            d=history(ticker,start,end,args.refresh_cache)
            if not validate_history(d):
                raise ValueError('OHLCV integrity failure')
            bars[ticker]=d
        except Exception as e:
            errors.append({'ticker':ticker,'error':str(e)[:200]})
        if i%20==0:
            print(f'OHLCV {i}/{len(tickers)} valid={len(bars)} failed={len(errors)}',flush=True)
    if len(bars)<max(1,int(len(tickers)*.90)):
        raise SystemExit(f'Insufficient OHLCV coverage: {len(bars)}/{len(tickers)}; refusing misleading report')
    summaries,trades,equities=[],[],[]
    for hold in holds:
        for capital in capitals:
            for strat in ('A_baseline','B_improved'):
                for policy in ('ticker_ascending','factor_rank'):
                    result,ts,eq=replay(x,bars,capital,strat,hold,policy,
                                        args.stop_pct,args.take_pct,args.cost_bps,args.slip_bps)
                    if result:
                        summaries.append(result);trades.extend(ts);equities.extend(eq)
    REPORTS.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(summaries).to_csv(REPORTS/'realism_v36_summary.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(trades).to_csv(REPORTS/'realism_v36_trades.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(equities).to_csv(REPORTS/'realism_v36_daily_equity.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(errors,columns=['ticker','error']).to_csv(REPORTS/'realism_v36_failures.csv',index=False,encoding='utf-8-sig')
    meta={'version':'C3 v3.6 daily OHLCV research','run_kst':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
          'signals':len(x),'tickers_requested':len(tickers),'tickers_valid':len(bars),
          'scenarios':len(summaries),'stop_pct':args.stop_pct,'take_pct':args.take_pct,
          'cost_bps_round_trip':args.cost_bps,'slip_bps_each_side':args.slip_bps,
          'live_trade_approval':False,
          'warnings':['Current-listed universe and current cap tier: survivorship/lookahead selection bias.',
                      '2023-2025 already inspected; not out-of-sample.',
                      'Daily OHLCV may be adjusted and inconsistent with original historical trade prices.',
                      'Intraday stop and take prices are assumptions; when both touched stop takes priority.',
                      'Opening gap executes at opening price; no guaranteed stop fills.',
                      'Close-marked daily MDD ignores intraday equity troughs.',
                      'Factor rank is an experimental proxy, NOT production C3 score.',
                      'No bid/ask, market impact, halt, liquidity, tax or exchange price limit simulation.',
                      'Missing/invalid histories are excluded; review failure report.']}
    (REPORTS/'realism_v36_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'C3 v3.6 complete: {len(summaries)} scenarios; {len(trades)} trades; {len(errors)} failed tickers')


if __name__=='__main__':
    main()
