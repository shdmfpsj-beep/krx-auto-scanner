"""C3 v1.1 historical-universe availability diagnostic and PIT candidate pilot.

Research only. Never replaces missing historical membership with today's listing.
If pykrx historical membership is unavailable, exits nonzero with detailed status.
"""
import argparse
import json
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from pykrx import stock

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports'
OUT.mkdir(parents=True, exist_ok=True)


def valid_codes(values):
    return {str(x).strip() for x in (values or []) if str(x).strip().isdigit() and len(str(x).strip()) == 6}


def get_universe(day, retries, delay, errors):
    ymd = day.strftime('%Y%m%d')
    for attempt in range(1, retries + 1):
        try:
            kp = valid_codes(stock.get_market_ticker_list(ymd, market='KOSPI'))
            kd = valid_codes(stock.get_market_ticker_list(ymd, market='KOSDAQ'))
            codes = {code: 'KOSPI' for code in kp}
            codes.update({code: 'KOSDAQ' for code in kd})
            if len(codes) > 1000:
                return codes
            errors.append(f'{ymd} attempt {attempt}: too few codes: KOSPI={len(kp)}, KOSDAQ={len(kd)}')
        except Exception as exc:
            errors.append(f'{ymd} attempt {attempt}: {type(exc).__name__}: {str(exc)[:150]}')
        if attempt < retries:
            time.sleep(delay * attempt)
    return None


def fetch_prices(code, start, end):
    df = stock.get_market_ohlcv_by_date(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), code, adjusted=True)
    if df is None or df.empty:
        return None
    df = df.rename(columns={'시가': 'open', '고가': 'high', '저가': 'low', '종가': 'close', '거래량': 'volume', '거래대금': 'turnover'})
    if not {'open', 'high', 'low', 'close', 'volume'}.issubset(df.columns):
        return None
    df.index = pd.to_datetime(df.index).normalize()
    df = df[~df.index.duplicated(keep='last')].sort_index()
    for col in ('open', 'high', 'low', 'close', 'volume', 'turnover'):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


def signals(df):
    c, v, h = df['close'], df['volume'], df['high']
    ma20, ma60, ma120 = (c.rolling(n, min_periods=n).mean() for n in (20, 60, 120))
    rvol = v / v.shift(1).rolling(20, min_periods=20).mean().replace(0, float('nan'))
    breakout = (c > h.shift(1).rolling(20, min_periods=20).max()) & (rvol >= 1.5) & (c > ma60)
    pullback = (ma20 > ma60) & (ma60 > ma120) & ((c / ma20 - 1).abs() <= .035) & (c > ma20)
    reversal = (c.shift(1) < ma60.shift(1)) & (c > ma60) & (ma20 > ma20.shift(5))
    weekly = c.resample('W-FRI').last().dropna()
    monthly = c.resample('ME').last().dropna()
    # Shift by one full calendar period: no current incomplete week/month used.
    w = (weekly > weekly.rolling(10, min_periods=10).mean()).shift(1)
    m = (monthly > monthly.rolling(6, min_periods=6).mean()).shift(1)
    out = pd.DataFrame(index=df.index)
    out['breakout'] = breakout.fillna(False)
    out['first_pullback_proxy'] = pullback.fillna(False)
    out['reversal_proxy'] = reversal.fillna(False)
    out['weekly_filter'] = w.reindex(out.index, method='ffill').fillna(False).astype(bool)
    out['monthly_filter'] = m.reindex(out.index, method='ffill').fillna(False).astype(bool)
    out['rvol20'] = rvol
    out['close'] = c
    out['volume'] = v
    out['turnover_krw'] = df['turnover'] if 'turnover' in df else c * v
    out['score'] = 3 * (out['breakout'].astype(int) + out['first_pullback_proxy'].astype(int) + out['reversal_proxy'].astype(int)) + out['weekly_filter'].astype(int) + out['monthly_filter'].astype(int)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--days', type=int, default=30)
    p.add_argument('--limit', type=int, default=30)
    p.add_argument('--delay', type=float, default=.2)
    p.add_argument('--retries', type=int, default=2)
    args = p.parse_args()
    if args.days < 1 or args.limit < 1 or args.retries < 1 or args.delay < 0:
        p.error('days, limit, retries must be positive; delay must be nonnegative')
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    end = now.date() - timedelta(days=1)
    start = end - timedelta(days=args.days - 1)
    status = {
        'version': 'C3 v1.1 historical universe diagnostic pilot',
        'run_kst': now.isoformat(), 'requested_start': str(start), 'requested_end': str(end),
        'ticker_limit': args.limit, 'universe_dates': 0, 'universe_dates_attempted': 0,
        'universe_dates_failed': 0, 'historical_universe_size': 0,
        'attempted': 0, 'succeeded': 0, 'candidates': 0,
        'universe_source': 'pykrx historical dated ticker list ONLY',
        'errors': [], 'pilot_complete': False, 'trade_approval': 'NO',
        'limitations': [
            'Historical KRX ticker API may be unavailable from GitHub Actions',
            'Even a successful dated ticker list does not prove delisted-stock completeness',
            'Pilot is alphabetical subset, not representative market-wide sampling',
            'Adjusted OHLCV can incorporate later corporate-action adjustments',
            'No trading simulation, slippage or costs; no trade approval',
            'Signals are calculated using same-day close; next-session entry only',
        ],
    }
    report = OUT / 'pit_v11_status.json'
    output = OUT / 'pit_candidates_v11.csv'
    try:
        universe_by_day = {}
        # Only actual weekdays; holidays may fail and are counted separately.
        for dt in pd.date_range(start, end, freq='B'):
            day = dt.date()
            status['universe_dates_attempted'] += 1
            membership = get_universe(day, args.retries, max(args.delay, .2), status['errors'])
            if membership:
                universe_by_day[dt.normalize()] = membership
            else:
                status['universe_dates_failed'] += 1
            time.sleep(args.delay)
        status['universe_dates'] = len(universe_by_day)
        if not universe_by_day:
            raise RuntimeError('Historical KRX ticker API returned no valid dated universe. No present-day fallback used.')
        # Incomplete dated universe cannot justify PIT results: fail closed.
        # Some weekday failures are holidays, so report missing days without claiming full coverage.
        all_codes = sorted(set().union(*(set(v) for v in universe_by_day.values())))
        status['historical_universe_size'] = len(all_codes)
        rows = []
        fetch_start = start - timedelta(days=550)
        for code in all_codes[:args.limit]:
            status['attempted'] += 1
            try:
                df = fetch_prices(code, fetch_start, end)
                if df is None or len(df) < 150:
                    continue
                sig = signals(df)
                status['succeeded'] += 1
                for day, membership in universe_by_day.items():
                    if code not in membership or day not in sig.index:
                        continue
                    r = sig.loc[day]
                    if not (r['breakout'] or r['first_pullback_proxy'] or r['reversal_proxy']):
                        continue
                    if pd.isna(r['rvol20']) or r['close'] <= 0 or r['volume'] <= 0:
                        continue
                    rows.append({
                        'date': day.strftime('%Y-%m-%d'), 'ticker': code,
                        'market_asof': membership[code], 'close': float(r['close']),
                        'rvol20': round(float(r['rvol20']), 3),
                        'breakout': bool(r['breakout']),
                        'first_pullback_proxy': bool(r['first_pullback_proxy']),
                        'reversal_proxy': bool(r['reversal_proxy']),
                        'weekly_filter': bool(r['weekly_filter']),
                        'monthly_filter': bool(r['monthly_filter']),
                        'score': int(r['score']), 'turnover_krw': float(r['turnover_krw']),
                    })
            except Exception as exc:
                status['errors'].append(f'prices {code}: {type(exc).__name__}: {str(exc)[:150]}')
            time.sleep(args.delay)
        cols = ['date','ticker','market_asof','close','rvol20','breakout','first_pullback_proxy','reversal_proxy','weekly_filter','monthly_filter','score','turnover_krw']
        pd.DataFrame(rows, columns=cols).sort_values(['date','score','rvol20'], ascending=[True,False,False]).to_csv(output, index=False, encoding='utf-8-sig')
        status['candidates'] = len(rows)
        status['pilot_complete'] = True
    except Exception as exc:
        status['errors'].append(f'FATAL: {type(exc).__name__}: {str(exc)[:200]}')
        output.unlink(missing_ok=True)
        raise
    finally:
        status['errors'] = status['errors'][:120]
        report.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(status, ensure_ascii=False))

if __name__ == '__main__':
    main()
