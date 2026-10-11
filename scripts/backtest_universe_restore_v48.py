#!/usr/bin/env python3
"""v4.8 historical KOSPI/KOSDAQ universe snapshot evidence collector.
Research only. Snapshot membership is not a complete PIT backtest.
"""
import argparse
import csv
import json
import time
from datetime import date, timedelta
from pathlib import Path


def month_end_days(start, end):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        d = min(date.fromordinal((date(ny, nm, 1) - timedelta(days=1)).toordinal()), end)
        if d >= start:
            yield d
        y, m = ny, nm


def write_csv(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def static_tickers(path):
    if not path.exists():
        return set(), 'MISSING_STATIC_FILE'
    with path.open(encoding='utf-8-sig', newline='') as f:
        r = csv.DictReader(f)
        cols = r.fieldnames or []
        key = next((x for x in ('ticker', 'code', 'symbol', '종목코드') if x in cols), None)
        if not key:
            return set(), 'UNKNOWN_TICKER_COLUMN:' + ','.join(cols)
        values = {str(row.get(key, '')).strip().zfill(6) for row in r if str(row.get(key, '')).strip()}
        return values, 'OK'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--start', default='2023-01-01')
    p.add_argument('--end', default='2025-12-31')
    p.add_argument('--static', default='reports/walkforward_v20_universe.csv')
    p.add_argument('--out', default='reports')
    p.add_argument('--pause', type=float, default=0.7)
    args = p.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if start > end or end > date.today():
        p.error('Dates must be ordered and must not be in the future')
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        from pykrx import stock
    except ImportError as e:
        raise SystemExit('pykrx missing: add pykrx to requirements.txt') from e

    static, static_status = static_tickers(Path(args.static))
    snapshots, members, errors = [], [], []
    union = set()
    for requested in month_end_days(start, end):
        # Previous actual business day, never next-day fallback.
        request = requested.strftime('%Y%m%d')
        try:
            actual = stock.get_nearest_business_day_in_a_week(request, prev=True)
            actual = str(actual).replace('-', '')
            if not (len(actual) == 8 and actual.isdigit() and actual <= request):
                raise ValueError('invalid asof date ' + actual)
            markets = {}
            for market in ('KOSPI', 'KOSDAQ'):
                data = None
                for attempt in range(3):
                    try:
                        data = stock.get_market_ticker_list(actual, market=market)
                        if not data:
                            raise ValueError('empty response')
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        time.sleep(2 * (attempt + 1))
                markets[market] = {str(t).strip().zfill(6) for t in data if str(t).strip()}
                time.sleep(max(args.pause, 0))
            overlap = markets['KOSPI'] & markets['KOSDAQ']
            if overlap:
                raise ValueError('market overlap: ' + ','.join(sorted(overlap)[:5]))
            all_tickers = markets['KOSPI'] | markets['KOSDAQ']
            union |= all_tickers
            for market, codes in markets.items():
                members.extend({'requested_date': requested.isoformat(), 'asof_date': actual,
                                'market': market, 'ticker': t,
                                'in_static_universe': int(t in static)} for t in sorted(codes))
            snapshots.append({'requested_date': requested.isoformat(), 'asof_date': actual,
                              'kospi': len(markets['KOSPI']), 'kosdaq': len(markets['KOSDAQ']),
                              'total': len(all_tickers), 'static_present': len(all_tickers & static),
                              'static_missing_from_market': len(static - all_tickers),
                              'market_missing_from_static': len(all_tickers - static), 'status': 'OK'})
        except Exception as exc:
            errors.append({'requested_date': requested.isoformat(), 'error': str(exc)[:250]})
            snapshots.append({'requested_date': requested.isoformat(), 'asof_date': '',
                              'kospi': '', 'kosdaq': '', 'total': '', 'static_present': '',
                              'static_missing_from_market': '', 'market_missing_from_static': '',
                              'status': 'FAILED'})
    write_csv(out / 'pit_v48_snapshots.csv', snapshots,
              ['requested_date','asof_date','kospi','kosdaq','total','static_present',
               'static_missing_from_market','market_missing_from_static','status'])
    write_csv(out / 'pit_v48_members.csv', members,
              ['requested_date','asof_date','market','ticker','in_static_universe'])
    write_csv(out / 'pit_v48_errors.csv', errors, ['requested_date','error'])
    expected = len(list(month_end_days(start, end)))
    status = 'SNAPSHOTS_COLLECTED_PIT_NOT_APPROVED' if len(snapshots) == expected and not errors and static_status == 'OK' else 'INCOMPLETE'
    meta = {'version': 'v4.8', 'status': status, 'source': 'pykrx historical KRX ticker API',
            'requested_snapshots': expected, 'successful_snapshots': expected - len(errors),
            'failed_snapshots': len(errors), 'static_file': args.static,
            'static_status': static_status, 'static_universe_size': len(static),
            'historical_union_tickers': len(union), 'historical_tickers_not_in_static': len(union-static),
            'static_tickers_not_seen_in_snapshots': len(static-union),
            'sampling_limit': 'Month-end only; not daily historical membership',
            'remaining_gaps': ['Historical OHLCV for missing securities', 'Delisting corporate action settlement',
                               'As-of signal feature regeneration', 'Independent holdout',
                               'API response cross-check against exchange archives'],
            'pit_approved': False, 'live_trade_approved': False}
    (out / 'pit_v48_metadata.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    if status == 'INCOMPLETE':
        raise SystemExit('v4.8 evidence incomplete; inspect pit_v48_errors.csv and static file')


if __name__ == '__main__':
    main()
