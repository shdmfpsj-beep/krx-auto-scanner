"""Research-only staged-entry simulator: first open, second support-limit order.

Conservative daily-OHLC assumptions. First entry is next open. Second entry
limit must be strictly above structural stop and below first entry. On an
opening gap below the limit, fill at open unless already below stop, in which
case exit without adding. Intraday same-bar ordering of second fill and stop
is unknown: mark AMBIGUOUS and exclude from performance statistics.
"""
from kiwoom_execution_audit import setup,pivot_stop

SPLITS={"A_100_0":(1.0,0.0),"B_60_40":(.6,.4),
        "C_50_50":(.5,.5),"D_70_30":(.7,.3)}

def simulate(bars,i,split=(.6,.4),horizon=5,cost_bps=30,
             second_limit=None,risk_budget_fraction=.05):
    if i+horizon>=len(bars):return {"status":"NO_FULL_HORIZON"}
    name=setup(bars,i)
    stop=pivot_stop(bars,i)
    if not name or stop is None:return {"status":"NO_SETUP_OR_STOP"}
    entry=float(bars[i+1]["open"])
    if entry<=stop:return {"status":"ENTRY_BELOW_STOP"}
    risk=(entry-stop)/entry
    if not .02<=risk<=.12:return {"status":"RISK_OUTSIDE_2_TO_12_PCT"}
    first_weight,second_weight=split
    if abs(first_weight+second_weight-1)>1e-9 or min(split)<0:
        raise ValueError("INVALID_SPLIT")
    if second_weight and (second_limit is None or not stop<second_limit<entry):
        return {"status":"NO_VALID_SECOND_SUPPORT"}
    # Account-level capital is normalized to 1. The risk budget is a fraction
    # of capital, not a percentage of position value.
    max_fraction=min(1.,risk_budget_fraction/(
        first_weight*risk+second_weight*(second_limit-stop)/second_limit
        if second_weight else risk))
    capital_first=first_weight*max_fraction
    capital_second=second_weight*max_fraction
    qty1=capital_first/entry
    qty2=0.
    second_filled=False
    status="TIME_EXIT"
    exit_price=float(bars[i+horizon]["close"])
    for k in range(i+1,i+horizon+1):
        b=bars[k]
        op,lo,hi=[float(b[x]) for x in ("open","low","high")]
        if op<=stop:
            status="STOP_GAP_OPEN";exit_price=op;break
        if second_weight and not second_filled and op<=second_limit:
            qty2=capital_second/op
            second_filled=True
        elif second_weight and not second_filled and lo<=second_limit:
            if lo<=stop:
                return {"status":"AMBIGUOUS_SECOND_AND_STOP","setup":name}
            qty2=capital_second/second_limit
            second_filled=True
        invested=capital_first+(capital_second if second_filled else 0.)
        qty=qty1+qty2
        avg=invested/qty
        target=avg+2*(avg-stop)
        if op>=target:
            status="TARGET_GAP_OPEN";exit_price=target;break
        if lo<=stop and hi>=target:
            return {"status":"AMBIGUOUS_STOP_TARGET","setup":name}
        if lo<=stop:
            status="STOP_FIRST";exit_price=stop;break
        if hi>=target:
            status="TARGET_FIRST";exit_price=target;break
    invested=capital_first+(capital_second if second_filled else 0.)
    pnl=(qty1+qty2)*exit_price-invested
    net_capital_pct=round(100*(pnl-invested*cost_bps/10000),4)
    return {"setup":name,"status":status,"second_filled":second_filled,
            "invested_fraction":round(invested,6),
            "average_entry":round(invested/(qty1+qty2),4),
            "stop":stop,"exit":round(exit_price,4),
            "net_account_pct":net_capital_pct,"trade_approval":"NO"}
