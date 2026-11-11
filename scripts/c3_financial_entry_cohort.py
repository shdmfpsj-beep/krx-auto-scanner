#!/usr/bin/env python3
"""Read-only as-of financial cohort for three entry models; no trade approval."""
import argparse,json
from pathlib import Path
from c3_three_entry_replay import MODELS
from sector_financial_join import PASS

def cohort(finance,asof):
    eligible=[];excluded=[]
    if finance.get("schema")!="opendart_annual_research_v1" or finance.get("asof")!=asof:
        return {"status":"FINANCIAL_SOURCE_DATE_OR_SCHEMA_MISMATCH","eligible":[],"excluded":[],
                "models":list(MODELS),"decision":"CASH","trade_approved":False}
    for r in finance.get("researched",[]):
        ticker=str(r.get("ticker",""))
        receipt=str(r.get("receipt_date") or "")
        recent=r.get("interim_research") or {}
        reasons=[]
        if len(ticker)!=6 or not ticker.isdigit():reasons.append("INVALID_TICKER")
        if r.get("status")!="DATED_ANNUAL_RESEARCH_ONLY":reasons.append("ANNUAL_NOT_VERIFIED")
        if not receipt or receipt>asof:reasons.append("FUTURE_OR_MISSING_FILING")
        if r.get("financial_quality")!=PASS or not r.get("financial_screen_pass"):reasons.append("ANNUAL_QUALITY_NOT_PASSED")
        if r.get("recent_financial_weakening_veto"):reasons.append("RECENT_INTERIM_WEAKENING")
        if not r.get("annual_plus_interim_growth_pass"):reasons.append("LATEST_INTERIM_GROWTH_NOT_VERIFIED")
        if r.get("sector_id") in ("BANK","INSURANCE","SECURITIES"):reasons.append("FINANCIAL_SECTOR_SPECIAL_MODEL_REQUIRED")
        item={"ticker":ticker,"receipt_date":receipt,"reasons":reasons}
        (excluded if reasons else eligible).append(item)
    return {"status":"DATED_FINANCIAL_RESEARCH_COHORT","asof":asof,
            "eligible":eligible,"excluded":excluded,"models":list(MODELS),
            "comparison_rule":"SAME_ELIGIBLE_TICKER_DATE_COHORT_ALL_THREE_MODELS",
            "financial_data_pit_backtest_verified":False,
            "historical_returns_certified":False,"decision":"CASH","trade_approved":False}
def main():
    p=argparse.ArgumentParser();p.add_argument("--financial",type=Path,required=True)
    p.add_argument("--asof",required=True);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();result=cohort(json.loads(a.financial.read_text()),a.asof)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("C3_FINANCIAL_ENTRY_COHORT",json.dumps({"status":result["status"],"eligible":len(result["eligible"]),"excluded":len(result["excluded"]),"decision":"CASH"}))
if __name__=="__main__":main()
