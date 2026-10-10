"""C3 v3.5 reproducibility / robustness audit of v3.4.
Research only; does not modify live scans or approve trading.
Run: python scripts/backtest_audit_v35.py
Requires reports/entry_v32_paired_trades.csv and scripts/backtest_portfolio_v34.py.
"""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from backtest_portfolio_v34 import load_source

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'


def order_key(ticker, signal_id, salt):
    return hashlib.sha256(f'{salt}|{ticker}|{signal_id}'.encode()).hexdigest()


def replay(source, hold, capital, improved, policy, cost_bps, max_trade_gain=None):
    y = source.loc[source.hold.eq(hold)].copy()
    if improved:
        y = y.loc[y.improved].copy()
    if policy == 'ticker_asc':
        y = y.sort_values(['entry_date', 'signal_date', 'ticker', 'signal_id'], kind='stable')
    elif policy == 'ticker_desc':
        y = y.sort_values(['entry_date', 'signal_date', 'ticker', 'signal_id'],
                          ascending=[True, True, False, True], kind='stable')
    elif policy.startswith('hash_'):
        y['_order'] = [order_key(t, s, policy) for t, s in zip(y.ticker, y.signal_id)]
        y = y.sort_values(['entry_date', 'signal_date', '_order'], kind='stable')
    else:
        raise ValueError(policy)
    cash = float(capital)
    free_date = pd.Timestamp.min
    rows = []
    for date, group in y.groupby('entry_date', sort=True):
        if date < free_date:
            continue
        pick = group.iloc[0]
        entry, exit_ = float(pick.entry_open), float(pick.exit_open)
        shares = int(cash // entry)
        if shares < 1:
            continue
        gross_return = exit_ / entry - 1
        if max_trade_gain is not None and gross_return > max_trade_gain:
            # Stress test ONLY: cap realized proceeds, not a realizable take-profit.
            exit_ = entry * (1 + max_trade_gain)
        invested = shares * entry
        proceeds = shares * exit_ - invested * cost_bps / 10000
        cash = cash - invested + proceeds
        if cash <= 0:
            raise ValueError('Nonpositive equity: inspect source and fees')
        free_date = pick.exit_date
        rows.append({'signal_id': pick.signal_id, 'ticker': pick.ticker,
                     'entry_date': date.date().isoformat(),
                     'exit_date': pick.exit_date.date().isoformat(),
                     'entry_open': entry, 'exit_open_raw': float(pick.exit_open),
                     'shares': shares, 'return_pct': (proceeds / invested - 1) * 100,
                     'cash_after_exit': cash})
    equities = np.array([capital] + [r['cash_after_exit'] for r in rows], dtype=float)
    closed_mdd = np.min(equities / np.maximum.accumulate(equities) - 1) * 100
    gains = sorted([r['return_pct'] for r in rows], reverse=True)
    return {'hold': hold, 'capital': capital, 'strategy': 'B_improved' if improved else 'A_baseline',
            'policy': policy, 'gain_cap': 'none' if max_trade_gain is None else max_trade_gain,
            'trades': len(rows), 'total_return_pct': (cash / capital - 1) * 100,
            'closed_trade_mdd_pct': closed_mdd,
            'win_rate_pct': 100 * sum(r['return_pct'] > 0 for r in rows) / len(rows) if rows else np.nan,
            'top_trade_return_pct': gains[0] if gains else np.nan}, rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', default=str(REPORTS / 'entry_v32_paired_trades.csv'))
    p.add_argument('--capital', type=int, default=1_000_000)
    p.add_argument('--holds', default='5,10,15,20')
    p.add_argument('--cost-bps', type=float, default=15)
    args = p.parse_args()
    if args.capital <= 0 or not 0 <= args.cost_bps < 1000:
        p.error('Invalid capital or fee')
    holds = [int(h) for h in args.holds.split(',')]
    if not holds or min(holds) < 1:
        p.error('Invalid holding periods')
    source = load_source(Path(args.input))
    if not set(holds).issubset(set(source.hold)):
        p.error('Source lacks a requested holding period')
    policies = ['ticker_asc', 'ticker_desc', 'hash_1', 'hash_2', 'hash_3']
    results, baseline_trades = [], []
    for hold in holds:
        for improved in (False, True):
            for policy in policies:
                result, trades = replay(source, hold, args.capital, improved, policy, args.cost_bps)
                results.append(result)
                if policy == 'ticker_asc':
                    for t in trades:
                        baseline_trades.append({'hold': hold, 'strategy': result['strategy'], **t})
            for cap in [0.30, 0.50, 1.00]:
                result, _ = replay(source, hold, args.capital, improved, 'ticker_asc', args.cost_bps, cap)
                results.append(result)
    output = pd.DataFrame(results)
    REPORTS.mkdir(parents=True, exist_ok=True)
    output.to_csv(REPORTS / 'audit_v35_sensitivity.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(baseline_trades).to_csv(REPORTS / 'audit_v35_reference_trades.csv', index=False, encoding='utf-8-sig')
    comparison = []
    for (hold, strategy), group in output[output.gain_cap.eq('none')].groupby(['hold', 'strategy']):
        returns = group.total_return_pct.to_numpy()
        comparison.append({'hold': hold, 'strategy': strategy,
                           'min_return_pct': float(np.min(returns)),
                           'median_return_pct': float(np.median(returns)),
                           'max_return_pct': float(np.max(returns)),
                           'spread_pp': float(np.max(returns) - np.min(returns)),
                           'selection_policies': len(returns)})
    pd.DataFrame(comparison).to_csv(REPORTS / 'audit_v35_policy_spread.csv', index=False, encoding='utf-8-sig')
    issues = []
    for hold in holds:
        subset = source.loc[source.hold.eq(hold)]
        if (subset.exit_date <= subset.entry_date).any():
            issues.append(f'hold {hold}: exit not after entry')
        if (subset.signal_date >= subset.entry_date).any():
            issues.append(f'hold {hold}: signal date not before entry')
    # v3.4 uses one round-trip fee on invested amount at exit, not explicit bid/ask.
    # The source only has entry/exit OPEN, so daily unrealized MDD cannot be recovered.
    meta = {'version': 'C3 v3.5 audit', 'run_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
            'capital_krw': args.capital, 'holds': holds, 'cost_bps': args.cost_bps,
            'policy_tests': policies, 'stress_test_gain_caps': [0.30, 0.50, 1.00],
            'input_rows': len(source), 'issues': issues, 'live_trade_approval': False,
            'limitations': [
                'NOT point-in-time: present-day listing and market-cap survivorship bias.',
                '2023-2025 already explored: no clean out-of-sample.',
                'Selection policy stress tests are deterministic, NOT market-realistic ranking.',
                'Gain caps are hypothetical return winsorization, NOT executable take-profits.',
                'Only realized closed-trade drawdown available; daily MDD requires daily OHLCV.',
                'No stops, slippage, market impact, taxes, suspensions or limit-order fills.',
                'v3.4 fee accounting charges assumed 15bps on entry notional at exit.',
                'Large compounded returns should not be extrapolated to actual investments.']}
    (REPORTS / 'audit_v35_metadata.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print('C3 v3.5 audit completed:', len(output), 'scenarios; issues:', len(issues))
    print(pd.DataFrame(comparison).to_string(index=False))
    if issues:
        raise SystemExit('DATA VALIDATION FAILED: ' + '; '.join(issues))


if __name__ == '__main__':
    main()
