"""C3 V5 causal continuation vs fill opportunity (RESEARCH ONLY).

The original B DAILY TOP2 selections from frozen v6 remain unchanged. Original
prior-session v7 A_SUPPORT_LIMIT plan remains unchanged. This module chooses
whether and at what limit to submit *one* hypothetical buy order, using only
data on the prior decision session.

Pre-registered (no parameter optimization on this 95-name holdout):
  V2_HIGH              prior plan HIGH; original benchmark
  V4_MIDPOINT          prior support band MIDPOINT; second benchmark
  V5_TREND_GATE_HIGH   original HIGH only if confirmed trend60 and
                       turnover_ratio>=1.0; otherwise CASH
  V5_TREND_ADAPTIVE    original HIGH if strong, MIDPOINT otherwise;
                       weaker candidates retain a price-improved opportunity
  V5_RISK_AWARE        choose HIGH if net R1 RR>=1 and raw stop risk<=12%;
                       else choose MIDPOINT only if same risks pass;
                       otherwise CASH. This rule deliberately may forgo
                       momentum winners; measure missed positive moves.

No pre-open planned order may be canceled retroactively with next-day OPEN,
and a stop-below open still fills mechanically with an unsafe-risk flag.
The first-resistance RR is ONLY the pre-existing v7 computed plan geometry.
Never use future price to choose variant, filter or limit.
"""
from __future__ import annotations
from math import isfinite
from c3_entry_v4_geometry import executable_cap,score_geometry,model_entry as v4_entry
from c3_entry_v2_preopen import entry as v2_entry

POLICIES=("V2_HIGH","V4_MIDPOINT","V5_TREND_GATE_HIGH",
          "V5_TREND_ADAPTIVE","V5_RISK_AWARE")

def _number(x):
    try:
        y=float(x)
        return y if isfinite(y) else None
    except (TypeError,ValueError):return None

def prior_strong(row):
    """The B selector already requires own RS and 5d RS acceleration > 0.

    Trend60 and turnover ratio are additional independent *prior-close*
    hypotheses; this is NOT a learned calibrated probability of continuation.
    """
    if not isinstance(row,dict):
        return dict(strong=False,missing=True,reason="NO_PREDECISION_FEATURE")
    trend=row.get("trend60")
    turnover=_number(row.get("turnover_ratio"))
    if not isinstance(trend,bool) or turnover is None:
        return dict(strong=False,missing=True,reason="PRIOR_FEATURE_NOT_VERIFIABLE",
                    trend60=trend,turnover_ratio=turnover)
    status=bool(trend and turnover>=1.0)
    return dict(strong=status,missing=False,
                reason="TREND_CONFIRMED_TURNOVER_GE_1" if status
                  else "PRIOR_TREND_OR_TURNOVER_NOT_CONFIRMED",
                trend60=trend,turnover_ratio=round(turnover,6),
                own_rs20=_number(row.get("own_rs20")),
                rs_accel5=_number(row.get("rs_accel5")))

def gate_risk(plan,limit):
    if limit is None:return dict(accepted=False,reason="NO_FROZEN_LIMIT")
    s=_number(plan.get("stop"));r=_number(plan.get("resistance"))
    if s is None or r is None or s<=0 or r<=0 or limit<=s:
        return dict(accepted=False,reason="MISSING_PRIOR_STOP_OR_R1")
    g=score_geometry(float(limit),s,r)
    if g["net_first_resistance_rr"] is None:
        return dict(accepted=False,reason="UNDEFINED_COSTED_R1_RR",geometry=g)
    ok=(g["raw_stop_distance_pct"]<=12. and
        g["net_first_resistance_rr"]>=1. and
        g["net_first_resistance_reward_pct"]>=1.)
    return dict(accepted=ok,
        reason="PREDECISION_RISK_BUDGET_PASS" if ok else
               "PREDECISION_RISK_OR_REWARD_NOT_ELIGIBLE",geometry=g)

def choose_plan(plan,prior,policy):
    """Plan must be pre-existing and prior is the *matched* frozen B decision."""
    if policy not in POLICIES:raise ValueError("UNREGISTERED_V5_HYPOTHESIS")
    if not plan:return dict(status="NO_ORIGINAL_SUPPORT_PLAN",submitted=False,
                            limit=None,policy=policy)
    strong=prior_strong(prior)
    high=executable_cap(plan,"V2_HIGH")
    mid=executable_cap(plan,"V4_MIDPOINT")
    if policy=="V2_HIGH":
        chosen=high;basis="ORIGINAL_V2"
    elif policy=="V4_MIDPOINT":
        chosen=mid;basis="ORIGINAL_MIDPOINT"
    elif policy=="V5_TREND_GATE_HIGH":
        if strong["missing"] or not strong["strong"]:
            return dict(status="NO_ORDER_PRIOR_TREND_NOT_CONFIRMED",
                submitted=False,limit=None,policy=policy,
                strength=strong)
        chosen=high;basis="STRENGTH_PRIOR_ONLY"
    elif policy=="V5_TREND_ADAPTIVE":
        if strong["missing"]:
            return dict(status="NO_ORDER_PRIOR_FEATURES_MISSING",
                submitted=False,limit=None,policy=policy,strength=strong)
        chosen=high if strong["strong"] else mid
        basis="STRONG_HIGH_ELSE_MID"
    else:
        # Refuse unsafe high but do not blindly put the remaining order
        # too far below range. Midpoint is a distinct *pre-open* limit.
        high_gate=gate_risk(plan,high.get("limit"))
        mid_gate=gate_risk(plan,mid.get("limit"))
        if high_gate["accepted"]:
            chosen=high;basis="RISK_APPROVED_HIGH"
        elif mid_gate["accepted"]:
            chosen=mid;basis="RISK_APPROVED_MID"
        else:
            return dict(status="NO_ORDER_COSTED_RISK_R1_FAIL",
                submitted=False,limit=None,policy=policy,
                strength=strong,high_gate=high_gate,mid_gate=mid_gate)
    if chosen["status"]!="PLAN_READY":
        return dict(status="NO_ORDER_"+chosen["status"],submitted=False,
                    limit=None,policy=policy,strength=strong)
    return dict(status="PREOPEN_LIMIT_FROZEN",submitted=True,
                limit=chosen["limit"],policy=policy,
                strength=strong,selection_basis=basis,
                original_low=plan["low"],original_high=plan["high"],
                original_stop=plan["stop"],
                original_first_resistance=plan.get("resistance"),
                generated_using_next_session_price=False)

def simulate(plan,prior,next_bar,policy):
    frozen=choose_plan(plan,prior,policy)
    if not frozen["submitted"]:
        return frozen,dict(status=frozen["status"],filled=False,
                           no_order=True,model_only=True)
    # Explicitly use the shared V2 matching fill model so the control
    # identity for original HIGH is exactly preserved.
    p=dict(plan)
    cap=float(frozen["limit"])
    p["high"]=cap
    if cap<p["low"]:p["low"]=cap
    e=v2_entry(p,next_bar,"RESTING_ONE")
    e["v5_policy"]=policy
    e["prior_close_limit"]=cap
    e["model_only"]=True
    e["no_order"]=False
    return frozen,e
