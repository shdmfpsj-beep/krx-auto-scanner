import argparse
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from pykrx import stock

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports'
OUT.mkdir(parents=True, exist_ok=True)

# These are research scenarios, not optimized trading rules.
SCENARIOS = [
    {'name': 'tight', 'stop_pct': 2.0, 'target_pct': 4.0, 'max_hold_days': 3},
    {'name': 'balanced', 'stop_pct': 3.0, 'target_pct': 6.0, 'max_hold_days': 5},
    {'name': 'wide', 'stop_pct': 4.0, 'target_pct': 8.0, 'max_hold_days': 7},
    {'name': 'legacy_comparison', 'stop_pct': 3.0, 'target_pct': 3.3, 'max_hold_days': 5},
]
TRADE_COLUMNS = [
    'scenario', 'ticker', 'setup', 'signal_date', 'entry_date', 'exit_date',
    'entry_price', 'exit_price', 'shares', 'entry_amount', 'exit_reason',
    'gross_return_pct', 'net_return_pct', 'net_profit_krw', 'capital_after'
]


def load_codes(limit):
    path = OUT / 'candidates.csv'
    if not path.exists():
        raise FileNotFoundError('Run full_scan first: reports/candidates.csv missing')
    df = pd.read_csv(path, dtype={'ticker': str})
    if 'ticker' not in df.columns:
        raise ValueError('ticker column missing')
    return df['ticker'].dropna().astype(str).str.zfill(6).drop_duplicates().tolist()[:limit]


def load_prices(code, start, end):
    df = stock.get_market_ohlcv_by_date(start, end, code, adjusted=True)
    if df is None or df.empty:
        raise ValueError('empty price history')
    df = df.sort_index().loc[lambda x: ~x.index.duplicated(keep='last')].copy()
    for col in ('시가', '고가', '저가', '종가', '거래량'):
        if col not in df.columns:
            raise ValueError(f'missing {col}')
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['시가', '고가', '저가', '종가', '거래량'])
    return df[(df[['시가', '고가', '저가', '종가']] > 0).all(axis=1)].copy()


def build_signals(df):
    close = df['종가'].astype(float)
    high = df['고가'].astype(float)
    volume = df['거래량'].astype(float)
    ma20, ma60, ma120 = (close.rolling(n).mean() for n in (20, 60, 120))
    rvol = volume / volume.shift(1).rolling(20).mean().replace(0, np.nan)
    breakout = (close > high.shift(1).rolling(20).max()) & (rvol >= 1.5) & (close > ma60)
    pullback = (ma20 > ma60) & (ma60 > ma120) & (close > ma20) & ((close / ma20 - 1).abs() <= .035)
    reversal = (close.shift(1) < ma60.shift(1)) & (close > ma60) & (ma20 > ma20.shift(5))
    weekly = close.resample('W-FRI').last().dropna()
    monthly = close.resample('ME').last().dropna()
    weekly_ok = weekly > weekly.rolling(10).mean()
    monthly_ok = monthly > monthly.rolling(6).mean()
    # Shift one full period so that an incomplete period is never consulted.
    weekly_daily = weekly_ok.shift(1).reindex(close.index, method='ffill').fillna(False)
    monthly_daily = monthly_ok.shift(1).reindex(close.index, method='ffill').fillna(False)
    trend = weekly_daily & monthly_daily
    flags = {'REVERSAL_PROXY': reversal & trend, 'PULLBACK_PROXY': pullback & trend, 'BREAKOUT': breakout & trend}
    base = {'REVERSAL_PROXY': 80, 'PULLBACK_PROXY': 70, 'BREAKOUT': 60}
    signals = []
    for setup, flag in flags.items():
        for date in df.index[flag.fillna(False)]:
            relative_volume = float(rvol.loc[date]) if pd.notna(rvol.loc[date]) else 0.0
            signals.append({
                'setup': setup, 'signal_date': pd.Timestamp(date),
                'signal_close': float(close.loc[date]),
                'score': base[setup] + min(relative_volume, 5.0) * 2,
            })
    return signals


def collect_data(codes, fetch_start, fetch_end, delay):
    price_data, signals, errors = {}, [], []
    for idx, code in enumerate(codes, 1):
        try:
            df = load_prices(code, fetch_start.strftime('%Y%m%d'), fetch_end.strftime('%Y%m%d'))
            if len(df) < 150:
                raise ValueError(f'insufficient history: {len(df)}')
            price_data[code] = df
            for item in build_signals(df):
                item['ticker'] = code
                signals.append(item)
        except Exception as exc:
            errors.append(f'{code}: {type(exc).__name__}: {exc}')
        print(f'Processed {idx}/{len(codes)}: {code}', flush=True)
        time.sleep(delay)
    return price_data, signals, errors


def simulate(price_data, signals, start_date, end_date, initial_capital, cost_pct, max_gap_pct, scenario):
    capital = float(initial_capital)
    trades, equity = [], []
    if not price_data:
        return trades, equity
    all_dates = sorted(set().union(*(set(df.index) for df in price_data.values())))
    by_date = {}
    for item in signals:
        if start_date <= item['signal_date'].date() <= end_date:
            by_date.setdefault(item['signal_date'], []).append(item)
    for items in by_date.values():
        items.sort(key=lambda x: (-x['score'], x['ticker'], x['setup']))

    position, pending = None, None
    for day in all_dates:
        if day.date() < start_date:
            continue
        if day.date() > end_date:
            break
        # A signal from the prior close is eligible only on the next market session.
        if position is None and pending is not None:
            code = pending['ticker']
            df = price_data[code]
            if day in df.index:
                opening = float(df.loc[day, '시가'])
                gap_pct = (opening / pending['signal_close'] - 1) * 100
                if opening > 0 and gap_pct <= max_gap_pct:
                    # Half the round-trip percentage is charged on each side.
                    shares = int(capital / (opening * (1 + cost_pct / 200)))
                    if shares >= 1:
                        position = {
                            'ticker': code, 'setup': pending['setup'],
                            'signal_date': str(pending['signal_date'].date()),
                            'entry_date': str(day.date()), 'entry_price': opening,
                            'shares': shares, 'entry_amount': opening * shares,
                            'days_held': 0,
                        }
            pending = None

        if position is not None and day in price_data[position['ticker']].index:
            row = price_data[position['ticker']].loc[day]
            entry = position['entry_price']
            opening, high, low, closing = (float(row[c]) for c in ('시가', '고가', '저가', '종가'))
            stop = entry * (1 - scenario['stop_pct'] / 100)
            target = entry * (1 + scenario['target_pct'] / 100)
            position['days_held'] += 1
            exit_price, reason = None, None
            if opening <= stop:
                exit_price, reason = opening, 'GAP_STOP'
            elif opening >= target:
                exit_price, reason = opening, 'GAP_TARGET'
            elif low <= stop:
                exit_price, reason = stop, 'STOP_FIRST_ASSUMPTION'
            elif high >= target:
                exit_price, reason = target, 'TARGET'
            elif position['days_held'] >= scenario['max_hold_days']:
                exit_price, reason = closing, 'TIME_EXIT'
            if exit_price is not None:
                shares = position['shares']
                gross_pct = (exit_price / entry - 1) * 100
                buy_fee = entry * shares * cost_pct / 200
                sell_fee = exit_price * shares * cost_pct / 200
                profit = (exit_price - entry) * shares - buy_fee - sell_fee
                capital += profit
                trades.append({
                    'scenario': scenario['name'], 'ticker': position['ticker'],
                    'setup': position['setup'], 'signal_date': position['signal_date'],
                    'entry_date': position['entry_date'], 'exit_date': str(day.date()),
                    'entry_price': round(entry, 2), 'exit_price': round(exit_price, 2),
                    'shares': shares, 'entry_amount': round(position['entry_amount'], 2),
                    'exit_reason': reason, 'gross_return_pct': round(gross_pct, 4),
                    'net_return_pct': round(profit / (entry * shares) * 100, 4),
                    'net_profit_krw': round(profit, 2), 'capital_after': round(capital, 2),
                })
                position = None

        # No same-day re-entry after a sale: signals are evaluated after the close.
        if position is None and pending is None:
            choices = by_date.get(day, [])
            if choices:
                pending = choices[0]

        estimated = capital
        if position is not None:
            code = position['ticker']
            df = price_data[code]
            if day in df.index:
                closing = float(df.loc[day, '종가'])
                estimated += (closing - position['entry_price']) * position['shares']
                estimated -= (position['entry_price'] + closing) * position['shares'] * cost_pct / 200
        equity.append({
            'scenario': scenario['name'], 'date': str(day.date()),
            'equity_krw': round(estimated, 2),
            'holding_ticker': position['ticker'] if position is not None else '',
        })
    return trades, equity


def summarize(trades, equity, initial_capital, scenario):
    df, curve = pd.DataFrame(trades), pd.DataFrame(equity)
    final_equity = float(curve.iloc[-1]['equity_krw']) if not curve.empty else float(initial_capital)
    if not curve.empty:
        values = pd.concat([pd.Series([float(initial_capital)]), curve['equity_krw'].astype(float)], ignore_index=True)
        mdd = float(((values / values.cummax()) - 1).min() * 100)
    else:
        mdd = 0.0
    if not df.empty:
        pnl = df['net_profit_krw'].astype(float)
        wins, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
        win_rate = float((pnl > 0).mean() * 100)
        pf = float(wins / losses) if losses > 0 else None
        avg = float(df['net_return_pct'].mean())
    else:
        win_rate, pf, avg = 0.0, None, 0.0
    return {
        'scenario': scenario['name'], 'stop_pct': scenario['stop_pct'],
        'target_pct': scenario['target_pct'], 'max_hold_days': scenario['max_hold_days'],
        'initial_capital_krw': initial_capital, 'final_equity_krw': round(final_equity, 2),
        'total_return_pct': round((final_equity / initial_capital - 1) * 100, 3),
        'max_drawdown_pct': round(mdd, 3), 'completed_trades': len(trades),
        'win_rate_pct': round(win_rate, 2), 'average_net_return_pct': round(avg, 3),
        'profit_factor': round(pf, 3) if pf is not None else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--days', type=int, default=365)
    parser.add_argument('--delay', type=float, default=0.2)
    parser.add_argument('--capital', type=int, default=1000000)
    parser.add_argument('--cost-pct', type=float, default=0.35)
    parser.add_argument('--max-gap-pct', type=float, default=3.0)
    args = parser.parse_args()
    if args.limit < 1 or args.days < 30 or args.capital <= 0 or args.delay < 0 or args.cost_pct < 0:
        parser.error('Invalid limit, days, capital, delay or cost')
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    end_date = now.date()
    start_date = end_date - timedelta(days=args.days)
    fetch_start = start_date - timedelta(days=550)
    codes = load_codes(args.limit)
    prices, signals, errors = collect_data(codes, fetch_start, end_date, args.delay)
    all_trades, all_equity, summaries = [], [], []
    for scenario in SCENARIOS:
        trades, equity = simulate(prices, signals, start_date, end_date, args.capital,
                                  args.cost_pct, args.max_gap_pct, scenario)
        all_trades.extend(trades)
        all_equity.extend(equity)
        summaries.append(summarize(trades, equity, args.capital, scenario))
    pd.DataFrame(all_trades, columns=TRADE_COLUMNS).to_csv(
        OUT / 'backtest_portfolio_trades.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(all_equity, columns=['scenario', 'date', 'equity_krw', 'holding_ticker']).to_csv(
        OUT / 'backtest_equity.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(summaries).to_csv(OUT / 'backtest_scenarios.csv', index=False, encoding='utf-8-sig')
    status = {
        'version': 'C3 portfolio exploratory scenario comparison 0.3',
        'run_kst': now.isoformat(), 'evaluation_days': args.days,
        'initial_capital_krw': args.capital, 'round_trip_cost_pct': args.cost_pct,
        'max_entry_gap_pct': args.max_gap_pct, 'requested_sample_count': len(codes),
        'successful_tickers': len(prices), 'errors': errors, 'scenarios': summaries,
        'trade_approval': 'NO',
        'limitations': [
            'Current candidates only: severe selection and survivorship bias',
            'Scenario comparison is exploratory and not an optimized or out-of-sample result',
            'Daily OHLCV cannot establish intraday stop/target order; stop assumed first',
            'One-stock allocation and next-open fills are hypothetical',
            'No market-wide historical point-in-time screening, liquidity constraints or realistic slippage model',
            'Open positions at end are marked to market with estimated exit fees',
            'No guarantee of profitability or live trade suitability',
        ],
    }
    (OUT / 'backtest_portfolio_status.json').write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
