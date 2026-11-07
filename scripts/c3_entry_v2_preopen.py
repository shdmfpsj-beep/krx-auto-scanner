"""C3 Entry V2: research-only, time-ordered resting pre-open limit sensitivity.

Separates mechanical resting-order execution from 'safe' research eligibility.
A resting pre-open BUY limit can fill BELOW its limit, including below a stop.
The historical strict no-gap model was an idealised open-time veto: it is not
the same as a previously submitted order at the exchange.

No broker connections, orders, historical ledgers, signals or Telegram calls.
The source/market scope must be validated separately before actionable use.
"""
from __future__ import annotations
from collections import Counter
from math import isfinite
from statistics import mean

# Frozen existing research execution costs; not actual broker-calibrated fees.
BUY_COST = .0015
SELL_COST = .005
SLIPPAGE_EACH_SIDE = .001


def _tick(price:float)->int:
    for maximum, step in ((2_000,1),(5_000,5),(20_000,10),(50_000,50),
                          (200_000,100),(500_000,500)):
        if price < maximum:return step
    return 1000


def _quote_down(price:float)->float:
    from math import floor
    unit=_tick(price)
    return float(floor(price/unit+1e-10)*unit)


def _bar_ok(b:dict)->bool:
    try:
        o,h,l,c=[float(b[k]) for k in ("open","high","low","close")]
        v=float(b.get("volume",1))
        return (all(map(isfinite,(o,h,l,c,v))) and v>0 and
                0<l<=min(o,c)<=max(o,c)<=h and
                b.get("tradable",True) is not False and
                b.get("invalid_data",False) is not True and
                b.get("action_boundary",False) is not True)
    except (KeyError,TypeError,ValueError):return False


def _limit_fill(price_cap:float,b:dict)->dict:
    """Auction fill if open <= cap; otherwise one-tick trade-through proxy.

    A mere low==limit is not verified fill due to queue ordering.
    Trading through a resting limit is a model fill, NOT broker proof.
    """
    if float(b["open"])<=price_cap:
        return dict(price=float(b["open"]),when="AT_OPEN",one_tick_trade_through=True)
    if (float(b["high"])>=price_cap and
        float(b["low"])<=price_cap-_tick(price_cap)):
        return dict(price=float(price_cap),when="INTRADAY_LIMIT_ASSUMED",one_tick_trade_through=True)
    return {}


def entry(plan:dict,bar:dict|None,method:str)->dict:
    """One-session result; prices and stop are frozen at prior close.

    Methods:
      LEGACY_GAP_VETO   historical algorithm (not pre-open executable veto)
      RESTING_ONE       one pre-open resting limit at plan['high']
      RESTING_TWO       TWO independently resting limits at high and low
      POST_OPEN_REVIEW  cannot prove auction/1min recovery from daily OHLCV

    RESTING_ methods faithfully expose mechanical fills at opens BELOW stop.
    Risk guards cannot retroactively cancel a resting auction order.
    """
    if method not in ("LEGACY_GAP_VETO","RESTING_ONE","RESTING_TWO","POST_OPEN_REVIEW"):
        raise ValueError("UNKNOWN_RESEARCH_ENTRY_VARIANT")
    if bar is None:return dict(status="NEXT_SESSION_MISSING",method=method,filled=False)
    if not _bar_ok(bar):return dict(status="INVALID_OR_UNTRADABLE_BAR",method=method,filled=False)
    hi,lo,stop=(float(plan[k]) for k in ("high","low","stop"))
    if not 0<stop<lo<=hi:raise ValueError("FROZEN_ENTRY_GEOMETRY_INVALID")
    if method=="POST_OPEN_REVIEW":
        return dict(status="INTRADAY_SEQUENCE_UNOBSERVED",method=method,filled=False,
                    requires_intraday_opening_confirmation=True)
    if method=="LEGACY_GAP_VETO":
        from c3_daily_top2_v4 import next_day_entry
        old=next_day_entry(plan,[bar],[plan["decision_date"],bar["date"]])
        if old["status"]!="MODEL_ENTRY":
            return dict(status=old["status"],method=method,filled=False,
                        original_status=old["status"])
        fills=[dict(price=float(old["price"]),when="AT_OPEN" if old["at_open"] else "INTRADAY_LIMIT_ASSUMED",
                    one_tick_trade_through=True)]
        allocation=1.0
    else:
        caps=[hi] if method=="RESTING_ONE" else [hi,lo]
        fills=[item for cap in caps if (item:=_limit_fill(cap,bar))]
        if not fills:return dict(status="DAY_EXPIRED_NO_FILL",method=method,filled=False)
        allocation=len(fills)/len(caps)
    prices=[f["price"] for f in fills]
    # Equal nominal budget per order: portfolio effective cost is harmonic mean.
    effective_entry=len(prices)/sum(1.0/p for p in prices)
    gap_below_stop=float(bar["open"])<=stop
    stopped_intraday=float(bar["low"])<=stop
    output=dict(
        status=("FILLED_BELOW_STOP_RISK" if gap_below_stop else
                "MODEL_ENTRY_RESEARCH_ONLY"),
        method=method,filled=True,fill_count=len(prices),
        allocations_filled=allocation,
        price=effective_entry,individual_fills=fills,
        open_below_plan_low=float(bar["open"])<lo,
        open_at_or_below_stop=gap_below_stop,
        same_day_low_touched_stop=stopped_intraday,
        actual_broker_fill_verified=False,
        model_only_no_order_routing=True)
    return output


def exit_model(plan:dict,entry_day:str,entry_result:dict,
               by_date:dict,sessions:list[str],horizon:int,
               include_unsafe_mechanical:bool=False)->dict:
    """Exit on next open after first *close* below frozen stop or time limit.

    No same-candle intraday stop/target ordering assumed; no trailing or
    look-ahead to future bars. The observation is censored if any bar missing.
    """
    if horizon not in (5,10,20):raise ValueError("UNREGISTERED_HORIZON")
    if not entry_result.get("filled"):
        return dict(status="NO_ENTRY",net_pct=None)
    if entry_result.get("open_at_or_below_stop") and not include_unsafe_mechanical:
        return dict(status="UNSAFE_AT_OPEN_NO_APPROVED_TRADE",net_pct=None)
    idx=sessions.index(entry_day)
    fill_price=float(entry_result["price"])
    stop=float(plan["stop"])
    # Use the same horizon-then-following-open definition as the v4 engine.
    pending=None
    mfe=None;mae=None
    for i in range(idx,len(sessions)):
        d=sessions[i];b=by_date.get(d)
        if b is None or not _bar_ok(b):
            return dict(status="CENSORED_MISSING_OR_INVALID_BAR",net_pct=None)
        mfe=max(mfe or -float("inf"),(float(b["high"])/fill_price-1)*100)
        mae=min(mae or float("inf"),(float(b["low"])/fill_price-1)*100)
        if pending is not None:
            exit_price=float(b["open"])
            net=100*(exit_price*(1-SELL_COST)*(1-SLIPPAGE_EACH_SIDE)/
                     (fill_price*(1+BUY_COST)*(1+SLIPPAGE_EACH_SIDE))-1)
            return dict(status="COMPLETE",entry_date=entry_day,exit_date=d,
                        exit_reason=pending,exit_open=exit_price,
                        net_pct=round(net,6),
                        opportunity_cash_adjusted_pct=round(net*entry_result["allocations_filled"],6),
                        mfe_pct=round(mfe,5),mae_pct=round(mae,5),
                        same_session_ordering_unknown=entry_result.get("same_day_low_touched_stop",False),
                        unsafe_unconditional_preopen_fill=entry_result.get("open_at_or_below_stop",False))
        if float(b["close"])<stop:pending="CLOSE_BELOW_FROZEN_STOP_NEXT_OPEN"
        if i-idx>=horizon and pending is None:pending="HORIZON_NEXT_OPEN"
    return dict(status="WINDOW_NOT_MATURED",net_pct=None,
                pending=pending,mfe_pct=mfe,mae_pct=mae)


def direct_case(plan:dict,bar:dict,methods=None)->dict:
    """No backfilling a pre-open publication time from a later report."""
    methods=methods or ("LEGACY_GAP_VETO","RESTING_ONE","RESTING_TWO","POST_OPEN_REVIEW")
    results={m:entry(plan,bar,m) for m in methods}
    return dict(ticker=plan["ticker"],signal_session=plan["decision_date"],
                next_session=bar["date"],reference_close=plan["reference_close"],
                frozen_plan={k:plan.get(k) for k in ("low","high","stop","resistance","resistance2")},
                observed_bar={k:bar[k] for k in ("date","open","high","low","close")},
                variants=results)


def stats(outcomes:list[dict])->dict:
    good=[x["net_pct"] for x in outcomes if x["status"]=="COMPLETE"]
    o=[x["opportunity_cash_adjusted_pct"] for x in outcomes if x["status"]=="COMPLETE"]
    stop_count=sum(x.get("exit_reason","").startswith("CLOSE_BELOW_") for x in outcomes)
    return dict(n=len(outcomes),complete=len(good),mean_net_pct=round(mean(good),5) if good else None,
                mean_cash_adjusted_pct=round(mean(o),5) if o else None,
                win_rate_pct=round(100*sum(v>0 for v in good)/len(good),3) if good else None,
                stop_exit_count=stop_count,
                missing_or_unmatured=len(outcomes)-len(good),
                no_success_claim_if_n_small=True)
