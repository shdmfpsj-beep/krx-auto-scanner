"""Experimental free NAVER OHLCV reference. Never certifies regular-session prices."""
import argparse
import csv
import json
from pathlib import Path

FIELDS=("open","high","low","close","volume")

def normalize(ticker, frame):
    if frame is None or frame.empty:
        raise ValueError("EMPTY_NAVER_REFERENCE:"+ticker)
    required=("Open","High","Low","Close","Volume")
    if any(field not in frame.columns for field in required):
        raise ValueError("MISSING_NAVER_OHLCV:"+ticker)
    result=[]
    for day,row in frame.iterrows():
        date=day.strftime("%Y-%m-%d")
        values=[float(row[k]) for k in required]
        if any(not __import__("math").isfinite(v) for v in values):
            raise ValueError("NONFINITE_NAVER_PRICE:"+ticker)
        o,h,l,c,v=values
        if min(o,h,l,c)<=0 or v<0 or l>min(o,c) or h<max(o,c):
            raise ValueError("INVALID_NAVER_OHLCV:"+ticker)
        result.append(dict(ticker=ticker,date=date,open=o,high=h,low=l,close=c,volume=v))
    if len({r["date"] for r in result})!=len(result):
        raise ValueError("DUPLICATE_NAVER_DATE:"+ticker)
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True)
    p.add_argument("--start",required=True)
    p.add_argument("--end",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--status",required=True)
    a=p.parse_args()
    import FinanceDataReader as fdr
    with open(a.plans,encoding="utf-8-sig",newline="") as f:
        plans=list(csv.DictReader(f))
    tickers=[r["ticker"] for r in plans]
    if len(tickers)!=2 or len(set(tickers))!=2:
        raise ValueError("EXPECTED_UNIQUE_TOP2")
    rows=[]
    for ticker in tickers:
        frame=fdr.DataReader("NAVER:"+ticker,a.start,a.end)
        rows.extend(normalize(ticker,frame))
    if not rows or any(not any(r["ticker"]==t for r in rows) for t in tickers):
        raise ValueError("NAVER_REFERENCE_INCOMPLETE")
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=("ticker","date",*FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    status=dict(schema="C3_NAVER_REFERENCE_EXPERIMENT_V1",provider="FinanceDataReader_NAVER",
                rows=len(rows),tickers=tickers,regular_only_certified=False,
                adjustment_basis_verified=False,independent_source_certified=False,
                trade_approved=False,orders_enabled=False)
    Path(a.status).write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(status,ensure_ascii=False))
if __name__=="__main__":
    main()
