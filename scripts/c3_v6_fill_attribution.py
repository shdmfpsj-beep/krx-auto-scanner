"""V6 read-only explanation of why a precommitted C3 limit did/did not fill.

This is an AFTER-THE-FACT attribution audit, never a trade-selection rule.
The opening auction, daily low, and future reference profit may be used only
to explain observed results. They must not modify frozen prior-close orders.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from math import isfinite
from statistics import mean, median

from c3_entry_v2_preopen import _tick

CAUSES = (
    "NO_ORIGINAL_SUPPORT_PLAN",
    "PREOPEN_POLICY_REJECTED",
    "BAR_UNOBSERVABLE",
    "AUCTION_GAP_AT_OR_BELOW_STOP",
    "AUCTION_FILLED",
    "INTRADAY_TRADE_THROUGH_MODEL_ONLY",
    "NO_FILL_NEVER_REACHED_LIMIT",
    "NO_FILL_TOUCH_QUEUE_UNPROVEN",
)

def _num(x):
    try:
        y = float(x)
        return y if isfinite(y) else None
    except (ValueError, TypeError):
        return None

def _valid_daily_bar(bar):
    if not isinstance(bar, dict):
        return False
    vals = [_num(bar.get(x)) for x in ("open", "high", "low", "close", "volume")]
    if any(v is None for v in vals):
        return False
    o, h, l, c, v = vals
    return (v > 0 and 0 < l <= min(o, c) <= max(o, c) <= h
            and bar.get("tradable", True) is not False
            and bar.get("invalid_data", False) is not True
            and bar.get("action_boundary", False) is not True)

def explain(plan, planned, actual_model, next_bar, *, expected_ticker=None,
            expected_decision_date=None):
    """Classify one preclose decision; do NOT derive a new order or target.

    PRICE FACTS are available only after the session and are explicitly labelled
    retrospective. A limit touched without one-tick penetration cannot be
    asserted filled; an intraday trade-through remains merely a model proxy.
    """
    if not isinstance(planned, dict) or not isinstance(actual_model, dict):
        raise ValueError("V6_MISSING_FROZEN_DECISION_OR_EXECUTION")
    if plan is None:
        if planned.get("submitted") or actual_model.get("filled"):
            raise ValueError("V6_NONEXISTENT_PLAN_CANNOT_FILL")
        cause = "NO_ORIGINAL_SUPPORT_PLAN"
        return dict(cause=cause, submitted=False, filled=False,
                    cap=None, observed_session_only=True)
    if not isinstance(plan, dict) or (
        expected_ticker is not None and plan.get("ticker") != expected_ticker
    ) or (
        expected_decision_date is not None
        and plan.get("decision_date") != expected_decision_date
    ):
        raise ValueError("V6_ORIGINAL_SIGNAL_IDENTITY_MISMATCH")
    if not planned.get("submitted"):
        if actual_model.get("filled"):
            raise ValueError("V6_REJECTED_POLICY_CANNOT_FILL")
        return dict(cause="PREOPEN_POLICY_REJECTED",submitted=False,filled=False,
                    cap=None,rejection=planned.get("status"),
                    observed_session_only=True)
    if not _valid_daily_bar(next_bar):
        if actual_model.get("filled"):
            raise ValueError("V6_INVALID_BAR_CANNOT_MODEL_FILL")
        return dict(cause="BAR_UNOBSERVABLE",submitted=True,filled=False,
                    cap=planned.get("limit"),observed_session_only=True)
    cap = _num(planned.get("limit"))
    stop = _num(plan.get("stop"))
    if cap is None or stop is None or cap <= stop or stop <= 0:
        raise ValueError("V6_INVALID_PRIOR_CLOSE_LIMIT_OR_STOP")
    o = float(next_bar["open"])
    low = float(next_bar["low"])
    tick = _tick(cap)
    filled = bool(actual_model.get("filled"))
    if filled:
        if not isinstance(actual_model.get("individual_fills"), list) or len(actual_model["individual_fills"]) != 1:
            raise ValueError("V6_ONE_LIMIT_EXPECTS_ONE_MODEL_FILL")
        receipt = actual_model["individual_fills"][0]
        if o <= cap:
            if receipt.get("when") != "AT_OPEN" or float(receipt.get("price", -1)) != o:
                raise ValueError("V6_AUCTION_PARITY_BROKEN")
            cause = ("AUCTION_GAP_AT_OR_BELOW_STOP" if o <= stop
                     else "AUCTION_FILLED")
        elif low <= cap - tick:
            if receipt.get("when") != "INTRADAY_LIMIT_ASSUMED":
                raise ValueError("V6_TRADE_THROUGH_PARITY_BROKEN")
            cause = "INTRADAY_TRADE_THROUGH_MODEL_ONLY"
        else:
            raise ValueError("V6_MODEL_FILLED_WITHOUT_PRICE_REACH")
    else:
        if o <= cap or low <= cap-tick:
            raise ValueError("V6_MODEL_MISSED_VERIFIABLE_AUCTION_OR_PROXY_TOUCH")
        cause = ("NO_FILL_NEVER_REACHED_LIMIT" if low > cap
                 else "NO_FILL_TOUCH_QUEUE_UNPROVEN")
    # Ex-post distance required to touch a missed limit is descriptive only.
    min_intraday_price_overshoot_pct = (
        round(max(0.0, (low-cap)/cap*100), 6)
        if not filled else 0.0
    )
    return dict(
        cause=cause, submitted=True, filled=filled, cap=cap,
        open_price=o, daily_low=low, stop=stop,
        first_session_low_touches_stop=low <= stop,
        auction_open_at_or_below_stop=o <= stop,
        min_intraday_price_overshoot_pct=min_intraday_price_overshoot_pct,
        queue_fill_verified=False,
        intraday_sequence_verified=False,
        observed_session_only=True,
    )

def summarize(attributed, *, baseline="V2_HIGH"):
    """Same original selection denominator across policies, CASH counts as 0."""
    if not attributed:
        return dict(n=0, no_profit_claim=True)
    policies=tuple(attributed[0]["causes"])
    if baseline not in policies:
        raise ValueError("V6_MISSING_CONTROL")
    cause_tables={}
    for policy in policies:
        reasons=Counter(row["causes"][policy]["cause"] for row in attributed)
        missed_ref=Counter()
        negative_ref_avoided=Counter()
        low_margin=[]
        for row in attributed:
            item=row["causes"][policy]
            label=row["next_open_reference_net_pct"]
            if not item["filled"]:
                if label>0: missed_ref[item["cause"]]+=1
                if label<0: negative_ref_avoided[item["cause"]]+=1
                if item.get("min_intraday_price_overshoot_pct") is not None:
                    low_margin.append(item["min_intraday_price_overshoot_pct"])
        cause_tables[policy]=dict(
            n=len(attributed),causes=dict(sorted(reasons.items())),
            filled=sum(row["causes"][policy]["filled"] for row in attributed),
            missed_positive_reference_by_cause=dict(sorted(missed_ref.items())),
            avoided_negative_reference_by_cause=dict(sorted(negative_ref_avoided.items())),
            missed_positive_reference_total=sum(missed_ref.values()),
            avoided_negative_reference_total=sum(negative_ref_avoided.values()),
            filled_unverified_intraday_proxy=reasons["INTRADAY_TRADE_THROUGH_MODEL_ONLY"],
            fills_open_below_or_at_stop=reasons["AUCTION_GAP_AT_OR_BELOW_STOP"],
            no_touch_gap_pct_median=round(median(low_margin),6) if low_margin else None)
    transitions={}
    for policy in policies:
        if policy==baseline:continue
        x=Counter()
        for row in attributed:
            a=row["causes"][baseline]["cause"]
            b=row["causes"][policy]["cause"]
            if a!=b:x[a+" => "+b]+=1
        transitions[policy]=dict(sorted(x.items()))
    return dict(n=len(attributed),policy_causes=cause_tables,
                transition_vs_control=transitions,
                reported_future_profit_only_as_retrospective_reference=True,
                no_profit_claim=True)
