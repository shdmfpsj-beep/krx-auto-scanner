"""C3 v3.0 research: compare 1..20 trading-session fixed holding horizons.

Add as scripts/backtest_holding_v30.py; leave existing v2.0.1 and workflow intact.
Uses identical v2.0.1 universe, signals, next-open entry, cost, and accounting.
WARNING: current listings/cap tiers cause survivorship/lookahead selection bias.
Not point-in-time, not investment or live trade approval.
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backtest_walkforward_v14 as base

OUT = Path(__file__).resolve().parents[1] / 'reports'
OUT.mkdir(parents=True, exist_ok=True)


def safe_float(x):
    return None if not np.isfinite(x) else float(x)


def trade_metrics(trades, capital):
    if trades.empty:
        return {'trades': 0, 'win_rate': None, 'mean_net_return': None,
                'median_net_return': None, 'profit_factor': None,
                'mean_holding_calendar_days': None}
    t = trades.copy()
    t['net_return'] = t.pnl_krw / (t.shares * t.entry_price * (1 + t.cost_bps / 10000))
    gains = float(t.loc[t.pnl_krw > 0, 'pnl_krw'].sum())
    losses = float(-t.loc[t.pnl_krw < 0, 'pnl_krw'].sum())
    pf = gains / losses if losses > 0 else (None if gains == 0 else None)
    return {'trades': int(len(t)),
            'win_rate': float((t.net_return > 0).mean()),
            'mean_net_return': float(t.net_return.mean()),
            'median_net_return': float(t.net_return.median()),
            'profit_factor': safe_float(pf) if pf is not None else None,
            'mean_holding_calendar_days': float((pd.to_datetime(t.exit_date) - pd.to_datetime(t.entry_date)).dt.days.mean())}


def main():
    p = argparse.ArgumentParser(description='C3 fixed holding period sensitivity 1..20 sessions')
    p.add_argument('--limit', type=int, default=120)
    p.add_argument('--start-year', type=int, default=2023)
    p.add_argument('--end-year', type=int, default=2025)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--max-hold', type=int, default=20)
    p.add_argument('--cost-bps', type=float, default=15)
    p.add_argument('--capital', type=float, default=300000)
    a = p.parse_args()
    if a.limit < 1 or a.start_year > a.end_year or not 1 <= a.max_hold <= 40 or a.capital <= 0 or a.cost_bps < 0:
        p.error('Invalid parameter')

    selected, sample = base.universe(a.limit, a.seed)
    fetch_start = (pd.Timestamp(f'{a.start_year}-01-01') - pd.Timedelta(days=270)).strftime('%Y-%m-%d')
    # Enough post-year data for max 40 sessions, including year-end exits.
    fetch_end = (pd.Timestamp(f'{a.end_year}-12-31') + pd.Timedelta(days=100)).strftime('%Y-%m-%d')
    book, signals, failures = {}, [], []
    for i, (code, name, market, tier, stratum) in enumerate(selected.itertuples(index=False, name=None), 1):
        try:
            x = base.prices(code, fetch_start, fetch_end)
            if x is None:
                failures.append({'ticker': code, 'reason': 'missing/insufficient OHLCV'})
                continue
            book[code] = {'name': name, 'market': market, 'data': x}
            y = base.indicators(x)
            for dt, r in y.loc[f'{a.start_year}-01-01':f'{a.end_year}-12-31'].iterrows():
                if bool(r.signal):
                    signals.append({'date': dt, 'ticker': code, 'name': name,
                                    'setup': 'breakout' if r.breakout else 'pullback',
                                    'score': float(r.score), 'rvol20': float(r.rvol20)})
        except Exception as exc:
            failures.append({'ticker': code, 'reason': str(exc)[:180]})
        if i % 20 == 0:
            print(f'Downloaded {i}/{len(selected)}', flush=True)
        time.sleep(.12)
    if not book:
        raise RuntimeError('No OHLCV downloaded')
    sig = pd.DataFrame(signals, columns=['date', 'ticker', 'name', 'setup', 'score', 'rvol20'])
    if not sig.empty:
        sig = sig.sort_values(['date', 'score', 'rvol20', 'ticker'], ascending=[True, False, False, True])

    rows, trades_all, equity_all, failures_sim = [], [], [], []
    for hold in range(1, a.max_hold + 1):
        args = SimpleNamespace(capital=a.capital, cost_bps=a.cost_bps, hold=hold)
        for year in range(a.start_year, a.end_year + 1):
            # Open is the primary executable-price approximation; close/low are
            # reopening sensitivity variants, NOT additional independent trades.
            for scenario in ('open', 'close', 'low'):
                try:
                    result, td, ed, delayed = base.simulate(year, scenario, book, sig, args)
                except Exception as exc:
                    failures_sim.append({'hold': hold, 'year': year, 'scenario': scenario,
                                         'reason': str(exc)[:200]})
                    continue
                if not td.empty:
                    td = td.copy()
                    td['hold'] = hold
                    td['cost_bps'] = a.cost_bps
                    trades_all.append(td)
                if not ed.empty:
                    ed = ed.copy()
                    ed['hold'] = hold
                    equity_all.append(ed)
                # Count only trades closed within the calendar year when computing
                # trade statistics; post-period exits are still preserved in CSV.
                completed = td[td.exit_date <= f'{year}-12-31'] if not td.empty else td
                stats = trade_metrics(completed, a.capital)
                rows.append({'hold': hold, 'year': year, 'scenario': scenario,
                             **result, **stats})
        print(f'Compared hold={hold}/{a.max_hold}', flush=True)

    results = pd.DataFrame(rows)
    if results.empty:
        raise RuntimeError(f'No simulation succeeded: {failures_sim[:3]}')
    results.to_csv(OUT / 'holding_v30_by_year.csv', index=False, encoding='utf-8-sig')
    all_trades = pd.concat(trades_all, ignore_index=True) if trades_all else pd.DataFrame()
    all_trades.to_csv(OUT / 'holding_v30_trades.csv', index=False, encoding='utf-8-sig')
    all_equity = pd.concat(equity_all, ignore_index=True) if equity_all else pd.DataFrame()
    all_equity.to_csv(OUT / 'holding_v30_equity.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(failures).to_csv(OUT / 'holding_v30_download_failures.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(failures_sim).to_csv(OUT / 'holding_v30_simulation_failures.csv', index=False, encoding='utf-8-sig')
    selected.to_csv(OUT / 'holding_v30_universe.csv', index=False, encoding='utf-8-sig')

    summary_rows = []
    for (hold, scenario), g in results.groupby(['hold', 'scenario'], sort=True):
        # Equal-weight years, not compounded. Reset each year.
        valid = g.dropna(subset=['period_return', 'daily_mdd'])
        summary_rows.append({
            'hold': int(hold), 'scenario': scenario,
            'years': int(len(valid)),
            'mean_yearly_return': float(valid.period_return.mean()),
            'median_yearly_return': float(valid.period_return.median()),
            'worst_year_return': float(valid.period_return.min()),
            'mean_yearly_mdd': float(valid.daily_mdd.mean()),
            'worst_year_mdd': float(valid.daily_mdd.min()),
            'completed_trades_in_year': int(valid.completed_trades_within_period.sum()),
            'mean_yearly_trade_win_rate': safe_float(valid.win_rate.mean()),
            'mean_yearly_trade_net_return': safe_float(valid.mean_net_return.mean()),
        })
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT / 'holding_v30_summary.csv', index=False, encoding='utf-8-sig')

    # Setups are observational, because the one-position-at-a-time account
    # means each horizon changes subsequent entry opportunities.
    setups = []
    if not all_trades.empty:
        t = all_trades[(all_trades.scenario == 'open') &
                       (all_trades.exit_date.str[:4] == all_trades.year.astype(str))].copy()
        t['net_return'] = t.pnl_krw / (t.shares * t.entry_price * (1 + a.cost_bps / 10000))
        for (hold, setup), g in t.groupby(['hold', 'setup']):
            setups.append({'hold': int(hold), 'setup': setup, 'trades': int(len(g)),
                           'win_rate': float((g.net_return > 0).mean()),
                           'mean_net_return': float(g.net_return.mean())})
    pd.DataFrame(setups, columns=['hold', 'setup', 'trades', 'win_rate', 'mean_net_return']).to_csv(
        OUT / 'holding_v30_by_setup.csv', index=False, encoding='utf-8-sig')

    # This is a descriptive in-sample ranking, NOT a validated optimum.
    primary = summary[summary.scenario == 'open'].copy()
    ranked = primary.sort_values(['mean_yearly_return', 'worst_year_mdd'], ascending=[False, False])
    meta = {
        'version': 'C3 v3.0 fixed holding horizon exploratory test',
        'run_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        'settings': vars(a), 'sample': sample,
        'requested_tickers': int(len(selected)), 'downloaded_tickers': int(len(book)),
        'signal_count': int(len(sig)), 'download_failures': int(len(failures)),
        'simulation_failures': failures_sim,
        'descriptive_best_hold_open_by_mean_yearly_return': int(ranked.iloc[0]['hold']) if len(ranked) else None,
        'not_out_of_sample_optimum': True, 'live_trade_approval': False,
        'warnings': [
            'Current KRX listings and present-day market-cap strata: NOT historical PIT, survivorship bias.',
            'Fixed holding horizon comparison, not an independently validated trading strategy.',
            'All 1..N horizons evaluated on same years: selecting the best is multiple-testing overfit.',
            '2025 was already inspected in previous runs; cannot claim untouched holdout.',
            'Different holding horizons change subsequent trades; do not treat rows as paired trade outcomes.',
            'Shared-market calendar and price adjustments may diverge from actual execution.',
            'Open/close/low scenarios differ only for delayed reopening exits; not three independent samples.',
            '15 bps per side is a model assumption; taxes, slippage and market impact not fully modeled.',
            'Yearly accounts reset to initial capital; yearly returns must not be compounded directly.',
            'No fundamental filters in this test; Open DART key not required.'
        ]
    }
    (OUT / 'holding_v30_metadata.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=base.json_safe), encoding='utf-8')
    print('=== TOP 10 IN-SAMPLE OPEN HORIZONS (NOT VERIFIED) ===')
    print(ranked.head(10).to_string(index=False))
    print('Saved reports/holding_v30_*.csv and metadata.json')


if __name__ == '__main__':
    main()
