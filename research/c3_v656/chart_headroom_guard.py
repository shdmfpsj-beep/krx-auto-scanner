"""C3 v6.56: price-headroom and forward-event timing guard, research ONLY.

Full local 264-signal and 192-stock replay with 52 tests is in the user ZIP.
No broker APIs, no account cash or share quantities, no live authorizations.
"""
from dataclasses import dataclass
from datetime import date
from math import isfinite

@dataclass(frozen=True)
class KnownDChart:
    ticker:str
    date_d:str
    price_d:float
    structural_stop_d:float
    actual_recorded_first_resistance_d:float|None

def headroom(d:KnownDChart):
    if not (len(d.ticker)==6 and d.ticker.isdigit()):
        raise ValueError("BAD_TICKER")
    if date.fromisoformat(d.date_d).isoformat()!=d.date_d:
        raise ValueError("BAD_DATE")
    e,s=d.price_d,d.structural_stop_d
    if not (isfinite(e) and isfinite(s) and s>0 and e>s):
        raise ValueError("BAD_DAILY_STRUCTURE")
    t=d.actual_recorded_first_resistance_d
    if t is None:
        return dict(status="OVERHEAD_MISSING_NOT_ZERO_UPSIDE",
           recorded_hurdle_R=None,arithmetic_2R_entry_ceiling=None,
           is_current_Buy=False,orders_enabled=False,actual_broker_fills=0)
    if not(isfinite(t) and t>e):
        raise ValueError("RECORDED_HURDLE_NEEDS_DATE_AND_ABOVE_D_PRICE")
    risk=e*1.0015-s*.995
    reward=t*.995-e*1.0015
    r=reward/risk
    cap=(t+2*s)*.995/(3*1.0015)
    return dict(status="R2_ONLY_HISTORICAL_PRICE_GEOMETRY",
        recorded_hurdle_R=r,arithmetic_2R_entry_ceiling=cap,
        ceiling_is_verified_support=False,
        next_overhead_above_first_known=False,
        is_current_Buy=False,orders_enabled=False,actual_broker_fills=0)

def prospective_retest_timing(original_d,breakout_completed_date,retest_completed_date,
                              future_open_date):
    """No same-bar buy: breakout D+n close known, then later retest close known,
    THEN the earliest possible next-session open quote proxy. Never infer fill.
    """
    a,b,c,d=map(date.fromisoformat,(original_d,breakout_completed_date,
                                       retest_completed_date,future_open_date))
    if not (a<b<c<d):
        raise ValueError("LOOKAHEAD_OR_SAME_BAR_ENTRY")
    return dict(event_confirmed_on=c.isoformat(),
        earliest_research_next_open=d.isoformat(),
        broker_fill_verified=False,profitability_established=False,
        original_D_may_know_this_event=False,trade_approved=False,orders_enabled=False)
