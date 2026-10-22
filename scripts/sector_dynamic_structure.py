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
from datetime import date,datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from focus_daily_structure import calculate,fetch_history,save,normalize

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

def reuse_v18_daily_bars(evidence_root,tickers,asof):
    """Reuse dated, completed KRX daily OHLCV already collected by v18.

    No guessing about missing highs/lows. Missing or insufficient samples are
    handled by the existing independent FDR/pykrx fallback instead.
    """
    if not evidence_root or not Path(evidence_root).is_dir() or not tickers:
        return {}
    roots=list(Path(evidence_root).rglob("market/daily_prices"))
    if len(roots)!=1:
        return {}
    root=roots[0]
    found={t:{} for t in tickers}
    duplicates=set()
    start=asof-timedelta(days=240)
    for market in ("KOSPI","KOSDAQ"):
        folder=root/market
        if not folder.is_dir():continue
        for path in sorted(folder.glob("*.csv")):
            try:d=date.fromisoformat(path.stem[:10])
            except ValueError:continue
            if not start<=d<=asof:continue
            with path.open(encoding="utf-8-sig",newline="") as file:
                for r in csv.DictReader(file):
                    ticker=str(r.get("ticker","")).strip()
                    if ticker not in found:continue
                    try:bar_date=date.fromisoformat(str(r.get("Date",""))[:10])
                    except ValueError:continue
                    if bar_date!=d:
                        duplicates.add(ticker)
                        continue
                    if d in found[ticker]:
                        duplicates.add(ticker)
                    else:
                        found[ticker][d]=dict(date=str(d),
                            open=r.get("Open"),high=r.get("High"),
                            low=r.get("Low"),close=r.get("Close"),
                            volume=r.get("Volume"))
    cache={}
    for ticker,byday in found.items():
        if ticker in duplicates or asof not in byday:continue
        bars,problem=normalize(ticker,[byday[k] for k in sorted(byday)])
        if not problem:
            cache[ticker]=(bars,"V18_KRX_CACHED",[])
    return cache

def generate(status,stock_rows,asof,fetch=fetch_history,max_total=12,per_sector=4,
             evidence_root=None):
    names,issues=select(status,stock_rows,asof,max_total,per_sector)
    results=[]
    # Cached v18 evidence is read once across all selected candidates.
    # Avoid N separate paid or redundant network requests.
    try:
        cache=reuse_v18_daily_bars(evidence_root,names,asof)
    except (OSError,ValueError,csv.Error):
        cache={}
        issues.append("V18_OHLCV_CACHE_UNAVAILABLE")
    for ticker,name in names.items():
        try:
            if ticker in cache:
                bars,source,errors=cache[ticker]
            else:
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
    parser.add_argument("--evidence-root",type=Path,default=Path("inputs/evidence"))
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
                              max_total=a.max_total,per_sector=a.per_sector,
                              evidence_root=a.evidence_root)
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
