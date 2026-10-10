"""C3 v3.3: compare predeclared entry gates on identical v3.2 signals.
Research only; no point-in-time universe, no trading approval.
Run after entry_v32: python scripts/backtest_entry_rules_v33.py
"""
import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'
SOURCE = REPORTS / 'entry_v32_paired_trades.csv'

# Declared in advance for this version. Do not choose thresholds using 2025 results.
RULES = {
    'baseline_all': lambda x: pd.Series(True, index=x.index),
    'no_60d_over_60pct': lambda x: x.ret60 < .60,
    'rising_ma20_ma60': lambda x: x.ma_rising,
    'breakout_only': lambda x: x.setup.eq('breakout'),
    'no_ma20_distance_over_15pct': lambda x: x.distance_ma20 < .15,
    'breakout_rising_no_heat60': lambda x: x.setup.eq('breakout') & x.ma_rising & x.ret60.lt(.60),
    'breakout_rising_heat20_10to25': lambda x: (x.setup.eq('breakout') & x.ma_rising
                                                   & x.ret20.ge(.10) & x.ret20.lt(.25)),
    'breakout_rising_no_heat60_no_dist15': lambda x: (x.setup.eq('breakout') & x.ma_rising
                                                        & x.ret60.lt(.60) & x.distance_ma20.lt(.15)),
}


def metrics(df):
    if df.empty:
        return {'signals': 0, 'tickers': 0, 'signal_dates': 0,
                'mean_net_pct': None, 'median_net_pct': None,
                'win_rate_pct': None, 'p10_net_pct': None}
    return {'signals': int(len(df)), 'tickers': int(df.ticker.nunique()),
            'signal_dates': int(df.signal_date.nunique()),
            'mean_net_pct': float(df.net_return.mean() * 100),
            'median_net_pct': float(df.net_return.median() * 100),
            'win_rate_pct': float((df.net_return > 0).mean() * 100),
            'p10_net_pct': float(df.net_return.quantile(.1) * 100)}


def ticker_cluster_ci(df, seed, iterations):
    """Ticker-cluster bootstrap for difference vs ALL signals on same horizon/year.
    The bootstrap is descriptive: ticker clusters do not account for market-wide shocks.
    """
    if df.empty or df.ticker.nunique() < 10:
        return None, None
    groups = [g[['net_return', 'selected']].to_numpy(dtype=float)
              for _, g in df.groupby('ticker', sort=True)]
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(iterations):
        ids = rng.integers(0, len(groups), size=len(groups))
        values = np.concatenate([groups[j] for j in ids], axis=0)
        chosen = values[:, 1] > 0
        if chosen.sum() < 5 or chosen.all():
            continue
        diffs.append((values[chosen, 0].mean() - values[:, 0].mean()) * 100)
    if len(diffs) < iterations * .8:
        return None, None
    return [float(v) for v in np.quantile(diffs, [.025, .975])], len(diffs)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', default=str(SOURCE))
    p.add_argument('--bootstrap', type=int, default=500)
    p.add_argument('--seed', type=int, default=42)
    a = p.parse_args()
    if a.bootstrap < 100:
        p.error('--bootstrap must be >= 100')
    path = Path(a.input)
    if not path.is_file():
        raise SystemExit('Missing entry_v32_paired_trades.csv. Run entry_v32 first.')
    x = pd.read_csv(path, dtype={'ticker': str, 'signal_id': str})
    required = {'signal_id', 'ticker', 'signal_date', 'year', 'hold', 'setup',
                'ma_rising', 'ret20', 'ret60', 'distance_ma20', 'net_return'}
    missing = required - set(x.columns)
    if missing:
        raise SystemExit(f'Missing input columns: {sorted(missing)}')
    x['ticker'] = x.ticker.str.zfill(6)
    x['ma_rising'] = x.ma_rising.astype(str).str.lower().eq('true')
    for col in ['ret20', 'ret60', 'distance_ma20', 'net_return']:
        x[col] = pd.to_numeric(x[col], errors='coerce')
    x['hold'] = pd.to_numeric(x.hold, errors='raise').astype(int)
    x['year'] = pd.to_numeric(x.year, errors='raise').astype(int)
    x = x.dropna(subset=['net_return'])
    if x.duplicated(['signal_id', 'hold']).any():
        raise SystemExit('Duplicate signal_id + hold rows; input is not paired')
    horizons = [int(v) for v in sorted(x.hold.unique())]
    if horizons != list(range(1, max(horizons) + 1)):
        raise SystemExit('Missing holding horizons')
    counts = x.groupby('hold').signal_id.nunique()
    if counts.nunique() != 1:
        raise SystemExit('Holding horizons have different signal counts')
    years = [int(v) for v in sorted(x.year.unique())]
    if not set([2023, 2024, 2025]).issubset(years):
        raise SystemExit('Expected 2023-2025 results for train/holdout comparison')
    # Use one row per signal to construct rule membership, then apply to all horizons.
    one = x[x.hold == horizons[0]].set_index('signal_id')
    membership = {}
    for name, func in RULES.items():
        mask = func(one).fillna(False).astype(bool)
        membership[name] = set(one.index[mask])
    x['split'] = np.where(x.year <= 2024, 'development_2023_2024', 'review_2025_seen')
    rows, year_rows, paired_rows = [], [], []
    for split, part in x.groupby('split', sort=True):
        for hold, g in part.groupby('hold', sort=True):
            base_mean = float(g.net_return.mean() * 100)
            for name, ids in membership.items():
                sub = g[g.signal_id.isin(ids)]
                m = metrics(sub)
                diff = None if not len(sub) else m['mean_net_pct'] - base_mean
                rows.append({'split': split, 'hold': int(hold), 'rule': name,
                             **m, 'baseline_mean_net_pct': base_mean,
                             'difference_vs_baseline_pp': diff,
                             'retained_pct': float(len(sub) / len(g) * 100)})
                if name != 'baseline_all' and len(sub):
                    paired = g[['ticker', 'signal_id', 'net_return']].copy()
                    paired['selected'] = paired.signal_id.isin(ids)
                    ci, n = ticker_cluster_ci(paired, a.seed + int(hold), a.bootstrap)
                    paired_rows.append({'split': split, 'hold': int(hold), 'rule': name,
                                        'difference_vs_baseline_pp': diff,
                                        'ticker_bootstrap_ci95_pp': json.dumps(ci),
                                        'valid_bootstrap_draws': n})
    for (year, hold), g in x.groupby(['year', 'hold'], sort=True):
        for name, ids in membership.items():
            sub = g[g.signal_id.isin(ids)]
            year_rows.append({'year': int(year), 'hold': int(hold), 'rule': name,
                              **metrics(sub), 'retained_pct': float(len(sub) / len(g) * 100)})
    REPORTS.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(REPORTS / 'entry_v33_rule_comparison.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(year_rows).to_csv(REPORTS / 'entry_v33_yearly.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(paired_rows).to_csv(REPORTS / 'entry_v33_cluster_ci.csv', index=False, encoding='utf-8-sig')
    # Development-only ranking: descriptive, never a trade approval.
    dev = pd.DataFrame(rows)
    dev = dev[(dev.split == 'development_2023_2024') & (dev.rule != 'baseline_all')]
    dev = dev[dev.signals >= 30].sort_values('difference_vs_baseline_pp', ascending=False)
    dev.head(30).to_csv(REPORTS / 'entry_v33_development_candidates.csv', index=False, encoding='utf-8-sig')
    metadata = {
        'version': 'C3 v3.3 fixed entry-rule comparison',
        'run_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        'source': str(path), 'signals': int(counts.iloc[0]),
        'years': years, 'horizons': horizons, 'rule_names': list(RULES),
        'bootstrap_iterations': a.bootstrap, 'live_trade_approval': False,
        'warnings': [
            '2025 is NOT a pristine holdout: it was already inspected during v3.1/v3.2.',
            'Thresholds and combinations were informed by prior inspection of the same data.',
            'Present-day KRX listings and market cap create survivorship and PIT bias.',
            'Paired hypothetical signals overlap; these are NOT one-position portfolio returns.',
            'Ticker-cluster bootstrap ignores market-date common shocks and is exploratory.',
            'No market regime, historical fundamentals, valuation or actual liquidity impact.',
            'Differences vs baseline reflect filtering, not causal improvement.',
            'Multiple comparisons across rules/horizons require new independent validation.',
            'No same-day stop/target fills, taxes or actual order-book slippage modeled.',
        ]}
    (REPORTS / 'entry_v33_metadata.json').write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print('C3 v3.3 complete. Source signals:', int(counts.iloc[0]))
    print('Top exploratory development candidates (not validated):')
    print(dev[['rule', 'hold', 'signals', 'mean_net_pct', 'difference_vs_baseline_pp']].head(12).to_string(index=False))


if __name__ == '__main__':
    main()
