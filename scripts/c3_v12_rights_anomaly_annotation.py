#!/usr/bin/env python3
"""Attach only five primary-rights notice proofs to original 73 dated KRX anomalies.
This is an annotation; it never rewrites adjusted prices or trade outcomes.
"""
import argparse,json,hashlib
from pathlib import Path

def annotate(rights,issuer):
    e={(x["ticker"],x["date"]):x for x in issuer["events"]}
    if len(e)!=73 or len(issuer["events"])!=73:raise ValueError("FROZEN_73_ORIGINAL_ISSUER_EVENTS_CHANGED")
    if issuer.get("price_anomalies")!=410:raise ValueError("FROZEN_410_CHANGED")
    if rights.get("requested_primary_rights_notices")!=5:raise ValueError("PRIMARY_5_PROVENANCE_MISMATCH")
    verified=[];rejected=[]
    for c in rights["cases"]:
        ticker,date=c["ticker"],c.get("parsed_ex_date")
        k=(ticker,date)
        a=e.get(k)
        if c.get("status")!="PRIMARY_RIGHTS_NOTICE_VERIFIED" or not a:
            rejected.append({"ticker":ticker,"date":date,"reason":"SOURCE_OR_DATE_NOT_VERIFIED"});continue
        if not c.get("ticker_table_matches") or c.get("current_archive_sha256")!=c.get("file_sha256_expected"):
            rejected.append({"ticker":ticker,"date":date,"reason":"SOURCE_SHA_OR_TICKER_CONFLICT"});continue
        if c.get("parsed_reference_price_krw",0)<=0 or c.get("actual_ex_date_closing_price",0)<=0:
            rejected.append({"ticker":ticker,"date":date,"reason":"MISSING_REFERENCE_PRICE_OR_DAILY_CLOSE"});continue
        if abs(a["close_ratio"]-c.get("raw_close_ratio",float("nan")))>0.00001:
            rejected.append({"ticker":ticker,"date":date,"reason":"RAW_DAILY_SOURCE_RATIO_CONFLICT"});continue
        verified.append({
            "ticker":ticker,"date":date,
            "receipt_no":c["receipt_no"],
            "original_zip_sha256":c["current_archive_sha256"],
            "rights_reference_price":c["parsed_reference_price_krw"],
            "observed_close_krw":c["actual_ex_date_closing_price"],
            "actual_close_vs_reference_pct":c["close_vs_official_reference_pct"],
            "unadjusted_raw_close_ratio":a["close_ratio"],
            "status":"PRIMARY_RIGHTS_NOTICE_VERIFIED_ONLY_NO_TOTAL_RETURN"}
        )
    return {"schema":"C3_V12_OFFICIAL_RIGHTS_RESEARCH_ANNOTATION",
       "fixed_410_price_discontinuities":410,
       "fixed_73_adjacent_market_day_discontinuities":73,
       "first_party_rights_reference_and_ex_date_verified":len(verified),
       "remaining_adjacent_anomalies_without_primary_rights_proof":73-len(verified),
       "missing_ticker_market_session_337_unresolved":337,
       "rejected_requested_proof":rejected,
       "no_split_adjusted_prices_written":True,
       "no_past_returns_or_entry_bands_rewritten":True,
       "preexisting_129_cohort_outcome_labels_unchanged":True,
       "no_total_shareholder_return_certification":True,
       "market_regular_1530_not_certified":True,
       "operating_main_modified":False,
       "trade_approved":False,"decision":"CASH",
       "cases":verified}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rights",required=True,type=Path)
    p.add_argument("--issuer",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    report=annotate(json.loads(a.rights.read_text()),json.loads(a.issuer.read_text()))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("C3_V12_ANNOTATED_RIGHTS",json.dumps({k:v for k,v in report.items() if k!="cases"},ensure_ascii=False))
if __name__=="__main__":main()
