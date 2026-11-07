"""C3 V4: prior-close-only price geometry, read-only *research*.

Hypotheses are fixed BEFORE running HOLDOUT:
  V2_HIGH: old one-session pre-open resting BUY limit at prior planned high.
  V4_BALANCED: lower entry cap for net first-resistance RR>=1.0, stop
               distance<=12%, minimum 1% net reward, limited 0.5 ATR
               below original lower budget.
  V4_DEFENSIVE: lower entry cap for net RR>=1.5, stop distance<=8%,
                minimum 2% net reward, max 0.5 ATR below original low.
  V4_MIDPOINT: one resting limit at mid original range, no extra veto.
Every order uses preceding close, ATR, structural stop, first resistance,
and known prior 20-day turnover ONLY; no next day's OHLCV or news. Orders
submitted preopen are mechanical: gapping below stop still fills (unsafe)
and must stay in P/L; avoid retroactive veto.

These generic percentages are RESEARCH hypotheses, not trained optimal rules.
No orders, no modified signals, no ledger, no Telegram or notifications.
"""
from __future__ import annotations
from math import isfinite
from dataclasses import dataclass
from c3_entry_v2_preopen import BUY_COST,SELL_COST,SLIPPAGE_EACH_SIDE,_quote_down,_tick,entry

VARIANTS=("V2_HIGH","V4_BALANCED","V4_DEFENSIVE","V4_MIDPOINT")
BUY_FACTOR=(1+BUY_COST)*(1+SLIPPAGE_EACH_SIDE)
SELL_FACTOR=(1-SELL_COST)*(1-SLIPPAGE_EACH_SIDE)

@dataclass(frozen=True)
class Prescription:
    rr:float
    max_stop_pct:float
    min_net_reward_pct:float
    max_lower_extension_atr:float

# All threshold values fixed independent of retrospective outcomes.
PREDEFINED={
    "V4_BALANCED":Prescription(1.,12.,1.,.5),
    "V4_DEFENSIVE":Prescription(1.5,8.,2.,.5),
}

def positive(x):
    try:
        a=float(x)
        return a if isfinite(a) and a>0 else None
    except (ValueError,TypeError):return None

def actual_net_r1_rr(entry_cap,stop,r1):
    """Fees and bid/ask slippage are charged on both entry and exit."""
    buy=entry_cap*BUY_FACTOR
    liquidation=stop*SELL_FACTOR
    target=r1*SELL_FACTOR
    risk=buy-liquidation
    return (target-buy)/risk if risk>0 else None

def score_geometry(price,stop,resistance):
    r1=positive(resistance)
    risk=(100*(price-stop)/price if price>stop else None)
    reward=100*(r1*SELL_FACTOR/(price*BUY_FACTOR)-1) if r1 else None
    return dict(entry_cap=float(price),frozen_structural_stop=float(stop),
        first_resistance=r1,raw_stop_distance_pct=round(risk,6) if risk is not None else None,
        net_first_resistance_reward_pct=round(reward,6) if reward is not None else None,
        net_first_resistance_rr=round(actual_net_r1_rr(price,stop,r1),6) if r1 and price>stop else None)

def executable_cap(plan,variant):
    """Return ONE frozen limit cap or a research-only reject reason.

    Stops are NOT resting order stop orders. A calculated cap never guarantees
    safety after a gap-down open or before a limit fill.
    """
    if variant not in VARIANTS:raise ValueError("UNKNOWN_V4_VARIANT")
    keys=("high","low","stop","atr","reference_close")
    if any(positive(plan.get(k)) is None for k in keys):
        return dict(status="BAD_FROZEN_PLAN",limit=None,variant=variant)
    high,low,stop,atr,close=(float(plan[k]) for k in keys)
    if not (0<stop<low<=high and atr>0 and close>0):
        return dict(status="BAD_FROZEN_GEOMETRY",limit=None,variant=variant)
    r1=positive(plan.get("resistance"))
    if variant=="V2_HIGH":
        return dict(status="PLAN_READY",limit=high,variant=variant,
            policy="ORIGINAL_V2_SINGLE_RESTING")
    if variant=="V4_MIDPOINT":
        limit=_quote_down((low+high)/2)
        if limit<=stop:return dict(status="MIDPOINT_AT_OR_BELOW_STOP",limit=None,variant=variant)
        return dict(status="PLAN_READY",limit=limit,variant=variant,
            policy="MIDPOINT_IN_OLD_SUPPORT_RANGE")
    if r1 is None or r1<=stop:return dict(status="UNKNOWN_OR_INVALID_R1",limit=None,variant=variant)
    spec=PREDEFINED[variant]
    # Planned entry cost (not realised next-day execution) must satisfy both:
    # (R1 proceeds - buy cost)/(buy cost - stop proceeds) >= min RR
    # ((entry - stop)/entry)*100 <= max stop distance.
    limit_by_rr=(SELL_FACTOR*(r1+spec.rr*stop)) / ((1+spec.rr)*BUY_FACTOR)
    limit_by_risk=stop/(1-spec.max_stop_pct/100)
    # Minimum target reward net, including frozen entry/exit costs.
    limit_by_reward=(r1*SELL_FACTOR)/(BUY_FACTOR*(1+spec.min_net_reward_pct/100))
    limit=_quote_down(min(high,limit_by_rr,limit_by_risk,limit_by_reward))
    if limit<=stop:return dict(status="CAP_BELOW_STOP",limit=None,variant=variant)
    # Do not invent arbitrary near-zero orders just to get high RR.
    # The only permitted extension is half an ATR below the original
    # low. It is a farther buy LIMIT, not assumed fill or approval.
    if limit<low-spec.max_lower_extension_atr*atr:
        return dict(status="CAP_TOO_FAR_BELOW_FROZEN_BAND",limit=None,
                    variant=variant,raw_frozen_cap=limit)
    if limit>high:return dict(status="CAP_ABOVE_ORIGINAL_BUDGET",limit=None,variant=variant)
    geometry=score_geometry(limit,stop,r1)
    eps=1e-7
    if (geometry["raw_stop_distance_pct"]>spec.max_stop_pct+eps or
        geometry["net_first_resistance_rr"]<spec.rr-eps or
        geometry["net_first_resistance_reward_pct"]<spec.min_net_reward_pct-eps):
        return dict(status="QUOTE_OR_COST_CONSTRAINT_FAILED",limit=None,variant=variant)
    return dict(status="PLAN_READY",limit=limit,variant=variant,
        extension_below_original_low=limit<low,
        prior_turnover=plan.get("rank_turnover"),
        prior_rs20=plan.get("rs20"),
        **geometry)

def model_entry(frozen_plan,next_bar,variant):
    """Do not let post-open price features change an already-resting limit."""
    planned=executable_cap(frozen_plan,variant)
    if planned["status"]!="PLAN_READY":
        return dict(status=planned["status"],filled=False,method=variant,
                    no_order_due_to_previous_close_geometry=True),planned
    e=dict(frozen_plan,high=float(planned["limit"]))
    if planned["limit"]<float(e["low"]):
        # V2 requires low <= high as its original budget integrity check.
        # A deeper V4 one-limit plan is constrained to a single actual cap.
        e["low"]=float(planned["limit"])
    execution=entry(e,next_bar,"RESTING_ONE")
    execution["method"]=variant
    execution["original_high"]=frozen_plan["high"]
    execution["preopen_frozen_limit"]=planned["limit"]
    execution["computed_without_next_session_bar"]=True
    return execution,planned
