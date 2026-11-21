#!/usr/bin/env python3
"""TOP5: executable entries, dated financial risk gate and existing quality ranks."""
import argparse
import json
import math
from datetime import datetime
from pathlib import Path

ACCEPTED = {"FINANCIAL_RESEARCH_GATE_PASSED",
            "PARTIAL_OR_FAILED_FINANCIAL_GATE",
            "NEXT_DAY_FINANCIAL_RESEARCH_NOT_PIT_CERTIFIED",
            "HISTORICAL_DISCLOSURE_DATE_FILTERED_RESEARCH_ONLY"}
FINANCIAL_CANDIDATE_LIMIT = 30
ANNUAL_POINTS = {"ANNUAL_GROWTH_AND_MARGIN_OBSERVED": 16,
                 "ANNUAL_POSITIVE_MIXED": 11, "ANNUAL_RISK_OR_SLOWDOWN": 5}
INTERIM_POINTS = {"INTERIM_SALES_AND_PROFIT_GROWTH_OBSERVED": 14,
                  "INTERIM_MIXED": 9, "INTERIM_PROFIT_OR_SALES_WEAKENING": 4}

def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

def entry_state(low, high, close):
    if not all(finite(v) and v > 0 for v in (low, high, close)) or low >= high:
        return "WATCH"
    if low <= close <= high:
        return "ENTRY_READY"
    return "NEAR_ENTRY" if close > high and (close-high)/close*100 <= 2.0 else "WATCH"

def valid_entry(c):
    """Recompute from executable prices; rounded risk labels are never authority."""
    if not isinstance(c, dict) or not c.get("geometry_validated"):
        return False
    if "status" in c and "entry_status" in c and c["status"] != c["entry_status"]:
        return False
    low, high, stop, close, risk, r1 = (c.get(k) for k in
        ("entry_low", "entry_high", "stop_ref", "close", "risk_pct", "r1_ref"))
    if not all(finite(v) and v > 0 for v in (low, high, stop, close, risk, r1)):
        return False
    def tick(p):
        return (1 if p < 2000 else 5 if p < 5000 else 10 if p < 20000 else
                50 if p < 50000 else 100 if p < 200000 else 500 if p < 500000 else 1000)
    r2 = c.get("r2_ref")
    prices = [low, high, stop, r1] + ([r2] if r2 is not None else [])
    if not all(finite(p) and p > 0 and p % tick(p) == 0 for p in prices):
        return False
    if not (stop < low < high and stop < close and r1 > max(high, close)):
        return False
    if r2 is not None and r2 <= r1:
        return False
    actual_risk = (high-stop)/high*100
    return (1.5 <= actual_risk <= 5 and abs(actual_risk-risk) <= .011 and
            c.get("status", c.get("entry_status")) == entry_state(low, high, close) and
            entry_state(low, high, close) in ("ENTRY_READY", "NEAR_ENTRY"))

def requested_candidates(geometry):
    # Invalid/WATCH charts must not consume the bounded OpenDART call budget.
    candidates = [c for c in geometry.get("candidates", []) if valid_entry(c)]
    candidates.sort(key=lambda c: (0 if c["status"] == "ENTRY_READY" else 1,
        -float(c.get("opportunity_score") or 0), -float(c.get("score") or 0), c["code"]))
    return candidates[:FINANCIAL_CANDIDATE_LIMIT]

def financial_points(item):
    """Reuse the existing report's /30 annual + interim evidence score."""
    if not isinstance(item, dict):
        return None
    annual = ANNUAL_POINTS.get(item.get("financial_quality"))
    interim = INTERIM_POINTS.get(item.get("interim_quality"))
    return annual + interim if annual is not None and interim is not None else None

def classify(item, asof=None):
    """Financial risk is the hard gate; earnings growth/slowdown is a score."""
    if not isinstance(item, dict):
        return "REVIEW_INSUFFICIENT_EVIDENCE"
    if not item.get("financial_risk_gate_pass") or item.get("exclusion_reasons"):
        return "REVIEW_FAILED_FINANCIAL_GATE"
    if item.get("annual_status") != "DATED_ANNUAL_RESEARCH_ONLY" or not item.get("filing_date"):
        return "REVIEW_INSUFFICIENT_EVIDENCE"
    if item.get("interim_status") != "DATED_INTERIM_YTD_RESEARCH_ONLY" or not item.get("interim_filing_date"):
        return "REVIEW_INSUFFICIENT_EVIDENCE"
    if financial_points(item) is None:
        return "REVIEW_INSUFFICIENT_EVIDENCE"
    if asof:
        try:
            day = datetime.strptime(asof, "%Y%m%d").date()
            if any(datetime.strptime(item[k], "%Y-%m-%d").date() > day
                   for k in ("filing_date", "interim_filing_date")):
                return "REVIEW_INSUFFICIENT_EVIDENCE"
        except (ValueError, TypeError):
            return "REVIEW_INSUFFICIENT_EVIDENCE"
    return "QUALIFIED_BASIC_FINANCIAL_RISK"

def select(geometry, financial):
    asof = geometry.get("asof")
    candidates = geometry.get("candidates", [])
    requested_rows = requested_candidates(geometry)
    requested = {c["code"] for c in requested_rows}
    evidence = financial.get("researched", []) + financial.get("excluded", [])
    covered = [x.get("ticker") for x in evidence if isinstance(x, dict)]
    coverage_ok = len(covered) == len(set(covered)) and set(covered) == requested
    valid = (financial.get("asof") == asof and (financial.get("status") in ACCEPTED
             or (not requested and financial.get("status") == "NO_CANDIDATES"))
             and coverage_ok)
    classifications = {x["ticker"]: classify(x, asof) for x in evidence} if valid else {}
    valid = valid and "REVIEW_INSUFFICIENT_EVIDENCE" not in classifications.values()
    geometry_error = any(isinstance(c, dict) and c.get("geometry_validated") and
        c.get("status") in ("ENTRY_READY", "NEAR_ENTRY") and not valid_entry(c)
        for c in candidates)
    valid = valid and not geometry_error
    qualified = [c for c in requested_rows
                 if valid and classifications.get(c.get("code")) == "QUALIFIED_BASIC_FINANCIAL_RISK"]
    by_ticker = {x["ticker"]: x for x in evidence} if valid else {}
    # Preserve ENTRY_READY priority. Within each state use already-calculated
    # financial quality, then leverage, opportunity and technical strength.
    qualified.sort(key=lambda c: (
        0 if c.get("status") == "ENTRY_READY" else 1,
        -financial_points(by_ticker[c["code"]]),
        by_ticker[c["code"]].get("liabilities_to_equity_pct")
        if finite(by_ticker[c["code"]].get("liabilities_to_equity_pct")) else float("inf"),
        -float(c.get("opportunity_score") or 0),
        -float(c.get("score") or 0), c["code"]))
    selected = qualified[:5]
    signals = [{"code": c["code"], "signal": "BUY_CONSIDER" if c.get("status") == "ENTRY_READY" else "WAIT_FOR_ENTRY",
                "technical_status": c.get("status"),
                "financial_flag": classifications.get(c["code"])}
               for c in selected]
    return {"schema": "C3_TOP5_FINANCE_FIRST_CONDITIONAL_SIGNAL_V3",
            "asof": asof, "status": "ERROR_ENTRY_GEOMETRY" if geometry_error else "CONDITIONAL_SIGNALS" if valid else "ERROR_FINANCIAL_EVIDENCE",
            "financial_evidence_status": financial.get("status"),
            "coverage_complete": coverage_ok,
            "point_in_time_certification_required": False,
            "independent_price_certification_required": False,
            "data_quality_validation_required": True,
            "decision": ("ERROR" if not valid else "ENTRY_READY" if any(x["signal"] == "BUY_CONSIDER" for x in signals) else ("WAIT_FOR_ENTRY" if selected else "CASH")),
            "trade_approved": False, "user_executes_trades": True,
            "signals": signals,
            "selected": [{"code": c["code"], "name": c.get("name"),
                          "technical_status": c.get("status"),
                          "financial_quality": by_ticker[c["code"]].get("financial_quality"),
                          "financial_points": financial_points(by_ticker[c["code"]]),
                          "financial_flag": classifications.get(c["code"])}
                         for c in selected],
            "financial_classifications": classifications,
            "review_count": sum(v.startswith("REVIEW_") for v in classifications.values()),
            "excluded_count": sum(v == "REVIEW_FAILED_FINANCIAL_GATE" for v in classifications.values()),
            "slowdown_flag_count": sum(bool(x.get("recent_slowdown_flag")) for x in by_ticker.values()),
            "watch_count": 0,
            "financial_pass_count": len(qualified),
            "selection_priority": "ENTRY_STATE_FINANCIAL_QUALITY_LEVERAGE_OPPORTUNITY_STRENGTH",
            "financial_request_limit": FINANCIAL_CANDIDATE_LIMIT,
            "financial_requested_count": len(requested),
            "financial_budget_deferred_count": max(0, sum(valid_entry(c) for c in candidates)-len(requested)),
            "historical_pit_certified": bool(financial.get("point_in_time_snapshot_verified")),
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
