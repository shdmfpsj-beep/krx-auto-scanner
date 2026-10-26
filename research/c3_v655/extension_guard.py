"""C3 v6.55 frozen read-only D+5 extension evidence guard.

This compact GitHub version only enforces the timing/safety of D5 decisions.
Full 264-signal empirical replay with 28 passed tests is supplied separately
as the portable ChatGPT C3_v655 research ZIP. NEVER send orders.
"""
from dataclasses import dataclass
from datetime import date
from math import isfinite

SCHEMA="C3_V655_D5_EXTENSION_RESEARCH_ONLY"
CLOSED_BEFORE_D5={"STOP_PRICE_PROXY","TARGET_TOUCH_PROXY"}

@dataclass(frozen=True)
class CompletedD5:
    ticker:str
    signal_day:str
    decision_day:str
    five_day_status:str
    observed_net_return_5d_pct:float
    completed_D5_close:float
    completed_D5_MA20:float

def research_extension_decision(s:CompletedD5):
    if len(s.ticker)!=6 or not s.ticker.isdigit():raise ValueError("BAD_TICKER")
    d0=date.fromisoformat(s.signal_day)
    d5=date.fromisoformat(s.decision_day)
    if d5<=d0:raise ValueError("MUST_USE_LATER_COMPLETED_D5")
    values=(s.observed_net_return_5d_pct,s.completed_D5_close,s.completed_D5_MA20)
    if not all(isfinite(v) for v in values) or values[1]<=0 or values[2]<=0:
        raise ValueError("MISSING_COMPLETE_D5_BAR")
    if s.five_day_status not in (CLOSED_BEFORE_D5|{"TIME_CLOSE_PROXY"}):
        raise ValueError("BAD_EXIT_STATUS")
    can_still_decide=s.five_day_status=="TIME_CLOSE_PROXY"
    profit_only=can_still_decide and s.observed_net_return_5d_pct>0
    profit_and_ma20=profit_only and s.completed_D5_close>s.completed_D5_MA20
    return {"schema":SCHEMA,"ticker":s.ticker,"decision_day":s.decision_day,
        "eligible_D5_survivor":can_still_decide,
        "hypothesis_profit_extension12":bool(profit_only),
        "hypothesis_profit_and_MA20_extension12":bool(profit_and_ma20),
        "actual_live_strategy_rule_approved":False,
        "source_venue_KRX_regular_only_certified":False,
        "actual_broker_fill_verified":False,
        "independent_future_study_success":False,
        "orders_enabled":False,"trade_approved":False}
