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
REVIEW_SCOPE = 'TECHNICAL_INTEREST_POOL_V1'
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
    # Legacy executable-entry scope remains available for compatibility.
    candidates = [c for c in geometry.get("candidates", []) if valid_entry(c)]
    candidates.sort(key=lambda c: (0 if c["status"] == "ENTRY_READY" else 1,
        -float(c.get("opportunity_score") or 0), -float(c.get("score") or 0), c["code"]))
    return candidates[:FINANCIAL_CANDIDATE_LIMIT]

def financial_review_candidates(geometry):
    """Review technical interest independently of whether an entry exists today.

    Keep the existing API budget and prefer actionable entries before WATCH.
    Geometry failures still cannot enter TOP5 after a financial PASS.
    """
    candidates = list(geometry.get('candidates', []))
    candidates.sort(key=lambda c: (0 if valid_entry(c) and c.get('entry_status')=='ENTRY_READY'
        else 1 if valid_entry(c) else 2, -float(c.get('opportunity_score') or 0),
        -float(c.get('score') or 0), c['code']))
    return candidates[:FINANCIAL_CANDIDATE_LIMIT]

def financial_points(item):
    """Reuse the existing report's /30 annual + interim evidence score."""
    if not isinstance(item, dict):
        return None
    if item.get("financial_model") == "BALANCED_QUALITY_TIMING_V1":
        q = item.get("quality_100", {})
        score = q.get("score")
        return round(score * .3, 4) if finite(score) and 0 <= score <= 100 and q.get("comparison_signature") else None
    annual = ANNUAL_POINTS.get(item.get("financial_quality"))
    interim = INTERIM_POINTS.get(item.get("interim_quality"))
    return annual + interim if annual is not None and interim is not None else None

def classify(item, asof=None):
    """Financial risk is the hard gate; earnings growth/slowdown is a score."""
    if not isinstance(item, dict):
        return "REVIEW_INSUFFICIENT_EVIDENCE"
    if item.get('financial_model')=='BALANCED_QUALITY_TIMING_V1' and item.get('financial_verdict'):
        verdict=item['financial_verdict']
        if verdict=='ERROR' or item.get('financial_evidence_state') in ('API_ERROR','VALIDATION_ERROR'):
            return 'ERROR_FINANCIAL_EVIDENCE'
        if verdict=='QUALIFIED' and asof:
            try:
                day=datetime.strptime(asof,'%Y%m%d').date()
                if any(datetime.strptime(item[key],'%Y-%m-%d').date()>day for key in ('filing_date','interim_filing_date')):
                    return 'ERROR_FINANCIAL_EVIDENCE'
            except (ValueError,KeyError,TypeError):
                return 'ERROR_FINANCIAL_EVIDENCE'
        if verdict=='REJECTED_FINANCIAL_RISK':
            from c3_balanced_financials import rejection_proven
            return 'REJECTED_FINANCIAL_RISK' if rejection_proven(item,asof) else 'ERROR_FINANCIAL_EVIDENCE'
        if verdict=='REVIEW_REQUIRED':
            return 'REVIEW_INSUFFICIENT_EVIDENCE'
        if verdict!='QUALIFIED':
            return 'ERROR_FINANCIAL_EVIDENCE'
    # An exclusion is meaningful only after its underlying evidence is valid.
    # Missing/API-failed statements must never become ordinary financial CASH.
    if item.get("financial_evidence_complete") is not True:
        return "REVIEW_INSUFFICIENT_EVIDENCE"
    if item.get("financial_model") == "BALANCED_QUALITY_TIMING_V1":
        risk = item.get("risk_assessment", {})
        if risk.get("state") not in ("PASS", "FAIL") or risk.get("mandatory_missing"):
            return "REVIEW_INSUFFICIENT_EVIDENCE"
        if (risk.get("state") == "PASS") != bool(item.get("financial_risk_gate_pass")):
            return "REVIEW_INSUFFICIENT_EVIDENCE"
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
    if not item.get("financial_risk_gate_pass") or item.get("exclusion_reasons"):
        return "REVIEW_FAILED_FINANCIAL_GATE"
    return "QUALIFIED_BASIC_FINANCIAL_RISK"

def select(geometry, financial):
    asof = geometry.get("asof")
    candidates = geometry.get("candidates", [])
    broad = financial.get('request_scope') == REVIEW_SCOPE
    requested_rows = financial_review_candidates(geometry) if broad else requested_candidates(geometry)
    requested = {c["code"] for c in requested_rows}
    evidence = financial.get("researched", []) + financial.get("excluded", [])
    balanced = financial.get('model')=='BALANCED_QUALITY_TIMING_V1' or any(
        isinstance(x,dict) and x.get('financial_model')=='BALANCED_QUALITY_TIMING_V1' for x in evidence)
    covered = [x.get("ticker") for x in evidence if isinstance(x, dict)]
    coverage_ok = len(covered) == len(set(covered)) and set(covered) == requested
    valid = (financial.get("asof") == asof and (financial.get("status") in ACCEPTED
             or (not requested and financial.get("status") == "NO_CANDIDATES"))
             and coverage_ok)
    classifications = {x["ticker"]: classify(x, asof) for x in evidence} if coverage_ok and financial.get('asof')==asof else {}
    review_pending = 'REVIEW_INSUFFICIENT_EVIDENCE' in classifications.values()
    candidate_error = 'ERROR_FINANCIAL_EVIDENCE' in classifications.values()
    valid = valid and not review_pending and not candidate_error
    geometry_error = any(isinstance(c, dict) and c.get("geometry_validated") and
        c.get("status") in ("ENTRY_READY", "NEAR_ENTRY") and not valid_entry(c)
        for c in candidates)
    codes = [c.get('code') for c in candidates if isinstance(c, dict)]
    geometry_error = geometry_error or len(codes) != len(candidates) or len(set(codes)) != len(codes)
    valid = valid and not geometry_error
    qualified = [c for c in requested_rows
                 if valid and valid_entry(c) and classifications.get(c.get("code")) == "QUALIFIED_BASIC_FINANCIAL_RISK"]
    by_ticker = {x["ticker"]: x for x in evidence} if valid else {}
    # Compare the same observed features. General quality gaps must not become
    # a new hard risk veto; reduce to their common feature set where possible.
    signatures = {tuple(by_ticker[c["code"]].get("quality_100", {}).get("comparison_signature", ["LEGACY_30"]))
                  for c in qualified}
    rank_points = {c['code']: financial_points(by_ticker[c['code']]) for c in qualified}
    ranking_coverage = None
    comparability_error = False
    if len(signatures) > 1:
        common = set.intersection(*(set(s) for s in signatures))
        if not common or any(not common.issubset(by_ticker[c['code']].get('quality_100', {}).get('feature_scores', {})) for c in qualified):
            comparability_error = True
        else:
            ranking_coverage = sorted(common)
            for c in qualified:
                features = by_ticker[c['code']]['quality_100']['feature_scores']
                available = sum(features[name]['weight'] for name in common)
                rank_points[c['code']] = round(sum(features[name]['earned'] for name in common) / available * 30, 4)
    if comparability_error:
        valid = False
        qualified = []
    # Preserve ENTRY_READY priority. Within each state use already-calculated
    # financial quality, then leverage, opportunity and technical strength.
    qualified.sort(key=lambda c: (
        0 if c.get("status") == "ENTRY_READY" else 1,
        -rank_points[c["code"]],
        by_ticker[c["code"]].get("latest_liabilities_to_equity_pct", by_ticker[c["code"]].get("liabilities_to_equity_pct"))
        if finite(by_ticker[c["code"]].get("liabilities_to_equity_pct")) else float("inf"),
        -float(c.get("opportunity_score") or 0),
        -float(c.get("score") or 0), c["code"]))
    selected = qualified[:5]
    deferred = sum(valid_entry(c) and c['code'] not in requested for c in candidates)
    interest_deferred = max(0, len(candidates)-len(requested)) if broad else 0
    incomplete_cash = valid and not selected and (deferred > 0 or interest_deferred > 0)
    if incomplete_cash:
        # The existing API budget is unchanged. Unreviewed eligible charts
        # prevent a conclusion that the complete candidate set failed finance.
        valid = False
    unresolved_review = (balanced and review_pending and not candidate_error and not geometry_error and
                         coverage_ok and financial.get('asof')==asof and financial.get('status') not in ('ERROR',))
    signals = [{"code": c["code"], "signal": "BUY_CONSIDER" if c.get("status") == "ENTRY_READY" else "WAIT_FOR_ENTRY",
                "technical_status": c.get("status"),
                "financial_flag": classifications.get(c["code"])}
               for c in selected]
    operational_status = ('ERROR' if candidate_error or geometry_error or not coverage_ok or
        financial.get('status') == 'ERROR' else 'HOLD_FINANCIAL_UNVERIFIED'
        if unresolved_review or incomplete_cash else 'ERROR' if not valid else 'TOP5_READY' if selected else 'CASH_NO_ELIGIBLE')
    return {"schema": "C3_TOP5_FINANCE_FIRST_CONDITIONAL_SIGNAL_V3",
            "operational_status": operational_status,
            "financial_request_scope": REVIEW_SCOPE if broad else 'EXECUTABLE_ENTRIES',
            "asof": asof, "status": "ERROR_ENTRY_GEOMETRY" if geometry_error else "CONDITIONAL_SIGNALS" if valid else "REVIEW_REQUIRED" if unresolved_review else "ERROR_FINANCIAL_EVIDENCE",
            "financial_evidence_status": "INCOMPARABLE_FINANCIAL_SCORE_COVERAGE" if comparability_error else "INCOMPLETE_FINANCIAL_COVERAGE_BUDGET" if incomplete_cash else financial.get("status"),
            "coverage_complete": coverage_ok and not incomplete_cash,
            "point_in_time_certification_required": False,
            "independent_price_certification_required": False,
            "data_quality_validation_required": True,
            "decision": ("REVIEW_REQUIRED" if unresolved_review else "ERROR" if not valid else "ENTRY_READY" if any(x["signal"] == "BUY_CONSIDER" for x in signals) else ("WAIT_FOR_ENTRY" if selected else "CASH")),
            "trade_approved": False, "user_executes_trades": True,
            "signals": signals,
            "selected": [{"code": c["code"], "name": c.get("name"),
                          "technical_status": c.get("status"),
                          "financial_quality": by_ticker[c["code"]].get("financial_quality"),
                          "financial_points": financial_points(by_ticker[c["code"]]),
                          **({"financial_ranking_score_100": round(rank_points[c['code']] / .3, 3),
                              "financial_ranking_features": ranking_coverage}
                             if ranking_coverage is not None else {}),
                          **({"financial_model": by_ticker[c["code"]]["financial_model"],
                              "quality_100": by_ticker[c["code"]].get("quality_100"),
                              "risk_flags": by_ticker[c["code"]].get("risk_assessment", {}).get("risk_flags", [])}
                             if by_ticker[c["code"]].get("financial_model") else {}),
                          "financial_flag": classifications.get(c["code"])}
                         for c in selected],
            "financial_classifications": classifications,
            "financial_verdicts": {code: ('PASS' if state=='QUALIFIED_BASIC_FINANCIAL_RISK' else
                'REJECTED_FINANCIAL_RISK' if state in ('REVIEW_FAILED_FINANCIAL_GATE','REJECTED_FINANCIAL_RISK')
                else 'ERROR' if state=='ERROR_FINANCIAL_EVIDENCE' else 'REVIEW_REQUIRED')
                for code,state in classifications.items()},
            "review_count": sum(v.startswith("REVIEW_") for v in classifications.values()),
            "excluded_count": sum(v in ("REVIEW_FAILED_FINANCIAL_GATE","REJECTED_FINANCIAL_RISK") for v in classifications.values()),
            "financial_decision_counts": {'QUALIFIED':sum(v=='QUALIFIED_BASIC_FINANCIAL_RISK' for v in classifications.values()),
                'REJECTED_FINANCIAL_RISK':sum(v in ('REVIEW_FAILED_FINANCIAL_GATE','REJECTED_FINANCIAL_RISK') for v in classifications.values()),
                'REVIEW_REQUIRED':sum(v=='REVIEW_INSUFFICIENT_EVIDENCE' for v in classifications.values()),
                'ERROR':sum(v=='ERROR_FINANCIAL_EVIDENCE' for v in classifications.values())},
            "slowdown_flag_count": sum(bool(x.get("recent_slowdown_flag")) for x in by_ticker.values()),
            "watch_count": sum(not valid_entry(c) and c.get('geometry_validated') is True for c in candidates),
            "financial_pass_count": sum(v=='QUALIFIED_BASIC_FINANCIAL_RISK' for v in classifications.values()),
            "selection_priority": "ENTRY_STATE_FINANCIAL_QUALITY_LEVERAGE_OPPORTUNITY_STRENGTH",
            "financial_request_limit": FINANCIAL_CANDIDATE_LIMIT,
            "financial_requested_count": len(requested),
            "financial_unreviewed_candidate_count": len((set(codes) if broad else requested)-set(covered)),
            "financial_budget_deferred_count": deferred,
            "financial_interest_budget_deferred_count": interest_deferred,
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
