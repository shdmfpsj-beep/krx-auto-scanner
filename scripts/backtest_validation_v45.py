"""C3 v4.5 research-only chronology, leakage and ledger integrity audit.
Run from repository root: python scripts/backtest_validation_v45.py
Consumes v4.4 reports; no network, no trading or scheduled-scan changes.
This is an audit of saved outputs, NOT independent point-in-time validation.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'
KEY = ['period', 'rule', 'hold', 'selection', 'arm']
PERIODS = {'development_2023_2024': ('2023-01-01', '2024-12-31'),
           'later_2025': ('2025-01-01', '2025-12-31')}


def check(condition, message, findings, severity='error', **details):
    findings.append({'severity': severity, 'check': message, 'passed': bool(condition), **details})


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--reports', type=Path, default=REPORTS)
    args = p.parse_args()
    r = args.reports
    paths = {n: r / n for n in ['exposure_v44_summary.csv', 'exposure_v44_trades.csv',
             'exposure_v44_daily.csv', 'entry_v32_paired_trades.csv']}
    missing = [n for n, path in paths.items() if not path.is_file()]
    if missing:
        raise SystemExit(f'Missing prerequisite reports: {missing}; run exposure_v44 first')
    summary = pd.read_csv(paths['exposure_v44_summary.csv'])
    trades = pd.read_csv(paths['exposure_v44_trades.csv'], dtype={'ticker': str, 'signal_id': str})
    daily = pd.read_csv(paths['exposure_v44_daily.csv'], dtype={'ticker': str})
    signals = pd.read_csv(paths['entry_v32_paired_trades.csv'], dtype={'ticker': str, 'signal_id': str})
    findings, scenarios, boundary = [], [], []
    for name, df in [('summary', summary), ('trades', trades), ('daily', daily)]:
        check(all(c in df for c in KEY), f'{name}_scenario_keys_present', findings)
        if not all(c in df for c in KEY):
            raise SystemExit(f'Missing scenario keys in {name}')
    check(not summary.duplicated(KEY).any(), 'unique_scenario_summary', findings)
    check(not daily.duplicated(KEY + ['date']).any(), 'unique_daily_marks', findings)
    check(set(summary.period).issubset(PERIODS), 'known_period_labels', findings)
    check(not summary.empty and not daily.empty, 'nonempty_outputs', findings)
    check(all(c in signals for c in ['signal_id', 'signal_date', 'entry_date', 'ticker']),
          'signal_provenance_columns_present', findings)
    signals = signals.loc[signals.hold.eq(1)].copy() if 'hold' in signals else signals.copy()
    signals = signals.drop_duplicates('signal_id')
    signals['signal_date'] = pd.to_datetime(signals.signal_date)
    signals['entry_date'] = pd.to_datetime(signals.entry_date)
    check((signals.signal_date < signals.entry_date).all(), 'signal_precedes_entry', findings,
          violating_rows=int((signals.signal_date >= signals.entry_date).sum()))
    check(not signals.signal_id.duplicated().any(), 'unique_source_signal_ids', findings)
    provenance = signals.set_index('signal_id')[['ticker', 'signal_date', 'entry_date']]
    trades['entry_date'] = pd.to_datetime(trades.entry_date)
    trades['exit_date'] = pd.to_datetime(trades.exit_date)
    daily['date'] = pd.to_datetime(daily.date)
    check((trades.exit_date >= trades.entry_date).all(), 'no_exit_before_entry', findings)
    check((trades.shares > 0).all(), 'positive_traded_shares', findings)
    check(np.isfinite(pd.to_numeric(trades.net_pnl, errors='coerce')).all(), 'finite_trade_pnl', findings)
    orphan = ~trades.signal_id.isin(provenance.index)
    check(not orphan.any(), 'all_trades_have_source_signal', findings, missing=int(orphan.sum()))
    matched = trades.loc[~orphan].copy()
    if not matched.empty:
        src = provenance.loc[matched.signal_id]
        check((src.ticker.to_numpy() == matched.ticker.to_numpy()).all(),
              'trade_ticker_matches_signal', findings)
        check((src.entry_date.to_numpy() == matched.entry_date.to_numpy()).all(),
              'trade_entry_matches_signal', findings)
        check((src.signal_date.to_numpy() < matched.entry_date.to_numpy()).all(),
              'trade_uses_prior_signal', findings)
    for key, group in daily.groupby(KEY, dropna=False, sort=False):
        labels = dict(zip(KEY, key))
        period = labels['period']
        if period not in PERIODS:
            continue
        first, last = map(pd.Timestamp, PERIODS[period])
        group = group.sort_values('date')
        st = summary
        for k, v in labels.items():
            st = st.loc[st[k].eq(v)]
        if len(st) != 1:
            check(False, 'daily_has_exactly_one_summary', findings, **labels)
            continue
        st = st.iloc[0]
        gt = trades
        for k, v in labels.items():
            gt = gt.loc[gt[k].eq(v)]
        equity = pd.to_numeric(group.equity, errors='coerce').to_numpy(dtype=float)
        cash = pd.to_numeric(group.cash, errors='coerce').to_numpy(dtype=float)
        pos = pd.to_numeric(group.position_value, errors='coerce').to_numpy(dtype=float)
        exposure = pd.to_numeric(group.capital_exposure_pct, errors='coerce').to_numpy(dtype=float)
        mdd = float((equity / np.maximum.accumulate(equity) - 1).min() * 100) if len(equity) else np.nan
        ret = float((equity[-1] / equity[0] - 1) * 100) if len(equity) else np.nan
        boundary_exits = gt.loc[gt.exit_date > last]
        outside = gt.loc[(gt.entry_date < first) | (gt.entry_date > last)]
        boundary.append({**labels, 'trades_included_with_exit_after_period':len(boundary_exits),
                         'trades_entry_outside_period':len(outside),
                         'initial_equity_deviation_pct':100*(equity[0]/float(st.initial_equity)-1) if len(equity) else np.nan,
                         'first_mark_vs_research_capital_pct':100*(equity[0]/1000000-1) if len(equity) else np.nan,
                         'open_position_at_period_end':bool(st.open_position_at_end)})
        issues = []
        if not ((group.date >= first) & (group.date <= last)).all(): issues.append('daily_outside_period')
        if not (np.isfinite(equity).all() and (equity > 0).all()): issues.append('invalid_equity')
        if not np.allclose(equity, cash + pos, atol=.02, rtol=1e-9): issues.append('equity_cash_position_mismatch')
        if not np.allclose(exposure, 100*pos/equity, atol=.001, rtol=1e-8): issues.append('exposure_mismatch')
        if not np.isclose(mdd, float(st.mdd_pct_from_first_mark), atol=.0001): issues.append('mdd_mismatch')
        if not np.isclose(ret, float(st.return_pct_from_first_mark), atol=.0001): issues.append('return_mismatch')
        if int(st.trades_closed) != len(gt): issues.append('trade_count_mismatch')
        if int(st.days_marked) != len(group): issues.append('daily_count_mismatch')
        if len(boundary_exits): issues.append('trade_exit_after_period_included')
        if len(outside): issues.append('trade_entry_outside_period_included')
        scenarios.append({**labels, 'daily_rows':len(group), 'trade_rows':len(gt),
                          'first_date':group.date.iloc[0].date().isoformat(),
                          'last_date':group.date.iloc[-1].date().isoformat(),
                          'initial_equity':equity[0], 'end_equity':equity[-1],
                          'return_pct_recomputed':ret, 'mdd_pct_recomputed':mdd,
                          'boundary_exits':len(boundary_exits),
                          'issues':';'.join(issues), 'passed':not issues})
    scenario_df = pd.DataFrame(scenarios)
    boundary_df = pd.DataFrame(boundary)
    check(bool(len(scenario_df)) and scenario_df.passed.all(), 'all_scenario_ledger_checks_pass', findings,
          failures=int((~scenario_df.passed).sum()) if len(scenario_df) else 0)
    # Same-day one-position invariant from end-of-day marks; no intraday guarantee.
    check((pd.to_numeric(daily.shares, errors='coerce').fillna(-1) >= 0).all(),
          'nonnegative_daily_shares', findings)
    # Contamination and independent holdout status are fixed disclosures, not success criteria.
    check(False, 'independent_point_in_time_universe_verified', findings, 'warning',
          note='Historical universe membership is not independently point-in-time certified')
    check(False, 'untouched_out_of_sample_2025', findings, 'warning',
          note='2025 was inspected during earlier strategy development; not pristine OOS')
    check(False, 'live_fill_validated', findings, 'warning',
          note='Daily OHLCV and fixed slippage do not prove executable fills')
    r.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(findings).to_csv(r/'validation_v45_checks.csv', index=False, encoding='utf-8-sig')
    scenario_df.to_csv(r/'validation_v45_scenarios.csv', index=False, encoding='utf-8-sig')
    boundary_df.to_csv(r/'validation_v45_boundaries.csv', index=False, encoding='utf-8-sig')
    hard_failures = [x for x in findings if x['severity'] == 'error' and not x['passed']]
    report = {'version':'v4.5', 'research_only':True, 'status':'AUDIT_FAILED' if hard_failures else 'AUDIT_PASSED_WITH_LIMITATIONS',
              'scenarios':len(scenario_df), 'trades':len(trades), 'daily_marks':len(daily),
              'hard_failures':[x['check'] for x in hard_failures],
              'scenario_failures':int((~scenario_df.passed).sum()) if len(scenario_df) else 0,
              'boundary_exit_trades_counted_across_scenarios':int(boundary_df.trades_included_with_exit_after_period.sum()) if len(boundary_df) else 0,
              'critical_limitations':['2025 reused, not untouched OOS','Universe and signal features not independently PIT-audited',
                  'Daily OHLCV cannot verify fills','This script audits existing saved v4.4 outputs; it does not create a new holdout'],
              'live_strategy_approval':False}
    (r/'validation_v45_metadata.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if hard_failures:
        raise SystemExit('v4.5 audit found integrity errors; inspect validation_v45_checks.csv and scenarios.csv')

if __name__ == '__main__':
    main()
