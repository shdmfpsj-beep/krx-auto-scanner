#!/usr/bin/env python3
"""Shrink one complete Sector Evidence v18 run to immutable dated KOSPI/KOSDAQ.

This creates an exact SHA-256 full-market daily observation snapshot, NOT
independently verified 09:00–15:30 regular-session price or trade authority.
A day's file may be used in forward monitoring only if its collection truly
completed AFTER the original frozen signal snapshot.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,shutil
from collections import Counter
from datetime import date,datetime,timezone
from pathlib import Path

SCHEMA="C3_K100_FULLMARKET_DAY_SLICE_V63"
REQUIRED_COLUMNS=("ticker","Date","Open","High","Low","Close","Volume","TurnoverKRW")
MARKETS=("KOSPI","KOSDAQ")
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def date_value(s):
    try:
        d=date.fromisoformat(s)
        if d.isoformat()==s:return d
    except (TypeError,ValueError):pass
    raise ValueError("V18_ASOF_NOT_ISO_DATE")
def stamp(s):
    try:t=datetime.fromisoformat(s.replace("Z","+00:00"))
    except (TypeError,AttributeError,ValueError):raise ValueError("SOURCE_TIME_UNREADABLE")
    if t.tzinfo is None or t.utcoffset()!=timezone.utc.utcoffset(t):
        raise ValueError("SOURCE_TIME_NOT_UTC")
    return t
def day_market(src,asof):
    if not Path(src).is_file():raise ValueError("MARKET_FILE_MISSING")
    seen=set()
    with Path(src).open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        if tuple(reader.fieldnames or ())!=REQUIRED_COLUMNS:
            raise ValueError("MARKET_COLUMNS_UNEXPECTED")
        n=0
        for row in reader:
            t=row["ticker"]
            if (len(t)!=6 or not t.isdigit() or t in seen
                or row["Date"]!=asof):
                raise ValueError("MARKET_DUPLICATE_TICKER_OR_DATE")
            seen.add(t);n+=1
            for field in REQUIRED_COLUMNS[2:]:
                try:float(row[field])
                except (ValueError,TypeError):raise ValueError("NONNUMERIC_MARKET_FIELD")
    if n<100:raise ValueError("MARKET_UNIVERSE_TOO_SMALL")
    return n,seen
def extract(report,outdir,run_id,completed):
    q=json.loads((report/"diagnostics/collection_status.json").read_text(encoding="utf-8"))
    d=date_value(q.get("asof"))
    krx=q.get("datasets",{}).get("krx_preflight",{})
    if (krx.get("status")!="OK" or krx.get("asof")!=str(d)
        or q.get("orders_enabled") is not False):
        raise ValueError("V18_SOURCE_NOT_COMPLETED_OR_NO_TRADE")
    if not str(run_id).isdigit():raise ValueError("V18_EXACT_RUN_ID_REQUIRED")
    clock=stamp(completed)
    if clock.date()<d:raise ValueError("COLLECTION_TIME_BEFORE_MARKET")
    dest=outdir/str(d)
    dest.mkdir(parents=True,exist_ok=True)
    counts={};hashes={};markets=[]
    for market in MARKETS:
        src=report/f"market/daily_prices/{market}/{d}.csv"
        count,all_tickers=day_market(src,str(d))
        counts[market]=count
        markets.append(all_tickers)
        target=dest/f"{market}.csv"
        shutil.copy2(src,target)
        hashes[market]=sha(target)
    if markets[0]&markets[1]:
        raise ValueError("SAME_TICKER_IN_KOSPI_AND_KOSDAQ")
    metadata=dict(schema=SCHEMA,asof=str(d),v18_run_id=str(run_id),
        source_completed_utc=clock.isoformat(),source_run_success=True,
        regular_only_verified=False,market_counts=counts,
        total_covered_tickers=sum(counts.values()),
        sha256=hashes,source_notes="v18 completed daily OHLC; sessions and adjustments not independently verified",
        orders_enabled=False,trade_approved=False)
    (dest/"meta.json").write_text(
        json.dumps(metadata,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return metadata
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--outdir",type=Path,required=True)
    p.add_argument("--v18-run-id",required=True)
    p.add_argument("--completed-utc",required=True)
    a=p.parse_args()
    print(json.dumps(extract(a.report,a.outdir,a.v18_run_id,a.completed_utc),
        ensure_ascii=False))
if __name__=="__main__":main()
