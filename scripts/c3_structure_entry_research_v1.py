"""Research-only daily structural entry geometry. No orders, alerts or holder-stop changes."""
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class EntryEvidence:
    price_date: str
    registered_at: str
    support_date: str
    support_low: float
    atr14: float
    first_resistance: float
    close: float
    right_completed_bars: int
    source_regular_certified: bool = False

def evaluate(e: EntryEvidence, *, buy_cost=0.0015, sell_cost=0.005,
             min_net_r=2.0, tick=100, max_atr_distance=1.0):
    """No fabricated entry: conservative lower tick rounding for stop, upward for entry.
    Price bands are RESEARCH ONLY and require post-registration support confirmation.
    """
    import math
    if not all(math.isfinite(x) and x > 0 for x in
               (e.support_low, e.atr14, e.first_resistance, e.close)):
        return {"state": "DATA_INVALID", "range": None}
    if e.right_completed_bars < 2:
        return {"state": "WAIT_RIGHT_BARS", "range": None}
    stop = math.floor((e.support_low - 0.1 * e.atr14) / tick) * tick
    if stop <= 0:
        return {"state": "DATA_INVALID", "range": None}
    if e.close <= stop:
        return {"state": "CANCEL_CLOSE_BELOW_STOP", "range": None, "stop": stop}
    if e.close >= e.first_resistance:
        return {"state": "WAIT_FIRST_RESISTANCE_RECLAIM", "range": None, "stop": stop}
    # Require evidence of support proximity; do not invent a higher support.
    if e.close - e.support_low > max_atr_distance * e.atr14:
        return {"state": "WAIT_NEW_SUPPORT", "range": None, "stop": stop}
    # Cost-adjusted 2R against the nearest obstacle, not a farther target.
    # Reward = target*(1-sell_cost)-entry*(1+buy_cost)
    # Risk = entry*(1+buy_cost)-stop*(1-sell_cost)
    # Reward >= min_net_r * Risk.
    cap = ((e.first_resistance * (1-sell_cost)) +
           min_net_r * stop * (1-sell_cost)) / ((min_net_r+1)*(1+buy_cost))
    upper = math.floor(min(cap, e.first_resistance - tick) / tick) * tick
    lower = math.ceil(max(e.support_low, stop + tick) / tick) * tick
    if lower > upper:
        return {"state": "NO_COSTED_2R_RANGE", "range": None, "stop": stop,
                "first_resistance": e.first_resistance}
    result = {"state": "RESEARCH_CONDITIONAL" if e.source_regular_certified else "WAIT_SOURCE_CERTIFICATION",
              "range": [lower, upper], "stop": stop,
              "first_resistance": e.first_resistance,
              "price_date": e.price_date, "registered_at": e.registered_at,
              "support_date": e.support_date, "source_regular_certified": e.source_regular_certified}
    return result
