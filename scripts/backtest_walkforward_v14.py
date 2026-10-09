"""C3 v1.5 exploratory walk-forward backtest (NOT PIT universe)."""
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

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports'
OUT.mkdir(parents=True, exist_ok=True)


def universe(limit):
    x = fdr.StockListing('KRX').copy()
    x = x[x['Market'].astype(str).str.upper().isin(['KOSPI', 'KOSDAQ'])]
    x['Code'] = x['Code'].astype(str).str.zfill(6)
    x['Name'] = x['Name'].astype(str)
    # Conservative name filter; classification is imperfect.
    excluded = r'(스팩|SPAC|우B?$|우C$|우\d|우선주|리츠|REIT|ETF|ETN|인버스|레버리지)'
    x = x[~x['Name'].str.contains(excluded, case=False, regex=True, na=False)]
    x = x[x['Code'].str.fullmatch(r'\d{6}')]
    x = x.drop_duplicates('Code').sort_values('Code')
    return x[['Code', 'Name', 'Market']].head(limit) if limit > 0 else x[['Code', 'Name', 'Market']]


def prices(code, start, end):
    x = fdr.DataReader(code, start, end)
    if x is None or x.empty or not {'Open', 'High', 'Low', 'Close', 'Volume'}.issubset(x.columns):
        return None
    x = x[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    x.index = pd.to_datetime(x.index).normalize()
    x = x[~x.index.duplicated(keep='last')].sort_index()
    for c in x.columns:
        x[c] = pd.to_numeric(x[c], errors='coerce')
    x = x.dropna()
    x = x[(x[['Open', 'High', 'Low', 'Close']] > 0).all(axis=1) & (x['Volume'] > 0)]
    return x if len(x) >= 130 else None


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
        raise ValueError('Invalid hold, capital or cost-bps')
    start, end = pd.Timestamp(a.start), pd.Timestamp(a.end)
    if start > end:
        raise ValueError('start after end')
    lookback = (start - pd.Timedelta(days=270)).strftime('%Y-%m-%d')
    fetch_end = (end + pd.Timedelta(days=35)).strftime('%Y-%m-%d')
    names = universe(a.limit)
    book, signals, failures = {}, [], []
    for i, row in enumerate(names.itertuples(index=False), 1):
        code, name, market = row
        try:
            x = prices(code, lookback, fetch_end)
            if x is None:
                failures.append({'ticker': code, 'reason': 'missing/insufficient OHLCV'})
                continue
            book[code] = {'name': name, 'market': market, 'data': x}
            y = indicators(x)
            for dt, r in y.loc[start:end].iterrows():
                if not bool(r.signal):
                    continue
                signals.append({'date': dt, 'ticker': code, 'name': name,
                                'setup': 'breakout' if r.breakout else 'pullback',
                                'score': float(r.score), 'rvol20': float(r.rvol20)})
        except Exception as e:
            failures.append({'ticker': code, 'reason': str(e)[:180]})
        if i % 10 == 0:
            print(f'Fetched {i}/{len(names)}', flush=True)
        time.sleep(0.12)
    if not book:
        raise RuntimeError('No valid OHLCV downloaded')

    sig = pd.DataFrame(signals, columns=['date', 'ticker', 'name', 'setup', 'score', 'rvol20'])
    if not sig.empty:
        sig = sig.sort_values(['date', 'score', 'rvol20', 'ticker'], ascending=[True, False, False, True])
    grouped = {dt: g for dt, g in sig.groupby('date')} if not sig.empty else {}
    # Signal calendar: union of observed trading dates; no same-day signal execution.
    calendar = sorted(set().union(*(set(v['data'].index) for v in book.values())))
    calendar = [d for d in calendar if start <= d <= end + pd.Timedelta(days=35)]
    calendar_index = {d: i for i, d in enumerate(calendar)}
    cash = float(a.capital)
    position = None
    pending = None
    trades = []
    daily = []
    skipped = []
    for day in calendar:
        # Close position at open after exactly `hold` trading sessions including entry day.
        if position and day >= position['exit_day']:
            code = position['ticker']
            x = book[code]['data']
            if day in x.index and x.at[day, 'Open'] > 0:
                px = float(x.at[day, 'Open'])
                proceeds = position['shares'] * px * (1 - a.cost_bps / 10000)
                cash += proceeds
                gross = px / position['entry_price'] - 1
                net = proceeds / position['total_entry_cost'] - 1
                trades.append({**{k: position[k] for k in ('signal_date','entry_date','ticker','name','setup','score','shares','entry_price')},
                               'exit_date': str(day.date()), 'exit_price': px,
                               'gross_return': gross, 'net_return': net,
                               'pnl_krw': proceeds - position['total_entry_cost']})
                position = None
            else:
                # Missing exit quote: retain position and flag it, never fabricate a fill.
                skipped.append({'date': str(day.date()), 'ticker': code, 'reason': 'exit_open_missing'})
        # Pending order from previous signal; try ranked candidates at today's open.
        if position is None and pending is not None:
            if day == pending['entry_day']:
                for _, cand in pending['group'].iterrows():
                    code = cand.ticker
                    x = book[code]['data']
                    if day not in x.index:
                        continue
                    px = float(x.at[day, 'Open'])
                    if px <= 0:
                        continue
                    shares = int(cash // (px * (1 + a.cost_bps / 10000)))
                    if shares < 1:
                        continue
                    entry_cost = shares * px * (1 + a.cost_bps / 10000)
                    cash -= entry_cost
                    idx = calendar_index[day]
                    exit_idx = idx + a.hold
                    if exit_idx >= len(calendar):
                        cash += entry_cost
                        skipped.append({'date': str(day.date()), 'ticker': code, 'reason': 'no_exit_calendar'})
                        break
                    position = {'ticker': code, 'name': cand['name'], 'setup': cand.setup,
                                'score': float(cand.score), 'signal_date': str(pending['signal_day'].date()),
                                'entry_date': str(day.date()), 'entry_price': px, 'shares': shares,
                                'total_entry_cost': entry_cost, 'exit_day': calendar[exit_idx]}
                    break
                pending = None
            elif day > pending['entry_day']:
                pending = None
        # Mark-to-market at close; if ticker quote is missing, flag and use last available close.
        equity = cash
        if position is not None:
            x = book[position['ticker']]['data']
            available = x.loc[:day, 'Close']
            if available.empty:
                skipped.append({'date': str(day.date()), 'ticker': position['ticker'], 'reason': 'mark_missing'})
                mark = position['entry_price']
            else:
                mark = float(available.iloc[-1])
                if day not in x.index:
                    skipped.append({'date': str(day.date()), 'ticker': position['ticker'], 'reason': 'stale_mark'})
            equity += position['shares'] * mark
        if start <= day <= end:
            daily.append({'date': str(day.date()), 'equity': equity, 'cash': cash,
                          'ticker': position['ticker'] if position else ''})
        # At today's close, signal can be observed even if we exited at today's open.
        if position is None and pending is None and day in grouped and day in calendar_index:
            idx = calendar_index[day]
            if idx + 1 < len(calendar):
                pending = {'signal_day': day, 'entry_day': calendar[idx + 1], 'group': grouped[day]}
    # No invented liquidation: open positions at end are explicitly reported.
    daily_df = pd.DataFrame(daily)
    trade_df = pd.DataFrame(trades)
    if not daily_df.empty:
        eq = daily_df['equity'].astype(float)
        dd = eq / np.maximum.accumulate(np.r_[a.capital, eq.to_numpy()])[1:] - 1
        mdd = float(dd.min())
        period_return = float(eq.iloc[-1] / a.capital - 1)
    else:
        mdd = None
        period_return = None
    by_setup = {}
    if not trade_df.empty:
        for setup, group in trade_df.groupby('setup'):
            by_setup[setup] = {'trades': len(group), 'win_rate': float((group.net_return > 0).mean()),
                               'avg_net_return': float(group.net_return.mean()),
                               'total_pnl_krw': float(group.pnl_krw.sum())}
    summary = {'version': 'C3 v1.5', 'run_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
               'survivorship_bias': True, 'point_in_time_universe': False, 'live_trade_approval': False,
               'universe_source': 'FDR current KRX; name-based common-stock filter (imperfect)',
               'requested_universe': len(names), 'downloaded_universe': len(book), 'fetch_failures': len(failures),
               'signal_count': len(sig), 'completed_trades': len(trades), 'initial_capital': a.capital,
               'holding_sessions': a.hold, 'entry_exit': 'next open / open after hold sessions',
               'cost_bps_each_side': a.cost_bps, 'period_return_mark_to_market': period_return,
               'daily_equity_mdd': mdd, 'by_setup': by_setup,
               'open_position_at_run_end': bool(position), 'skipped_events': len(skipped),
               'warnings': ['NOT a historical point-in-time universe',
                            'No realistic liquidity, market impact, trading halts, corporate action or tax model',
                            'Union calendar may include non-common trading days',
                            'End-of-period position may remain open; no forced liquidation']}
    (OUT / 'walkforward_v15_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    sig.to_csv(OUT / 'walkforward_v15_candidates.csv', index=False, encoding='utf-8-sig')
    trade_df.to_csv(OUT / 'walkforward_v15_trades.csv', index=False, encoding='utf-8-sig')
    daily_df.to_csv(OUT / 'walkforward_v15_equity.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(failures).to_csv(OUT / 'walkforward_v15_failures.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(skipped).to_csv(OUT / 'walkforward_v15_skipped.csv', index=False, encoding='utf-8-sig')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
