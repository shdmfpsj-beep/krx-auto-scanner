"""C3 v6.54 read-only D-day stock trend and price-headroom gates.

Selection considers completed D features, not future trade returns or account capital.
Historical market breadth is archived-price-universe proxy, NOT official KRX.
"""
from dataclasses import dataclass
from datetime import date
from math import isfinite

@dataclass(frozen=True)
class SignalD:
    ticker: str
    asof: str
    d_close: float
    d_stop: float
    ret5: float
    breadth20: float
    recorded_resistance: float | None = None

def historical_research_gate(d:SignalD):
    if len(d.ticker)!=6 or not d.ticker.isdigit():raise ValueError("INVALID_TICKER")
    if date.fromisoformat(d.asof).isoformat()!=d.asof:raise ValueError("INVALID_D")
    if not all(isfinite(x) for x in [d.d_close,d.d_stop,d.ret5,d.breadth20]):
        raise ValueError("INVALID_SIGNAL")
    if d.d_close<=d.d_stop or d.d_stop<=0 or not(0<=d.breadth20<=1):
        raise ValueError("STRUCTURE_OR_BREADTH_BROKEN")
    eligible=d.breadth20>=.5 and d.ret5>0
    rr=None
    if d.recorded_resistance is not None:
        t=d.recorded_resistance
        if not isfinite(t) or t<=0:raise ValueError("BAD_OVERHEAD")
        risk=d.d_close*1.0015-d.d_stop*.995
        upside=t*.995-d.d_close*1.0015
        rr=round(upside/risk,6)
    return {"ticker":d.ticker,"D":d.asof,"research_strong_market_stock":eligible,
            "original_D_chart_stop":d.d_stop,
            "recorded_overhead_R":rr,
            "overhead_verified_R2":bool(rr is not None and rr>=2),
            "complete_original_KRX_regular_price_verified":False,
            "contemporaneous_issuer_and_sector_verified":False,
            "stock_buy_approved":False,"orders_enabled":False}
