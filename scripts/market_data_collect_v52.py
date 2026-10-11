#!/usr/bin/env python3
"""v5.3 FDR listing + dated daily-bar cross-check, research only.

Produces the same v5.2 report names plus market_data_v53_dated_sample.csv.
A StockListing snapshot does not contain per-row trading dates. Cross-checks
are performed only on explicitly queried securities; dates are NEVER imputed
onto unverified listing rows. No orders, BUY approval, or real-time claims.
"""
import argparse
import csv
import json
import math
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
FIELDS = ['ticker','name','market','snapshot_date','open','high','low','close','volume','verified_turnover_krw','turnover_source','instrument_status','snapshot_source']
REQUIRED = {'Code','Name','Open','High','Low','Close','Volume','Amount'}
SAMPLE_FIELDS = ['ticker','name','market','listing_close','daily_date','daily_open','daily_high','daily_low','daily_close','daily_volume','daily_amount','date_match','ohlcv_match','amount_match','status','reason']


def integer(value):
    try:
        n = float(value)
        return int(n) if math.isfinite(n) and n >= 0 and n.is_integer() else None
    except (ValueError, TypeError, OverflowError):
        return None


def collect_market(fdr, market):
    df = fdr.StockListing(market)
    if df is None or df.empty:
        raise ValueError(f'{market}: empty listing')
    missing = REQUIRED - set(map(str, df.columns))
    if missing:
        raise ValueError(f'{market}: missing columns {sorted(missing)}; got={list(map(str,df.columns))}')
    rows, rejected, seen = [], Counter(), set()
    for _, rec in df.iterrows():
        ticker = str(rec['Code']).strip()
        if len(ticker) != 6 or not ticker.isdigit() or ticker in seen:
            rejected['bad_or_duplicate_ticker'] += 1
            continue
        seen.add(ticker)
        values = [integer(rec[c]) for c in ('Open','High','Low','Close','Volume','Amount')]
        if any(v is None for v in values):
            rejected['missing_or_noninteger'] += 1
            continue
        o, h, l, c, v, amount = values
        if not (0 < l <= o <= h and l <= c <= h and v > 0 and amount > 0):
            rejected['invalid_price_volume_amount'] += 1
            continue
        name = str(rec['Name']).strip()
        if not name or name.lower() == 'nan':
            rejected['missing_name'] += 1
            continue
        rows.append(dict(ticker=ticker, name=name, market=market, snapshot_date='',
                         open=o, high=h, low=l, close=c, volume=v,
                         verified_turnover_krw=amount,
                         turnover_source='FDR_STOCKLISTING_AMOUNT_UNRECONCILED',
                         instrument_status='UNKNOWN_VERIFY',
                         snapshot_source='FinanceDataReader.StockListing'))
    return rows, dict(raw_rows=len(df), accepted_rows=len(rows), rejected=dict(rejected))


def sample_check(fdr, row, expected_date, start, end):
    result = dict(ticker=row['ticker'], name=row['name'], market=row['market'],
                  listing_close=row['close'], daily_date='', daily_open='',
                  daily_high='', daily_low='', daily_close='', daily_volume='',
                  daily_amount='', date_match=False, ohlcv_match=False,
                  amount_match=False, status='UNVERIFIED', reason='')
    try:
        bars = fdr.DataReader(row['ticker'], start, end)
        if bars is None or bars.empty:
            result['reason'] = 'NO_DAILY_BARS'
            return result
        bars = bars.sort_index()
        last = bars.iloc[-1]
        date = bars.index[-1].date().isoformat()
        result['daily_date'] = date
        result['date_match'] = date == expected_date
        for field, column in [('daily_open','Open'),('daily_high','High'),('daily_low','Low'),
                              ('daily_close','Close'),('daily_volume','Volume')]:
            result[field] = integer(last.get(column))
        result['ohlcv_match'] = (result['date_match'] and all(
            result[dst] is not None and result[dst] == row[src]
            for dst, src in [('daily_open','open'),('daily_high','high'),
                             ('daily_low','low'),('daily_close','close'),
                             ('daily_volume','volume')]))
        # Some FDR DataReader providers do not include Amount. Missing != 0.
        amt = integer(last.get('Amount')) if 'Amount' in bars.columns else None
        result['daily_amount'] = '' if amt is None else amt
        result['amount_match'] = amt is not None and amt == row['verified_turnover_krw']
        if result['ohlcv_match'] and result['amount_match']:
            result['status'] = 'SAME_PROVIDER_DATED_OHLCV_AMOUNT_MATCH'
        elif result['ohlcv_match']:
            result['status'] = 'SAME_PROVIDER_DATED_OHLCV_MATCH_AMOUNT_UNVERIFIED'
        else:
            result['status'] = 'MISMATCH'
            result['reason'] = 'DATE_OR_OHLCV_DIFFERENCE'
    except Exception as exc:
        result['reason'] = f'{type(exc).__name__}: {str(exc)[:160]}'
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', default='reports')
    parser.add_argument('--date', default='', help='YYYYMMDD unsupported for historical listing')
    parser.add_argument('--sample-size', type=int, default=20, help='per-market sample size, max 50')
    args = parser.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    audit = dict(version='v5.3', research_only=True, status='DATA_UNAVAILABLE',
                 run_kst=datetime.now(KST).isoformat(), requested_date=args.date or 'AUTO',
                 provider='FinanceDataReader', row_count=0, live_buy_approved=0,
                 verified_common_stocks=0, date_verified_for_all=False,
                 turnover_independently_reconciled=False, market_diagnostics={},
                 sample_validation={}, errors=[],
                 limitations=['Listing data has no per-security trade date',
                              'Sample cross-check uses SAME provider, not independent verification',
                              'Unqueried listing rows remain undated',
                              'Common-stock classification and sector flows not verified',
                              'No real-time data or BUY approval'])
    try:
        if args.date:
            datetime.strptime(args.date, '%Y%m%d')
            raise ValueError('Historical --date unsupported by current listing snapshot')
        if not 1 <= args.sample_size <= 50:
            raise ValueError('--sample-size must be 1..50')
        import FinanceDataReader as fdr
        audit['provider_version'] = getattr(fdr, '__version__', 'unknown')
        markets, all_rows = {}, []
        for market in ('KOSPI','KOSDAQ'):
            rows, diag = collect_market(fdr, market)
            audit['market_diagnostics'][market] = diag
            if len(rows) < 100:
                raise ValueError(f'{market}: insufficient valid listing rows {len(rows)}')
            markets[market] = rows
            all_rows.extend(rows)
        if len({r['ticker'] for r in all_rows}) != len(all_rows):
            raise ValueError('Cross-market duplicate ticker')
        # Write undated listing as research snapshot, even if sample cross-check fails.
        with (out / 'market_data_v52.csv').open('w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(all_rows)
        audit['row_count'] = len(all_rows)
        audit['market_counts'] = dict(Counter(r['market'] for r in all_rows))
        audit['status'] = 'FDR_LISTING_SNAPSHOT_UNDATED_RESEARCH_ONLY'
        # Latest completed Korean trading session is not inferred from a Sunday run.
        # Use the most recent dated bar of a liquid anchor as a *candidate* date.
        now = datetime.now(KST).date()
        start = (now - timedelta(days=18)).isoformat()
        end = (now + timedelta(days=1)).isoformat()
        anchor = next((r for r in markets['KOSPI'] if r['ticker'] == '005930'),
                      max(markets['KOSPI'], key=lambda r: r['verified_turnover_krw']))
        anchor_bars = fdr.DataReader(anchor['ticker'], start, end)
        if anchor_bars is None or anchor_bars.empty:
            raise ValueError('Anchor daily bars empty; listing retained undated')
        expected = anchor_bars.sort_index().index[-1].date().isoformat()
        audit['candidate_session_date_from_anchor'] = expected
        # Mix highest-turnover and spread-out securities to avoid only large caps.
        checks = []
        for market in ('KOSPI','KOSDAQ'):
            ordered = sorted(markets[market], key=lambda r: r['verified_turnover_krw'], reverse=True)
            top_n = (args.sample_size + 1) // 2
            selected = ordered[:top_n]
            remaining = ordered[top_n:]
            other_n = args.sample_size - top_n
            if other_n and remaining:
                for i in range(other_n):
                    selected.append(remaining[min(len(remaining)-1, (i + 1) * len(remaining) // (other_n + 1))])
            checks.extend(sample_check(fdr, r, expected, start, end) for r in selected)
        with (out / 'market_data_v53_dated_sample.csv').open('w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=SAMPLE_FIELDS)
            w.writeheader()
            w.writerows(checks)
        counts = Counter(x['status'] for x in checks)
        audit['sample_validation'] = dict(sample_size=len(checks), statuses=dict(counts),
                                          date_matches=sum(x['date_match'] for x in checks),
                                          ohlcv_matches=sum(x['ohlcv_match'] for x in checks),
                                          amount_matches=sum(x['amount_match'] for x in checks),
                                          sample_file='market_data_v53_dated_sample.csv')
        audit['status'] = ('FDR_SAMPLED_DAILY_BARS_MATCH_RESEARCH_ONLY'
                           if checks and all(x['ohlcv_match'] for x in checks)
                           else 'FDR_SNAPSHOT_SAMPLE_INCONSISTENT_RESEARCH_ONLY')
    except Exception as exc:
        audit['errors'].append(f'{type(exc).__name__}: {str(exc)[:300]}')
        if audit['row_count']:
            audit['status'] = 'FDR_LISTING_COLLECTED_SAMPLE_CHECK_FAILED_RESEARCH_ONLY'
    finally:
        (out / 'market_data_v52_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit['row_count'] else 2


if __name__ == '__main__':
    sys.exit(main())
