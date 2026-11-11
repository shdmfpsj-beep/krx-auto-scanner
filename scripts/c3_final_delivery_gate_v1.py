"""Read-only, fail-closed final presentation eligibility for C3 research TOP2.

This is a delivery *review* only, not a trading model, selector, order approval,
or a replacement for the immutable as-of ledger. No historical reranking.
Activation is separately gated in c3_telegram_notify.py (default OFF).
"""
import hashlib
import json
import math
import re
from copy import deepcopy
from datetime import date

from c3_entry_geometry_gate import assess, MAX_ENTRY_PREMIUM_PCT


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _day(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _source_blockers(row, report):
    reasons = []
    asof = report.get("source_price_asof")
    if row.get("source_price_asof") != asof or not _day(asof):
        reasons.append("ASOF_OR_DATE_MISMATCH")
    if not report.get("source_run_id") or row.get("source_run_id") != report.get("source_run_id"):
        reasons.append("SOURCE_RUN_ID_MISMATCH")
    if report.get("research_top2_registered_for_source_session") is not True:
        reasons.append("UNREGISTERED_SOURCE_TOP2")
    if report.get("orders_enabled") is not False or report.get("current_action") != "CASH":
        reasons.append("UPSTREAM_ORDER_POLICY_MISMATCH")
    if report.get("source_regular_only_certified") is not True or row.get("source_regular_only_certified") is not True:
        reasons.append("REGULAR_SESSION_NOT_CERTIFIED")
    if not re.fullmatch("[a-f0-9]{64}", str(report.get("source_validation_sha256") or "")):
        reasons.append("PRICE_SOURCE_SHA_UNVERIFIED")
    bars = row.get("chart_bars")
    if not isinstance(bars, list) or len(bars) < 60 or not bars or bars[-1].get("date") != asof:
        reasons.append("SAME_SOURCE_60_BARS_MISSING")
    if row.get("chart_price_basis") != "KRX_UNADJUSTED_AS_TRADED":
        reasons.append("CHART_PRICE_BASIS_UNVERIFIED")
    return reasons


def classify(row, report):
    """Report both technical diagnosis and source certification separately."""
    check = assess(row, row.get("chart_bars"))
    p = ((row.get("entry_plans") or {}).get("A_SUPPORT_LIMIT") or {}).get("plan")
    asof = report.get("source_price_asof")
    close = row.get("reference_close", row.get("close"))
    source_issues = _source_blockers(row, report)
    reasons = list(check["reasons"])
    age = None
    premium = check.get("metrics", {}).get("premium_over_entry_high_pct")
    if isinstance(p, dict):
        known, current = _day(p.get("known_on")), _day(asof)
        if known and current and known <= current:
            bars = row.get("chart_bars") or []
            # Count actual observed source bars, not calendar days.
            age = sum(known < _day(b.get("date")) <= current for b in bars if _day(b.get("date"))) if bars else None
        if p.get("decision_date") != asof:
            reasons.append("PLAN_DECISION_DATE_MISMATCH")
        if _number(close) and _number(p.get("high")) and p["high"] > 0:
            premium = round(100 * (close / p["high"] - 1), 2)
    # Known-on is a pivot/plan fact, NOT proof an order was ever placed.
    stale = (isinstance(premium, (int, float)) and premium > MAX_ENTRY_PREMIUM_PCT
             and isinstance(p, dict) and _day(p.get("known_on")) is not None
             and _day(asof) is not None and _day(p["known_on"]) < _day(asof)
             and (age is None or age >= 3))
    if stale:
        diagnosis = "STALE_ENTRY"
        reasons.append("OLD_SUPPORT_PLAN_FAR_BELOW_CLOSE")
    elif any(k in reasons for k in ("FIRST_RESISTANCE_UNVERIFIED",
                                      "FIRST_RESISTANCE_NOT_ABOVE_ENTRY",
                                      "ENTRY_REWARD_RISK_BELOW_1_5")):
        diagnosis = "RISK_REJECTED"
    elif "CHASE_ENTRY_PREMIUM_OVER_5PCT" in reasons:
        diagnosis = "WAIT_PULLBACK"
    elif p is None or "INVALID_ENTRY_GEOMETRY" in reasons or "PLAN_DECISION_DATE_MISMATCH" in reasons:
        diagnosis = "DATA_BLOCKED"
    elif check["eligible"]:
        diagnosis = "ENTRY_WATCH"
    else:
        diagnosis = "RISK_REJECTED"
    qualified = diagnosis == "ENTRY_WATCH" and not source_issues
    return {
        "ticker": row.get("ticker"), "name": row.get("name"), "original_rank": row.get("rank"),
        "signal_id": row.get("signal_id"), "source_run_id": row.get("source_run_id"),
        "source_date": asof, "technical_status": diagnosis,
        "final_status": diagnosis if not source_issues else "DATA_BLOCKED",
        "presentation_eligible": qualified,
        "known_on_observed_sessions_ago": age, "premium_over_entry_high_pct": premium,
        "costed_r1_rr": p.get("net_r1_rr") if isinstance(p, dict) else None,
        "technical_reasons": list(dict.fromkeys(reasons)),
        "source_blockers": source_issues,
        "thresholds": "PROVISIONAL_RESEARCH_SAFETY_ONLY_NOT_PROFITABILITY_PROVEN",
    }


def review(report, frozen_ranked_pool=None, pool_proof=None):
    """Only evaluate immutable original TOP2. No unverified alternate candidates.

    A third-party/incomplete pool is intentionally NOT accepted for promotion.
    New full-pool as-of source proof must be integrated in a later approved task.
    """
    rows = report.get("research_top2") or []
    if not isinstance(rows, list):
        raise ValueError("TOP2_NOT_A_LIST")
    tickers = [row.get("ticker") for row in rows]
    if len(tickers) != len(set(tickers)) or len(rows) > 2:
        raise ValueError("TOP2_IMMUTABLE_IDENTITY_INVALID")
    original_digest = hashlib.sha256(_canonical(rows)).hexdigest()
    audited = [classify(row, report) for row in rows]
    approved = [item for item in audited if item["presentation_eligible"]]
    # A one-photo album must NOT be sent through sendMediaGroup.
    sendable = len(approved) == 2
    return {
        "schema": "C3_FINAL_PRESENTATION_REVIEW_V1",
        "asof": report.get("source_price_asof"),
        "source_run_id": report.get("source_run_id"),
        "price_source_sha256": report.get("source_validation_sha256"),
        "original_top2_sha256": original_digest,
        "original_top2_count": len(rows),
        "reviewed": audited, "eligible": approved,
        "eligible_count": len(approved),
        "candidate_pool_status": "CANDIDATE_POOL_UNVERIFIED",
        "replacement_count": 0, "substitutes_invented": False,
        "telegram_policy": "TWO_PHOTOS_ONLY_ELSE_SILENT_SKIP",
        "sendable": sendable, "orders_enabled": False,
        "decision": "ENTRY_WATCH_ONLY" if sendable else "CASH",
        "read_only": True,
    }


def filtered_report_for_presentation(report, evaluation):
    """Never modify the original report; requires exactly two certified rows."""
    if evaluation.get("sendable") is not True:
        raise ValueError("NO_TWO_ELIGIBLE_PRESENTATION_CANDIDATES")
    allowed = {r["ticker"] for r in evaluation["eligible"]}
    result = deepcopy(report)
    result["research_top2"] = [r for r in result["research_top2"] if r["ticker"] in allowed]
    if len(result["research_top2"]) != 2:
        raise ValueError("PRESENTATION_ELIGIBILITY_IDENTITY_MISMATCH")
    return result
