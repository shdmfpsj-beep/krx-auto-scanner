#!/usr/bin/env python3
"""Read-only join of dated DART disclosure titles to KRX adjacent-day anomalies.
A filing *title* may indicate planned corporate action, never proves ex-date or ratio.
Do not infer adjusted prices or shareholder total return from a title.
"""
import argparse,csv,io,json,zipfile
from collections import Counter,defaultdict
from datetime import date
from pathlib import Path
from c3_v11_adjacent_anomaly_issuer import read_adjacent

ACTION_TERMS=("권리락","무상증자","액면분할","주식분할","병합","감자결정","유무상증자")
HALT_TERMS=("매매거래정지","상장폐지","거래정지")
LOOKBACK_DAYS=30

def classify_title(title):
    value=str(title or "").strip()
    if any(k in value for k in ACTION_TERMS):return "CORPORATE_DISCLOSURE_TITLE"
    if any(k in value for k in HALT_TERMS):return "HALT_OR_DELISTING_DISCLOSURE_TITLE"
    return None

def join(events,disclosures):
    by=defaultdict(list)
    for x in disclosures:
        t=str(x.get("ticker") or "").strip()
        try:pub=date.fromisoformat(str(x["receipt_date"]))
        except (KeyError,ValueError):continue
        typ=classify_title(x.get("report_name"))
        if not t or not typ:continue
        receipt=str(x.get("receipt_no") or "")
        if len(receipt)!=14 or not receipt.isdigit():continue
        by[t].append((pub,typ,x))
    matches=[];count=Counter()
    for e in events:
        try:d=date.fromisoformat(e["date"])
        except ValueError:raise ValueError("INVALID_ANOMALY_DATE")
        allowed=[]
        for pub,kind,x in by.get(e["ticker"],[]):
            delta=(d-pub).days
            # Publication time is unknown; even same-day receipt is not usable
            # at 15:30. Require receipt_date strictly BEFORE observed anomaly day.
            if not 1<=delta<=LOOKBACK_DAYS:continue
            allowed.append({"receipt_date":pub.isoformat(),"days_prior":delta,
                "kind":kind,"receipt_no":x["receipt_no"],
                "report_name":x["report_name"].strip()})
        allowed.sort(key=lambda x:(x["days_prior"],x["receipt_no"]))
        kinds={x["kind"] for x in allowed}
        label=("PRIOR_ACTION_TITLE_UNVERIFIED_CAUSE" if "CORPORATE_DISCLOSURE_TITLE" in kinds
            else "PRIOR_HALT_TITLE_UNVERIFIED_CAUSE" if kinds else "NO_MATCHING_PRIOR_TITLE_IN_SNAPSHOT")
        count[label]+=1
        matches.append({**e,"label":label,"prior_30_day_titles":allowed[:6]})
    return {"schema":"C3_V11_DART_ADJACENT_ANOMALY_TITLE_JOIN",
        "strictly_prior_day_only":True,"lookback_calendar_days":LOOKBACK_DAYS,
        "total_adjacent_anomalies":len(events),
        "classification_counts":dict(count),
        "source_vintage":"2026-11-10_RECOLLECTED_DART_LIST_NOT_ORIGINAL_DAILY_ARCHIVE",
        "original_corporate_action_filing_body_and_effective_date_verified":False,
        "not_a_stock_split_proof":True,"no_production_changes":True,
        "trade_approved":False,"decision":"CASH","events":matches}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--v18",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    anomal,gaps=read_adjacent(a.root)
    if len(anomal)!=73 or gaps!=337:raise ValueError("FROZEN_410_ANOMALY_MISMATCH")
    if a.v18.is_dir():data=(a.v18/"catalysts/disclosures.csv").read_bytes()
    else:
        with zipfile.ZipFile(a.v18) as z:data=z.read("catalysts/disclosures.csv")
    disclosures=list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    result=join(anomal,disclosures)
    result["dart_list_title_records"]=len(disclosures)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("C3_V11_DART_ADJACENT",json.dumps({k:v for k,v in result.items() if k!="events"},ensure_ascii=False))
if __name__=="__main__":main()
