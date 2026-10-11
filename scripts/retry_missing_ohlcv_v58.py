#!/usr/bin/env python3
"""v5.8.2 research-only selective retry with granular OHLCV diagnostics.
Never modifies merged data, never approves trades, historical batch pinned.
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


def diagnose(o, h, l, c, v):
    issues = []
    if any(x is None for x in (o, h, l, c, v)):
        issues.append('NULL_NONINTEGER_NEGATIVE_OR_NONFINITE')
        return issues
    if any(x == 0 for x in (o, h, l, c)):
        issues.append('ZERO_PRICE')
    if not l <= h:
        issues.append('LOW_GREATER_THAN_HIGH')
    if not l <= o <= h:
        issues.append('OPEN_OUTSIDE_LOW_HIGH')
    if not l <= c <= h:
        issues.append('CLOSE_OUTSIDE_LOW_HIGH')
    if v == 0:
        issues.append('ZERO_VOLUME')
    return issues


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--outdir', default='reports')
    p.add_argument('--max-tickers', type=int, default=40)
    p.add_argument('--offset', type=int, default=40, help='Start at missing ticker index; default skips first 40 diagnosed tickers')
    p.add_argument('--delay', type=float, default=0.35)
    p.add_argument('--retries', type=int, default=1)
    a = p.parse_args()
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    audit = {'version':'v5.8.2','research_only':True,'status':'FAILED_CLOSED',
             'live_buy_approved':0,'auto_merge':False,
             'turnover_independently_reconciled':False,
             'instrument_type_independently_verified':False,
             'warnings':[],'error_counts':{}}
    successes, failures = [], []
    fields = ['ticker','name','market','snapshot_date','open','high','low','close','volume',
              'verified_turnover_krw','turnover_source','instrument_status','snapshot_source',
              'listing_close','listing_amount_unreconciled','listing_daily_close_match',
              'dated_ohlcv_valid','date_source','price_basis','research_eligible']
    failure_fields = ['ticker','name','market','reason','diagnostic_codes',
                      'raw_open','raw_high','raw_low','raw_close','raw_volume',
                      'bars_count','available_last_date','attempts']
    try:
        if not 1 <= a.max_tickers <= 111 or not 0 <= a.offset < 111 or not 0 <= a.retries <= 2 or not 0 <= a.delay <= 5:
            raise ValueError('INVALID_BOUNDS')
        merge = json.loads((out/'market_data_v56_merge_audit.json').read_text(encoding='utf-8'))
        session = merge.get('batch_date')
        if merge.get('shards_collected') != merge.get('shard_count') or merge.get('universe_count') != 2679:
            raise ValueError('INCOMPLETE_OR_CHANGED_UNIVERSE')
        if session != '2026-10-08':
            raise ValueError('SESSION_CHANGED: this v5.8.2 batch is pinned to 2026-10-08')
        universe = read_csv(out/'market_data_v52.csv')
        merged = read_csv(out/'market_data_v56_merged.csv')
        if len(universe) != 2679 or len(merged) != 2568:
            raise ValueError('INPUT_COUNTS_CHANGED')
        keys = [(r['ticker'],r['market']) for r in universe]
        present = {(r['ticker'],r['market']) for r in merged}
        if len(set(keys)) != len(keys) or len(present) != len(merged) or not present.issubset(set(keys)):
            raise ValueError('DUPLICATE_OR_UNEXPECTED_KEYS')
        if any(r.get('snapshot_date') != session or r.get('dated_ohlcv_valid','').lower() != 'true' for r in merged):
            raise ValueError('EXISTING_MERGE_HAS_INVALID_DATES')
        missing = sorted((r for r in universe if (r['ticker'],r['market']) not in present),
                         key=lambda r:(r['market'],r['ticker']))
        if len(missing) != 111:
            raise ValueError('MISSING_COUNT_CHANGED')
        import FinanceDataReader as fdr
        start = (date.fromisoformat(session)-timedelta(days=9)).isoformat()
        end = (date.fromisoformat(session)+timedelta(days=1)).isoformat()
        counts = Counter()
        selected = missing[a.offset:a.offset + a.max_tickers]
        if not selected:
            raise ValueError('EMPTY_SELECTED_RANGE')
        for row in selected:
            code = row['ticker']
            diagnostic = {'ticker':code,'name':row['name'],'market':row['market'],
                          'reason':'UNKNOWN','diagnostic_codes':'',
                          'raw_open':'','raw_high':'','raw_low':'','raw_close':'','raw_volume':'',
                          'bars_count':'','available_last_date':'','attempts':0}
            success = False
            for attempt in range(a.retries+1):
                diagnostic['attempts'] = attempt+1
                try:
                    bars = fdr.DataReader(code,start,end)
                    if bars is None or bars.empty:
                        raise ValueError('EMPTY_DAILY_BARS')
                    bars = bars.sort_index()
                    diagnostic['bars_count'] = len(bars)
                    diagnostic['available_last_date'] = str(bars.index[-1])[:10]
                    matching = bars[bars.index.strftime('%Y-%m-%d') == session]
                    if matching.empty:
                        raise ValueError('TARGET_DATE_NOT_PRESENT')
                    bar = matching.iloc[-1]
                    raw = [bar.get(k) for k in ('Open','High','Low','Close','Volume')]
                    for k,v in zip(('raw_open','raw_high','raw_low','raw_close','raw_volume'),raw):
                        diagnostic[k] = str(v)[:60]
                    o,h,l,c,v = [whole(x) for x in raw]
                    issues = diagnose(o,h,l,c,v)
                    if issues:
                        diagnostic['diagnostic_codes'] = '|'.join(issues)
                        raise ValueError('DAILY_OHLCV_INCONSISTENT')
                    successes.append({'ticker':code,'name':row['name'],'market':row['market'],
                                      'snapshot_date':session,'open':o,'high':h,'low':l,'close':c,'volume':v,
                                      'verified_turnover_krw':'','turnover_source':'UNVERIFIED',
                                      'instrument_status':'UNKNOWN_VERIFY',
                                      'snapshot_source':'FinanceDataReader.DataReader_RETRY',
                                      'listing_close':'','listing_amount_unreconciled':'',
                                      'listing_daily_close_match':'','dated_ohlcv_valid':'True',
                                      'date_source':'DAILY_BAR_INDEX',
                                      'price_basis':'DATED_DAILY_BAR_UNADJUSTED_STATUS_UNKNOWN',
                                      'research_eligible':'OHLCV_ONLY_NO_TURNOVER_OR_INSTRUMENT_VALIDATION'})
                    success = True
                    break
                except Exception as exc:
                    diagnostic['reason'] = f'{type(exc).__name__}:{str(exc)[:160]}'
                    if attempt < a.retries:
                        time.sleep(0.6)
            if not success:
                failures.append(diagnostic)
                if diagnostic['diagnostic_codes']:
                    for code_type in diagnostic['diagnostic_codes'].split('|'):
                        counts[code_type] += 1
                else:
                    counts[diagnostic['reason'].split(':',1)[-1].split(':',1)[0]] += 1
            time.sleep(a.delay)
        write_csv(out/'market_data_v58_retry_candidates.csv',fields,successes)
        write_csv(out/'market_data_v58_retry_failures.csv',failure_fields,failures)
        audit.update(status='RETRY_CANDIDATES_ONLY_NO_BUY',batch_date=session,
                     missing_total=len(missing),offset=a.offset,selected_count=len(selected),
                     selected_indices=[a.offset,a.offset+len(selected)-1],
                     attempted=len(successes)+len(failures),
                     candidate_valid=len(successes),still_failed_in_attempt=len(failures),
                     unattempted=len(missing)-len(successes)-len(failures),
                     remaining_after_selected=max(0,len(missing)-a.offset-len(selected)),
                     error_counts=dict(counts),
                     warnings=['No automatic merge; same-provider data is not independent confirmation.',
                               'ZERO_VOLUME is a diagnostic, NOT proof of a trading halt.'])
    except Exception as exc:
        audit['warnings'].append(f'{type(exc).__name__}:{str(exc)[:200]}')
    (out/'market_data_v58_retry_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))
    return 0 if audit['status']=='RETRY_CANDIDATES_ONLY_NO_BUY' else 2

if __name__=='__main__':
    raise SystemExit(main())
