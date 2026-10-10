"""C3 v3.1: paired 1..20 ticker-tradable-session horizon study.

Save as scripts/backtest_paired_v31.py. Independent research; no portfolio
simulation, no PIT universe, no live trading approval. Uses v2.0.1 signals.
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import backtest_walkforward_v14 as base

OUT = Path(__file__).resolve().parents[1] / 'reports'
OUT.mkdir(parents=True, exist_ok=True)


def mean_ci_by_signal_day(g, seed=42, repeats=400):
    """Cluster bootstrap by signal day (still ignores serial cross-day dependence)."""
    day_means = g.groupby('signal_date').net_return.agg(['sum', 'count'])
    if len(day_means) < 2:
        return None, None
    rng = np.random.default_rng(seed)
    sums = day_means['sum'].to_numpy(dtype=float)
    counts = day_means['count'].to_numpy(dtype=float)
    draws = rng.integers(0, len(sums), size=(repeats, len(sums)))
    means = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    return float(np.quantile(means, .025)), float(np.quantile(means, .975))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--limit', type=int, default=120)
    p.add_argument('--start-year', type=int, default=2023)
    p.add_argument('--end-year', type=int, default=2025)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--max-hold', type=int, default=20)
    p.add_argument('--cost-bps', type=float, default=15)
    a = p.parse_args()
    if a.limit < 1 or a.start_year > a.end_year or not 1 <= a.max_hold <= 40 or a.cost_bps < 0:
        p.error('Invalid arguments')

    selected, sample = base.universe(a.limit, a.seed)
    fetch_start = (pd.Timestamp(f'{a.start_year}-01-01') - pd.Timedelta(days=270)).strftime('%Y-%m-%d')
    fetch_end = (pd.Timestamp(f'{a.end_year}-12-31') + pd.Timedelta(days=130)).strftime('%Y-%m-%d')
    records, failures = [], []
    # Each signal is an independent hypothetical entry. No capital constraint;
    # overlapping signals are correlated and are NOT executable as one-position C3.
    for i, (code, name, market, tier, stratum) in enumerate(selected.itertuples(index=False, name=None), 1):
        try:
            raw = base.prices(code, fetch_start, fetch_end)
            if raw is None:
                failures.append({'ticker': code, 'reason': 'missing/insufficient OHLCV'})
                continue
            y = base.indicators(raw)
            x = y[y.Volume > 0].copy()
            dates = x.index
            signals = x.loc[f'{a.start_year}-01-01':f'{a.end_year}-12-31']
            for signal_date, r in signals[signals.signal].iterrows():
                loc = int(dates.searchsorted(signal_date))
                entry_idx = loc + 1
                # Require all horizons available for a truly paired comparison.
                if entry_idx + a.max_hold >= len(x):
                    continue
                entry = x.iloc[entry_idx]
                entry_price = float(entry.Open)
                if not np.isfinite(entry_price) or entry_price <= 0:
                    continue
                setup = 'breakout' if bool(r.breakout) else 'pullback'
                entry_cost = entry_price * (1 + a.cost_bps / 10000)
                for hold in range(1, a.max_hold + 1):
                    # Exit at OPEN of the Nth ticker-tradable session after entry.
                    # No intraday stop/target assumed; future signal bars are not
                    # used in selecting entries.
                    exit_bar = x.iloc[entry_idx + hold]
                    exit_price = float(exit_bar.Open)
                    net = exit_price * (1 - a.cost_bps / 10000) / entry_cost - 1
                    records.append({
                        'signal_id': f'{code}:{signal_date.date()}',
                        'ticker': code, 'name': name, 'market': market,
                        'tier_current': str(tier), 'year': int(signal_date.year),
                        'setup': setup, 'signal_date': str(signal_date.date()),
                        'entry_date': str(dates[entry_idx].date()),
                        'entry_open': entry_price, 'hold': hold,
                        'exit_date': str(dates[entry_idx + hold].date()),
                        'exit_open': exit_price, 'net_return': float(net),
                    })
        except Exception as exc:
            failures.append({'ticker': code, 'reason': str(exc)[:180]})
        if i % 20 == 0:
            print(f'Processed {i}/{len(selected)}', flush=True)
        time.sleep(.12)

    detail = pd.DataFrame(records)
    if detail.empty:
        raise RuntimeError(f'No complete paired signal horizons; failures={failures[:3]}')
    counts = detail.groupby('hold').signal_id.nunique()
    if counts.nunique() != 1:
        raise RuntimeError('Pairing failed: unequal entry sets across horizons')
    detail.to_csv(OUT / 'paired_v31_trades.csv', index=False, encoding='utf-8-sig')
    summary = []
    for keys, g in detail.groupby(['hold', 'year', 'setup'], sort=True):
        hold, year, setup = keys
        lo, hi = mean_ci_by_signal_day(g, seed=a.seed + int(hold) + int(year))
        summary.append({
            'hold': int(hold), 'year': int(year), 'setup': setup,
            'signals': int(g.signal_id.nunique()),
            'signal_days': int(g.signal_date.nunique()),
            'win_rate': float((g.net_return > 0).mean()),
            'mean_net_return': float(g.net_return.mean()),
            'median_net_return': float(g.net_return.median()),
            'p10_net_return': float(g.net_return.quantile(.1)),
            'p90_net_return': float(g.net_return.quantile(.9)),
            'mean_ci95_low_cluster_day': lo,
            'mean_ci95_high_cluster_day': hi,
        })
    pd.DataFrame(summary).to_csv(OUT / 'paired_v31_by_year_setup.csv', index=False, encoding='utf-8-sig')
    overall = []
    for hold, g in detail.groupby('hold'):
        lo, hi = mean_ci_by_signal_day(g, seed=a.seed + int(hold))
        annual = g.groupby('year').net_return.mean()
        overall.append({
            'hold': int(hold), 'signals': int(g.signal_id.nunique()),
            'win_rate': float((g.net_return > 0).mean()),
            'mean_net_return': float(g.net_return.mean()),
            'median_net_return': float(g.net_return.median()),
            'worst_year_mean_net_return': float(annual.min()),
            'positive_years': int((annual > 0).sum()),
            'years': int(len(annual)),
            'mean_ci95_low_cluster_day': lo,
            'mean_ci95_high_cluster_day': hi,
        })
    result = pd.DataFrame(overall)
    result.to_csv(OUT / 'paired_v31_summary.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(failures, columns=['ticker', 'reason']).to_csv(
        OUT / 'paired_v31_failures.csv', index=False, encoding='utf-8-sig')
    meta = {
        'version': 'C3 v3.1 paired signal holding study',
        'run_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        'settings': vars(a), 'sample': sample,
        'paired_signal_count': int(counts.iloc[0]),
        'live_trade_approval': False,
        'warnings': [
            'Present-day listed universe and cap tiers; severe survivorship/PIT bias.',
            'Every qualifying signal is an independent hypothetical trade; overlapping entries are correlated.',
            'Not a capital-constrained portfolio; do not interpret mean trade returns as account returns.',
            'Exit at next-session OPEN N ticker-tradable sessions after entry; no stop/target.',
            'All horizons share the exact same entry signal IDs; late signals without 20-day follow-up excluded.',
            'Entry at next tradable session OPEN may be impossible after suspension/delisting.',
            'Fees approximated as bps per side; taxes, slippage and market impact not fully included.',
            'Bootstrap clusters by signal day only; cross-day dependence and repeated tickers remain.',
            '2023-2025 data already inspected; results are exploratory, not clean out-of-sample validation.',
            'Picking best of 20 horizons on these same observations causes multiple-comparison bias.',
        ],
    }
    (OUT / 'paired_v31_metadata.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=base.json_safe), encoding='utf-8')
    print(result.to_string(index=False))
    print('Saved reports/paired_v31_*; research only')


if __name__ == '__main__':
    main()
