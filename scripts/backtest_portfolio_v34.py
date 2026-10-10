"""C3 v3.4: one-position, multi-capital portfolio replay from v3.2 paired trades.
Research only. Current-listing survivorship bias; not PIT or live trade approval.
Run: python scripts/backtest_portfolio_v34.py
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
CAPITALS = [300_000, 500_000, 1_000_000, 3_000_000, 10_000_000]
HOLDS = [5, 10, 15, 20]
COST_BPS = 15.0  # assumed round-trip costs, already included in source net_return


def load_source(path):
    x = pd.read_csv(path, dtype={'ticker': str, 'signal_id': str})
    required = {'signal_id', 'ticker', 'signal_date', 'entry_date', 'exit_date',
                'entry_open', 'exit_open', 'hold', 'setup', 'ma_rising',
                'ret60', 'distance_ma20', 'net_return'}
    missing = required - set(x.columns)
    if missing:
        raise ValueError(f'Missing source columns: {sorted(missing)}')
    if x.duplicated(['signal_id', 'hold']).any():
        raise ValueError('Duplicate signal_id + hold rows')
    for c in ['entry_open', 'exit_open', 'ret60', 'distance_ma20', 'net_return']:
        x[c] = pd.to_numeric(x[c], errors='coerce')
    x['hold'] = pd.to_numeric(x.hold, errors='raise').astype(int)
    x['ma_rising'] = x.ma_rising.astype(str).str.lower().eq('true')
    for c in ['entry_date', 'exit_date', 'signal_date']:
        x[c] = pd.to_datetime(x[c], errors='coerce')
    if x[['entry_date', 'exit_date', 'signal_date']].isna().any().any():
        raise ValueError('Invalid dates in input')
    if ((x.entry_open <= 0) | (x.exit_open <= 0)).any():
        raise ValueError('Nonpositive entry/exit prices')
    if (x.exit_date <= x.entry_date).any():
        raise ValueError('Exit must be later than entry')
    # All entry decisions use signal-day attributes. No future returns in filters.
    x['improved'] = (x.setup.eq('breakout') & x.ma_rising &
                     x.ret60.lt(.60) & x.distance_ma20.lt(.15))
    # Source net_return contains a 15 bps round-trip approximation. Preserve it
    # for fractional reference; whole-share replay uses gross ratio minus same fee.
    return x


def candidates_for(x, hold, improved):
    y = x.loc[x.hold.eq(hold)].copy()
    if improved:
        y = y.loc[y.improved].copy()
    # Fixed, outcome-blind ranking; one candidate per day when flat.
    # The signal_date is the preceding signal day, entry at following open.
    y = y.sort_values(['entry_date', 'signal_date', 'ticker', 'signal_id'],
                      kind='stable').reset_index(drop=True)
    return y


def simulate(x, hold, improved, capital, fractional, cost_bps):
    y = candidates_for(x, hold, improved)
    if y.empty:
        return None, [], []
    cash = float(capital)
    initial = cash
    next_free = pd.Timestamp.min
    trades = []
    missed_cash = 0
    skipped_occupied = 0
    all_dates = sorted(set(x.loc[x.hold.eq(hold), 'entry_date']) |
                       set(x.loc[x.hold.eq(hold), 'exit_date']))
    # One order opportunity per entry date. While occupied, ignore signals.
    for date, day in y.groupby('entry_date', sort=True):
        if date < next_free:
            skipped_occupied += len(day)
            continue
        # If the account is flat, use deterministic first eligible ticker.
        pick = day.iloc[0]
        price = float(pick.entry_open)
        shares = cash / price if fractional else int(cash // price)
        if shares <= 0:
            missed_cash += 1
            continue
        invested = shares * price
        fee = invested * cost_bps / 10_000
        proceeds = shares * float(pick.exit_open) - fee
        cash = cash - invested + proceeds
        if cash < 0:
            raise ValueError('Negative cash; invalid fill calculation')
        next_free = pick.exit_date
        trades.append({'strategy': 'B_improved' if improved else 'A_baseline',
                       'hold': hold, 'initial_capital': capital,
                       'fractional_reference': fractional,
                       'signal_id': pick.signal_id, 'ticker': pick.ticker,
                       'entry_date': date.date().isoformat(),
                       'exit_date': pick.exit_date.date().isoformat(),
                       'entry_open': price, 'exit_open': float(pick.exit_open),
                       'shares': shares, 'invested': invested,
                       'cash_after_exit': cash,
                       'trade_return_pct': (proceeds - invested) / invested * 100})
    # Equity between trades: use last realized equity, NOT an invented daily mark.
    # Therefore max drawdown below is CLOSED-TRADE drawdown only.
    realized = [initial] + [t['cash_after_exit'] for t in trades]
    peak = np.maximum.accumulate(realized)
    mdd = float(np.min(np.asarray(realized) / peak - 1) * 100)
    begin = min(all_dates)
    end = max(all_dates)
    years = (end - begin).days / 365.25
    total = (cash / initial - 1) * 100
    cagr = ((cash / initial) ** (1 / years) - 1) * 100 if years > 0 and cash > 0 else None
    wins = [t['trade_return_pct'] for t in trades if t['trade_return_pct'] > 0]
    losses = [t['trade_return_pct'] for t in trades if t['trade_return_pct'] <= 0]
    gross_gain = sum(wins)
    gross_loss = -sum(losses)
    summary = {'strategy': 'B_improved' if improved else 'A_baseline',
               'hold': hold, 'initial_capital': capital,
               'fractional_reference': fractional,
               'start': begin.date().isoformat(), 'end': end.date().isoformat(),
               'trades': len(trades), 'skipped_while_occupied': skipped_occupied,
               'missed_unaffordable_dates': missed_cash,
               'ending_capital': cash, 'total_return_pct': total,
               'cagr_pct': cagr, 'closed_trade_mdd_pct': mdd,
               'win_rate_pct': len(wins) / len(trades) * 100 if trades else None,
               'profit_factor_approx': gross_gain / gross_loss if gross_loss else None,
               'days_in_position': sum((pd.Timestamp(t['exit_date']) -
                                        pd.Timestamp(t['entry_date'])).days for t in trades),
               'period_days': (end - begin).days,
               'selection_policy': 'ticker ascending, outcome-blind; one position'}
    return summary, trades, realized


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default=str(SOURCE))
    parser.add_argument('--capitals', default=','.join(map(str, CAPITALS)))
    parser.add_argument('--holds', default=','.join(map(str, HOLDS)))
    parser.add_argument('--cost-bps', type=float, default=COST_BPS)
    args = parser.parse_args()
    capitals = [int(z) for z in args.capitals.split(',')]
    holds = [int(z) for z in args.holds.split(',')]
    if not capitals or min(capitals) <= 0 or not holds or min(holds) <= 0:
        parser.error('Capitals and holds must be positive')
    if args.cost_bps < 0 or args.cost_bps >= 1000:
        parser.error('Invalid cost-bps')
    source = Path(args.input)
    if not source.is_file():
        raise SystemExit('Missing v3.2 paired CSV; run entry_v32 first')
    x = load_source(source)
    available = set(x.hold.unique())
    if not set(holds).issubset(available):
        raise SystemExit(f'Missing hold periods: {sorted(set(holds) - available)}')
    summaries, trades = [], []
    for hold in holds:
        for capital in capitals:
            for improved in (False, True):
                result, ts, _ = simulate(x, hold, improved, capital, False, args.cost_bps)
                if result:
                    summaries.append(result)
                    trades.extend(ts)
        # Large nominal capital with fractional shares is a capital-unconstrained
        # REFERENCE only, not a realistic account or a no-capacity market model.
        for improved in (False, True):
            result, ts, _ = simulate(x, hold, improved, 1_000_000, True, args.cost_bps)
            if result:
                result['initial_capital_label'] = 'fractional_reference'
                summaries.append(result)
                trades.extend(ts)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(summaries)
    out.to_csv(REPORTS / 'portfolio_v34_summary.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(trades).to_csv(REPORTS / 'portfolio_v34_trades.csv', index=False, encoding='utf-8-sig')
    comp = out.pivot_table(index=['hold', 'initial_capital', 'fractional_reference'],
                           columns='strategy', values=['total_return_pct', 'closed_trade_mdd_pct',
                                                       'trades'], aggfunc='first')
    comp.columns = [f'{metric}_{strategy}' for metric, strategy in comp.columns]
    comp = comp.reset_index()
    if {'total_return_pct_A_baseline', 'total_return_pct_B_improved'}.issubset(comp.columns):
        comp['improved_minus_baseline_pp'] = (comp['total_return_pct_B_improved'] -
                                              comp['total_return_pct_A_baseline'])
    comp.to_csv(REPORTS / 'portfolio_v34_comparison.csv', index=False, encoding='utf-8-sig')
    meta = {'version': 'C3 v3.4 capital sensitivity one-position replay',
            'run_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
            'source': str(source), 'capitals_krw': capitals, 'holds': holds,
            'round_trip_cost_bps': args.cost_bps,
            'trade_entry': 'next ticker session open after signal',
            'trade_exit': 'open after N ticker-tradable sessions',
            'position_limit': 1, 'position_sizing': 'all affordable whole shares',
            'reinvestment': True, 'no_averaging_down': True,
            'live_trade_approval': False,
            'warnings': [
                'Current-listed sample, current market-cap tiers: NOT PIT; survivorship bias.',
                '2023-2025 were previously inspected; NOT clean out-of-sample.',
                'A/B signals may be different on each day; no causal attribution.',
                'No intraday stop, limit, slippage, market impact, taxes, halts or liquidity capacity.',
                'Fee is approximate; fractional model is an unrealistic reference.',
                'Closed-trade drawdown ignores unrealized losses and is NOT daily equity MDD.',
                'Idle cash is included; portfolio cannot buy another ticker until exit date.',
                'Deterministic ticker sorting is not a validated selection/ranking model.',
                'No 2026 data; not validated for current market conditions.'
            ]}
    (REPORTS / 'portfolio_v34_metadata.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print('C3 v3.4 completed:', len(out), 'scenarios;', len(trades), 'trades')
    print(comp.to_string(index=False, max_rows=14))


if __name__ == '__main__':
    main()
