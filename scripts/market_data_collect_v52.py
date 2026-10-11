#!/usr/bin/env python3
"""v5.2.1 fail-closed market-data diagnostics with optional FDR cross-check.
Research only. No orders, no fabricated OHLCV/turnover, no full-universe claims.
"""
import argparse
import csv
import json
import math
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
FIELDS = ['ticker','name','market','snapshot_date','open','high','low','close','volume','verified_turnover_krw','turnover_source','instrument_status','snapshot_source']
REQUIRED = {'시가','고가','저가','종가','거래량','거래대금'}


def valid_int(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
        if not math.isfinite(f) or f < 0 or not f.is_integer():
            return None
        return int(f)
    except (TypeError, ValueError, OverflowError):
        return None


def check_frame(df, date, market):
    if df is None:
        return None, {'date':date,'market':market,'issue':'NULL_RESPONSE'}
    if not hasattr(df, 'columns'):
        return None, {'date':date,'market':market,'issue':'INVALID_RESPONSE_TYPE','type':type(df).__name__}
    columns = list(map(str,df.columns))
    if df.empty:
        return None, {'date':date,'market':market,'issue':'EMPTY_RESPONSE','columns':columns}
    missing = sorted(REQUIRED-set(columns))
    if missing:
        return None, {'date':date,'market':market,'issue':'PROVIDER_SCHEMA_MISMATCH','columns':columns,'missing':missing,'rows':len(df)}
    result=[]; bad=0; duplicates=0; seen=set()
    for ticker, rec in df.iterrows():
        code=str(ticker).strip().zfill(6)
        if len(code)!=6 or not code.isdigit() or code in seen:
            duplicates += 1
            continue
        seen.add(code)
        values=[valid_int(rec[k]) for k in ('시가','고가','저가','종가','거래량','거래대금')]
        if any(v is None for v in values):
            bad += 1
            continue
        o,h,l,c,v,turn=values
        if not (0<l<=o<=h and l<=c<=h and v>=0 and turn>=0):
            bad += 1
            continue
        result.append({'ticker':code,'name':'','market':market,'snapshot_date':date[:4]+'-'+date[4:6]+'-'+date[6:],
                       'open':o,'high':h,'low':l,'close':c,'volume':v,
                       'verified_turnover_krw':turn,'turnover_source':'PYKRX_REPORTED_DAILY_TURNOVER',
                       'instrument_status':'UNKNOWN_VERIFY','snapshot_source':'pykrx.get_market_ohlcv_by_ticker'})
    return result, {'date':date,'market':market,'issue':'VALIDATED_SCHEMA','raw_rows':len(df),
                    'valid_rows':len(result),'bad_rows':bad,'duplicates_or_invalid_tickers':duplicates,'columns':columns}


def fdr_diagnostic(audit, date):
    """Independent provider probe ONLY; never use it to claim full KRX coverage."""
    probe={'provider':'FinanceDataReader','status':'NOT_TESTED'}
    try:
        import FinanceDataReader as fdr
        probe['version']=str(getattr(fdr,'__version__','unknown'))
        listings={}
        for market in ('KOSPI','KOSDAQ'):
            try:
                listing=fdr.StockListing(market)
                listings[market]={'rows':int(len(listing)), 'columns':list(map(str,listing.columns))}
            except Exception as exc:
                listings[market]={'error':f'{type(exc).__name__}: {str(exc)[:250]}'}
        probe['listings']=listings
        # Single liquid ticker probe only, not a universe scan.
        try:
            end=(datetime.strptime(date,'%Y%m%d')+timedelta(days=1)).strftime('%Y-%m-%d')
            start=(datetime.strptime(date,'%Y%m%d')-timedelta(days=10)).strftime('%Y-%m-%d')
            frame=fdr.DataReader('005930',start,end)
            probe['sample_005930']={'rows':int(len(frame)), 'columns':list(map(str,frame.columns)),
                                    'last_date':str(frame.index[-1])[:10] if len(frame) else None}
        except Exception as exc:
            probe['sample_005930']={'error':f'{type(exc).__name__}: {str(exc)[:250]}'}
        probe['status']='PROBED_NOT_FULL_MARKET_VERIFIED'
    except ImportError as exc:
        probe['status']='DEPENDENCY_MISSING'
        probe['error']=str(exc)
    except Exception as exc:
        probe['status']='PROBE_FAILED'
        probe['error']=f'{type(exc).__name__}: {str(exc)[:250]}'
    audit['fallback_probe']=probe


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--outdir',default='reports')
    parser.add_argument('--date',default='',help='YYYYMMDD; empty means recent dates')
    args=parser.parse_args()
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    audit={'version':'v5.2.1','status':'DATA_UNAVAILABLE','research_only':True,
           'asof_run_kst':datetime.now(KST).isoformat(),'requested_date':args.date or 'AUTO',
           'primary_provider':'pykrx','market_diagnostics':[],'errors':[],
           'row_count':0,'verified_common_stocks':0,'live_buy_approved':0,
           'limitations':['No independent security-type validation','No intraday order book or real-time confirmation',
                          'FinanceDataReader probe is NOT a replacement for complete daily market data']}
    today=datetime.now(KST).date()
    try:
        if args.date:
            day=datetime.strptime(args.date,'%Y%m%d').date()
            if day>today:
                raise ValueError('future date not permitted')
            dates=[day]
        else:
            dates=[today-timedelta(days=i) for i in range(11)]
        try:
            import pykrx
            audit['pykrx_version']=str(getattr(pykrx,'__version__','unknown'))
            from pykrx import stock
        except Exception as exc:
            audit['errors'].append({'stage':'pykrx_import','type':type(exc).__name__,'message':str(exc)[:300]})
            stock=None
        if stock is not None:
            for day in dates:
                ds=day.strftime('%Y%m%d'); by_market={}; failed=False
                for market in ('KOSPI','KOSDAQ'):
                    try:
                        frame=stock.get_market_ohlcv_by_ticker(ds,market=market)
                        rows,diag=check_frame(frame,ds,market)
                        audit['market_diagnostics'].append(diag)
                        if rows is None or len(rows)<100:  # safety floor, not proof of full coverage
                            failed=True
                            if rows is not None:
                                audit['errors'].append({'date':ds,'market':market,'issue':'TOO_FEW_ROWS','rows':len(rows)})
                            break
                        by_market[market]=rows
                    except Exception as exc:
                        audit['errors'].append({'date':ds,'market':market,'type':type(exc).__name__,
                                                'message':str(exc)[:350],
                                                'traceback_tail':traceback.format_exc(limit=3)[-1000:]})
                        failed=True
                        break
                if not failed and len(by_market)==2:
                    records=by_market['KOSPI']+by_market['KOSDAQ']
                    with (out/'market_data_v52.csv').open('w',newline='',encoding='utf-8-sig') as fh:
                        writer=csv.DictWriter(fh,fieldnames=FIELDS)
                        writer.writeheader();writer.writerows(records)
                    audit.update(status='DAILY_SNAPSHOT_COLLECTED_NOT_LIVE',row_count=len(records),
                                 snapshot_date=day.isoformat(),market_counts={k:len(v) for k,v in by_market.items()})
                    break
                # If provider fails on a trading weekday, diagnose rather than hammer all dates.
                if day.weekday()<5:
                    break
        if audit['row_count']==0:
            audit['status']='PRIMARY_PROVIDER_FAILED_FALLBACK_DIAGNOSTIC_ONLY'
            probe_date=next((d for d in dates if d.weekday()<5),dates[-1]).strftime('%Y%m%d')
            fdr_diagnostic(audit,probe_date)
    except Exception as exc:
        audit['errors'].append({'stage':'main','type':type(exc).__name__,'message':str(exc)[:350]})
    finally:
        (out/'market_data_v52_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(audit,ensure_ascii=False,indent=2))
    return 0 if audit['row_count'] else 2

if __name__=='__main__':
    sys.exit(main())
