"""C3 v6.58 research-only price cushion diagnostic (NO broker orders).

Standalone GitHub guard; full 264-signal / 1,584 additional case replay and
34 local tests are supplied in the separately reproducible user ZIP.
Do NOT treat a daily low touch as an actual Kiwoom fill.
"""
from dataclasses import dataclass
from datetime import date
from math import isfinite, floor

def cash_equity_grid_2023(price: float)->int:
    if not isfinite(price) or price<=0:raise ValueError("BAD_PRICE")
    return (1 if price<2000 else 5 if price<5000 else
            10 if price<20000 else 50 if price<50000 else
            100 if price<200000 else 500 if price<500000 else 1000)

def floor_cash_tick(price:float)->int:
    return int(floor(price/cash_equity_grid_2023(price))*cash_equity_grid_2023(price))

@dataclass(frozen=True)
class FrozenD:
    ticker:str
    signal_date:str
    close:float
    atr14:float
    original_daily_structure_stop:float
    first_recorded_overhead:float|None
    overhead_proven_date:str|None

def preopen_research_caps(x:FrozenD):
    if not(len(x.ticker)==6 and x.ticker.isdigit()):raise ValueError("BAD_TICKER")
    d=date.fromisoformat(x.signal_date)
    if d.isoformat()!=x.signal_date:raise ValueError("BAD_DATE")
    if not all(isfinite(t) and t>0 for t in
               (x.close,x.atr14,x.original_daily_structure_stop)):
        raise ValueError("BAD_D_PRICE")
    if x.close<=x.original_daily_structure_stop:raise ValueError("BAD_D_STOP")
    t=x.first_recorded_overhead
    if t is not None:
        if (not isfinite(t) or t<=x.close or x.overhead_proven_date is None
            or date.fromisoformat(x.overhead_proven_date)>d):
            raise ValueError("NO_D_KNOWN_OVERHEAD")
    bids={}
    for name,mult in (("D_CLOSE",0),("CAP10",.10),("CAP25",.25),("CAP50",.50)):
        cap=floor_cash_tick(x.close+mult*x.atr14)
        bids[name]=cap if cap>x.original_daily_structure_stop and (t is None or cap<t) else None
    return {"ticker":x.ticker,"D":x.signal_date,"original_stop_unchanged":x.original_daily_structure_stop,
        "first_recorded_overhead":t,"overhead_known":t is not None,
        "cap_limit_research_only":bids,
        "second_target":None,"company_catalyst_verified":False,
        "market_KRX_only_verified":False,"broker_fills":0,
        "orders_enabled":False,"live_buy_approved":False}
