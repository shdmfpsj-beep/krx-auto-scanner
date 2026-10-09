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

POLICIES = [
    {'name': 'B_no_breakout', 'setups': ('PULLBACK_PROXY', 'REVERSAL_PROXY'), 'cooldown': 0, 'risk_pct': None, 'market': 'none'},
    {'name': 'E_market_own_index', 'setups': ('PULLBACK_PROXY', 'REVERSAL_PROXY'), 'cooldown': 0, 'risk_pct': None, 'market': 'own'},
    {'name': 'F_market_both_indices', 'setups': ('PULLBACK_PROXY', 'REVERSAL_PROXY'), 'cooldown': 0, 'risk_pct': None, 'market': 'both'},
    {'name': 'G_market_own_risk1', 'setups': ('PULLBACK_PROXY', 'REVERSAL_PROXY'), 'cooldown': 0, 'risk_pct': 1.0, 'market': 'own'},
]

TRADE_COLUMNS = [
    'policy', 'ticker', 'setup', 'signal_date', 'entry_date', 'exit_date',
    'entry_price', 'exit_price', 'shares', 'entry_amount', 'exit_reason',
    'gross_return_pct', 'net_return_pct', 'net_profit_krw', 'capital_after',
]
EQUITY_COLUMNS = ['policy', 'date', 'equity_krw', 'holding_ticker']


def load_codes(limit):
    path = OUT / 'candidates.csv'
    if not path.exists():
        raise FileNotFoundError('Run full_scan first: reports/candidates.csv missing')
    df = pd.read_csv(path, dtype={'ticker': str})
    if 'ticker' not in df.columns:
        raise ValueError('ticker column missing')
    codes = df['ticker'].dropna().astype(str).str.zfill(6)
    return codes[codes.str.fullmatch(r'\d{6}')].drop_duplicates().tolist()[:limit]


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
    df = df[(df[['시가', '고가', '저가', '종가']] > 0).all(axis=1)].copy()
    return df


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
    trend = (weekly_ok.shift(1).reindex(close.index, method='ffill').fillna(False)
             & monthly_ok.shift(1).reindex(close.index, method='ffill').fillna(False))
    flags = {
        'REVERSAL_PROXY': reversal & trend,
        'PULLBACK_PROXY': pullback & trend,
        'BREAKOUT': breakout & trend,
    }
    base = {'REVERSAL_PROXY': 80, 'PULLBACK_PROXY': 70, 'BREAKOUT': 60}
    signals = []
    for setup, flag in flags.items():
        for day in df.index[flag.fillna(False)]:
            rv = float(rvol.loc[day]) if pd.notna(rvol.loc[day]) else 0.0
            signals.append({
                'setup': setup, 'signal_date': pd.Timestamp(day),
                'signal_close': float(close.loc[day]),
                'score': base[setup] + min(rv, 5.0) * 2,
            })
    return signals


def collect_data(codes, start, end, delay):
    prices, signals, errors = {}, [], []
    for i, code in enumerate(codes, 1):
        try:
            df = load_prices(code, start.strftime('%Y%m%d'), end.strftime('%Y%m%d'))
            if len(df) < 150:
                raise ValueError(f'insufficient history: {len(df)}')
            prices[code] = df
            for signal in build_signals(df):
                signal['ticker'] = code
                signals.append(signal)
        except Exception as exc:
            errors.append(f'{code}: {type(exc).__name__}: {exc}')
        print(f'Processed {i}/{len(codes)}: {code}', flush=True)
        if delay:
            time.sleep(delay)
    return prices, signals, errors


def load_market_gates(start, end):
    """Use pykrx indices, falling back to FinanceDataReader if KRX metadata fails.

    Never replace missing index observations with a permissive gate.
    """
    gates = {}
    for label, ticker, fdr_symbol in (
        ('KOSPI', '1001', 'KS11'), ('KOSDAQ', '2001', 'KQ11')
    ):
        primary_error = None
        try:
            df = stock.get_index_ohlcv_by_date(
                start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker
            )
            if df is None or df.empty or '종가' not in df.columns:
                raise ValueError('No valid index OHLCV returned')
            close = pd.to_numeric(df['종가'], errors='coerce')
            close.index = pd.to_datetime(close.index)
            close = close.dropna().sort_index()
        except Exception as exc:
            primary_error = f'{type(exc).__name__}: {exc}'
            try:
                import FinanceDataReader as fdr
                fallback = fdr.DataReader(fdr_symbol, start.strftime('%Y-%m-%d'),
                                          (end + timedelta(days=1)).strftime('%Y-%m-%d'))
                if fallback is None or fallback.empty or 'Close' not in fallback.columns:
                    raise ValueError('No valid fallback index Close returned')
                close = pd.to_numeric(fallback['Close'], errors='coerce')
                close.index = pd.to_datetime(close.index)
                close = close.dropna().sort_index()
                print(f'{label}: pykrx failed ({primary_error}); '
                      'using FinanceDataReader fallback', flush=True)
            except Exception as fallback_exc:
                raise RuntimeError(
                    f'{label} index data unavailable. pykrx: {primary_error}; '
                    f'FinanceDataReader: {type(fallback_exc).__name__}: {fallback_exc}. '
                    'Market filter was NOT bypassed.'
                ) from fallback_exc
        close = close[~close.index.duplicated(keep='last')]
        close = close[(close.index.date >= start) & (close.index.date <= end)]
        if len(close) < 70:
            raise RuntimeError(f'Insufficient market index history: {label} '
                               f'({len(close)} rows); market filter NOT bypassed')
        ma60 = close.rolling(60).mean()
        gates[label] = ((close > ma60) & (ma60 > ma60.shift(5))).fillna(False)
    return gates


def load_market_membership(codes, end_date):
    """Classify current KRX listings; never infer a market from ticker digits."""
    requested = set(codes)
    kospi, kosdaq = set(), set()
    errors = []
    for market, destination in (('KOSPI', kospi), ('KOSDAQ', kosdaq)):
        try:
            found = stock.get_market_ticker_list(end_date.strftime('%Y%m%d'), market=market)
            if found:
                destination.update(set(map(str, found)) & requested)
        except Exception as exc:
            errors.append(f'pykrx {market}: {type(exc).__name__}: {exc}')

    missing = requested - kospi - kosdaq
    if missing:
        try:
            import FinanceDataReader as fdr
            listing = fdr.StockListing('KRX')
            if listing is None or listing.empty:
                raise ValueError('Empty KRX listing')
            code_col = next((c for c in ('Code', 'Symbol', '종목코드') if c in listing.columns), None)
            market_col = next((c for c in ('Market', '시장구분', '시장') if c in listing.columns), None)
            if code_col is None or market_col is None:
                raise ValueError(f'Listing columns lack code/market: {list(listing.columns)}')
            for code, market in zip(listing[code_col], listing[market_col]):
                normalized = str(code).strip().split('.')[0].zfill(6)
                if normalized not in missing:
                    continue
                label = str(market).strip().upper()
                if label in ('KOSPI', 'KOSDAQ'):
                    (kospi if label == 'KOSPI' else kosdaq).add(normalized)
            print('Market classification: FinanceDataReader KRX fallback checked', flush=True)
        except Exception as exc:
            errors.append(f'FinanceDataReader KRX listing: {type(exc).__name__}: {exc}')

    ambiguous = kospi & kosdaq
    if ambiguous:
        raise RuntimeError(f'Ambiguous market membership: {sorted(ambiguous)}')
    missing = requested - kospi - kosdaq
    if missing:
        raise RuntimeError(
            f'Market classification unavailable for {sorted(missing)}; '
            f'errors={errors}. Market filter NOT bypassed.'
        )
    return kospi, kosdaq


def ticker_market(code):
    # pykrx market classification; do not guess if unavailable.
    kospi = ticker_market.kospi
    kosdaq = ticker_market.kosdaq
    if code in kospi:
        return 'KOSPI'
    if code in kosdaq:
        return 'KOSDAQ'
    return None


def market_pass(day, code, mode, gates):
    if mode == 'none':
        return True
    own = ticker_market(code)
    if own is None:
        return False
    targets = (own,) if mode == 'own' else ('KOSPI', 'KOSDAQ')
    for label in targets:
        series = gates[label]
        # Require a genuine observation on signal date, not a future index value.
        if day not in series.index or not bool(series.loc[day]):
            return False
    return True


def simulate(prices, signals, start_date, end_date, capital, cost_pct,
             max_gap_pct, stop_pct, target_pct, max_hold_days, policy, gates):
    capital = float(capital)
    trades, equity = [], []
    if not prices:
        return trades, equity
    dates = sorted(set().union(*(set(df.index) for df in prices.values())))
    date_positions = {day: i for i, day in enumerate(dates)}
    by_date = {}
    for item in signals:
        day = item['signal_date']
        if not (start_date <= day.date() <= end_date):
            continue
        if policy['setups'] is not None and item['setup'] not in policy['setups']:
            continue
        if not market_pass(day, item['ticker'], policy['market'], gates):
            continue
        by_date.setdefault(day, []).append(item)
    for choices in by_date.values():
        choices.sort(key=lambda x: (-x['score'], x['ticker'], x['setup']))

    position, pending = None, None
    cooldown_until = {}
    last_close = {}
    fee_rate = cost_pct / 200.0
    for day in dates:
        if not (start_date <= day.date() <= end_date):
            continue
        for code, df in prices.items():
            if day in df.index:
                last_close[code] = float(df.loc[day, '종가'])

        if position is None and pending is not None:
            item = pending
            pending = None
            code = item['ticker']
            df = prices[code]
            # Only next global trading session; never fill an old signal later.
            if (date_positions[day] == date_positions[item['signal_date']] + 1
                    and day in df.index):
                opening = float(df.loc[day, '시가'])
                gap = (opening / item['signal_close'] - 1) * 100
                if opening > 0 and gap <= max_gap_pct:
                    shares = int(capital / (opening * (1 + fee_rate)))
                    if policy['risk_pct'] is not None:
                        planned_loss = opening * (stop_pct / 100 + fee_rate * (2 - stop_pct / 100))
                        risk_shares = int(capital * policy['risk_pct'] / 100 / planned_loss)
                        shares = min(shares, risk_shares)
                    if shares >= 1:
                        position = {
                            'ticker': code, 'setup': item['setup'],
                            'signal_date': str(item['signal_date'].date()),
                            'entry_date': str(day.date()), 'entry_price': opening,
                            'shares': shares, 'entry_amount': opening * shares,
                            'days_held': 0,
                        }

        if position is not None and day in prices[position['ticker']].index:
            row = prices[position['ticker']].loc[day]
            entry = position['entry_price']
            opening, high, low, closing = (float(row[c]) for c in ('시가', '고가', '저가', '종가'))
            stop, target = entry * (1 - stop_pct / 100), entry * (1 + target_pct / 100)
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
            elif position['days_held'] >= max_hold_days:
                exit_price, reason = closing, 'TIME_EXIT'
            if exit_price is not None:
                shares = position['shares']
                pnl = (exit_price - entry) * shares - (entry + exit_price) * shares * fee_rate
                capital += pnl
                trades.append({
                    'policy': policy['name'], 'ticker': position['ticker'],
                    'setup': position['setup'], 'signal_date': position['signal_date'],
                    'entry_date': position['entry_date'], 'exit_date': str(day.date()),
                    'entry_price': round(entry, 2), 'exit_price': round(exit_price, 2),
                    'shares': shares, 'entry_amount': round(position['entry_amount'], 2),
                    'exit_reason': reason,
                    'gross_return_pct': round((exit_price / entry - 1) * 100, 4),
                    'net_return_pct': round(pnl / (entry * shares) * 100, 4),
                    'net_profit_krw': round(pnl, 2), 'capital_after': round(capital, 2),
                })
                if reason in ('GAP_STOP', 'STOP_FIRST_ASSUMPTION') and policy['cooldown']:
                    ticker_dates = prices[position['ticker']].index
                    idx = ticker_dates.get_loc(day)
                    cooldown_until[position['ticker']] = ticker_dates[
                        min(idx + policy['cooldown'], len(ticker_dates) - 1)]
                position = None

        if position is None and pending is None:
            for item in by_date.get(day, []):
                blocked = cooldown_until.get(item['ticker'])
                if blocked is not None and day <= blocked:
                    continue
                pending = item
                break

        estimated = capital
        if position is not None:
            closing = last_close.get(position['ticker'], position['entry_price'])
            entry, shares = position['entry_price'], position['shares']
            estimated += (closing - entry) * shares - (entry + closing) * shares * fee_rate
        equity.append({
            'policy': policy['name'], 'date': str(day.date()),
            'equity_krw': round(estimated, 2),
            'holding_ticker': position['ticker'] if position else '',
        })
    return trades, equity


def summarize(trades, equity, initial_capital, name):
    df = pd.DataFrame(trades)
    curve = pd.DataFrame(equity)
    final = float(curve.iloc[-1]['equity_krw']) if not curve.empty else float(initial_capital)
    if not curve.empty:
        values = pd.concat([pd.Series([float(initial_capital)]), curve['equity_krw'].astype(float)], ignore_index=True)
        mdd = float((values / values.cummax() - 1).min() * 100)
    else:
        mdd = 0.0
    if not df.empty:
        pnl = df['net_profit_krw'].astype(float)
        gains, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
        pf = float(gains / losses) if losses > 0 else None
        win = float((pnl > 0).mean() * 100)
        avg = float(df['net_return_pct'].mean())
    else:
        pf, win, avg = None, 0.0, 0.0
    return {
        'policy': name, 'initial_capital_krw': initial_capital,
        'final_equity_krw': round(final, 2),
        'total_return_pct': round((final / initial_capital - 1) * 100, 3),
        'max_drawdown_pct': round(mdd, 3), 'completed_trades': len(trades),
        'win_rate_pct': round(win, 2), 'average_net_return_pct': round(avg, 3),
        'profit_factor': round(pf, 3) if pf is not None else None,
    }


def write_diagnostics(prices, signals, gates, start_date, end_date, trades):
    """Audit market gates and actual executed trades without changing simulation."""
    days = sorted(set(gates['KOSPI'].index) | set(gates['KOSDAQ'].index))
    rows = []
    for day in days:
        if not start_date <= day.date() <= end_date:
            continue
        k1 = bool(gates['KOSPI'].get(day, False))
        k2 = bool(gates['KOSDAQ'].get(day, False))
        rows.append({'date': str(day.date()), 'kospi_pass': k1,
                     'kosdaq_pass': k2, 'both_pass': k1 and k2,
                     'gates_disagree': k1 != k2})
    pd.DataFrame(rows).to_csv(OUT / 'backtest_v07_index_gate_audit.csv',
                              index=False, encoding='utf-8-sig')

    signal_rows = []
    for item in signals:
        day = item['signal_date']
        if not start_date <= day.date() <= end_date:
            continue
        if item['setup'] not in POLICIES[0]['setups']:
            continue
        own = ticker_market(item['ticker'])
        own_pass = market_pass(day, item['ticker'], 'own', gates)
        both_pass = market_pass(day, item['ticker'], 'both', gates)
        signal_rows.append({
            'signal_date': str(day.date()), 'ticker': item['ticker'],
            'market': own, 'setup': item['setup'],
            'own_index_pass': own_pass, 'both_indices_pass': both_pass,
            'different_gate_result': own_pass != both_pass,
        })
    pd.DataFrame(signal_rows, columns=[
        'signal_date', 'ticker', 'market', 'setup', 'own_index_pass',
        'both_indices_pass', 'different_gate_result'
    ]).to_csv(OUT / 'backtest_v07_signal_gate_audit.csv',
              index=False, encoding='utf-8-sig')

    executions = pd.DataFrame(trades)
    comparison = []
    if not executions.empty:
        for policy in ('B_no_breakout', 'E_market_own_index',
                       'F_market_both_indices', 'G_market_own_risk1'):
            part = executions[executions['policy'] == policy].copy()
            keys = set(zip(part['ticker'], part['signal_date'],
                           part['entry_date'], part['exit_date'], part['setup']))
            comparison.append((policy, keys))
        base = comparison[0][1]
        audit = []
        for name, keys in comparison:
            audit.append({'policy': name, 'trade_count': len(keys),
                          'only_in_B_count': len(base - keys),
                          'only_in_policy_count': len(keys - base),
                          'same_trades_as_B': keys == base})
        pd.DataFrame(audit).to_csv(OUT / 'backtest_v07_execution_audit.csv',
                                   index=False, encoding='utf-8-sig')
        e = executions[executions['policy'] == 'E_market_own_index'].copy()
        e['is_stop'] = e['exit_reason'].isin(('GAP_STOP', 'STOP_FIRST_ASSUMPTION'))
        e['stop_streak'] = e['is_stop'].groupby((~e['is_stop']).cumsum()).cumsum()
        e[['ticker', 'signal_date', 'entry_date', 'exit_date', 'exit_reason',
           'net_return_pct', 'net_profit_krw', 'stop_streak']].to_csv(
               OUT / 'backtest_v07_stop_streak_audit.csv', index=False,
               encoding='utf-8-sig')
    return {'index_gate_disagreement_days': sum(r['gates_disagree'] for r in rows),
            'signal_gate_disagreements': sum(r['different_gate_result'] for r in signal_rows),
            'signal_count': len(signal_rows)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--days', type=int, default=365)
    parser.add_argument('--delay', type=float, default=0.2)
    parser.add_argument('--capital', type=int, default=1000000)
    parser.add_argument('--cost-pct', type=float, default=0.35)
    parser.add_argument('--max-gap-pct', type=float, default=3.0)
    parser.add_argument('--stop-pct', type=float, default=4.0)
    parser.add_argument('--target-pct', type=float, default=8.0)
    parser.add_argument('--max-hold-days', type=int, default=7)
    args = parser.parse_args()
    if (args.limit < 1 or args.days < 60 or args.capital <= 0 or args.delay < 0
            or args.cost_pct < 0 or args.max_gap_pct < 0
            or not 0 < args.stop_pct < 100 or args.target_pct <= 0
            or args.max_hold_days < 1):
        parser.error('Invalid arguments')
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    end_date = now.date()
    start_date = end_date - timedelta(days=args.days)
    fetch_start = start_date - timedelta(days=550)
    codes = load_codes(args.limit)
    prices, signals, errors = collect_data(codes, fetch_start, end_date, args.delay)
    gates = load_market_gates(fetch_start, end_date)
    ticker_market.kospi, ticker_market.kosdaq = load_market_membership(
        list(prices), end_date
    )
    if not prices:
        raise RuntimeError('No valid price histories; see errors above')

    all_trades, all_equity, comparisons, splits = [], [], [], []
    mid_date = start_date + timedelta(days=args.days // 2)
    for policy in POLICIES:
        trades, equity = simulate(prices, signals, start_date, end_date, args.capital,
                                  args.cost_pct, args.max_gap_pct, args.stop_pct,
                                  args.target_pct, args.max_hold_days, policy, gates)
        all_trades.extend(trades)
        all_equity.extend(equity)
        comparisons.append(summarize(trades, equity, args.capital, policy['name']))
        # Independent flat-start half-period tests. This is NOT true out-of-sample
        # because policies and the present-day candidate universe were already selected.
        for label, period_start, period_end in (
            ('first_half', start_date, mid_date - timedelta(days=1)),
            ('second_half', mid_date, end_date),
        ):
            part_trades, part_equity = simulate(
                prices, signals, period_start, period_end, args.capital,
                args.cost_pct, args.max_gap_pct, args.stop_pct,
                args.target_pct, args.max_hold_days, policy, gates)
            result = summarize(part_trades, part_equity, args.capital, policy['name'])
            result['period'] = label
            result['start_date'] = str(period_start)
            result['end_date'] = str(period_end)
            splits.append(result)

    pd.DataFrame(all_trades, columns=TRADE_COLUMNS).to_csv(
        OUT / 'backtest_v07_trades.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(all_equity, columns=EQUITY_COLUMNS).to_csv(
        OUT / 'backtest_v07_equity.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(comparisons).to_csv(
        OUT / 'backtest_v07_comparison.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(splits).to_csv(
        OUT / 'backtest_v07_periods.csv', index=False, encoding='utf-8-sig')
    diagnostics = write_diagnostics(prices, signals, gates, start_date, end_date, all_trades)
    status = {
        'version': 'C3 exploratory v0.7 diagnostic', 'run_kst': now.isoformat(),
        'evaluation_days': args.days, 'initial_capital_krw': args.capital,
        'sample_count': len(codes), 'successful_tickers': len(prices),
        'errors': errors, 'stop_pct': args.stop_pct,
        'target_pct': args.target_pct, 'max_hold_days': args.max_hold_days,
        'comparison': comparisons, 'period_comparison': splits, 'diagnostics': diagnostics,
        'market_gate': 'signal-day index close > MA60 and MA60 > MA60 five sessions ago',
        'trade_approval': 'NO',
        'limitations': [
            'Present-day candidate selection creates severe look-ahead and survivorship bias',
            'Strategies and parameters were developed after reviewing prior test results',
            'Period splits are diagnostic only, NOT genuine out-of-sample validation',
            'Market filters were introduced after viewing v0.5 results: additional overfitting risk',
            'v0.7 is diagnostics only; policy logic unchanged from v0.6',
            'Current market classification may not match historical listing market',
            'Historical signals use simplified proxies and not full C3 screening rules',
            'Daily OHLCV cannot resolve intraday order; stop assumed first',
            'Assumed next-open fills, simple symmetric costs, no liquidity/slippage impact',
            'Unclosed positions are marked to market, not counted as completed trades',
            'Single position at a time; stop-loss can gap beyond planned risk',
        ],
    }
    (OUT / 'backtest_v07_status.json').write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
