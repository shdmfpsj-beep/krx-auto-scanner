#!/usr/bin/env python3
"""v5.8 research-only selective retry; NEVER modifies v5.6 merged data or approves trades.

Requires existing reports/market_data_v52.csv, market_data_v56_merged.csv,
market_data_v56_merge_audit.json from the SAME batch. Historical session pinned.
"""
import argparse
import csv
import json
import math
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, fields, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def whole(v):
    try:
        n = float(v)
        if math.isfinite(n) and n >= 0 and n.is_integer():
            return int(n)
    except (ValueError, TypeError, OverflowError):
        pass
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--outdir', default='reports')
    p.add_argument('--max-tickers', type=int, default=40)
    p.add_argument('--delay', type=float, default=0.35)
    p.add_argument('--retries', type=int, default=1)
    a = p.parse_args()
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    audit = {'version': 'v5.8', 'research_only': True, 'status': 'FAILED_CLOSED',
             'live_buy_approved': 0, 'auto_merge': False,
             'turnover_independently_reconciled': False,
             'instrument_type_independently_verified': False,
             'warnings': [], 'error_counts': {}}
    successes, failures = [], []
    fields = ['ticker','name','market','snapshot_date','open','high','low','close','volume',
              'verified_turnover_krw','turnover_source','instrument_status','snapshot_source',
              'listing_close','listing_amount_unreconciled','listing_daily_close_match',
              'dated_ohlcv_valid','date_source','price_basis','research_eligible']
    try:
        if not 1 <= a.max_tickers <= 111 or not 0 <= a.retries <= 2 or not 0 <= a.delay <= 5:
            raise ValueError('INVALID_BOUNDS')
        merge = json.loads((out/'market_data_v56_merge_audit.json').read_text(encoding='utf-8'))
        session = merge.get('batch_date')
        if merge.get('shards_collected') != merge.get('shard_count') or merge.get('universe_count') != 2679:
            raise ValueError('INCOMPLETE_OR_CHANGED_UNIVERSE')
        if not session or session != '2026-10-08':
            raise ValueError('SESSION_CHANGED: this v5.8 batch is pinned to 2026-10-08')
        universe = read_csv(out/'market_data_v52.csv')
        merged = read_csv(out/'market_data_v56_merged.csv')
        if len(universe) != 2679 or len(merged) != 2568:
            raise ValueError('INPUT_COUNTS_CHANGED')
        keys = [(r['ticker'], r['market']) for r in universe]
        present = {(r['ticker'], r['market']) for r in merged}
        if len(set(keys)) != len(keys) or len(present) != len(merged) or not present.issubset(set(keys)):
            raise ValueError('DUPLICATE_OR_UNEXPECTED_KEYS')
        if any(r.get('snapshot_date') != session or r.get('dated_ohlcv_valid','').lower() != 'true' for r in merged):
            raise ValueError('EXISTING_MERGE_HAS_INVALID_DATES')
        missing = sorted((r for r in universe if (r['ticker'], r['market']) not in present), key=lambda r:(r['market'],r['ticker']))
        if len(missing) != 111:
            raise ValueError('MISSING_COUNT_CHANGED')
        import FinanceDataReader as fdr
        # Query includes the historical target date. The provider may not serve this date;
        # do not accept a later/earlier bar or silently use the latest price.
        start = (date.fromisoformat(session)-timedelta(days=9)).isoformat()
        end = (date.fromisoformat(session)+timedelta(days=1)).isoformat()
        counts = Counter()
        for row in missing[:a.max_tickers]:
            code = row['ticker']
            error = 'UNKNOWN'
            for attempt in range(a.retries+1):
                try:
                    bars = fdr.DataReader(code, start, end)
                    if bars is None or bars.empty:
                        raise ValueError('EMPTY_DAILY_BARS')
                    bars = bars.sort_index()
                    matching = bars[bars.index.strftime('%Y-%m-%d') == session]
                    if matching.empty:
                        raise ValueError('TARGET_DATE_NOT_PRESENT')
                    bar = matching.iloc[-1]
                    values = [whole(bar.get(k)) for k in ('Open','High','Low','Close','Volume')]
                    if any(v is None for v in values):
                        raise ValueError('DAILY_OHLCV_NULL_OR_INVALID')
                    o,h,l,c,v = values
                    if not (0 < l <= o <= h and l <= c <= h and v > 0):
                        raise ValueError('DAILY_OHLCV_INCONSISTENT')
                    successes.append({'ticker':code,'name':row['name'],'market':row['market'],
                                      'snapshot_date':session,'open':o,'high':h,'low':l,'close':c,'volume':v,
                                      'verified_turnover_krw':'','turnover_source':'UNVERIFIED',
                                      'instrument_status':'UNKNOWN_VERIFY',
                                      'snapshot_source':'FinanceDataReader.DataReader_RETRY',
                                      'listing_close':'','listing_amount_unreconciled':'',
                                      'listing_daily_close_match':'', 'dated_ohlcv_valid':'True',
                                      'date_source':'DAILY_BAR_INDEX',
                                      'price_basis':'DATED_DAILY_BAR_UNADJUSTED_STATUS_UNKNOWN',
                                      'research_eligible':'OHLCV_ONLY_NO_TURNOVER_OR_INSTRUMENT_VALIDATION'})
                    error = None
                    break
                except Exception as exc:
                    error = f'{type(exc).__name__}:{str(exc)[:160]}'
                    if attempt < a.retries:
                        time.sleep(0.6)
            if error:
                failures.append({'ticker':code,'name':row['name'],'market':row['market'],'reason':error})
                counts[error.split(':',1)[-1].split(':',1)[0]] += 1
            time.sleep(a.delay)
        write_csv(out/'market_data_v58_retry_candidates.csv', fields, successes)
        write_csv(out/'market_data_v58_retry_failures.csv', ['ticker','name','market','reason'], failures)
        audit.update(status='RETRY_CANDIDATES_ONLY_NO_BUY',batch_date=session,missing_total=len(missing),
                     attempted=len(successes)+len(failures),candidate_valid=len(successes),
                     still_failed_in_attempt=len(failures),unattempted=len(missing)-len(successes)-len(failures),
                     error_counts=dict(counts),
                     warnings=['Candidates are NOT merged automatically; independently validate before any merge.',
                               'Same-provider OHLCV retry is not independent exchange confirmation.'])
    except Exception as exc:
        audit['warnings'].append(f'{type(exc).__name__}:{str(exc)[:200]}')
    (out/'market_data_v58_retry_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))
    return 0 if audit['status']=='RETRY_CANDIDATES_ONLY_NO_BUY' else 2


if __name__ == '__main__':
    raise SystemExit(main())
