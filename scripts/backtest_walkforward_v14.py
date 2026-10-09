"""C3 v2.0.1: current-listing stratified-sample, independent yearly scenario backtests.
Research only. NOT historical point-in-time; NOT trade approval.
Replace scripts/backtest_walkforward_v14.py; workflow mode remains walkforward_v14.
"""
import argparse
import hashlib
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
OHLCV = ['Open', 'High', 'Low', 'Close', 'Volume']


def universe(limit, seed):
    x = fdr.StockListing('KRX').copy()
    x = x[x['Market'].astype(str).str.upper().isin(['KOSPI', 'KOSDAQ'])].copy()
    x['Code'] = x['Code'].astype(str).str.zfill(6)
    x['Name'] = x['Name'].astype(str)
    excluded = r'(스팩|SPAC|우B?$|우C$|우\d|우선주|리츠|REIT|ETF|ETN|인버스|레버리지)'
    x = x[~x['Name'].str.contains(excluded, case=False, regex=True, na=False)]
    x = x[x.Code.str.fullmatch(r'\d{6}')].drop_duplicates('Code').copy()
    # Present-day market cap is ONLY a sampling proxy, NEVER historical PIT data.
    cap_col = next((c for c in ['Marcap', 'MarketCap', 'MarketCapKRW'] if c in x.columns), None)
    x['cap'] = pd.to_numeric(x[cap_col], errors='coerce') if cap_col else np.nan
    has_cap = bool(x['cap'].notna().sum() >= len(x) * .8 and (x['cap'] > 0).sum() >= len(x) * .8)
    if has_cap:
        x['tier'] = x.groupby('Market')['cap'].transform(
            lambda s: pd.qcut(s.rank(method='first'), q=3, labels=['small', 'mid', 'large']))
        x['tier'] = x['tier'].astype(str)
    else:
        x['tier'] = 'cap_unavailable'
    x['stratum'] = x['Market'].astype(str) + '/' + x['tier']
    x['order'] = x.Code.map(lambda c: hashlib.sha256(f'{seed}:{c}'.encode()).hexdigest())
    x = x.sort_values(['stratum', 'order'])
    groups = {k: g.reset_index(drop=True) for k, g in x.groupby('stratum', sort=True)}
    if limit <= 0 or limit >= len(x):
        chosen = x
    else:
        # Round-robin strata to avoid code-order and one-market concentration.
        rows = []
        for idx in range(max(len(g) for g in groups.values())):
            for group in groups.values():
                if idx < len(group):
                    rows.append(group.iloc[idx])
                    if len(rows) == limit:
                        break
            if len(rows) == limit:
                break
        chosen = pd.DataFrame(rows)
    return chosen[['Code', 'Name', 'Market', 'tier', 'stratum']], {
        'population_count': int(len(x)), 'sampling_method': 'deterministic_sha256_stratified_round_robin',
        'seed': seed, 'cap_column': cap_col if has_cap else None,
        'market_cap_is_current_not_historical': True,
        'sample_by_stratum': {str(k): int(v) for k, v in chosen.stratum.value_counts().items()}}


def prices(code, start, end):
    x = fdr.DataReader(code, start, end)
    if x is None or x.empty or not set(OHLCV).issubset(x.columns):
        return None
    x = x[OHLCV].copy()
    x.index = pd.to_datetime(x.index).normalize()
    x = x[~x.index.duplicated(keep='last')].sort_index()
    for c in OHLCV:
        x[c] = pd.to_numeric(x[c], errors='coerce')
    x = x.dropna()
    x = x[(x[['Open', 'High', 'Low', 'Close']] > 0).all(axis=1)]
    return x if int((x.Volume > 0).sum()) >= 130 else None


def indicators(x):
    y = x[x.Volume > 0].copy()
    y['ma20'] = y.Close.rolling(20).mean()
    y['ma60'] = y.Close.rolling(60).mean()
    y['ma120'] = y.Close.rolling(120).mean()
    y['rvol20'] = y.Volume / y.Volume.shift(1).rolling(20).mean().replace(0, np.nan)
    y['prev_high20'] = y.High.shift(1).rolling(20).max()
    y['ret20'] = y.Close.pct_change(20)
    trend = (y.Close > y.ma20) & (y.ma20 > y.ma60) & (y.ma60 > y.ma120)
    y['breakout'] = trend & (y.Close > y.prev_high20) & (y.rvol20 >= 1.5)
    y['pullback'] = trend & (y.Low <= y.ma20 * 1.02) & (y.Close >= y.ma20) & (y.Close > y.Open) & (y.rvol20 >= .8)
    y['signal'] = y.breakout | y.pullback
    y['score'] = (4*y.breakout.astype(int) + 3*y.pullback.astype(int)
                  + 2*trend.astype(int) + y.rvol20.clip(0, 5).fillna(0)
                  + 10*y.ret20.clip(-.2, .3).fillna(0))
    return y


def simulate(year, scenario, book, signals, args):
    start, end = pd.Timestamp(f'{year}-01-01'), pd.Timestamp(f'{year}-12-31')
    extended = end + pd.Timedelta(days=45)
    calendar = sorted(set().union(*(set(item['data'].loc[start:extended].index) for item in book.values())))
    if not calendar:
        raise RuntimeError(f'{year}: no trading calendar')
    index = {d: i for i, d in enumerate(calendar)}
    sy = signals[(signals.date >= start) & (signals.date <= end)]
    grouped = dict(tuple(sy.groupby('date'))) if not sy.empty else {}
    cash, position, pending = float(args.capital), None, None
    trades, daily, delayed = [], [], []
    snapshot = None
    for day in calendar:
        exit_at_close = False
        if position is not None and day >= position['target']:
            x = book[position['ticker']]['data']
            if day in x.index and float(x.at[day, 'Volume']) > 0:
                is_delayed = day > position['target']
                field = 'Open' if not is_delayed or scenario == 'open' else ('Close' if scenario == 'close' else 'Low')
                px = float(x.at[day, field])
                proceeds = position['shares'] * px * (1 - args.cost_bps / 10000)
                cash += proceeds
                trades.append({'year': year, 'scenario': scenario, 'ticker': position['ticker'],
                               'name': position['name'], 'setup': position['setup'],
                               'signal_date': str(position['signal'].date()),
                               'entry_date': str(position['entry'].date()),
                               'target_exit_date': str(position['target'].date()),
                               'exit_date': str(day.date()), 'shares': position['shares'],
                               'entry_price': position['entry_px'], 'exit_price': px,
                               'exit_basis': field.lower(), 'exit_delayed': is_delayed,
                               'pnl_krw': proceeds - position['cost']})
                if is_delayed:
                    delayed.append({'year': year, 'scenario': scenario, 'ticker': position['ticker'],
                                    'target_exit_date': str(position['target'].date()),
                                    'actual_exit_date': str(day.date()), 'basis': field.lower()})
                position = None
                exit_at_close = is_delayed and scenario != 'open'
        if position is None and pending is not None:
            if day == pending['entry_day']:
                if not exit_at_close:
                    for _, cand in pending['group'].iterrows():
                        x = book[cand.ticker]['data']
                        if day not in x.index or float(x.at[day, 'Volume']) <= 0:
                            continue
                        px = float(x.at[day, 'Open'])
                        shares = int(cash // (px * (1 + args.cost_bps / 10000)))
                        if shares < 1 or index[day] + args.hold >= len(calendar):
                            continue
                        cost = shares * px * (1 + args.cost_bps / 10000)
                        cash -= cost
                        position = {'ticker': cand.ticker, 'name': cand['name'], 'setup': cand.setup,
                                    'signal': pending['signal_day'], 'entry': day, 'entry_px': px,
                                    'shares': shares, 'cost': cost, 'target': calendar[index[day] + args.hold]}
                        break
                pending = None
            elif day > pending['entry_day']:
                pending = None
        equity = cash
        if position is not None:
            x = book[position['ticker']]['data']
            prior = x.loc[:day, 'Close']
            mark = float(prior.iloc[-1]) if len(prior) else position['entry_px']
            equity += position['shares'] * mark
        if start <= day <= end:
            daily.append({'year': year, 'scenario': scenario, 'date': str(day.date()),
                          'equity': equity, 'cash': cash, 'ticker': position['ticker'] if position else ''})
            snapshot = (cash, equity, position.copy() if position else None)
        if position is None and pending is None and day in grouped and index[day] + 1 < len(calendar):
            pending = {'signal_day': day, 'entry_day': calendar[index[day] + 1], 'group': grouped[day]}
    td, ed = pd.DataFrame(trades), pd.DataFrame(daily)
    eq = ed.equity.to_numpy(dtype=float)
    peaks = np.maximum.accumulate(np.r_[float(args.capital), eq])[1:]
    realized = float(td.loc[td.exit_date <= str(end.date()), 'pnl_krw'].sum()) if not td.empty else 0.0
    snap_cash, snap_equity, snap_position = snapshot
    unrealized = float(snap_equity - snap_cash - (snap_position['cost'] if snap_position else 0))
    delta = float(snap_equity - (args.capital + realized + unrealized))
    if abs(delta) >= .02:
        raise RuntimeError(f'{year} {scenario}: accounting mismatch {delta}')
    result = {'year': year, 'scenario': scenario, 'period_return': float(eq[-1] / args.capital - 1),
              'daily_mdd': float(np.min(eq / peaks - 1)), 'period_end_equity': float(snap_equity),
              'completed_trades_including_post_period': len(td),
              'completed_trades_within_period': int((td.exit_date <= str(end.date())).sum()) if not td.empty else 0,
              'delayed_exit_count': len(delayed), 'accounting_delta': delta,
              'accounting_ok': True, 'open_position_at_period_end': bool(snap_position)}
    return result, td, ed, pd.DataFrame(delayed)


def diagnose_trades(trade_frames, book, selected, args):
    """Ex-post descriptive analysis only; never feeds future bars into signals."""
    if not trade_frames or not any(not x.empty for x in trade_frames):
        return {'analyzed_trades': 0}, pd.DataFrame(), pd.DataFrame()
    all_trades = pd.concat([t for t in trade_frames if not t.empty], ignore_index=True)
    # OPEN only: avoid triple-counting the same trades under scenario variants.
    t = all_trades[all_trades.scenario == 'open'].copy()
    lookup = selected.set_index('Code')[['Market', 'tier', 'stratum']].to_dict('index')
    records = []
    for row in t.itertuples(index=False):
        x = book[row.ticker]['data']
        dt = pd.Timestamp(row.entry_date)
        tradable = x[(x.Volume > 0) & (x.index >= dt)]
        if dt not in tradable.index:
            continue
        j = tradable.index.get_loc(dt)
        entry = float(row.entry_price)
        rec = {'year': int(row.year), 'ticker': row.ticker, 'name': row.name,
               'setup': row.setup, 'entry_date': row.entry_date,
               'exit_date': row.exit_date, 'entry_price': entry,
               'realized_pnl_krw': float(row.pnl_krw),
               'realized_net_return': float(row.pnl_krw / (row.shares * entry * (1 + args.cost_bps / 10000))),
               'exit_delayed': bool(row.exit_delayed),
               'market': lookup.get(row.ticker, {}).get('Market', 'unknown'),
               'tier_current': lookup.get(row.ticker, {}).get('tier', 'unknown'),
               'stratum_current': lookup.get(row.ticker, {}).get('stratum', 'unknown')}
        for n in (1, 2, 3):
            # +n is the nth tradable ticker session AFTER entry, not the entry day.
            if j + n < len(tradable):
                z = tradable.iloc[j + 1:j + n + 1]
                rec[f'close_return_d{n}'] = float(z.Close.iloc[-1] / entry - 1)
                rec[f'mfe_d{n}'] = float(z.High.max() / entry - 1)
                rec[f'mae_d{n}'] = float(z.Low.min() / entry - 1)
            else:
                rec[f'close_return_d{n}'] = None
                rec[f'mfe_d{n}'] = None
                rec[f'mae_d{n}'] = None
        # Entry-session excursion is included separately, not mixed with future bars.
        e = tradable.loc[dt]
        rec['entry_day_high_return'] = float(e.High / entry - 1)
        rec['entry_day_low_return'] = float(e.Low / entry - 1)
        records.append(rec)
    detail = pd.DataFrame(records)
    if detail.empty:
        return {'analyzed_trades': 0}, detail, pd.DataFrame()
    def aggregate(frame, dims):
        rows = []
        for key, g in frame.groupby(dims, dropna=False):
            key = key if isinstance(key, tuple) else (key,)
            r = dict(zip(dims, key))
            r.update({'trades': len(g), 'win_rate_realized': float((g.realized_net_return > 0).mean()),
                      'mean_realized_net_return': float(g.realized_net_return.mean()),
                      'sum_realized_pnl_krw': float(g.realized_pnl_krw.sum())})
            for n in (1, 2, 3):
                for metric in ('close_return', 'mfe', 'mae'):
                    c = f'{metric}_d{n}'
                    r[f'mean_{c}'] = float(g[c].mean()) if g[c].notna().any() else None
                r[f'observations_d{n}'] = int(g[f'close_return_d{n}'].notna().sum())
            rows.append(r)
        return rows
    summary = {'analyzed_trades': int(len(detail)),
               'basis': 'OPEN scenario completed trades only, each counted once',
               'forward_definition': '1/2/3 ticker-tradable sessions after entry, excluding entry session',
               'returns_before_fees': 'close_return_dN, mfe_dN, mae_dN',
               'realized_returns_after_fees': True,
               'by_year': aggregate(detail, ['year']),
               'by_setup': aggregate(detail, ['setup']),
               'by_year_setup': aggregate(detail, ['year', 'setup']),
               'by_market_current': aggregate(detail, ['market']),
               'by_tier_current': aggregate(detail, ['tier_current']),
               'by_market_tier_current': aggregate(detail, ['stratum_current'])}
    grouped = []
    for name, dims in [('year', ['year']), ('setup', ['setup']),
                       ('year_setup', ['year', 'setup']), ('market', ['market']),
                       ('tier', ['tier_current']), ('market_tier', ['stratum_current'])]:
        for r in aggregate(detail, dims):
            grouped.append({'group_type': name, **r})
    return summary, detail, pd.DataFrame(grouped)


def json_safe(obj):
    """Convert NumPy/Pandas scalars into JSON-native values."""
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if obj is pd.NA:
        return None
    raise TypeError(f'Unsupported JSON type: {type(obj).__name__}')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--limit', type=int, default=120)
    p.add_argument('--start-year', type=int, default=2023)
    p.add_argument('--end-year', type=int, default=2025)
    p.add_argument('--seed', type=int, default=19)
    p.add_argument('--hold', type=int, default=3)
    p.add_argument('--cost-bps', type=float, default=15)
    p.add_argument('--capital', type=float, default=300000)
    a = p.parse_args()
    if a.start_year > a.end_year or a.hold < 1 or a.capital <= 0 or a.cost_bps < 0 or a.limit < 0:
        raise ValueError('Invalid arguments')
    selected, sample_info = universe(a.limit, a.seed)
    # One fetch per ticker for all years, with a 270-day indicator warmup.
    fetch_start = (pd.Timestamp(f'{a.start_year}-01-01') - pd.Timedelta(days=270)).strftime('%Y-%m-%d')
    fetch_end = (pd.Timestamp(f'{a.end_year}-12-31') + pd.Timedelta(days=45)).strftime('%Y-%m-%d')
    book, signals, failures = {}, [], []
    for i, (code, name, market, tier, stratum) in enumerate(selected.itertuples(index=False, name=None), 1):
        try:
            x = prices(code, fetch_start, fetch_end)
            if x is None:
                failures.append({'ticker': code, 'reason': 'missing/insufficient OHLCV'})
                continue
            book[code] = {'name': name, 'market': market, 'data': x}
            y = indicators(x)
            for dt, r in y.loc[f'{a.start_year}-01-01':f'{a.end_year}-12-31'].iterrows():
                if bool(r.signal):
                    signals.append({'date': dt, 'ticker': code, 'name': name,
                                    'setup': 'breakout' if r.breakout else 'pullback',
                                    'score': float(r.score), 'rvol20': float(r.rvol20)})
        except Exception as exc:
            failures.append({'ticker': code, 'reason': str(exc)[:180]})
        if i % 20 == 0:
            print(f'Fetched {i}/{len(selected)}', flush=True)
        time.sleep(.12)
    if not book:
        raise RuntimeError('No OHLCV downloaded')
    sig = pd.DataFrame(signals, columns=['date', 'ticker', 'name', 'setup', 'score', 'rvol20'])
    if not sig.empty:
        sig = sig.sort_values(['date', 'score', 'rvol20', 'ticker'], ascending=[True, False, False, True])
    all_results, trades, equity, delays = [], [], [], []
    for year in range(a.start_year, a.end_year + 1):
        for scenario in ('open', 'close', 'low'):
            result, td, ed, delayed = simulate(year, scenario, book, sig, a)
            all_results.append(result)
            trades.append(td)
            equity.append(ed)
            delays.append(delayed)
    def concat(frames):
        return pd.concat(frames, ignore_index=True) if any(not x.empty for x in frames) else pd.DataFrame()
    concat(trades).to_csv(OUT / 'walkforward_v20_trades.csv', index=False, encoding='utf-8-sig')
    concat(equity).to_csv(OUT / 'walkforward_v20_equity.csv', index=False, encoding='utf-8-sig')
    concat(delays).to_csv(OUT / 'walkforward_v20_reopenings.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(failures).to_csv(OUT / 'walkforward_v20_failures.csv', index=False, encoding='utf-8-sig')
    selected.to_csv(OUT / 'walkforward_v20_universe.csv', index=False, encoding='utf-8-sig')
    diagnostics, detail, groups = diagnose_trades(trades, book, selected, a)
    detail.to_csv(OUT / 'walkforward_v20_trade_diagnostics.csv', index=False, encoding='utf-8-sig')
    groups.to_csv(OUT / 'walkforward_v20_group_diagnostics.csv', index=False, encoding='utf-8-sig')
    (OUT / 'walkforward_v20_diagnostics.json').write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2, default=json_safe), encoding='utf-8')
    summary = {'version': 'C3 v2.0.1', 'run_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
               'survivorship_bias': True, 'point_in_time_universe': False, 'live_trade_approval': False,
               'initial_capital_each_year': a.capital, 'years_independent_reset': True,
               'requested_universe': len(selected), 'downloaded_universe': len(book),
               'fetch_failures': len(failures), 'signal_count': len(sig),
               'holding_sessions': a.hold, 'cost_bps_each_side': a.cost_bps,
               'sample': sample_info, 'results': all_results, 'diagnostics': diagnostics,
               'warnings': ['Present-day listing and market cap are NOT historical PIT; survivorship bias',
                            'Industry stratification unavailable; stratification uses market and present-day cap if available',
                            'Adjusted OHLCV may not be executable historical prices',
                            'Shared-calendar holding sessions and approximate common-stock filter',
                            'Reopening CLOSE/LOW are sensitivity proxies, not guaranteed fills',
                            'Each year resets to initial capital; do not compound annual returns',
                            'No realistic taxes, impact, true halt records, or corporate action model',
                            'Forward excursions use ticker-tradable sessions, while exit uses shared calendar; horizons differ',
                            'MFE/MAE are descriptive extremes, not guaranteed executable prices',
                            'Current market-cap tiers are not historical PIT classifications']}
    (OUT / 'walkforward_v20_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=json_safe), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=json_safe))


if __name__ == '__main__':
    main()
