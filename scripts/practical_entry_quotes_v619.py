#!/usr/bin/env python3
"""v6.19 live-usable KRX stock PRICE QUOTE primitives, with NO BUY authority.

This library returns order-grid-compatible hypothetical prices and checks
whether a proposed entry could be touched, while NOT issuing orders or
claiming executions. Always refresh regular-only prices, 65 daily bars,
actual broker cash/position, final 80 score, corporate catalysts and PIT
sources before a separate real BUY decision. Research only.
"""
from __future__ import annotations
import math
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING

SCHEMA="C3_V619_PRACTICAL_LIMIT_QUOTES_NO_ORDERS"
TICKS=((2000,1),(5000,5),(20000,10),(50000,50),
       (200000,100),(500000,500),(float("inf"),1000))
COST_PCT=.65

def tick(price):
    p=float(price)
    if not math.isfinite(p) or p<=0:raise ValueError("INVALID_STOCK_PRICE")
    return next(step for ceiling,step in TICKS if p<ceiling)

def krx_round(value,side="down"):
    d=Decimal(str(value))
    step=Decimal(tick(float(d)))
    kind={"down":ROUND_FLOOR,"up":ROUND_CEILING}.get(side)
    if kind is None:raise ValueError("UNKNOWN_QUOTE_SIDE")
    q=float((d/step).to_integral_value(rounding=kind)*step)
    if side=="up" and tick(q)!=tick(float(d)):
        bigger=Decimal(tick(q))
        q=float((Decimal(str(q))/bigger).to_integral_value(rounding=ROUND_CEILING)*bigger)
    if q<=0 or (Decimal(str(q))/Decimal(tick(q)))%1!=0:
        raise ValueError("NON_KRX_QUOTE")
    return int(q)

def quote_set(close,atr14,sma20,structural_stop,prior20_high,
              overhead_resistance=None,setup="FIRST_MA20_RESUME"):
    """Return proposed FIRST and an ALTERNATIVE if FIRST never fills.

    Second is an order replacement, NOT a planned averaging-down fill.
    Structural stop is set before choosing any entry. Price levels are
    deterministic from completed signal-day bars, without future information.
    """
    vals=[close,atr14,sma20,structural_stop,prior20_high]
    if any(not isinstance(x,(int,float)) or not math.isfinite(x) or x<=0 for x in vals):
        raise ValueError("MISSING_VERIFIED_NUMERIC_DAILY_GEOMETRY")
    if not structural_stop<close or atr14/close>.12:
        raise ValueError("INVALID_DAILY_STRUCTURE")
    stop=krx_round(structural_stop,"down")
    near=krx_round(close-.20*atr14,"down")
    if setup=="FRESH_20D_BREAKOUT" and close>prior20_high:
        alt=krx_round(prior20_high+.15*atr14,"down")
        method="BREAKOUT_RETEST"
    else:
        alt=krx_round(max(sma20+.35*atr14,close-.70*atr14),"down")
        method="MA20_FIRST_PULLBACK"
    result=[]
    for label,price in (("FIRST_NEAR_CLOSE",near),("REPLACEMENT_IF_UNFILLED_"+method,alt)):
        if price>=close or price<=stop or (close-price)/atr14>1.15:continue
        risk=100*(price-stop)/price
        if not 2<=risk<=12:continue
        over=(krx_round(overhead_resistance,"down") if overhead_resistance
              and overhead_resistance>close else None)
        rr=(round((over-price-COST_PCT/100*price)/
                  (price-stop+COST_PCT/100*price),3) if over else None)
        synthetic=krx_round(price+2*(price-stop+.0065*price)+.0065*price,"up")
        result.append(dict(schema=SCHEMA,method=label,
            proposed_limit_krw=price,day_structure_stop_krw=stop,
            structural_risk_pct=round(risk,3),
            limit_below_completed_close_atr=round((close-price)/atr14,3),
            verified_overhead_krw=over,verified_overhead_net_R=rr,
            scenario_two_R_target_not_verified=synthetic,
            research_tier=("CONFIRMED_OVERHEAD_GEOMETRY_2R_RESEARCH"
                if rr is not None and rr>=2 else "WATCH_PRICE_ONLY_NO_VERIFIED_2R"),
            one_slot_second_not_add_on=True,
            asof_regular_session_certified=False,
            account_available_cash_verified=False,
            final_stock_80_verified=False,
            price_touch_not_a_fill=True,
            trade_approved=False,orders_enabled=False))
    return result

def next_session_touch(plan,signal_close,atr14,open_price,high,low):
    """A resting limit hypothetical: reject gap-through, gap-up chasing and stop.
    No same-day candle path or broker fill inferred.
    """
    e=plan["proposed_limit_krw"];s=plan["day_structure_stop_krw"]
    if any(not math.isfinite(float(x)) or float(x)<=0
           for x in (open_price,high,low,signal_close,atr14)):
        raise ValueError("BAD_NEXT_SESSION_OHLC")
    if not low<=open_price<=high:return "INVALID_CANDLE"
    if open_price<=s:return "CANCEL_OPEN_BELOW_STRUCTURE_STOP"
    if open_price<e:return "CANCEL_GAP_THROUGH_RESTING_LIMIT"
    if open_price>signal_close+min(.5*atr14,.035*signal_close):
        return "CANCEL_OPEN_TOO_HIGH_NO_CHASE"
    if not low<=e<=high:return "PENDING_LIMIT_NOT_TOUCHED"
    if low<=s:return "STUDY_TOUCH_WITH_AMBIGUOUS_SAME_DAY_STOP_FIRST"
    return "STUDY_PRICE_CONTACT_NOT_BROKER_FILL"

def completed_retest_signal(d1_open,d1_high,d1_low,d1_close,
                            asof_support,atr14,stop):
    """Called AFTER the entire D+1 session has closed; can only enter D+2."""
    if not (0<d1_low<=min(d1_open,d1_close)
            <=max(d1_open,d1_close)<=d1_high):
        return False
    span=d1_high-d1_low
    return bool(span>0 and d1_low<=asof_support+.4*atr14
        and d1_close>max(d1_open,asof_support,stop)
        and d1_close>=d1_low+.58*span)

def confirmed_d2_open(d1_close,atr14,d2_open,stop):
    """Price available at D+2 opening, not D+1 closing candle."""
    if not all(math.isfinite(float(x)) and x>0 for x in
       (d1_close,atr14,d2_open,stop)):
        return None
    if not d1_close-.30*atr14<=d2_open<=d1_close+.35*atr14:
        return None
    entry=krx_round(d2_open,"up")
    risk=100*(entry-krx_round(stop,"down"))/entry
    return entry if 2<=risk<=12 else None

def risk_capacity(orderable_cash,entry,stop,verified_cash=False,risk_budget_pct=1.0):
    """Optional quantity only if the broker-available cash was verified.
    Worst-loss estimate excludes unbounded gap slippage; NOT risk guaranteed.
    """
    if not verified_cash:return None
    if any(not isinstance(z,(int,float)) or not math.isfinite(z)
           for z in (orderable_cash,entry,stop,risk_budget_pct)):
        return None
    if not (orderable_cash>0 and 0<stop<entry and 0<risk_budget_pct<=2):
        return None
    usable=math.floor(orderable_cash/entry)
    budget=orderable_cash*risk_budget_pct/100
    by_loss=math.floor(budget/(entry-stop+.0065*entry))
    return max(0,min(usable,by_loss))
