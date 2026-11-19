#!/usr/bin/env python3
"""TOP5 conditional trading signals: financial quality first, entry timing second."""
import argparse
import json
from pathlib import Path

ACCEPTED = {"FINANCIAL_RESEARCH_GATE_PASSED",
            "PARTIAL_OR_FAILED_FINANCIAL_GATE",
            "NEXT_DAY_FINANCIAL_RESEARCH_NOT_PIT_CERTIFIED"}
ANNUAL_OK = {"ANNUAL_GROWTH_AND_MARGIN_OBSERVED", "ANNUAL_POSITIVE_MIXED"}

def classify(item):
    """Unknown evidence is never treated as proof of financial safety."""
    quality = item.get("financial_quality")
    reasons = set(item.get("exclusion_reasons") or [])
    if quality == "ANNUAL_RISK_OR_SLOWDOWN":
        return "REVIEW_ANNUAL_SLOWDOWN"
    if quality not in ANNUAL_OK or item.get("annual_status") != "DATED_ANNUAL_RESEARCH_ONLY" or not item.get("filing_date"):
        return "REVIEW_INSUFFICIENT_EVIDENCE"
    if item.get("interim_status") != "DATED_INTERIM_YTD_RESEARCH_ONLY" or not item.get("interim_quality"):
        return "REVIEW_INSUFFICIENT_EVIDENCE"
    if item.get("interim_quality") == "INTERIM_PROFIT_OR_SALES_WEAKENING":
        return "QUALIFIED_WITH_SLOWDOWN_FLAG"
    if item.get("interim_quality") not in ("INTERIM_SALES_AND_PROFIT_GROWTH_OBSERVED", "INTERIM_MIXED"):
        return "REVIEW_UNRECOGNIZED_INTERIM_QUALITY"
    return "QUALIFIED"

def select(geometry, financial):
    asof = geometry.get("asof")
    candidates = geometry.get("candidates", [])
    requested = {c.get("code") for c in candidates[:10] if isinstance(c, dict)}
    actionable = {c.get("code") for c in candidates if isinstance(c, dict)
                  and c.get("status") in ("ENTRY_READY", "NEAR_ENTRY")
                  and isinstance(c.get("risk_pct"), (int, float))
                  and 0 < c["risk_pct"] <= 5}
    evidence = financial.get("researched", []) + financial.get("excluded", [])
    covered = [x.get("ticker") for x in evidence if isinstance(x, dict)]
    coverage_ok = len(covered) == len(set(covered)) and set(covered) == requested
    valid = (financial.get("asof") == asof and financial.get("status") in ACCEPTED
             and coverage_ok)
    classifications = {x["ticker"]: classify(x) for x in evidence} if valid else {}
    qualified = [c for c in candidates if isinstance(c, dict)
                 and c.get("code") in actionable
                 and classifications.get(c.get("code")) in ("QUALIFIED", "QUALIFIED_WITH_SLOWDOWN_FLAG")]
    quality_by_ticker = {x["ticker"]: x.get("financial_quality") for x in evidence} if valid else {}
    qualified.sort(key=lambda c: (
        0 if c.get("status") == "ENTRY_READY" else 1,
        0 if classifications.get(c["code"]) == "QUALIFIED" else 1,
        0 if quality_by_ticker.get(c["code"]) == "ANNUAL_GROWTH_AND_MARGIN_OBSERVED" else 1,
        -float(c.get("opportunity_score") or 0),
        -float(c.get("score") or 0), c["code"]))
    selected = qualified[:5]
    signals = [{"code": c["code"], "signal": "BUY_CONSIDER" if c.get("status") == "ENTRY_READY" else "WAIT_FOR_ENTRY",
                "technical_status": c.get("status"),
                "financial_flag": classifications.get(c["code"])}
               for c in selected]
    return {"schema": "C3_TOP5_FINANCE_FIRST_CONDITIONAL_SIGNAL_V3",
            "asof": asof, "status": "CONDITIONAL_SIGNALS" if valid else "CASH_EVIDENCE_INVALID",
            "financial_evidence_status": financial.get("status"),
            "coverage_complete": coverage_ok,
            "point_in_time_certification_required": False,
            "independent_price_certification_required": False,
            "decision": "BUY_CONSIDER" if any(x["signal"] == "BUY_CONSIDER" for x in signals) else "CASH",
            "trade_approved": False, "user_executes_trades": True,
            "signals": signals,
            "selected": [{"code": c["code"], "name": c.get("name"),
                          "technical_status": c.get("status"),
                          "financial_quality": quality_by_ticker.get(c["code"]),
                          "financial_flag": classifications.get(c["code"])}
                         for c in selected],
            "financial_classifications": classifications,
            "review_count": sum(v.startswith("REVIEW_") for v in classifications.values()),
            "excluded_count": sum(v == "EXCLUDED_CONFIRMED_RISK" for v in classifications.values()),
            "slowdown_flag_count": sum(v == "QUALIFIED_WITH_SLOWDOWN_FLAG" for v in classifications.values()),
            "watch_count": 0,
            "financial_pass_count": len(qualified),
            "selected_count": len(selected)}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--geometry", type=Path, required=True)
    p.add_argument("--financial", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    result = select(json.loads(a.geometry.read_text()), json.loads(a.financial.read_text()))
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("FINANCIAL_SELECTION", result["selected_count"], "decision="+result["decision"])

if __name__ == "__main__":
    main()
