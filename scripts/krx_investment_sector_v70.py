#!/usr/bin/env python3
"""v7.0: bounded, checkpointed historical OHLCV acquisition for v6.9.
Research only. No orders, rankings, or live trading signals.
"""
import argparse
import csv
import json
import math
import os
import time
from datetime import date, timedelta
from pathlib import Path


def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv_atomic(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with open(tmp, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def number(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def validate(rows, asof, snapshot_close, tolerance=0.03):
    if not rows:
        return 'EMPTY'
    dates = [r.get('Date', '') for r in rows]
    if len(dates) != len(set(dates)):
        return 'DUPLICATE_DATES'
    if dates != sorted(dates):
        return 'UNSORTED_DATES'
    if dates[-1] != asof:
        return 'STALE_LAST_DATE_' + str(dates[-1])
    if len(rows) < 21:
        return 'LESS_THAN_21_SESSIONS'
    for r in rows[-21:]:
        c = number(r.get('Close'))
        if c is None or c <= 0:
            return 'INVALID_CLOSE'
    actual = number(rows[-1]['Close'])
    if snapshot_close is None or snapshot_close <= 0:
        return 'INVALID_SNAPSHOT_CLOSE'
    if abs(actual / snapshot_close - 1) > tolerance:
        return 'CLOSE_MISMATCH_GT_3PCT'
    return 'VALID'


def normalize(frame, asof):
    rows = []
    for idx, r in frame.iterrows():
        d = str(idx.date() if hasattr(idx, 'date') else idx)[:10]
        if d > asof:
            continue
        values = {k: number(r.get(k)) for k in ('Open', 'High', 'Low', 'Close', 'Volume')}
        if any(v is None for v in values.values()):
            continue
        if values['Close'] <= 0 or values['Volume'] < 0:
            continue
        rows.append({'Date': d, **{k: int(v) if float(v).is_integer() else v for k, v in values.items()}})
    rows.sort(key=lambda x: x['Date'])
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--members', default='reports/v68_investment_sector_members.csv')
    p.add_argument('--market', default='reports/market_data_v56_merged.csv')
    p.add_argument('--cache', default='reports/v36_ohlcv_cache')
    p.add_argument('--outdir', default='reports')
    p.add_argument('--batch-size', type=int, default=20)
    p.add_argument('--batch-index', type=int, default=0, help='Zero-based batch; one batch per GitHub run')
    p.add_argument('--sleep', type=float, default=0.6)
    p.add_argument('--source', choices=['NAVER', 'AUTO'], default='NAVER')
    a = p.parse_args()
    if not 1 <= a.batch_size <= 40 or a.batch_index < 0 or a.sleep < 0:
        p.error('batch-size must be 1..40; batch-index and sleep must be nonnegative')
    members = read_csv(a.members)
    market = read_csv(a.market)
    dates = {r.get('snapshot_date') for r in members}
    market_dates = {r.get('snapshot_date') for r in market}
    if len(dates) != 1 or dates != market_dates:
        raise SystemExit('Snapshot dates mismatch or mixed')
    asof = next(iter(dates))
    day = date.fromisoformat(asof)
    snapshots = {r['ticker'].zfill(6): r for r in market}
    tickers = sorted({r['ticker'].zfill(6) for r in members})
    if any(t not in snapshots for t in tickers):
        raise SystemExit('Member ticker absent from market snapshot')
    count = (len(tickers) + a.batch_size - 1) // a.batch_size
    if a.batch_index >= count:
        raise SystemExit(f'Batch index {a.batch_index} out of range (0..{count-1})')
    selected = tickers[a.batch_index*a.batch_size:(a.batch_index+1)*a.batch_size]
    cache = Path(a.cache)
    outdir = Path(a.outdir)
    cache.mkdir(parents=True, exist_ok=True)
    outdir.mkdir(parents=True, exist_ok=True)
    # End is exclusive for FinanceDataReader; use the next calendar day.
    start = (day - timedelta(days=95)).isoformat()
    end = (day + timedelta(days=1)).isoformat()
    results = []
    fdr = None
    for ticker in selected:
        fp = cache / f'{ticker}.csv'
        snapclose = number(snapshots[ticker].get('close'))
        prior_status = ''
        if fp.exists():
            try:
                old = read_csv(fp)
                prior_status = validate(old, asof, snapclose)
                if prior_status == 'VALID':
                    results.append({'ticker':ticker, 'status':'CACHE_REUSED', 'reason':'', 'rows':len(old), 'last_date':old[-1]['Date'], 'source':'EXISTING_CACHE'})
                    continue
            except (OSError, ValueError, KeyError) as e:
                prior_status = 'CACHE_READ_ERROR_' + type(e).__name__
        if fdr is None:
            try:
                import FinanceDataReader as fdr
            except ImportError:
                raise SystemExit('finance-datareader is missing; install it in the workflow')
        status, reason, source, rows = 'FAILED', '', '', []
        providers = [f'NAVER:{ticker}'] if a.source == 'NAVER' else [f'NAVER:{ticker}', ticker]
        for provider in providers:
            try:
                frame = fdr.DataReader(provider, start, end)
                rows = normalize(frame, asof)
                check = validate(rows, asof, snapclose)
                if check == 'VALID':
                    write_csv_atomic(fp, rows, ['Date','Open','High','Low','Close','Volume'])
                    status, reason, source = 'COLLECTED_VALID', '', provider.split(':')[0] if ':' in provider else 'AUTO'
                    break
                reason = check
            except Exception as e:
                reason = type(e).__name__ + ': ' + str(e)[:180]
            time.sleep(a.sleep)
        results.append({'ticker':ticker, 'status':status, 'reason':reason, 'rows':len(rows), 'last_date':rows[-1]['Date'] if rows else '', 'source':source})
    path = outdir / f'v70_history_batch_{a.batch_index:02d}.csv'
    write_csv_atomic(path, results, ['ticker','status','reason','rows','last_date','source'])
    report = {'status':'RESEARCH_COLLECTION_ONLY', 'asof':asof, 'total_tickers':len(tickers), 'batch_size':a.batch_size, 'batch_index':a.batch_index, 'total_batches':count, 'attempted':len(selected), 'valid_collected':sum(r['status']=='COLLECTED_VALID' for r in results), 'cache_reused':sum(r['status']=='CACHE_REUSED' for r in results), 'failed':sum(r['status']=='FAILED' for r in results), 'source':a.source, 'window_start':start, 'window_end_exclusive':end, 'report_csv':str(path), 'limitations':['No unverified prices saved to cache','No trade signals','Historical as-of 2026-10-08 snapshot; not current market','Snapshot-to-history close comparison <=3% does not prove same adjustment basis','Batch CSV is per-run; commit reports/cache for persistence']}
    (outdir/f'v70_history_batch_{a.batch_index:02d}_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
