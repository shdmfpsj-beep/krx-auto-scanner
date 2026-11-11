#!/usr/bin/env python3
"""Read-only audit of historical C3 provisional DART availability dates.
Do NOT promote revised API financial values to original-vintage PIT.
Proof of official market session uses ONLY frozen market dates in hashed KRX archive;
filings before archive start remain DATE_UNVERIFIED, not an invented XKRX holiday.
"""
import argparse,datetime as dt,json,hashlib
from collections import Counter
from pathlib import Path

def sha(b):return hashlib.sha256(b).hexdigest()
def archive_market_dates(root):
    dates=[];hashes={}
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():continue
        mf=folder/"krx_v65_collect_status.json"
        if not mf.exists():continue
        stat=json.loads(mf.read_text())
        if stat.get("official_dataset_usable") is not True:continue
        day=dt.date.fromisoformat(folder.name)
        if day.isoformat()!=stat.get("asof"):raise ValueError("SOURCE_DATE_MISMATCH")
        for market in ("KOSPI","KOSDAQ"):
            path=folder/f"{market}_official.csv"
            actual=sha(path.read_bytes())
            if actual!=stat.get("market_file_sha256",{}).get(market):
                raise ValueError("SOURCE_SHA256_MISMATCH")
            hashes[f"{day}/{market}"]=actual
        dates.append(day)
    if len(dates)<120 or dates!=sorted(set(dates)):raise ValueError("MARKET_HISTORY_INVALID")
    return dates,hashes

def inspect(events,dates):
    result=[];status=Counter();days=set(dates);lower,upper=dates[0],dates[-1]
    for e in events:
        f=e.get("financial") or {}
        available=f.get("available_date")
        if not available:continue
        receipt=f.get("receipt_no")
        filing=f.get("filing_date")
        if not (receipt and filing):raise ValueError("INCOMPLETE_PROVISIONAL_LINK")
        filing_day=dt.date.fromisoformat(filing)
        old=dt.date.fromisoformat(available)
        future=next((x for x in dates if x>filing_day),None) if lower<=filing_day<upper else None
        day_in_market=old in days
        original_weekend=old.weekday()>=5
        corrected=future.isoformat() if future else None
        classification=(
            "OUTSIDE_ARCHIVED_KRX_CALENDAR_CANNOT_CERTIFY" if not future
            else "ORIGINAL_AVAILABLE_DATE_IS_NOT_MARKET_SESSION" if not day_in_market
            else "NEXT_SESSION_DATE_MISMATCH" if old!=future
            else "MATCHES_FIRST_FROZEN_KRX_SESSION")
        status[classification]+=1
        if original_weekend:status["WEEKEND_AVAILABLE_DATE"]+=1
        selection=dt.date.fromisoformat(e["date"])
        if future and future>selection:status["PROPOSED_NEXT_SESSION_AFTER_SELECTION"]+=1
        result.append({
            "ticker":e["ticker"],"selection_date":e["date"],"receipt_no":receipt,
            "filing_date":filing,"old_available_date":available,
            "old_available_was_weekend":original_weekend,
            "old_available_in_frozen_market_sessions":day_in_market,
            "first_observed_KRX_market_session_after_filing":corrected,
            "classification":classification,
            "selection_after_frozen_next_KRX_session":selection>=future if future else None,
            "original_filing_received_intraday_time_verified":False,
            "financial_original_numeric_vintage_verified":False
        })
    return {"schema":"C3_V12_DART_PIT_CALENDAR_DATE_AUDIT",
        "linked_provisional_receipt_events":len(result),
        "counts":dict(status),
        "frozen_market_date_first":lower.isoformat(),
        "frozen_market_date_last":upper.isoformat(),
        "date_join_original_snapshot_verified":False,
        "corrected_date_does_not_promote_original_financial_values":True,
        "original_filing_release_time_known":False,
        "selection_model_unchanged":True,
        "operating_main_modified":False,"decision":"CASH","events":result}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True,type=Path)
    p.add_argument("--join",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    dates,hashes=archive_market_dates(a.root)
    j=json.loads(a.join.read_text())
    if j.get("event_count")!=129:raise ValueError("FROZEN_129_EVENTS_CHANGED")
    report=inspect(j["events"],dates)
    report["official_market_sessions"]=len(dates)
    report["archive_price_manifest_aggregate_sha256"]=sha(json.dumps(hashes,sort_keys=True).encode())
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("C3_V12_DART_PIT_DATE",json.dumps({k:v for k,v in report.items() if k!="events"},ensure_ascii=False))
if __name__=="__main__":main()
