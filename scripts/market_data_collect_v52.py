#!/usr/bin/env python3
"""v5.2 research-only KRX daily market snapshot; fail closed on missing evidence.
Requires: pip install pykrx pandas. Does not place orders or claim real-time data.
"""
import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
FIELDS = ['ticker','name','market','snapshot_date','open','high','low','close','volume','verified_turnover_krw','turnover_source','instrument_status','snapshot_source']

def number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--outdir',default='reports')
    p.add_argument('--date',default='',help='YYYYMMDD; default most recent available within 10 calendar days')
    args=p.parse_args()
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    audit={'version':'v5.2','status':'NO_DATA','research_only':True,'asof_run_kst':datetime.now(KST).isoformat(), 'requested_date':args.date or 'AUTO','source':'pykrx/KRX market OHLCV','limitations':['Exchange-sourced through third-party pykrx, not independently reconciled','Instrument classification is conservative; common stock NOT independently verified','No intraday data, sector money flow, institutional flow, order book, or entry triggers','No live trading approval']}
    rows=[]; errors=[]
    try:
        from pykrx import stock
        if args.date:
            dates=[datetime.strptime(args.date,'%Y%m%d').date()]
        else:
            today=datetime.now(KST).date()
            dates=[today-timedelta(days=i) for i in range(11)]
        for d in dates:
            date=d.strftime('%Y%m%d'); day=[]
            for market in ('KOSPI','KOSDAQ'):
                try:
                    df=stock.get_market_ohlcv_by_ticker(date,market=market)
                    if df is None or df.empty:
                        errors.append(f'{date} {market}: empty')
                        day=[];break
                    cols=set(map(str,df.columns))
                    required={'시가','고가','저가','종가','거래량','거래대금'}
                    if not required.issubset(cols):
                        errors.append(f'{date} {market}: missing {sorted(required-cols)}')
                        day=[];break
                    for ticker,rec in df.iterrows():
                        t=str(ticker).zfill(6)
                        try: name=stock.get_market_ticker_name(t) or ''
                        except Exception: name=''
                        if not name: name=''
                        day.append({'ticker':t,'name':name,'market':market,'snapshot_date':d.isoformat(),
                          'open':number(rec['시가']),'high':number(rec['고가']),'low':number(rec['저가']),
                          'close':number(rec['종가']),'volume':number(rec['거래량']),
                          'verified_turnover_krw':number(rec['거래대금']),
                          'turnover_source':'PYKRX_KRX_DAILY_OHLCV',
                          'instrument_status':'UNKNOWN_VERIFY',
                          'snapshot_source':'pykrx.stock.get_market_ohlcv_by_ticker'})
                except Exception as exc:
                    errors.append(f'{date} {market}: {type(exc).__name__}: {str(exc)[:160]}')
                    day=[];break
            if day and all(any(x['market']==m for x in day) for m in ('KOSPI','KOSDAQ')):
                rows=day;audit['snapshot_date']=d.isoformat();break
        if rows:
            with (out/'market_data_v52.csv').open('w',newline='',encoding='utf-8-sig') as f:
                w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
            audit.update(status='DAILY_SNAPSHOT_COLLECTED_NOT_LIVE',row_count=len(rows),market_counts={m:sum(r['market']==m for r in rows) for m in ('KOSPI','KOSDAQ')},verified_common_stocks=0,live_buy_approved=0)
        else:
            audit.update(status='DATA_UNAVAILABLE',row_count=0,live_buy_approved=0)
    except Exception as exc:
        errors.append(f'initialization: {type(exc).__name__}: {str(exc)[:200]}')
        audit.update(status='DATA_UNAVAILABLE',row_count=0,live_buy_approved=0)
    audit['errors']=errors[-30:]
    (out/'market_data_v52_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))
    return 0 if rows else 2

if __name__=='__main__':sys.exit(main())
