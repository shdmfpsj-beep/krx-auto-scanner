"""C3 v3.6.3 OHLCV diagnostic; independent of previous workflow artifacts.
Usage: python scripts/diagnose_ohlcv_v363.py
Research only. Does not alter trading rules or coverage requirements.
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
# The 15 failed tickers were confirmed in the prior v3.6.2 artifact.
KNOWN_FAILED = ('001460','006040','011230','025900','064850',
                '067570','073640','088980','101360','119650',
                '138360','246250','279600','319400','457190')
COLS = ('Open','High','Low','Close','Volume')


def inspect(ticker, start, end):
    raw = fdr.DataReader(ticker, start.strftime('%Y-%m-%d'),
                         (end + pd.Timedelta(days=1)).strftime('%Y-%m-%d'))
    if raw is None or raw.empty:
        return [{'ticker':ticker,'date':'','issue':'empty_history','detail':''}]
    data = raw.copy()
    data.index = pd.DatetimeIndex(pd.to_datetime(data.index, errors='raise')).normalize()
    data = data.loc[(data.index >= start) & (data.index <= end)].sort_index()
    if data.empty:
        return [{'ticker':ticker,'date':'','issue':'empty_in_requested_window','detail':''}]
    issues = []
    for date in data.index[data.index.duplicated(keep=False)].unique():
        issues.append({'ticker':ticker,'date':date.date().isoformat(),
                       'issue':'duplicate_date','detail':''})
    for col in COLS:
        if col not in data.columns:
            issues.append({'ticker':ticker,'date':'','issue':'missing_column','detail':col})
    if any(c not in data.columns for c in COLS):
        return issues
    for col in COLS:
        data[col] = pd.to_numeric(data[col], errors='coerce')
    for date, row in data.iterrows():
        o,h,l,c = (row[k] for k in ('Open','High','Low','Close'))
        if pd.isna([o,h,l,c]).any():
            issue='missing_price'
        elif min(o,h,l,c) <= 0:
            issue='nonpositive_price'
        elif h < max(o,c,l) or l > min(o,c,h):
            issue='ohlc_inconsistent'
        else:
            continue
        issues.append({'ticker':ticker,'date':date.date().isoformat(),
                       'issue':issue,
                       'detail':','.join(f'{k}={row[k]}' for k in COLS)})
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
    if args.delay < 0:
        p.error('--delay must be >= 0')
    failures_path=Path(args.failures)
    if failures_path.is_file():
        failures=pd.read_csv(failures_path,dtype={'ticker':str})
        if 'ticker' not in failures:
            raise ValueError('Failures CSV missing ticker column')
        tickers=sorted({str(t).strip().zfill(6) for t in failures.ticker.dropna()
                        if str(t).strip()})
        source='failures_csv'
    else:
        tickers=list(KNOWN_FAILED)
        source='known_15_failed_tickers_fallback'
        print('Failures CSV unavailable; diagnosing 15 tickers from prior artifact.',flush=True)
    signals=pd.read_csv(args.input,dtype={'ticker':str},usecols=['ticker','hold','entry_date'])
    signals=signals.loc[pd.to_numeric(signals.hold,errors='coerce').eq(1)].copy()
    if signals.empty:
        raise ValueError('No hold=1 entry signals')
    signals['entry_date']=pd.to_datetime(signals.entry_date,errors='raise')
    start=signals.entry_date.min().normalize()-pd.Timedelta(days=10)
    end=signals.entry_date.max().normalize()+pd.Timedelta(days=60)
    out=[]
    for ticker in tickers:
        try:
            rows=inspect(ticker,start,end)
        except Exception as exc:
            rows=[{'ticker':ticker,'date':'','issue':'download_or_parse_error',
                   'detail':f'{type(exc).__name__}: {str(exc)[:400]}'}]
        out.extend(rows)
        print(ticker,len(rows),rows[0]['issue'],flush=True)
        time.sleep(args.delay)
    REPORTS.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(out,columns=['ticker','date','issue','detail']).to_csv(
        REPORTS/'realism_v363_ohlcv_diagnostics.csv',index=False,encoding='utf-8-sig')
    meta={'version':'v3.6.3 independent diagnostic','run_kst':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
          'ticker_source':source,'failed_tickers_checked':len(tickers),
          'issue_counts':pd.Series([r['issue'] for r in out]).value_counts().to_dict(),
          'live_trade_approval':False}
    (REPORTS/'realism_v363_diagnostics_metadata.json').write_text(
        json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Diagnostic reports written; backtest coverage gate unchanged.',flush=True)


if __name__=='__main__':
    main()
