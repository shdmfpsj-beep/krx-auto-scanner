"""C3 v1.7 exploratory walk-forward backtest. NOT a PIT universe; NOT live trading.

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

    cash, position, pending = float(a.capital), None, None
    trades, daily, skipped, nontradable, reopenings = [], [], [], [], []
    end_snapshot = None
    for code, item in book.items():
        df = item['data']
        zero = df[(df.Volume <= 0) & (df.index >= start) & (df.index <= end)]
        for dt, row in zero.iterrows():
            nontradable.append({'date': str(dt.date()), 'ticker': code, 'name': item['name'],
                                'reason': 'zero_volume', 'reference_close': float(row.Close)})
    for day in calendar:
        # A position is exited on the first actual observed open ON/AFTER its
        # target calendar date; an abnormal delay is logged, never hidden.
        if position is not None and day >= position['target_exit_day']:
            code = position['ticker']
            x = book[code]['data']
            if day in x.index and float(x.at[day, 'Volume']) > 0:
                px = float(x.at[day, 'Open'])
                if day > position['target_exit_day']:
                    reopenings.append({'ticker': code, 'entry_date': position['entry_date'],
                                       'target_exit_date': str(position['target_exit_day'].date()),
                                       'actual_exit_date': str(day.date()),
                                       'open': px, 'low': float(x.at[day, 'Low']),
                                       'close': float(x.at[day, 'Close']),
                                       'volume': float(x.at[day, 'Volume']),
                                       'shares': position['shares'],
                                       'open_exit_pnl_krw': position['shares'] * px * (1 - a.cost_bps / 10000) - position['total_entry_cost'],
                                       'close_exit_pnl_krw_scenario': position['shares'] * float(x.at[day, 'Close']) * (1 - a.cost_bps / 10000) - position['total_entry_cost'],
                                       'low_exit_pnl_krw_scenario': position['shares'] * float(x.at[day, 'Low']) * (1 - a.cost_bps / 10000) - position['total_entry_cost']})
                proceeds = position['shares'] * px * (1 - a.cost_bps / 10000)
                cash += proceeds
                if day > position['target_exit_day']:
                    skipped.append({'date': str(day.date()), 'ticker': code,
                                    'reason': 'delayed_exit_nontradable_or_missing_quote',
                                    'target_exit_day': str(position['target_exit_day'].date())})
                trades.append({**{k: position[k] for k in
                                  ('signal_date', 'entry_date', 'ticker', 'name', 'setup',
                                   'score', 'shares', 'entry_price')},
                               'target_exit_date': str(position['target_exit_day'].date()),
                               'exit_date': str(day.date()), 'exit_price': px,
                               'gross_return': px / position['entry_price'] - 1,
                               'net_return': proceeds / position['total_entry_cost'] - 1,
                               'pnl_krw': proceeds - position['total_entry_cost'],
                               'exit_delayed': day > position['target_exit_day']})
                position = None
            else:
                skipped.append({'date': str(day.date()), 'ticker': code,
                                'reason': 'exit_zero_volume' if day in x.index else 'exit_open_missing'})

        if position is None and pending is not None:
            if day == pending['entry_day']:
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
                        skipped.append({'date': str(day.date()), 'ticker': code,
                                        'reason': 'no_exit_calendar'})
                        continue
                    entry_cost = shares * px * (1 + a.cost_bps / 10000)
                    cash -= entry_cost
                    position = {'ticker': code, 'name': cand['name'], 'setup': cand['setup'],
                                'score': float(cand['score']),
                                'signal_date': str(pending['signal_day'].date()),
                                'entry_date': str(day.date()), 'entry_price': px,
                                'shares': shares, 'total_entry_cost': entry_cost,
                                'target_exit_day': calendar[target_idx]}
                    break
                pending = None
            elif day > pending['entry_day']:
                pending = None

        equity = cash
        if position is not None:
            x = book[position['ticker']]['data']
            available = x.loc[:day, 'Close']
            mark = float(available.iloc[-1]) if not available.empty else position['entry_price']
            if day not in x.index or float(x.at[day, 'Volume']) <= 0:
                skipped.append({'date': str(day.date()), 'ticker': position['ticker'],
                                'reason': 'zero_volume_mark' if day in x.index else 'stale_mark'})
            equity += position['shares'] * mark
        if start <= day <= end:
            daily.append({'date': str(day.date()), 'equity': equity, 'cash': cash,
                          'ticker': position['ticker'] if position else ''})
            end_snapshot = {'date': str(day.date()), 'cash': cash,
                            'equity': equity, 'position': position.copy() if position else None}
        if position is None and pending is None and day in grouped:
            idx = calendar_index[day]
            if idx + 1 < len(calendar):
                pending = {'signal_day': day, 'entry_day': calendar[idx + 1],
                           'group': grouped[day]}

    trade_df = pd.DataFrame(trades)
    daily_df = pd.DataFrame(daily)
    if not daily_df.empty:
        eq = daily_df.equity.to_numpy(dtype=float)
        peaks = np.maximum.accumulate(np.r_[float(a.capital), eq])[1:]
        mdd = float(np.min(eq / peaks - 1))
        period_return = float(eq[-1] / a.capital - 1)
    else:
        mdd, period_return = None, None

    by_setup = {}
    if not trade_df.empty:
        for setup, g in trade_df.groupby('setup'):
            by_setup[setup] = {'trades': len(g), 'win_rate': float((g.net_return > 0).mean()),
                               'avg_net_return': float(g.net_return.mean()),
                               'total_pnl_krw': float(g.pnl_krw.sum())}

    # Reconcile the account AT THE PERIOD END. Later exits are deliberately
    # excluded from period P&L; they remain visible in the complete trade log.
    period_trades = trade_df[trade_df.exit_date <= str(end.date())] if not trade_df.empty else trade_df
    realized = float(period_trades.pnl_krw.sum()) if not period_trades.empty else 0.0
    snapshot = end_snapshot or {'cash': a.capital, 'equity': a.capital, 'position': None}
    open_cost = float(snapshot['position']['total_entry_cost']) if snapshot['position'] else 0.0
    unrealized = float(snapshot['equity'] - snapshot['cash'] - open_cost)
    reconcile_delta = float(snapshot['equity'] - (a.capital + realized + unrealized))
    reconciliation_ok = abs(reconcile_delta) < 0.02
    if not reconciliation_ok:
        raise RuntimeError(f'Accounting reconciliation failed: {reconcile_delta:.6f} KRW')

    summary = {
        'version': 'C3 v1.7', 'run_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        'survivorship_bias': True, 'point_in_time_universe': False,
        'live_trade_approval': False,
        'universe_source': 'FDR current KRX; imperfect name filter',
        'requested_universe': len(names), 'downloaded_universe': len(book),
        'fetch_failures': len(failures), 'signal_count': len(sig),
        'completed_trades_including_post_period': len(trade_df),
        'completed_trades_within_period': len(period_trades),
        'initial_capital': a.capital, 'holding_sessions': a.hold,
        'holding_definition': 'entry open to open after 3 shared-calendar sessions; zero-volume days cannot execute',
        'cost_bps_each_side': a.cost_bps,
        'period_return_mark_to_market': period_return,
        'daily_equity_mdd': mdd, 'by_setup_all_completed_trades': by_setup,
        'period_end_cash': float(snapshot['cash']),
        'period_end_equity': float(snapshot['equity']),
        'period_realized_pnl_krw': realized,
        'period_unrealized_pnl_krw': unrealized,
        'accounting_reconciliation_delta_krw': reconcile_delta,
        'accounting_reconciliation_ok': reconciliation_ok,
        'open_position_at_period_end': bool(snapshot['position']),
        'open_position_after_extended_simulation': bool(position),
        'delayed_exit_count': int(trade_df.exit_delayed.sum()) if not trade_df.empty else 0,
        'skipped_events': len(skipped),
        'zero_volume_ticker_days': len(nontradable),
        'reopening_exit_events': len(reopenings),
        'reopening_exit_scenarios_are_not_executable_fills': True,
        'warnings': [
            'NOT a historical point-in-time universe; survivorship bias',
            'Historical adjusted OHLCV may not represent executable prices',
            'Shared calendar may include non-common trading days',
            'Zero-volume sessions are non-tradable and may delay exits',
            'Reopening close/low P&L are sensitivity scenarios, NOT guaranteed executable fills',
            'No realistic tax, market impact, trading halt or corporate action model',
            'Period returns exclude exits after end date; full trade log includes them',
        ],
    }
    (OUT / 'walkforward_v17_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    sig.to_csv(OUT / 'walkforward_v17_candidates.csv', index=False, encoding='utf-8-sig')
    trade_df.to_csv(OUT / 'walkforward_v17_trades.csv', index=False, encoding='utf-8-sig')
    daily_df.to_csv(OUT / 'walkforward_v17_equity.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(failures).to_csv(OUT / 'walkforward_v17_failures.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(skipped).to_csv(OUT / 'walkforward_v17_skipped.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(nontradable, columns=['date','ticker','name','reason','reference_close']).to_csv(OUT / 'walkforward_v17_nontradable.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(reopenings, columns=['ticker','entry_date','target_exit_date','actual_exit_date','open','low','close','volume','shares','open_exit_pnl_krw','close_exit_pnl_krw_scenario','low_exit_pnl_krw_scenario']).to_csv(OUT / 'walkforward_v17_reopenings.csv', index=False, encoding='utf-8-sig')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
