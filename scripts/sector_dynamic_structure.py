#!/usr/bin/env python3
"""Sector TOP3 -> dynamically picked quality-research tickers -> independent
free OHLCV price/stop references. Never turns a research watchlist into BUY.

Uses existing research rows as *membership and selection* only. Fresh daily
OHLC comes independently from free FDR / pykrx; no paid API or secrets.
"""
import argparse
import csv
import json
import re
from datetime import date,datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from focus_daily_structure import calculate,fetch_history,save

BANNED=("HEALTH","PHARMA","BIOTECH","바이오","제약")

def read_rows(path):
    if not path.is_file():
        return []
    with path.open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def priority(row):
    try:
        v=float(row.get("research_proxy_index",""))
        return v if v==v and abs(v)<float("inf") else -1
    except (TypeError,ValueError):
        return -1

def select(status,rows,asof,max_total=12,per_sector=4):
    """Fail closed for stale data. Sector-balanced, not previous holdings-driven."""
    if not isinstance(status,dict) or status.get("asof")!=str(asof) or (
           status.get("scan_date")!=str(asof)) or not status.get("core_data_verified") or (
           not status.get("evidence_scan_dates_aligned")):
        return {},["MISSING_OR_STALE_VERIFIED_SECTOR_UNIVERSE"]
    sectors=status.get("research_top3_sector_ids")
    if not isinstance(sectors,list) or not sectors:
        return {},["SECTOR_TOP3_NOT_AVAILABLE"]
    sectors=[str(x) for x in sectors[:3] if not any(
        tag in str(x).upper() for tag in BANNED)]
    if not sectors:
        return {},["NO_ALLOWED_SECTORS"]
    eligible={}
    for r in rows:
        ticker=str(r.get("ticker","")).strip()
        sid=str(r.get("sector_id",""))
        name=str(r.get("name","")).strip()
        if (sid not in sectors or not re.fullmatch(r"\d{6}",ticker) or
                r.get("asof")!=str(asof) or
                r.get("price_flow_ready")!="YES" or
                priority(r)<0 or any(tag in (sid+" "+name).upper() for tag in BANNED)):
            continue
        if r.get("trade_approval") not in ("NO",""):
            continue
        old=eligible.get(ticker)
        if old is None or priority(r)>priority(old):
            eligible[ticker]=r
    by_sector={sid:[] for sid in sectors}
    for r in eligible.values():
        by_sector[r["sector_id"]].append(r)
    for arr in by_sector.values():
        arr.sort(key=lambda r:(-priority(r),r["ticker"]))
    picked={}
    for sid in sectors:
        for r in by_sector[sid][:per_sector]:
            if len(picked)<max_total:
                picked[r["ticker"]]=r["name"] or r["ticker"]
    # Fill remaining slots with ranked members of verified TOP3 sectors.
    additional=sorted(eligible.values(),key=lambda r:(-priority(r),r["ticker"]))
    for r in additional:
        if len(picked)>=max_total:break
        picked.setdefault(r["ticker"],r["name"] or r["ticker"])
    problems=[]
    if not picked:
        problems.append("NO_FRESH_TOP3_STOCK_RESEARCH_ROWS")
    return picked,problems

def generate(status,stock_rows,asof,fetch=fetch_history,max_total=12,per_sector=4):
    names,issues=select(status,stock_rows,asof,max_total,per_sector)
    results=[]
    for ticker,name in names.items():
        try:
            bars,source,errors=fetch(ticker,asof)
        except Exception as ex:
            bars,source,errors=[],"NONE",["COLLECTOR_"+type(ex).__name__]
        result=calculate(ticker,name,bars,source,errors,asof)
        result["candidate_source"]="TOP3_SECTOR_DYNAMIC_RESEARCH"
        results.append(result)
    return results,names,issues

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--status",type=Path,default=Path("output/sector_bridge_status.json"))
    parser.add_argument("--watchlist",type=Path,default=Path("output/sector_stock_research_ranking.csv"))
    parser.add_argument("--out",type=Path,default=Path("output/dynamic"))
    parser.add_argument("--max-total",type=int,default=12)
    parser.add_argument("--per-sector",type=int,default=4)
    parser.add_argument("--asof",default=datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat())
    a=parser.parse_args()
    try:
        status=json.loads(a.status.read_text(encoding="utf-8")) if a.status.is_file() else {}
    except (ValueError,OSError):
        status={}
    asof=date.fromisoformat(a.asof)
    if not (1<=a.max_total<=20 and 1<=a.per_sector<=10):
        raise SystemExit("INVALID_SECTOR_FOCUS_LIMITS")
    rows,names,issues=generate(status,read_rows(a.watchlist),asof,
                              max_total=a.max_total,per_sector=a.per_sector)
    audit=save(rows,a.out)
    audit.update(dynamic_top3_sector_watchlist=True,
       sector_research_asof=status.get("asof"),
       candidate_tickers=list(names),selection_blockers=issues,
       total_dynamic_candidates=len(names),decision="CASH",trade_approved=False)
    (a.out/"focus_daily_structure_status.json").write_text(
      json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(dict(sector_asof=status.get("asof"),
      candidates=len(names),daily_stop_references=audit["stop_reference_count"],
      problems=issues,decision="CASH"),ensure_ascii=False))

if __name__=="__main__":
    main()
