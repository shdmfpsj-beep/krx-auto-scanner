"""C3 v4.3: audit v4.2 paired results without new market downloads.
Research only. Requires reports/regime_v42_comparison.csv.
This audit cannot infer market exposure from summary-only v4.2 output.
"""
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'
SOURCE = REPORTS / 'regime_v42_comparison.csv'
OUT = REPORTS / 'regime_v43_audit.csv'
SUMMARY = REPORTS / 'regime_v43_summary.csv'
META = REPORTS / 'regime_v43_metadata.json'


def main():
    if not SOURCE.is_file():
        raise SystemExit(f'Missing {SOURCE}; run regime_v42 first')
    df = pd.read_csv(SOURCE)
    key = ['period', 'rule', 'hold', 'selection']
    metrics = ['return_pct', 'mdd_pct', 'win_rate_pct', 'trades_closed', 'adds_executed']
    required = key + ['arm', 'eligible_signals'] + metrics
    missing = set(required) - set(df.columns)
    if missing:
        raise SystemExit(f'Missing columns: {sorted(missing)}')
    if df.duplicated(key + ['arm']).any():
        raise SystemExit('Duplicate scenarios; audit aborted')
    if df[required].isna().any().any():
        raise SystemExit('Missing audit values; audit aborted')
    if not df['mdd_pct'].between(-100, 0).all():
        raise SystemExit('Invalid MDD range; audit aborted')
    baseline = df[df.arm.eq('all_in')][key + metrics].rename(columns={m: 'all_in_' + m for m in metrics})
    cash = df[df.arm.eq('cash_half')][key + metrics].rename(columns={m: 'cash_' + m for m in metrics})
    if baseline.duplicated(key).any() or cash.duplicated(key).any():
        raise SystemExit('Non-unique control scenarios')
    out = df.merge(baseline, on=key, how='left', validate='many_to_one')
    out = out.merge(cash, on=key, how='left', validate='many_to_one')
    if out[[f'cash_{m}' for m in metrics] + [f'all_in_{m}' for m in metrics]].isna().any().any():
        raise SystemExit('Missing matched baseline/cash controls')
    for base in ('cash', 'all_in'):
        out[f'return_delta_vs_{base}_pp'] = out.return_pct - out[f'{base}_return_pct']
        # Higher MDD percentage (less negative) means lower drawdown.
        out[f'mdd_improvement_vs_{base}_pp'] = out.mdd_pct - out[f'{base}_mdd_pct']
        out[f'trade_count_delta_vs_{base}'] = out.trades_closed - out[f'{base}_trades_closed']
    out['return_beats_cash'] = out.return_delta_vs_cash_pp > 0
    out['mdd_beats_cash'] = out.mdd_improvement_vs_cash_pp > 0
    out['both_beats_cash'] = out.return_beats_cash & out.mdd_beats_cash
    out['return_beats_all_in'] = out.return_delta_vs_all_in_pp > 0
    out['mdd_beats_all_in'] = out.mdd_improvement_vs_all_in_pp > 0
    out['both_beats_all_in'] = out.return_beats_all_in & out.mdd_beats_all_in
    # These are scenario comparisons, not independent observations or significance tests.
    group = ['period', 'rule', 'arm']
    summary = out.groupby(group, as_index=False).agg(
        scenarios=('return_pct', 'size'),
        median_return_pct=('return_pct', 'median'),
        median_mdd_pct=('mdd_pct', 'median'),
        median_win_rate_pct=('win_rate_pct', 'median'),
        median_trades=('trades_closed', 'median'),
        median_eligible_signals=('eligible_signals', 'median'),
        median_adds=('adds_executed', 'median'),
        median_return_delta_vs_cash_pp=('return_delta_vs_cash_pp', 'median'),
        median_mdd_improvement_vs_cash_pp=('mdd_improvement_vs_cash_pp', 'median'),
        return_beats_cash_count=('return_beats_cash', 'sum'),
        mdd_beats_cash_count=('mdd_beats_cash', 'sum'),
        both_beats_cash_count=('both_beats_cash', 'sum'),
        both_beats_all_in_count=('both_beats_all_in', 'sum'),
    )
    REPORTS.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False, encoding='utf-8-sig')
    summary.to_csv(SUMMARY, index=False, encoding='utf-8-sig')
    metadata = {
        'version': 'v4.3 audit', 'source': SOURCE.name,
        'scenarios': int(len(out)), 'summary_rows': int(len(summary)),
        'status': 'paired scenario audit, NOT an independent backtest',
        'limitations': [
            'Actual market exposure and time in market are NOT available in v4.2 summary; cannot calculate them honestly.',
            'MDD is portfolio daily-close drawdown, not intraday worst loss.',
            'Scenario counts are correlated parameter variations, NOT independent trials.',
            '2025 has been repeatedly inspected and is not untouched out-of-sample.',
            'Past-universe point-in-time integrity and signal lookahead have not been independently certified.',
            'Research capital is not a fixed live trading budget.',
            'Do not authorize live averaging down based on this report.',
        ],
        'next_requirement': 'Export daily equity curves, open-position exposure and transaction-level fills from replay for a true exposure-matched audit.',
    }
    META.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'v4.3 audited {len(out)} scenarios; summary rows {len(summary)}')
    print('Exposure unavailable: explicitly deferred until daily equity and position logs exist.')

if __name__ == '__main__':
    main()
