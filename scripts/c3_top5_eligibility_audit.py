#!/usr/bin/env python3
"""Read-only C3 TOP5 candidate eligibility audit; never authorizes orders."""
import argparse
import json
from pathlib import Path
from c3_top5_financial_selection import ACCEPTED, classify

def audit(receipt, financial):
    candidates = receipt.get("candidates", [])
    rows = financial.get("researched", [])
    valid = financial.get("status") in ACCEPTED
    verified = {r.get("ticker") for r in rows
                if classify(r, receipt.get("asof")) == "QUALIFIED_BASIC_FINANCIAL_RISK"}
    if financial.get("asof") != receipt.get("asof"):
        verified.clear()
    # Financial-qualified shortlist is informational until price provenance is verified.
    financial_shortlist = []
    integrity = receipt.get("source_integrity") or {}
    # Legacy receipt booleans are not independent proof of official provenance.
    # A separate authenticated certification process is required before promotion.
    price_ok = False
    actions_ok = False
    result = {"schema": "C3_TOP5_ELIGIBILITY_AUDIT_V1", "decision": "CASH",
              "trade_approved": False, "price_certified": price_ok,
              "corporate_actions_certified": actions_ok, "candidates": []}
    for c in candidates if isinstance(candidates, list) else []:
        code = c.get("code") if isinstance(c, dict) else None
        financial_ok = bool(valid and code in verified)
        if financial_ok:
            financial_shortlist.append(code)
        status = "ELIGIBLE_RESEARCH_ONLY" if financial_ok and price_ok and actions_ok else "WATCH_UNVERIFIED"
        result["candidates"].append({"code": code, "name": c.get("name") if isinstance(c, dict) else None,
            "technical_status": c.get("status") if isinstance(c, dict) else None,
            "financial_verified": financial_ok, "status": status,
            "trade_approved": False})
    result["financial_qualified_codes"] = financial_shortlist
    result["financial_qualified_count"] = len(financial_shortlist)
    result["eligible_count"] = sum(x["status"] == "ELIGIBLE_RESEARCH_ONLY" for x in result["candidates"])
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--financial", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    result = audit(json.loads(args.receipt.read_text()), json.loads(args.financial.read_text()))
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print("TOP5_ELIGIBILITY_AUDIT", json.dumps({"eligible_count": result["eligible_count"], "decision": "CASH"}))
if __name__ == "__main__":
    main()
