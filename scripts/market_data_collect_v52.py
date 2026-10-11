#!/usr/bin/env python3
"""v5.5: rotating bounded batches of dated daily bars, research only. Research only.

StockListing is used for universe discovery, NEVER as a dated OHLCV feed.
Writes the legacy undated research CSV, plus explicitly dated verified subset.
No trading signals or orders. Same-provider checks are not independent KRX validation.
"""
import argparse
import csv
import json
import math
import os
import time
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
FIELDS = ['ticker','name','market','snapshot_date','open','high','low','close','volume','verified_turnover_krw','turnover_source','instrument_status','snapshot_source']
DATED_FIELDS = FIELDS + ['listing_close','listing_amount_unreconciled','listing_daily_close_match','dated_ohlcv_valid','date_source','price_basis','research_eligible']
REQUIRED = {'Code','Name','Close','Amount'}


def whole(v):
    try:
        n = float(v)
        return int(n) if math.isfinite(n) and n >= 0 and n.is_integer() else None
    except (ValueError, TypeError, OverflowError):
        return None


def save_csv(path, fields, rows):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def listing(fdr, market):
    df = fdr.StockListing(market)
    if df is None or df.empty:
        raise ValueError(f'{market} empty listing')
    missing = REQUIRED - set(map(str, df.columns))
    if missing:
        raise ValueError(f'{market} missing listing columns: {sorted(missing)}')
    seen, rows, rejected = set(), [], Counter()
    for _, x in df.iterrows():
        t = str(x['Code']).strip()
        if len(t) != 6 or not t.isdigit() or t in seen:
            rejected['bad_or_duplicate_code'] += 1
            continue
        seen.add(t)
        name = str(x['Name']).strip()
        close = whole(x['Close'])
        amount = whole(x['Amount'])
        if not name or name.lower() == 'nan' or not close or close <= 0:
            rejected['missing_name_or_close'] += 1
            continue
        rows.append({'ticker':t, 'name':name, 'market':market,
                     'listing_close':close, 'listing_amount':amount})
    return rows, {'raw':len(df), 'eligible_for_dated_query':len(rows), 'rejected':dict(rejected)}


def dated_bar(fdr, row, start, end, expected):
    bars = fdr.DataReader(row['ticker'], start, end)
    if bars is None or bars.empty:
        raise ValueError('EMPTY_DAILY_BARS')
    bars = bars.sort_index()
    latest = bars.iloc[-1]
    date = bars.index[-1].date().isoformat()
    if date != expected:
        raise ValueError(f'STALE_DATE:{date} expected:{expected}')
    values = [whole(latest.get(k)) for k in ('Open','High','Low','Close','Volume')]
    if any(v is None for v in values):
        raise ValueError('DAILY_OHLCV_NULL_OR_INVALID')
    o,h,l,c,v = values
    if not (0 < l <= o <= h and l <= c <= h and v > 0):
        raise ValueError('DAILY_OHLCV_INCONSISTENT')
    # Do not infer turnover from close*volume, or promote listing Amount to verified.
    # Even if DataReader has Amount, same-provider equality is not independent evidence.
    result = dict(ticker=row['ticker'], name=row['name'], market=row['market'],
                  snapshot_date=date, open=o, high=h, low=l, close=c, volume=v,
                  verified_turnover_krw='', turnover_source='UNVERIFIED',
                  instrument_status='UNKNOWN_VERIFY',
                  snapshot_source='FinanceDataReader.DataReader',
                  listing_close=row['listing_close'],
                  listing_amount_unreconciled=row['listing_amount'] if row['listing_amount'] is not None else '',
                  listing_daily_close_match=(row['listing_close'] == c),
                  dated_ohlcv_valid=True, date_source='DAILY_BAR_INDEX',
                  price_basis='DATED_DAILY_BAR_UNADJUSTED_STATUS_UNKNOWN',
                  research_eligible='OHLCV_ONLY_NO_TURNOVER_OR_INSTRUMENT_VALIDATION')
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--outdir',default='reports')
    p.add_argument('--date',default='',help='Historical listing dates unsupported; omit')
    p.add_argument('--sample-size',type=int,default=40,help='Legacy argument (unused in v5.5)')
    p.add_argument('--batch-size',type=int,default=120,help='Max tickers per run, 1..300')
    p.add_argument('--shard-index',type=int,default=None,help='0-based batch index; default rotates by GITHUB_RUN_NUMBER')
    p.add_argument('--delay',type=float,default=0.25,help='Seconds between ticker requests')
    p.add_argument('--retries',type=int,default=1,help='Retries after initial attempt, 0..2')
    a=p.parse_args()
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    audit={'version':'v5.5','research_only':True,'run_kst':datetime.now(KST).isoformat(),
           'status':'DATA_UNAVAILABLE','row_count':0,'dated_valid_rows':0,
           'verified_common_stocks':0,'verified_turnover_rows':0,'live_buy_approved':0,
           'date_verified_for_all':False,'turnover_independently_reconciled':False,
           'errors':[],'market_diagnostics':{},'limitations':[
               'StockListing has no per-security date: its prices are not authoritative',
               'Only explicitly fetched DataReader rows have dated OHLCV',
               'Batches are not automatically merged across GitHub runs; no full market dated claim',
               'Daily-bar adjustment basis and independent exchange reconciliation unverified',
               'All turnover remains unverified; no sector money flow or BUY approval',
               'Stock types (common shares/ETF/SPAC) not independently verified']}
    try:
        if a.date:
            raise ValueError('Historical --date unsupported for current StockListing universe')
        if not 1 <= a.batch_size <= 300:
            raise ValueError('--batch-size must be 1..300')
        if not 0 <= a.retries <= 2 or not 0 <= a.delay <= 5:
            raise ValueError('invalid --retries or --delay')
        import FinanceDataReader as fdr
        audit['provider_version']=getattr(fdr,'__version__','unknown')
        markets={}
        for market in ('KOSPI','KOSDAQ'):
            rows, diag=listing(fdr,market)
            if len(rows)<100:
                raise ValueError(f'{market} insufficient listing codes')
            markets[market]=rows
            audit['market_diagnostics'][market]=diag
        if len({r['ticker'] for rows in markets.values() for r in rows}) != sum(map(len,markets.values())):
            raise ValueError('Cross-market duplicate ticker')
        # Legacy file is deliberately undated and stripped of listing-derived prices.
        # Downstream engines must NOT use this as OHLCV evidence.
        undated=[dict(ticker=r['ticker'],name=r['name'],market=m,snapshot_date='',
                      open='',high='',low='',close='',volume='',verified_turnover_krw='',
                      turnover_source='UNVERIFIED',instrument_status='UNKNOWN_VERIFY',
                      snapshot_source='FinanceDataReader.StockListing_UNIVERSE_ONLY')
                 for m,rows in markets.items() for r in rows]
        save_csv(out/'market_data_v52.csv',FIELDS,undated)
        audit['row_count']=len(undated)
        audit['market_counts']={m:len(rows) for m,rows in markets.items()}
        audit['status']='UNDATED_UNIVERSE_ONLY'
        now=datetime.now(KST).date()
        start=(now-timedelta(days=18)).isoformat()
        end=(now+timedelta(days=1)).isoformat()
        anchor=next((r for r in markets['KOSPI'] if r['ticker']=='005930'),markets['KOSPI'][0])
        bars=fdr.DataReader(anchor['ticker'],start,end)
        if bars is None or bars.empty:
            raise ValueError('ANCHOR_DAILY_BARS_EMPTY')
        expected=bars.sort_index().index[-1].date().isoformat()
        audit['candidate_session_date_from_anchor']=expected
        # Stable market-balanced rotation: every shard covers a disjoint segment
        # of each market, until the universe/listing changes. Never assume
        # separate GitHub runs persist data automatically.
        ordered=[]
        for market in ('KOSPI','KOSDAQ'):
            ordered.extend(sorted(markets[market],key=lambda r:r['ticker']))
        total=len(ordered)
        shard_count=(total+a.batch_size-1)//a.batch_size
        run_number=os.environ.get('GITHUB_RUN_NUMBER','')
        if a.shard_index is None:
            shard=(int(run_number)-1)%shard_count if run_number.isdigit() and int(run_number)>0 else 0
            shard_mode='GITHUB_RUN_NUMBER_ROTATION' if run_number.isdigit() and int(run_number)>0 else 'LOCAL_DEFAULT_ZERO'
        else:
            shard=a.shard_index
            shard_mode='EXPLICIT'
        if not 0 <= shard < shard_count:
            raise ValueError(f'--shard-index must be 0..{shard_count-1}')
        selected=ordered[shard*a.batch_size:(shard+1)*a.batch_size]
        audit.update(shard_index=shard,shard_count=shard_count,shard_mode=shard_mode,
                     batch_size=a.batch_size,batch_start=shard*a.batch_size,
                     batch_end_exclusive=shard*a.batch_size+len(selected),
                     universe_count=total,all_market_dated=False,
                     persistence='PER_RUN_ARTIFACT_ONLY_NOT_MERGED',
                     batch_date=expected)
        dated, failures=[],[]
        def checkpoint():
            save_csv(out/'market_data_v54_dated.csv',DATED_FIELDS,dated)
            save_csv(out/'market_data_v54_failures.csv',['ticker','market','reason'],failures)
            audit['dated_valid_rows']=len(dated)
            audit['dated_failures']=len(failures)
            audit['dated_requested_rows']=len(selected)
            (out/'market_data_v52_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
        checkpoint()
        for i,r in enumerate(selected,1):
            error=None
            for attempt in range(a.retries+1):
                try:
                    dated.append(dated_bar(fdr,r,start,end,expected))
                    error=None
                    break
                except Exception as exc:
                    error=f'{type(exc).__name__}:{str(exc)[:160]}'
                    if attempt < a.retries:
                        time.sleep(min(4,1.5*(attempt+1)))
            if error is not None:
                failures.append({'ticker':r['ticker'],'market':r['market'],'reason':error})
            if i%10==0:
                checkpoint()
            if i<len(selected) and a.delay:
                time.sleep(a.delay)
        checkpoint()
        audit['dated_valid_rows']=len(dated)
        audit['dated_requested_rows']=len(selected)
        audit['dated_failures']=len(failures)
        audit['listing_close_mismatch_count']=sum(not x['listing_daily_close_match'] for x in dated)
        audit['dated_market_counts']=dict(Counter(x['market'] for x in dated))
        audit['dated_file']='market_data_v54_dated.csv'
        audit['status']='DATED_PARTIAL_BATCH_NO_BUY' if dated else 'UNDATED_UNIVERSE_DATED_FAILED'
    except Exception as exc:
        audit['errors'].append(f'{type(exc).__name__}:{str(exc)[:250]}')
        if audit['row_count']:
            audit['status']='UNDATED_UNIVERSE_DATED_FAILED'
    finally:
        (out/'market_data_v52_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(audit,ensure_ascii=False,indent=2))
    return 0 if audit['dated_valid_rows'] else 2

if __name__=='__main__':
    sys.exit(main())
