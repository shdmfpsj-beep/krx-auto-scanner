"""C3 V7 fixed ex-ante limit-access vs frozen-stop/R1 feasibility frontier.

Research-only hypotheses, not trade instructions. Source original B DAILY TOP2 and
A_SUPPORT_LIMIT unchanged. Future OHLCV never enters make_prior_close_plans().
No variants are tuned to post-entry returns; SAFE is 12% / 1R / 1% net R1
with maximum +0.5 prior ATR uplift over frozen HIGH; UNGUARDED is a falsification
stress case, NOT an order recommendation. Both preserve already-resting
auction fill exposure even if the next open gaps below the structural stop.
"""
from __future__ import annotations

from math import isfinite
from c3_entry_v2_preopen import _quote_down, entry as v2_entry
from c3_entry_v4_geometry import (
    BUY_FACTOR, SELL_FACTOR, score_geometry
)
from c3_v5_continuation_entry import choose_plan as v5_choose_plan

POLICIES=("V2_HIGH","V7_CLOSE_UPLIFT_UNGUARDED","V7_CLOSE_R1_GUARDED")
RISK_STOP_MAX_PCT=12.
MIN_R1_RR=1.
MIN_NET_R1_REWARD_PCT=1.
ATR_UPLIFT_MAX=0.5

def positive(x):
    try:
        v=float(x)
        return v if isfinite(v) and v>0 else None
    except (TypeError,ValueError):
        return None

def prior_distance_diagnostics(plan,prior):
    if plan is None:
        return dict(status="NO_FROZEN_PLAN",eligible=False)
    if not isinstance(prior,dict) or (
        prior.get("ticker")!=plan.get("ticker")
        or prior.get("decision_date")!=plan.get("decision_date")
    ):
        return dict(status="PRIOR_IDENTITY_MISMATCH",eligible=False)
    high=positive(plan.get("high"));low=positive(plan.get("low"))
    stop=positive(plan.get("stop"));close=positive(plan.get("reference_close"))
    atr=positive(plan.get("atr"));r1=positive(plan.get("resistance"))
    if None in (high,low,stop,close,atr) or not 0<stop<low<=high:
        return dict(status="INVALID_FROZEN_GEOMETRY",eligible=False)
    # Prior-close status only; zero/negative close distance is not overshoot.
    gap_pct=100*(close/high-1)
    gap_atr=(close-high)/atr
    if gap_pct<=0:bucket="CLOSE_AT_OR_BELOW_HIGH"
    elif gap_pct<=2:bucket="ABOVE_HIGH_0_TO_2"
    elif gap_pct<=5:bucket="ABOVE_HIGH_2_TO_5"
    elif gap_pct<=10:bucket="ABOVE_HIGH_5_TO_10"
    else:bucket="ABOVE_HIGH_OVER_10"
    risk=score_geometry(high,stop,r1) if r1 else None
    return dict(status="PRIOR_GEOMETRY_READY",eligible=True,
                prior_close=close,original_high=high,original_low=low,
                original_stop=stop,atr=atr,r1=r1,
                high_to_prior_close_gap_pct=round(gap_pct,6),
                high_to_prior_close_gap_atr=round(gap_atr,6),
                gap_bucket=bucket,original_high_geometry=risk)

def make_prior_close_plans(plan,prior):
    """All caps fixed using decision-session information. Never read a future bar."""
    d=prior_distance_diagnostics(plan,prior)
    control=v5_choose_plan(plan,prior,"V2_HIGH")
    out={"V2_HIGH":control}
    if not control["submitted"] or not d["eligible"]:
        for policy in POLICIES[1:]:
            out[policy]=dict(status="NO_ORDER_ORIGINAL_SIGNAL_INVALID",
                             submitted=False,limit=None,policy=policy,
                             generated_using_next_session_price=False)
        return d,out
    high=d["original_high"];stop=d["original_stop"]
    cap_raw=min(d["prior_close"],high+ATR_UPLIFT_MAX*d["atr"])
    candidate=_quote_down(cap_raw)
    if candidate<=high:
        # No candidate: exact unchanged control rather than pretending a new order.
        status="UNCHANGED_NO_UPLIFT_AT_PRIOR_CLOSE"
        out["V7_CLOSE_UPLIFT_UNGUARDED"]=dict(status=status,submitted=True,
            limit=high,policy=POLICIES[1],uplifted=False)
        out["V7_CLOSE_R1_GUARDED"]=dict(status=status,submitted=True,
            limit=high,policy=POLICIES[2],uplifted=False)
        return d,out
    out["V7_CLOSE_UPLIFT_UNGUARDED"]=dict(
        status="FROZEN_UPLIFT_STRESS_NO_RISK_GUARD",submitted=True,
        limit=float(candidate),policy=POLICIES[1],uplifted=True)
    r1=d["r1"]
    if r1 is None or r1<=stop:
        out["V7_CLOSE_R1_GUARDED"]=dict(
            status="UNCHANGED_UNKNOWN_OR_INVALID_FROZEN_R1",
            submitted=True,limit=high,policy=POLICIES[2],uplifted=False)
        return d,out
    # Same mathematically conservative cost bounds as V4, independent of
    # any next-bar returns. Eligible only if a cap ABOVE original HIGH works.
    by_rr=SELL_FACTOR*(r1+MIN_R1_RR*stop)/((1+MIN_R1_RR)*BUY_FACTOR)
    by_stop=stop/(1-RISK_STOP_MAX_PCT/100)
    by_reward=r1*SELL_FACTOR/(BUY_FACTOR*(1+MIN_NET_R1_REWARD_PCT/100))
    safe=_quote_down(min(candidate,by_rr,by_stop,by_reward))
    geometry=score_geometry(safe,stop,r1) if safe>stop else None
    if (safe<=high or geometry is None
        or geometry["raw_stop_distance_pct"]>RISK_STOP_MAX_PCT+1e-6
        or geometry["net_first_resistance_rr"] is None
        or geometry["net_first_resistance_rr"]<MIN_R1_RR-1e-6
        or geometry["net_first_resistance_reward_pct"] is None
        or geometry["net_first_resistance_reward_pct"]<MIN_NET_R1_REWARD_PCT-1e-6):
        out["V7_CLOSE_R1_GUARDED"]=dict(
            status="UNCHANGED_GUARDED_R1_OR_STOP_BUDGET_NOT_PASSED",
            submitted=True,limit=high,policy=POLICIES[2],uplifted=False)
        return d,out
    out["V7_CLOSE_R1_GUARDED"]=dict(
        status="FROZEN_UPLIFT_GUARDED",submitted=True,limit=float(safe),
        policy=POLICIES[2],uplifted=True,
        net_r1_geometry_at_raised_cap=geometry)
    return d,out

def execute_frozen(plan,frozen,next_bar):
    """Pure V2 mechanical model for a prior submitted cap; no lookahead cancellation."""
    if not frozen.get("submitted"):
        return dict(status=frozen["status"],filled=False,no_order=True,
                    model_only=True)
    cap=positive(frozen.get("limit"))
    if plan is None or cap is None or cap<=positive(plan.get("stop")):
        raise ValueError("V7_INVALID_EXECUTABLE_FROZEN_CAP")
    order=dict(plan,high=cap)
    if cap<float(order["low"]):
        order["low"]=cap
    result=v2_entry(order,next_bar,"RESTING_ONE")
    result["v7_policy"]=frozen["policy"]
    result["preclose_limit"]=cap
    result["model_only"]=True
    return result
