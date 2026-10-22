"""C3/K100 risk-first final-score rule (2026-10-22).

The 100-point scoring scale is unchanged. Only the screening threshold
decreased from 85 to 80 inclusive. Evidence must be independently verified.
This code never places orders and never turns a research score into a final score.
"""
from __future__ import annotations
import math

SCORE_MAX = 100
BUY_REVIEW_SCORE_MIN = 80
MIN_COST_ADJUSTED_RR = 2.0
MANDATORY_EVIDENCE = (
    "final_score_independently_verified",
    "same_session_data_verified",
    "market_regime_pass",
    "sector_money_flow_verified",
    "foreign_institution_flows_verified",
    "direct_catalyst_or_fundamentals_verified",
    "daily_chart_history_and_structure_verified",
    "entry_trigger_verified",
    "structural_stop_verified",
    "liquidity_and_execution_verified",
    "cash_and_position_limits_verified",
)


def evaluate_review(score, evidence: dict | None = None, *, cost_adjusted_rr=None) -> dict:
    """Return a manual REVIEW eligibility gate, never a trade authorization.

    Boolean evidence must be literal True; estimates, unknowns and proxies fail
    closed. C3 holders cannot add another C3 position or average down.
    """
    checks = evidence if isinstance(evidence, dict) else {}
    blockers = []
    if (not isinstance(score, int) or isinstance(score, bool)
            or not 0 <= score <= SCORE_MAX):
        blockers.append("FINAL_SCORE_NOT_VERIFIED")
    elif score < BUY_REVIEW_SCORE_MIN:
        blockers.append("FINAL_SCORE_BELOW_80")
    for k in MANDATORY_EVIDENCE:
        if checks.get(k) is not True:
            blockers.append("EVIDENCE_UNVERIFIED:" + k)
    if (not isinstance(cost_adjusted_rr, (int, float))
            or isinstance(cost_adjusted_rr, bool)
            or not math.isfinite(cost_adjusted_rr)
            or cost_adjusted_rr < MIN_COST_ADJUSTED_RR):
        blockers.append("COST_ADJUSTED_RR_NOT_VERIFIED_AT_LEAST_2")
    if checks.get("c3_existing_position") is True and checks.get("account") == "C3":
        blockers.append("C3_ONE_POSITION_ALREADY_HELD")
    eligible = not blockers
    return {
        "schema": "manual_review_gate_v1",
        "scoring_scale": SCORE_MAX,
        "final_score_threshold": BUY_REVIEW_SCORE_MIN,
        "input_final_verified_score": score if isinstance(score, int) and not isinstance(score, bool) else None,
        "minimum_cost_adjusted_rr": MIN_COST_ADJUSTED_RR,
        "manual_review_eligible": eligible,
        "trade_approved": False,
        "orders_enabled": False,
        "decision": "CONDITIONAL_MANUAL_REVIEW_ONLY" if eligible else "CASH",
        "blockers": blockers,
        "note": "80 points is necessary, not sufficient. This module does not authorize orders.",
    }
