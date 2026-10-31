#!/usr/bin/env python3
"""Collect read-only dated stock OHLCV for PRE-REGISTERED C3 paper plans.

Uses pykrx adjusted=True, same provider class as the original scan. No
certification of KRX 09:00-15:30 regular-only scope; market-open-day decisions
are made only from correctly dated completed bars and matched scanner asof.
"""
from __future__ import annotations
import argparse,csv,hashlib,json
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from c3_paper_forward_v1 import load_csv,PLANS_REQUIRED,bar_valid

COLUMNS=("ticker","date","open","high","low","close","volume")

def collect(plans_path,outdir,now=None,fetch=None):
    now=(now or datetime.now(ZoneInfo("Asia/Seoul"))).astimezone(ZoneInfo("Asia/Seoul"))
    if now.hour<20 or now.hour==20 and now.minute<15:
        raise ValueError("SOURCE_CUTOFF_BEFORE_2015_KST")
    if fetch is None:
        from pykrx import stock
        fetch=lambda start,end,ticker: stock.get_market_ohlcv_by_date(
            start,end,ticker,adjusted=True)
    plans=load_csv(plans_path,PLANS_REQUIRED)
    codes=sorted({r["ticker"] for r in plans})
    start=(now.date()-timedelta(days=24)).strftime("%Y%m%d")
    end=now.date().strftime("%Y%m%d")
    folder=Path(outdir);folder.mkdir(parents=True,exist_ok=True)
    rows=[];status={}
    for ticker in codes:
        try:
            df=fetch(start,end,ticker)
            if df is None or df.empty:raise ValueError("EMPTY_SERIES")
            series=[]
            for stamp,record in df.iterrows():
                day=str(stamp.date() if hasattr(stamp,"date") else stamp)[:10]
                if day>now.date().isoformat():raise ValueError("FUTURE_PROVIDER_BAR")
                o=dict(ticker=ticker,date=day,open=record["시가"],
                   high=record["고가"],low=record["저가"],close=record["종가"],
                   volume=record["거래량"])
                series.append(bar_valid(o))
            rows.extend(series)
            status[ticker]=dict(capture_status="OHLCV_OBSERVED_UNVERIFIED_SCOPE",
                last_session=series[-1]["date"],historical_bars=len(series),
                provider="PYKRX_ADJUSTED_TRUE")
        except Exception as exc:
            status[ticker]=dict(capture_status="FAILED_OR_SUSPENDED_NO_PAPER_TRADE",
                error_type=type(exc).__name__,
                provider="PYKRX_ADJUSTED_TRUE")
    out=folder/"c3_paper_price_capture.csv"
    with out.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=COLUMNS);w.writeheader();w.writerows(rows)
    report=dict(schema="C3_PAPER_PRICE_CAPTURE_V1",captured_at_kst=now.isoformat(),
       fetch_to_day=end,requested_registered_symbols=len(codes),
       source_scope="PYKRX_ADJUSTED_TRUE_REGULAR_SESSION_UNCERTIFIED",
       source_provenance="C3 paper tracker supplemental read-only API; not identical to officially certified KRX close",
       ticker_states=status,regular_only_ohlcv_certified=False,
       raw_price_csv_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
       trade_approved=False,orders_enabled=False)
    (folder/"c3_paper_price_source_status.json").write_text(
       json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True);p.add_argument("--outdir",required=True)
    a=p.parse_args()
    x=collect(a.plans,a.outdir)
    print(json.dumps(dict(captured_at_kst=x["captured_at_kst"],
        requested_registered_symbols=x["requested_registered_symbols"],
        source_certified=x["regular_only_ohlcv_certified"]),ensure_ascii=False))
