"""C3 v3.2 entry-quality research, paired 1..20 session outcomes.
Add as scripts/backtest_entry_quality_v32.py. No live trading approval.
Run: python scripts/backtest_entry_quality_v32.py --limit 120 --seed 42
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


def band(value, limits, labels):
    if not np.isfinite(value):
        return 'unknown'
    for bound, label in zip(limits, labels):
        if value < bound:
            return label
    return labels[-1]


def aggregate(g):
    years = g.groupby('year').net_return.mean()
    return {
        'signals': int(g.signal_id.nunique()),
        'tickers': int(g.ticker.nunique()),
        'signal_days': int(g.signal_date.nunique()),
        'win_rate': float((g.net_return > 0).mean()),
        'mean_net_return': float(g.net_return.mean()),
        'median_net_return': float(g.net_return.median()),
        'p10_net_return': float(g.net_return.quantile(.1)),
        'positive_years': int((years > 0).sum()),
        'observed_years': int(len(years)),
        'worst_year_mean': float(years.min()),
    }


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

    chosen, sampling = base.universe(a.limit, a.seed)
    start = (pd.Timestamp(f'{a.start_year}-01-01') - pd.Timedelta(days=400)).strftime('%Y-%m-%d')
    end = (pd.Timestamp(f'{a.end_year}-12-31') + pd.Timedelta(days=140)).strftime('%Y-%m-%d')
    records, failures = [], []
    for i, (code, name, market, tier, stratum) in enumerate(chosen.itertuples(index=False, name=None), 1):
        try:
            raw = base.prices(code, start, end)
            if raw is None:
                failures.append({'ticker': code, 'reason': 'missing/insufficient OHLCV'})
                continue
            x = base.indicators(raw)
            x['ma20_slope5'] = x.ma20 / x.ma20.shift(5) - 1
            x['ma60_slope10'] = x.ma60 / x.ma60.shift(10) - 1
            x['high60_prev'] = x.High.shift(1).rolling(60).max()
            x['ret60'] = x.Close.pct_change(60)
            x['ret5'] = x.Close.pct_change(5)
            dates = x.index
            signals = x.loc[f'{a.start_year}-01-01':f'{a.end_year}-12-31']
            for signal_day, s in signals[signals.signal].iterrows():
                entry_idx = int(dates.searchsorted(signal_day)) + 1
                if entry_idx + a.max_hold >= len(x):
                    continue
                entry_price = float(x.iloc[entry_idx].Open)
                if not np.isfinite(entry_price) or entry_price <= 0:
                    continue
                # Features are computed ONLY using signal-day and earlier bars.
                distance20 = float(s.Close / s.ma20 - 1) if s.ma20 > 0 else np.nan
                distance60 = float(s.Close / s.ma60 - 1) if s.ma60 > 0 else np.nan
                ret20 = float(s.ret20)
                ret60 = float(s.ret60)
                trend = bool(pd.notna(s.ma20_slope5) and pd.notna(s.ma60_slope10)
                             and s.ma20_slope5 > 0 and s.ma60_slope10 > 0)
                near_high = bool(pd.notna(s.high60_prev) and s.high60_prev > 0
                                 and s.Close >= .97 * s.high60_prev)
                setup = 'breakout' if bool(s.breakout) else 'pullback'
                attrs = {
                    'signal_id': f'{code}:{signal_day.date()}',
                    'ticker': code, 'name': name, 'market': market,
                    'tier_current': str(tier), 'year': int(signal_day.year),
                    'setup': setup, 'signal_date': str(signal_day.date()),
                    'entry_date': str(dates[entry_idx].date()),
                    'entry_open': entry_price,
                    'signal_close': float(s.Close),
                    'rvol20': float(s.rvol20),
                    'ret5': float(s.ret5) if pd.notna(s.ret5) else np.nan,
                    'ret20': ret20, 'ret60': ret60,
                    'distance_ma20': distance20, 'distance_ma60': distance60,
                    'ma_rising': trend, 'near_prior_60d_high': near_high,
                    'heat20': band(ret20, [.10, .25], ['below_10pct', '10_to_25pct', '25pct_plus']),
                    'heat60': band(ret60, [.20, .60], ['below_20pct', '20_to_60pct', '60pct_plus']),
                    'ma20_distance': band(distance20, [.04, .10, .15],
                                          ['below_4pct', '4_to_10pct', '10_to_15pct', '15pct_plus']),
                    'volume_band': band(float(s.rvol20), [1.5, 3.0],
                                        ['below_1_5', '1_5_to_3', '3_plus']),
                }
                entry_cost = entry_price * (1 + a.cost_bps / 10000)
                for hold in range(1, a.max_hold + 1):
                    bar = x.iloc[entry_idx + hold]
                    records.append({**attrs, 'hold': hold,
                                    'exit_date': str(dates[entry_idx + hold].date()),
                                    'exit_open': float(bar.Open),
                                    'net_return': float(bar.Open * (1 - a.cost_bps / 10000) / entry_cost - 1)})
        except Exception as exc:
            failures.append({'ticker': code, 'reason': str(exc)[:180]})
        if i % 20 == 0:
            print(f'Processed {i}/{len(chosen)}', flush=True)
        time.sleep(.12)

    df = pd.DataFrame(records)
    if df.empty:
        raise RuntimeError('No complete signal histories; check data access')
    if df.groupby('hold').signal_id.nunique().nunique() != 1:
        raise RuntimeError('Paired signal sets differ across holding horizons')
    df.to_csv(OUT / 'entry_v32_paired_trades.csv', index=False, encoding='utf-8-sig')
    dimensions = ['setup', 'heat20', 'heat60', 'ma20_distance', 'volume_band',
                  'ma_rising', 'near_prior_60d_high', 'market', 'tier_current']
    rows = []
    for dimension in dimensions:
        for (category, hold), g in df.groupby([dimension, 'hold'], dropna=False):
            rows.append({'dimension': dimension, 'category': str(category), 'hold': int(hold), **aggregate(g)})
    pd.DataFrame(rows).to_csv(OUT / 'entry_v32_by_factor_hold.csv', index=False, encoding='utf-8-sig')
    # Crossed factors, with minimum sample counts left visible rather than filtered away.
    cross = []
    for (setup, heat, rising, hold), g in df.groupby(['setup', 'heat20', 'ma_rising', 'hold']):
        cross.append({'setup': setup, 'heat20': heat, 'ma_rising': bool(rising),
                      'hold': int(hold), **aggregate(g)})
    pd.DataFrame(cross).to_csv(OUT / 'entry_v32_cross_factors.csv', index=False, encoding='utf-8-sig')
    overall = [{'hold': int(hold), **aggregate(g)} for hold, g in df.groupby('hold')]
    pd.DataFrame(overall).to_csv(OUT / 'entry_v32_overall.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(failures, columns=['ticker', 'reason']).to_csv(
        OUT / 'entry_v32_failures.csv', index=False, encoding='utf-8-sig')
    metadata = {
        'version': 'C3 v3.2 entry-quality factor research',
        'run_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        'settings': vars(a), 'sampling': sampling,
        'paired_signals': int(df[df.hold == 1].signal_id.nunique()),
        'rows': int(len(df)), 'failed_tickers': int(len(failures)),
        'live_trade_approval': False,
        'warnings': [
            'Present-day listing and cap strata are NOT point-in-time; survivorship bias.',
            'Signal-day factors use no future OHLCV; this does not eliminate universe bias.',
            'These are descriptive factor slices, not causal effects or validated trading rules.',
            'Multiple comparisons and small subgroup counts can create false discoveries.',
            'Repeated ticker signals and adjacent days are dependent; naive confidence intervals invalid.',
            'All signals hypothetically entered independently; not executable one-position portfolio.',
            'Only signal types from v2.0.1 tested; no new entry signal logic yet.',
            'No fundamental data, index regime, weekly bars, or forward valuation in this version.',
            'Exit at OPEN of Nth ticker-tradable session after entry, without intraday stops.',
            'Fees estimated; taxes, slippage, impact and halts not fully modeled.',
            '2023-2025 data already examined; exploratory, not clean out-of-sample.',
        ],
    }
    (OUT / 'entry_v32_metadata.json').write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, default=base.json_safe), encoding='utf-8')
    print(pd.DataFrame(overall).to_string(index=False))
    print('Saved reports/entry_v32_*; research only')


if __name__ == '__main__':
    main()
