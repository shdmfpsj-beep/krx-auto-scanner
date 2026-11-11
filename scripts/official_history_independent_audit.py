#!/usr/bin/env python3
"""Independent evidence checks for KRX historical data. No authority to certify trading."""
import argparse,csv,hashlib,json
from collections import Counter,defaultdict
from pathlib import Path

FIELDS=("date","market","ticker","close","volume","turnover_krw")
REQUIRED=("official_holiday_calendar_verified","corporate_actions_adjusted_verified",
          "delisted_issuers_included_verified","historical_point_in_time_universe_verified",
          "regular_1530_session_verified")
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def audit(root,evidence=None):
    days=[];errors=[];hashes={};rows=0;tickers=set();missing=[];prices=defaultdict(list);date_market_counts=defaultdict(Counter)
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        status_file=folder/"krx_v65_collect_status.json"
        if not status_file.exists():missing.append(folder.name);continue
        st=json.loads(status_file.read_text())
        if not st.get("official_dataset_usable"):continue
        if st.get("asof")!=folder.name:errors.append("MANIFEST_DATE_MISMATCH:"+folder.name);continue
        daykeys=set();dayrows=0
        for market in ("KOSPI","KOSDAQ"):
            p=folder/(market+"_official.csv")
            if not p.is_file():errors.append("MISSING_MARKET_FILE:"+folder.name+":"+market);continue
            actual=digest(p);expected=st.get("market_file_sha256",{}).get(market)
            hashes[folder.name+":"+market]=actual
            if not expected or actual!=expected:
                errors.append("HASH_MISMATCH:"+folder.name+":"+market);continue
            with p.open(encoding="utf-8-sig",newline="") as f:
                for r in csv.DictReader(f):
                    if r.get("valid_daily_bar")!="True":continue
                    if r.get("asof")!=folder.name or r.get("market")!=market:
                        errors.append("ROW_SCOPE_MISMATCH:"+folder.name);continue
                    key=(folder.name,r.get("ticker"))
                    if key in daykeys:errors.append("DUPLICATE_DATE_TICKER:"+str(key));continue
                    daykeys.add(key);tickers.add(r["ticker"]);rows+=1;dayrows+=1
                    date_market_counts[folder.name][market]+=1
                    try:
                        close=float(str(r["close"]).replace(",",""))
                        if close>0:prices[r["ticker"]].append((folder.name,close))
                    except (ValueError,TypeError):errors.append("INVALID_CLOSE:"+str(key))
        if dayrows:days.append(folder.name)
    discontinuities=[]
    for ticker,series in prices.items():
        series.sort()
        for (d0,p0),(d1,p1) in zip(series,series[1:]):
            ratio=p1/p0
            if ratio>=1.5 or ratio<=2/3:
                discontinuities.append({"ticker":ticker,"previous_date":d0,"date":d1,"close_ratio":round(ratio,5),"classification":"CORPORATE_ACTION_OR_DATA_ERROR_UNVERIFIED"})
    # These are anomaly flags, never proof that corporate actions have been adjusted.
    proof={k:False for k in REQUIRED}
    # External evidence must be explicitly independently reviewed. Metadata alone never certifies.
    submitted={}
    if evidence and evidence.exists():
        submitted=json.loads(evidence.read_text())
    for k in REQUIRED:
        item=submitted.get(k)
        if isinstance(item,dict) and item.get("verified") is True and item.get("independent_review") is True and item.get("source_uri") and item.get("source_sha256") and item.get("asof"):
            # Review receipt only, NOT an automatic source certification.
            proof[k]=False
    gates={"minimum_120_dates":len(set(days))>=120,"no_integrity_errors":not errors,
           **proof}
    return {"schema":"C3_INDEPENDENT_HISTORICAL_AUDIT_V1","observed_dates":len(set(days)),
            "rows":rows,"unique_tickers":len(tickers),"missing_manifest_folders":missing,
            "errors":errors[:100],"hashes":hashes,"evidence_submitted":list(submitted),
            "market_coverage_by_date":{d:dict(v) for d,v in date_market_counts.items()},
            "unadjusted_price_discontinuities":discontinuities[:300],
            "unadjusted_price_discontinuity_count":len(discontinuities),
            "quality_gates":gates,"performance_publication_allowed":all(gates.values()),
            "trade_approved":False,"decision":"CASH"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True);p.add_argument("--evidence",type=Path)
    a=p.parse_args();result=audit(a.root,a.evidence)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("INDEPENDENT_HISTORY_AUDIT",json.dumps({k:v for k,v in result.items() if k!="hashes"},ensure_ascii=False))
    if result["errors"]:raise SystemExit(2)
if __name__=="__main__":main()
