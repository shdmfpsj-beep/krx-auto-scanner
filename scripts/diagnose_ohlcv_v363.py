"""C3 v3.6.3 research-only OHLCV failure diagnostics.
Run: python scripts/diagnose_ohlcv_v363.py
Does not alter the v3.6 backtest, data coverage gate, or live strategy.
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import FinanceDataReader as fdr

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'


def inspect(ticker, start, end):
    data = fdr.DataReader(ticker, start, (end + pd.Timedelta(days=1)).strftime('%Y-%m-%d'))
    if data is None or data.empty:
        return [{'ticker': ticker, 'date': '', 'issue': 'empty_history', 'detail': ''}]
    data = data.copy()
    data.index = pd.DatetimeIndex(pd.to_datetime(data.index)).normalize()
    data = data.loc[(data.index >= pd.Timestamp(start)) & (data.index <= end)].sort_index()
    issues = []
    if data.index.has_duplicates:
        for date in data.index[data.index.duplicated(keep=False)].unique():
            issues.append({'ticker':ticker,'date':date.date().isoformat(),'issue':'duplicate_date','detail':''})
    columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    for col in columns:
        if col not in data.columns:
            return [{'ticker':ticker,'date':'','issue':'missing_column','detail':col}]
        data[col] = pd.to_numeric(data[col], errors='coerce')
    for date, row in data.iterrows():
        o, h, l, c = [row[k] for k in ('Open','High','Low','Close')]
        bad = []
        if pd.isna([o,h,l,c]).any():
            bad.append('missing_price')
        elif min(o,h,l,c) <= 0:
            bad.append('nonpositive_price')
        elif h < max(o,c,l) or l > min(o,c,h):
            bad.append('ohlc_inconsistent')
        if bad:
            detail = ','.join(f'{k}={row[k]}' for k in columns)
            issues.append({'ticker':ticker,'date':date.date().isoformat(),
                           'issue':'+'.join(bad),'detail':detail})
    if not issues:
        issues.append({'ticker':ticker,'date':'','issue':'no_ohlc_anomaly_found',
                       'detail':f'rows={len(data)}'})
    return issues


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--failures',default=str(REPORTS/'realism_v36_failures.csv'))
    p.add_argument('--input',default=str(REPORTS/'entry_v32_paired_trades.csv'))
    p.add_argument('--delay',type=float,default=1.0)
    args=p.parse_args()
    failures=pd.read_csv(args.failures,dtype={'ticker':str})
    signals=pd.read_csv(args.input,dtype={'ticker':str})
    signals=signals.loc[signals['hold'].eq(1)]
    signals['entry_date']=pd.to_datetime(signals['entry_date'])
    start=signals['entry_date'].min()-pd.Timedelta(days=10)
    end=signals['entry_date'].max()+pd.Timedelta(days=60)
    out=[]
    for ticker in failures['ticker'].dropna().unique():
        ticker=ticker.zfill(6)
        try:
            rows=inspect(ticker,start,end)
        except Exception as exc:
            rows=[{'ticker':ticker,'date':'','issue':'download_or_parse_error',
                   'detail':f'{type(exc).__name__}: {str(exc)[:400]}'}]
        out.extend(rows)
        print(ticker, len(rows), rows[0]['issue'],flush=True)
        time.sleep(max(0,args.delay))
    REPORTS.mkdir(exist_ok=True,parents=True)
    pd.DataFrame(out,columns=['ticker','date','issue','detail']).to_csv(
        REPORTS/'realism_v363_ohlcv_diagnostics.csv',index=False,encoding='utf-8-sig')
    summary={'version':'v3.6.3 diagnostic only','run_kst':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
             'failed_tickers_checked':int(failures['ticker'].nunique()),
             'issue_counts':pd.Series([r['issue'] for r in out]).value_counts().to_dict(),
             'live_trade_approval':False}
    (REPORTS/'realism_v363_diagnostics_metadata.json').write_text(
        json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Diagnostic reports written; no backtest acceptance rules changed.')

if __name__=='__main__':
    main()
