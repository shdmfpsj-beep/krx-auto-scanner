#!/usr/bin/env python3
"""As-of evidence join for PR87/PR88 exploratory cohorts.
No substitutions of missing index, investor flows, original PIT or live TOP2.
Read-only, no orders, no score changes, no ledger writes.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter,defaultdict
from pathlib import Path

def load_csv(p):
    if p is None or not Path(p).is_file():return []
    with open(p,encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def load_json(p):
    if p is None or not Path(p).is_file():return {}
    return json.loads(Path(p).read_text(encoding="utf-8"))

def historical_operational_keys(paper,registry,selection):
    keys=set()
    for p in (paper.get("positions") or {}).values():
        plan=p.get("plan",{})
        if plan.get("selection_date") and plan.get("ticker"):
            keys.add((str(plan["ticker"]),str(plan["selection_date"])))
    for r in registry:
        if r.get("ticker") and r.get("price_date"):
            keys.add((str(r["ticker"]),str(r["price_date"])))
    for part in ("provisional_watch_top2","provisional_watch_top5"):
        for r in selection.get(part,[]):
            if r.get("ticker") and r.get("price_date"):
                keys.add((str(r["ticker"]),str(r["price_date"])))
    return keys

def source_manifest(root,day):
    folder=root/day
    manifest=load_json(folder/"krx_v65_collect_status.json")
    if not manifest.get("official_dataset_usable") or manifest.get("asof")!=day:
        return None,{},{}
    files={}
    content={}
    for market in ("KOSPI","KOSDAQ"):
        p=folder/(market+"_official.csv")
        if not p.exists():return None,{},{}
        sha=hashlib.sha256(p.read_bytes()).hexdigest()
        if sha!=manifest.get("market_file_sha256",{}).get(market):
            return None,{},{}
        files[market]=sha
        content[market]=load_csv(p)
    return manifest,files,content

def audit(cohort,root,financial=None,financial_quality=None,paper=None,registry=None,selection=None):
    events=cohort.get("events",[])
    f_by=defaultdict(list)
    for r in financial or []:
        if r.get("ticker") and r.get("available_date"):
            f_by[str(r["ticker"])].append(r)
    for rows in f_by.values():
        rows.sort(key=lambda v:(v["available_date"],v.get("receipt_no","")))
    opkeys=historical_operational_keys(paper or {},registry or [],selection or {})
    date_cache={}
    joined=[]
    counts=Counter()
    for e in events:
        ticker,date=str(e["ticker"]),str(e["date"])
        if date not in date_cache:
            date_cache[date]=source_manifest(root,date)
        manifest,sha,markets=date_cache[date]
        found=[]
        if manifest:
            for market,rows in markets.items():
                found += [(market,r) for r in rows if str(r.get("ticker"))==ticker]
        valid_source=len(found)==1 and found[0][1].get("valid_daily_bar")=="True"
        market=found[0][0] if valid_source else None
        counts["equity_rows_with_hashed_official_eod"]+=bool(valid_source)
        if valid_source:counts["market_"+market]+=1
        alnum=len(ticker)==6 and ticker.isalnum() and not ticker.isdigit()
        counts["alphanumeric_6char_tickers"]+=alnum
        eligible=[r for r in f_by.get(ticker,[]) if r["available_date"]<=date]
        latest=eligible[-1] if eligible else None
        counts["provisional_financial_date_matches"]+=bool(latest)
        numeric_certified=False # v91 current API/receipt never independently original-PIT certified
        market_name=found[0][1].get("name") if valid_source else None
        same_date=(ticker,date) in opkeys
        counts["same_ticker_date_operational_records"]+=same_date
        joined.append({
            "ticker":ticker,"date":date,"market":market,"name":market_name,
            "source":("KRX_EOD_HASH_VERIFIED_1530_UNCERTIFIED" if valid_source else "BLOCKED_NO_VALID_SOURCE_ROW"),
            "source_sha256":sha.get(market) if market else None,
            "share_type":"UNVERIFIED_NO_ISSUE_CLASSIFICATION",
            "delisting_and_management":"UNVERIFIED_NO_HISTORICAL_ISSUER_STATE",
            "corporate_actions":"UNVERIFIED_NO_ADJUSTMENT_VERIFICATION",
            "index_20d_relative_strength":"BLOCKED_NO_DATED_INDEX_CLOSE_SERIES",
            "foreign_institutional_net_flow":"BLOCKED_NO_VERIFIED_INVESTOR_TYPE_FILE",
            "financial":{
                "status":("DATE_JOIN_ONLY_NOT_ORIGINAL_PIT" if latest else "BLOCKED_NO_PRIOR_FILING"),
                "available_date":latest.get("available_date") if latest else None,
                "filing_date":latest.get("filing_date") if latest else None,
                "receipt_no":latest.get("receipt_no") if latest else None,
                "source_status":latest.get("validation_status") if latest else None,
                "numeric_pit_certified":numeric_certified,
            },
            "operational_top2_same_date":("DATE_RECORD_EXISTS_NOT_PROVEN_LIVE_TOP2" if same_date else "BLOCKED_NO_SAME_DATE_TOP2"),
            "may_approve_trading":False
        })
    return {
        "schema":"C3_PR87_STRICT_ASOF_FILE_JOIN_V1",
        "event_count":len(events),
        "unique_ticker_dates":len({(str(e["ticker"]),str(e["date"])) for e in events}),
        "source_counts":dict(counts),
        "financial_strict_pit_approved":bool((financial_quality or {}).get("strict_pit_approved") is True and False),
        "market_index":"BLOCKED","investor_type_flow":"BLOCKED",
        "operational_top2_comparison":"BLOCKED" if not counts["same_ticker_date_operational_records"] else "DATE_JOIN_ONLY",
        "fundamental_filter":"UNVERIFIED_NO_ORIGINAL_NUMERIC_VINTAGE",
        "share_type_and_corporate_actions":"UNVERIFIED",
        "same_day_signal_and_filing_future_leakage_prevented":True,
        "trading_approved":False,"decision":"CASH","production_changed":False,
        "events":joined
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cohort",type=Path,required=True)
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--financial",type=Path,required=True)
    p.add_argument("--financial-quality",type=Path,required=True)
    p.add_argument("--paper",type=Path,required=True)
    p.add_argument("--registry",type=Path,required=True)
    p.add_argument("--selection",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    d=audit(load_json(a.cohort),a.root,load_csv(a.financial),load_json(a.financial_quality),
            load_json(a.paper),load_csv(a.registry),load_json(a.selection))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("C3_ASOF_JOIN",json.dumps({k:v for k,v in d.items() if k!="events"},ensure_ascii=False))

if __name__=="__main__":main()
