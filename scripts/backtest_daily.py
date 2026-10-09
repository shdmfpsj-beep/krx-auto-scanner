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
COST_PCT = 0.35  # Round-trip assumed fees, taxes and slippage combined.
HOLD_DAYS = (1, 3, 5)


def load_codes(limit):
    file = OUT / 'candidates.csv'
    if not file.exists():
        raise FileNotFoundError('Run full_scan first: reports/candidates.csv missing')
    df = pd.read_csv(file, dtype={'ticker': str})
    if 'ticker' not in df:
        raise ValueError('ticker column missing')
    codes = df['ticker'].dropna().str.zfill(6).drop_duplicates().tolist()
    return codes[:limit]


def load_prices(code, start, end):
    df = stock.get_market_ohlcv_by_date(start, end, code, adjusted=True)
    if df is None or df.empty:
        raise ValueError('empty price history')
    df = df.sort_index()
    df = df.loc[~df.index.duplicated(keep='last')].copy()
    for col in ('시가', '고가', '종가', '거래량'):
        if col not in df:
            raise ValueError(f'missing {col}')
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['시가', '고가', '종가', '거래량'])
    return df[(df['시가'] > 0) & (df['종가'] > 0)]


def signals(df):
    close = df['종가'].astype(float)
    high = df['고가'].astype(float)
    volume = df['거래량'].astype(float)
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    ma120 = close.rolling(120).mean()
    previous_volume = volume.shift(1).rolling(20).mean()
    rvol = volume / previous_volume.replace(0, np.nan)
    prior_high20 = high.shift(1).rolling(20).max()
    breakout = (close > prior_high20) & (rvol >= 1.5) & (close > ma60)
    pullback = (ma20 > ma60) & (ma60 > ma120) & ((close / ma20 - 1).abs() <= .035) & (close > ma20)
    reversal = (close.shift(1) < ma60.shift(1)) & (close > ma60) & (ma20 > ma20.shift(5))
    weekly = close.resample('W-FRI').last().dropna()
    monthly = close.resample('ME').last().dropna()
    weekly_ok = weekly > weekly.rolling(10).mean()
    monthly_ok = monthly > monthly.rolling(6).mean()
    # A completed week/month can only become available at the period end.
    # Use previous completed period for each daily observation.
    weekly_daily = weekly_ok.shift(1).reindex(close.index, method='ffill').fillna(False)
    monthly_daily = monthly_ok.shift(1).reindex(close.index, method='ffill').fillna(False)
    trend = weekly_daily & monthly_daily
    return {'BREAKOUT': breakout & trend, 'PULLBACK_PROXY': pullback & trend,
            'REVERSAL_PROXY': reversal & trend}


def backtest_one(code, df, start_date, end_date):
    results = []
    flags = signals(df)
    opens = df['시가'].to_numpy(dtype=float)
    closes = df['종가'].to_numpy(dtype=float)
    dates = pd.DatetimeIndex(df.index)
    for setup, series in flags.items():
        positions = np.flatnonzero(series.fillna(False).to_numpy())
        for i in positions:
            if dates[i].date() < start_date or dates[i].date() > end_date:
                continue
            for hold in HOLD_DAYS:
                exit_idx = i + hold
                entry_idx = i + 1
                if exit_idx >= len(df) or entry_idx >= len(df):
                    continue
                entry = opens[entry_idx]
                exit_price = closes[exit_idx]
                if entry <= 0 or exit_price <= 0:
                    continue
                gross_pct = (exit_price / entry - 1) * 100
                net_pct = gross_pct - COST_PCT
                results.append({
                    'ticker': code, 'setup': setup, 'signal_date': str(dates[i].date()),
                    'entry_date': str(dates[entry_idx].date()), 'exit_date': str(dates[exit_idx].date()),
                    'holding_days': hold, 'entry_open': round(entry, 2),
                    'exit_close': round(exit_price, 2), 'gross_return_pct': round(gross_pct, 4),
                    'net_return_pct': round(net_pct, 4)
                })
    return results


def summarize(trades):
    summary = []
    for (setup, hold), group in trades.groupby(['setup', 'holding_days']):
        r = group['net_return_pct'].astype(float)
        profits = r[r > 0].sum()
        losses = -r[r < 0].sum()
        summary.append({
            'setup': setup, 'holding_days': int(hold), 'signals': len(group),
            'distinct_tickers': int(group['ticker'].nunique()),
            'win_rate_pct': round(float((r > 0).mean() * 100), 2),
            'mean_net_return_pct': round(float(r.mean()), 3),
            'median_net_return_pct': round(float(r.median()), 3),
            'profit_factor': round(float(profits / losses), 3) if losses > 0 else None,
            'note': 'Overlapping hypothetical signals; not a portfolio equity curve'
        })
    return pd.DataFrame(summary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=20, help='Current candidates to sample')
    parser.add_argument('--days', type=int, default=365, help='Historical signal evaluation window')
    parser.add_argument('--delay', type=float, default=0.2)
    args = parser.parse_args()
    if args.limit < 1 or args.days < 30:
        parser.error('limit >= 1 and days >= 30 required')
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    end = now.date()
    start_date = end - timedelta(days=args.days)
    fetch_start = start_date - timedelta(days=550)
    fetch_end = end + timedelta(days=10)
    codes = load_codes(args.limit)
    rows, errors = [], []
    for idx, code in enumerate(codes, 1):
        try:
            df = load_prices(code, fetch_start.strftime('%Y%m%d'), fetch_end.strftime('%Y%m%d'))
            if len(df) < 150:
                raise ValueError(f'insufficient history: {len(df)}')
            rows.extend(backtest_one(code, df, start_date, end))
        except Exception as exc:
            errors.append(f'{code}: {type(exc).__name__}: {exc}')
        print(f'Processed {idx}/{len(codes)}: {code}', flush=True)
        time.sleep(args.delay)
    trade_file = OUT / 'backtest_trades.csv'
    summary_file = OUT / 'backtest_summary.csv'
    if rows:
        trades = pd.DataFrame(rows).sort_values(['signal_date', 'ticker', 'holding_days'])
        trades.to_csv(trade_file, index=False, encoding='utf-8-sig')
        summary = summarize(trades)
        summary.to_csv(summary_file, index=False, encoding='utf-8-sig')
    else:
        trade_file.unlink(missing_ok=True)
        summary_file.unlink(missing_ok=True)
    status = {
        'version': 'C3 exploratory backtest 0.1', 'run_kst': now.isoformat(),
        'sample_method': 'CURRENT_CANDIDATES_ONLY (SURVIVORSHIP AND SELECTION BIAS)',
        'sample_count': len(codes), 'successful_count': len(codes) - len(errors),
        'signals_count': len(rows), 'evaluation_days': args.days,
        'holding_days': list(HOLD_DAYS), 'round_trip_cost_pct': COST_PCT,
        'trade_approval': 'NO', 'errors': errors,
        'limitations': [
            'Current candidate sample is not historical point-in-time universe',
            'Signals may overlap; statistics are not a tradable portfolio',
            'Entry at next-day open and exit at closing price are hypothetical',
            'No intraday stops, liquidity impact or actual order execution',
            'Adjusted OHLCV and estimated transaction costs may differ from real trades',
            'Weekly/monthly filters use previous completed periods conservatively',
            'Not an out-of-sample validation or a strategy performance claim'
        ]
    }
    (OUT / 'backtest_status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if not rows:
        raise RuntimeError('No backtest signals. Check reports/backtest_status.json')


if __name__ == '__main__':
    main()
