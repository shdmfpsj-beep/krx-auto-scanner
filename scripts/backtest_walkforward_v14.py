"""C3 v1.8 exploratory walk-forward backtest. NOT a PIT universe; NOT live trading.

Uses a current KRX listing (survivorship bias), past-only signals, next-session
open entry, and an explicitly defined 3-session holding period. Prices may be
adjusted and are not guaranteed executable historical quotes.
"""
import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import FinanceDataReader as fdr
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[1] / 'reports'
OUT.mkdir(parents=True, exist_ok=True)


def universe(limit):
    x = fdr.StockListing('KRX').copy()
    x = x[x['Market'].astype(str).str.upper().isin(['KOSPI', 'KOSDAQ'])]
    x['Code'] = x['Code'].astype(str).str.zfill(6)
    x['Name'] = x['Name'].astype(str)
    excluded = r'(스팩|SPAC|우B?$|우C$|우\d|우선주|리츠|REIT|ETF|ETN|인버스|레버리지)'
    x = x[~x['Name'].str.contains(excluded, case=False, regex=True, na=False)]
    x = x[x['Code'].str.fullmatch(r'\d{6}')].drop_duplicates('Code').sort_values('Code')
    return x[['Code', 'Name', 'Market']].head(limit) if limit > 0 else x[['Code', 'Name', 'Market']]


def prices(code, start, end):
    x = fdr.DataReader(code, start, end)
    required = ['Open', 'High', 'Low', 'Close', 'Volume']
    if x is None or x.empty or not set(required).issubset(x.columns):
        return None
    x = x[required].copy()
    x.index = pd.to_datetime(x.index).normalize()
    x = x[~x.index.duplicated(keep='last')].sort_index()
    for c in required:
        x[c] = pd.to_numeric(x[c], errors='coerce')
    # Keep zero-volume rows to audit non-tradable intervals.
    x = x.dropna()
    x = x[(x[['Open', 'High', 'Low', 'Close']] > 0).all(axis=1)]
    return x if int((x.Volume > 0).sum()) >= 130 else None


def indicators(x):
    y = x.copy()
    y['ma20'] = y.Close.rolling(20).mean()
    y['ma60'] = y.Close.rolling(60).mean()
    y['ma120'] = y.Close.rolling(120).mean()
    y['rvol20'] = y.Volume / y.Volume.shift(1).rolling(20).mean().replace(0, np.nan)
    y['prev_high20'] = y.High.shift(1).rolling(20).max()
    y['ret20'] = y.Close.pct_change(20)
    trend = (y.Close > y.ma20) & (y.ma20 > y.ma60) & (y.ma60 > y.ma120)
    y['breakout'] = trend & (y.Close > y.prev_high20) & (y.rvol20 >= 1.5)
    y['pullback'] = trend & (y.Low <= y.ma20 * 1.02) & (y.Close >= y.ma20) & (y.Close > y.Open) & (y.rvol20 >= 0.8)
    y['signal'] = y.breakout | y.pullback
    y['score'] = (4 * y.breakout.astype(int) + 3 * y.pullback.astype(int)
                  + 2 * trend.astype(int) + y.rvol20.clip(0, 5).fillna(0)
                  + 10 * y.ret20.clip(-0.2, 0.3).fillna(0))
    return y


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--limit', type=int, default=30)
    p.add_argument('--start', default='2025-01-01')
    p.add_argument('--end', default='2025-12-31')
    p.add_argument('--hold', type=int, default=3)
    p.add_argument('--cost-bps', type=float, default=15)
    p.add_argument('--capital', type=float, default=300000)
    a = p.parse_args()
    if a.hold < 1 or a.capital <= 0 or a.cost_bps < 0:
        raise ValueError('Invalid hold/capital/cost')
    start, end = pd.Timestamp(a.start), pd.Timestamp(a.end)
    if start > end:
        raise ValueError('start after end')
    lookback = (start - pd.Timedelta(days=270)).strftime('%Y-%m-%d')
    fetch_end = (end + pd.Timedelta(days=45)).strftime('%Y-%m-%d')
    names = universe(a.limit)
    book, signals, failures = {}, [], []
    for i, (code, name, market) in enumerate(names.itertuples(index=False, name=None), 1):
        try:
            x = prices(code, lookback, fetch_end)
            if x is None:
                failures.append({'ticker': code, 'reason': 'missing/insufficient OHLCV'})
                continue
            book[code] = {'name': name, 'market': market, 'data': x}
            # Preserve v1.6 signal calculations: zero-volume sessions are excluded.
            y = indicators(x[x.Volume > 0])
            for dt, r in y.loc[start:end].iterrows():
                if bool(r.signal):
                    signals.append({'date': dt, 'ticker': code, 'name': name,
                                    'setup': 'breakout' if r.breakout else 'pullback',
                                    'score': float(r.score), 'rvol20': float(r.rvol20)})
        except Exception as exc:
            failures.append({'ticker': code, 'reason': str(exc)[:180]})
        if i % 10 == 0:
            print(f'Fetched {i}/{len(names)}', flush=True)
        time.sleep(0.12)
    if not book:
        raise RuntimeError('No valid OHLCV')

    sig = pd.DataFrame(signals, columns=['date', 'ticker', 'name', 'setup', 'score', 'rvol20'])
    if not sig.empty:
        sig = sig.sort_values(['date', 'score', 'rvol20', 'ticker'], ascending=[True, False, False, True])
    grouped = dict(tuple(sig.groupby('date'))) if not sig.empty else {}
    calendar = sorted(set().union(*(set(v['data'].index) for v in book.values())))
    calendar = [d for d in calendar if start <= d <= end + pd.Timedelta(days=45)]
    calendar_index = {d: i for i, d in enumerate(calendar)}

    nontradable = []
    for code, item in book.items():
        df = item['data']
        zero = df[(df.Volume <= 0) & (df.index >= start) & (df.index <= end)]
        for dt, row in zero.iterrows():
            nontradable.append({'date': str(dt.date()), 'ticker': code,
                                'reason': 'zero_volume', 'reference_close': float(row.Close)})

    def simulate(scenario):
        cash, position, pending = float(a.capital), None, None
        trades, daily, delayed = [], [], []
        snapshot = None
        for day in calendar:
            exit_at_close = False
            if position is not None and day >= position['target_exit_day']:
                code = position['ticker']
                x = book[code]['data']
                if day in x.index and float(x.at[day, 'Volume']) > 0:
                    was_delayed = day > position['target_exit_day']
                    # The scenario applies ONLY to delayed/reopening exits.
                    # Close/low scenarios settle at end-of-day, not at the open.
                    field = ('Open' if not was_delayed or scenario == 'open' else
                             'Close' if scenario == 'close' else 'Low')
                    px = float(x.at[day, field])
                    proceeds = position['shares'] * px * (1 - a.cost_bps / 10000)
                    cash += proceeds
                    trades.append({**{k: position[k] for k in
                                      ('signal_date','entry_date','ticker','name','setup','score','shares','entry_price')},
                                   'target_exit_date': str(position['target_exit_day'].date()),
                                   'exit_date': str(day.date()), 'exit_price': px,
                                   'exit_price_basis': field.lower(),
                                   'exit_delayed': was_delayed,
                                   'pnl_krw': proceeds - position['total_entry_cost'],
                                   'net_return': proceeds / position['total_entry_cost'] - 1})
                    if was_delayed:
                        delayed.append({'ticker': code, 'target_exit_date': str(position['target_exit_day'].date()),
                                        'actual_exit_date': str(day.date()), 'exit_price_basis': field.lower(),
                                        'shares': position['shares'], 'exit_price': px})
                    position = None
                    exit_at_close = was_delayed and scenario != 'open'
            # Orders from yesterday's close can execute at today's open, but not
            # when a delayed exit is executed at today's close/low proxy.
            if position is None and pending is not None:
                if day == pending['entry_day']:
                    if not exit_at_close:
                        for _, cand in pending['group'].iterrows():
                            code = cand['ticker']
                            x = book[code]['data']
                            if day not in x.index or float(x.at[day, 'Volume']) <= 0:
                                continue
                            px = float(x.at[day, 'Open'])
                            shares = int(cash // (px * (1 + a.cost_bps / 10000)))
                            if shares < 1:
                                continue
                            idx = calendar_index[day]
                            target_idx = idx + a.hold
                            if target_idx >= len(calendar):
                                continue
                            cost = shares * px * (1 + a.cost_bps / 10000)
                            cash -= cost
                            position = {'ticker': code, 'name': cand['name'], 'setup': cand['setup'],
                                        'score': float(cand['score']), 'signal_date': str(pending['signal_day'].date()),
                                        'entry_date': str(day.date()), 'entry_price': px, 'shares': shares,
                                        'total_entry_cost': cost, 'target_exit_day': calendar[target_idx]}
                            break
                    pending = None
                elif day > pending['entry_day']:
                    pending = None
            equity = cash
            if position is not None:
                x = book[position['ticker']]['data']
                prior = x.loc[:day, 'Close']
                mark = float(prior.iloc[-1]) if not prior.empty else position['entry_price']
                equity += position['shares'] * mark
            if start <= day <= end:
                daily.append({'date': str(day.date()), 'equity': equity, 'cash': cash,
                              'ticker': position['ticker'] if position else ''})
                snapshot = {'cash': cash, 'equity': equity,
                            'position': position.copy() if position else None}
            if position is None and pending is None and day in grouped:
                idx = calendar_index[day]
                if idx + 1 < len(calendar):
                    pending = {'signal_day': day, 'entry_day': calendar[idx + 1], 'group': grouped[day]}
        td = pd.DataFrame(trades)
        ed = pd.DataFrame(daily)
        eq = ed.equity.to_numpy(dtype=float)
        peaks = np.maximum.accumulate(np.r_[float(a.capital), eq])[1:]
        period_return = float(eq[-1] / a.capital - 1)
        mdd = float(np.min(eq / peaks - 1))
        in_period = td[td.exit_date <= str(end.date())] if not td.empty else td
        realized = float(in_period.pnl_krw.sum()) if not in_period.empty else 0.0
        snap = snapshot or {'cash': a.capital, 'equity': a.capital, 'position': None}
        open_cost = float(snap['position']['total_entry_cost']) if snap['position'] else 0.0
        unrealized = float(snap['equity'] - snap['cash'] - open_cost)
        delta = float(snap['equity'] - (a.capital + realized + unrealized))
        if abs(delta) >= 0.02:
            raise RuntimeError(f'{scenario} accounting mismatch: {delta}')
        return ({'scenario': scenario, 'period_return': period_return, 'daily_mdd': mdd,
                 'period_end_equity': float(snap['equity']), 'period_realized_pnl': realized,
                 'period_unrealized_pnl': unrealized, 'accounting_delta': delta,
                 'completed_trades': len(td), 'delayed_exit_count': len(delayed),
                 'open_position_at_period_end': bool(snap['position'])}, td, ed, delayed)

    results = {}
    for scenario in ('open', 'close', 'low'):
        result, trades, equity, delayed = simulate(scenario)
        results[scenario] = result
        trades.to_csv(OUT / f'walkforward_v18_{scenario}_trades.csv', index=False, encoding='utf-8-sig')
        equity.to_csv(OUT / f'walkforward_v18_{scenario}_equity.csv', index=False, encoding='utf-8-sig')
        pd.DataFrame(delayed).to_csv(OUT / f'walkforward_v18_{scenario}_reopenings.csv', index=False, encoding='utf-8-sig')
    summary = {'version': 'C3 v1.8', 'run_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
               'survivorship_bias': True, 'point_in_time_universe': False,
               'live_trade_approval': False, 'initial_capital': a.capital,
               'requested_universe': len(names), 'downloaded_universe': len(book),
               'fetch_failures': len(failures), 'signal_count': len(sig),
               'holding_sessions': a.hold, 'cost_bps_each_side': a.cost_bps,
               'zero_volume_ticker_days': len(nontradable), 'scenarios': results,
               'warnings': [
                   'Current KRX universe: survivorship bias, not historical PIT',
                   'Adjusted historical OHLCV may not be executable prices',
                   'Reopening CLOSE assumes exit at closing price; execution not guaranteed',
                   'Reopening LOW is an adverse sensitivity proxy, NOT a tradable fill',
                   'Reopening scenario is applied only to delayed exits',
                   'Shared-calendar session count and imperfect common-stock filter remain',
                   'No market impact, taxes, true halt records, or corporate-action model',
               ]}
    (OUT / 'walkforward_v18_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    pd.DataFrame(nontradable).to_csv(OUT / 'walkforward_v18_nontradable.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(failures).to_csv(OUT / 'walkforward_v18_failures.csv', index=False, encoding='utf-8-sig')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
