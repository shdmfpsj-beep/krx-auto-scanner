"""C3 V3 close-confirmed exits: research-only, no broker/ledger/notification access.

All signals are from the frozen prior session. No intraday high is a target fill:
- BASELINE: original close below structural stop or horizon -> NEXT open full exit.
- HALF_R1: first CLOSE >= frozen R1 schedules half at NEXT open; remainder
  stays on original structural stop, full exit at horizon.
- TRAIL_7_ATR: once CLOSE >= entry +7%, use a 1.5*frozen-ATR high-close
  trail, activated only FOR FOLLOWING CLOSES, exit NEXT open on breach.
- HALF_R1_TRAIL: independently combines the above two causal rules.

A resting preopen order can fill below the initial stop. This scenario remains
an unsafe mechanical fill in the research P/L, NOT a retroactively cancelled
order, never a user trade recommendation.

The original V2 exit model is imported only for exact BASELINE parity checks.
"""
from __future__ import annotations

from math import isfinite
from statistics import mean
from c3_entry_v2_preopen import BUY_COST, SELL_COST, SLIPPAGE_EACH_SIDE, _bar_ok

POLICIES=("BASELINE","HALF_R1","TRAIL_7_ATR","HALF_R1_TRAIL")
HORIZONS=(5,10,20)
TRAIL_TRIGGER_PCT=7.
TRAIL_ATR_MULT=1.5

def require(ok,code):
    if not ok:raise ValueError(code)

def net_pct(entry_price,exit_price):
    return 100*(exit_price*(1-SELL_COST)*(1-SLIPPAGE_EACH_SIDE)/
                (entry_price*(1+BUY_COST)*(1+SLIPPAGE_EACH_SIDE))-1)

def exit_strategy(plan,entry_day,ent,by_date,sessions,horizon,policy):
    if policy not in POLICIES:raise ValueError("UNREGISTERED_EXIT_POLICY")
    if horizon not in HORIZONS:raise ValueError("UNREGISTERED_HORIZON")
    if not ent.get("filled"):return dict(status="NO_ENTRY",net_pct=None,policy=policy)
    require(entry_day in sessions,"ENTRY_DAY_NOT_ON_CALENDAR")
    e=sessions.index(entry_day)
    entry_price=float(ent["price"])
    stop=float(plan["stop"])
    require(0<stop<entry_price*10 and isfinite(entry_price),"INVALID_FROZEN_STOP")
    atr=float(plan.get("atr") or 0)
    if "TRAIL" in policy:require(isfinite(atr) and atr>0,"TRAIL_MISSING_FROZEN_ATR")
    r1=plan.get("resistance")
    target=(float(r1) if r1 is not None else None)
    target_available=bool(target is not None and isfinite(target) and target>entry_price)
    partial_enabled="HALF_R1" in policy and target_available
    trailing_enabled="TRAIL" in policy
    quantity=1.0
    cash_proceeds_net_pct=0.
    realized_parts=[]
    scheduled_full=None
    scheduled_half=False
    half_scheduled_once=False
    activated_at=None
    active_stop=stop
    peak_close=None
    stop_raise_count=0
    price_extremes={"mfe":None,"mae":None}
    # Consume each day in clock order. An exit at an open must never
    # observe that same session's subsequent high, low or close.
    for i in range(e,len(sessions)):
        day=sessions[i]
        bar=by_date.get(day)
        if bar is None or not _bar_ok(bar):
            return dict(status="CENSORED_MISSING_OR_INVALID_BAR",net_pct=None,
                        policy=policy,censor_date=day)
        op=float(bar["open"])
        if scheduled_full is not None:
            part=net_pct(entry_price,op)
            cash_proceeds_net_pct+=quantity*part
            realized_parts.append(dict(date=day,price=op,weight=round(quantity,8),
                                       reason=scheduled_full,tranche_net_pct=round(part,6)))
            quantity=0.
            return dict(status="COMPLETE",policy=policy,entry_date=entry_day,
                        exit_date=day,exit_open=op,exit_reason=scheduled_full,
                        net_pct=round(cash_proceeds_net_pct,6),
                        opportunity_cash_adjusted_pct=round(cash_proceeds_net_pct*
                                                            ent["allocations_filled"],6),
                        realized_parts=realized_parts,
                        partial_execution_count=sum(x["weight"]<1 for x in realized_parts),
                        target_close_confirmation_only=True,trail_activated_at=activated_at,
                        stop_raise_count=stop_raise_count,
                        unsafe_unconditional_preopen_fill=ent.get("open_at_or_below_stop",False))
        if scheduled_half:
            # Half of ORIGINAL holdings; proceeds are not redeployed in this
            # isolated single-signal comparison. No free capital reinvestment.
            half=0.5
            require(quantity>=half,"HALF_ORDER_QUANTITY_UNDERFLOW")
            part=net_pct(entry_price,op)
            cash_proceeds_net_pct+=half*part
            realized_parts.append(dict(date=day,price=op,weight=half,
                                       reason="R1_CONFIRMED_CLOSE_HALF_NEXT_OPEN",
                                       tranche_net_pct=round(part,6)))
            quantity-=half
            scheduled_half=False
        # All intraday bar extremes are unknown in sequence; exits below
        # are CLOSE-confirmed only, so the bar is observed for drawdown only.
        # Stop is compared with its pre-existing level BEFORE any trailing
        # update from the current close. Strict '<' matches frozen V2.
        close=float(bar["close"])
        old_active_stop=active_stop
        if close<old_active_stop:
            scheduled_full=("TRAIL_CLOSE_BREAK_NEXT_OPEN" if old_active_stop>stop
                            else "CLOSE_BELOW_FROZEN_STOP_NEXT_OPEN")
        if i-e>=horizon and scheduled_full is None:
            scheduled_full="HORIZON_NEXT_OPEN"
        if scheduled_full is None and partial_enabled and not half_scheduled_once and close>=target:
            scheduled_half=True
            half_scheduled_once=True
        if trailing_enabled and scheduled_full is None:
            if peak_close is None or close>peak_close:peak_close=close
            if peak_close>=entry_price*(1+TRAIL_TRIGGER_PCT/100):
                if activated_at is None:activated_at=day
                # New stop begins NEXT bar; can't change today's evaluation.
                candidate=peak_close-TRAIL_ATR_MULT*atr
                if candidate>active_stop:
                    active_stop=candidate
                    stop_raise_count+=1
    return dict(status="WINDOW_NOT_MATURED",policy=policy,net_pct=None,
                pending=scheduled_full or ("HALF_TARGET_NEXT_OPEN" if scheduled_half else None))

def aggregation(rows):
    """Always report both trade-conditional return and opportunities with CASH.

    Opportunity metric is an equal-notional single-signal hypothetical,
    NOT a capital-constrained multi-stock portfolio.
    """
    evaluated=[x for x in rows if x["status"] in ("COMPLETE","NO_ENTRY")]
    complete=[x for x in evaluated if x["status"]=="COMPLETE"]
    cond=[x["net_pct"] for x in complete]
    opp=[x["opportunity_cash_adjusted_pct"] if x["status"]=="COMPLETE" else 0.
         for x in evaluated]
    return dict(plans=len(rows),valid_common_clock=len(evaluated),
                completed=len(complete),
                no_entry=sum(x["status"]=="NO_ENTRY" for x in evaluated),
                incomplete=len(rows)-len(evaluated),
                conditional_mean_net_pct=round(mean(cond),6) if cond else None,
                opportunity_mean_with_cash_pct=round(mean(opp),6) if opp else None,
                win_rate_pct=round(100*sum(x>0 for x in cond)/len(cond),3) if cond else None,
                partial_execution_count=sum(any(part["weight"]<1.0 for part in x["realized_parts"])
                    for x in complete),
                trail_activated_count=sum(x.get("trail_activated_at") is not None
                    for x in complete),
                sample_too_small_for_strategy_promotion=True)
