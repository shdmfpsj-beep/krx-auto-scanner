#!/usr/bin/env python3
"""v5.2.2: fail-closed FDR market-listing collection (research only).

A StockListing is a provider snapshot WITHOUT per-row exchange trade dates.
Do not label its OHLCV as independently verified dated daily bars or use
this output to authorize trades. Retains v5.2 report names/CLI interface.
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


def nonnegative_integer(value):
    try:
        n = float(value)
        if not math.isfinite(n) or n < 0 or not n.is_integer():
            return None
        return int(n)
    except (TypeError, ValueError, OverflowError):
        return None


def collect_market(fdr, market):
    df = fdr.StockListing(market)
    if df is None or df.empty:
        raise ValueError(f'{market}: empty StockListing')
    missing = REQUIRED - set(map(str, df.columns))
    if missing:
        raise ValueError(f'{market}: missing columns {sorted(missing)}; returned={list(map(str,df.columns))}')
    rows = []
    rejected = Counter()
    seen = set()
    for _, rec in df.iterrows():
        ticker = str(rec['Code']).strip()
        if not (len(ticker) == 6 and ticker.isdigit()) or ticker in seen:
            rejected['bad_or_duplicate_ticker'] += 1
            continue
        seen.add(ticker)
        vals = [nonnegative_integer(rec[c]) for c in ('Open','High','Low','Close','Volume','Amount')]
        if any(v is None for v in vals):
            rejected['non_integer_or_missing'] += 1
            continue
        o, h, l, c, v, amount = vals
        if not (0 < l <= o <= h and l <= c <= h and v > 0 and amount > 0):
            rejected['invalid_ohlcv_or_amount'] += 1
            continue
        name = str(rec['Name']).strip()
        if not name or name.lower() == 'nan':
            rejected['missing_name'] += 1
            continue
        rows.append(dict(ticker=ticker, name=name, market=market,
                         snapshot_date='',  # listing response has NO verified per-row trade date
                         open=o, high=h, low=l, close=c, volume=v,
                         verified_turnover_krw=amount,
                         turnover_source='FDR_STOCKLISTING_AMOUNT_UNRECONCILED',
                         instrument_status='UNKNOWN_VERIFY',
                         snapshot_source='FinanceDataReader.StockListing'))
    return rows, dict(raw_rows=len(df), accepted_rows=len(rows), rejected=dict(rejected),
                      columns=list(map(str, df.columns)))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--outdir', default='reports')
    p.add_argument('--date', default='', help='YYYYMMDD; cannot reconstruct historical listing dates')
    args = p.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    audit = dict(version='v5.2.2', status='DATA_UNAVAILABLE', research_only=True,
                 run_kst=datetime.now(KST).isoformat(), requested_date=args.date or 'AUTO',
                 provider='FinanceDataReader.StockListing', row_count=0,
                 verified_common_stocks=0, live_buy_approved=0,
                 date_verified=False, turnover_independently_reconciled=False,
                 market_diagnostics={}, errors=[],
                 limitations=['Listing rows have no independently verified per-security trade date',
                              'Amount is provider-reported, not independently reconciled',
                              'Common-stock classification not verified',
                              'No real-time/intraday, institutional flow or sector flow',
                              'No BUY approval; historical --date unsupported'])
    try:
        if args.date:
            datetime.strptime(args.date, '%Y%m%d')
            raise ValueError('Historical --date cannot be satisfied by current StockListing; refusing to misdate data')
        import FinanceDataReader as fdr
        audit['provider_version'] = str(getattr(fdr, '__version__', 'unknown'))
        rows = []
        for market in ('KOSPI','KOSDAQ'):
            market_rows, diag = collect_market(fdr, market)
            audit['market_diagnostics'][market] = diag
            if len(market_rows) < 100:
                raise ValueError(f'{market}: insufficient valid rows {len(market_rows)}')
            rows.extend(market_rows)
        codes = [r['ticker'] for r in rows]
        if len(codes) != len(set(codes)):
            raise ValueError('Duplicate ticker across markets')
        # The source is a current listing snapshot; do NOT invent a trade date.
        with (out/'market_data_v52.csv').open('w', newline='', encoding='utf-8-sig') as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        audit.update(status='FDR_LISTING_SNAPSHOT_UNDATED_RESEARCH_ONLY', row_count=len(rows),
                     market_counts=dict(Counter(r['market'] for r in rows)),
                     sample_tickers=[r['ticker'] for r in rows[:5]])
    except Exception as exc:
        audit['errors'].append(f'{type(exc).__name__}: {str(exc)[:500]}')
    finally:
        (out/'market_data_v52_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit['row_count'] else 2

if __name__ == '__main__':
    sys.exit(main())
