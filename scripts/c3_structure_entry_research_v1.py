"""Research-only daily structural entry geometry. No orders, alerts or holder-stop changes."""
from dataclasses import dataclass
from datetime import date, datetime

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
    support_confirmed: bool = False
    first_resistance_verified: bool = False
    source_family: str = ""
    right_bar_dates: tuple = ()
    entry_mode: str = "RETEST"

def evaluate(e: EntryEvidence, *, buy_cost=0.0015, sell_cost=0.005,
             min_net_r=2.0, tick=None, max_atr_distance=1.0):
    """No fabricated entry: conservative lower tick rounding for stop, upward for entry.
    Price bands are RESEARCH ONLY and require post-registration support confirmation.
    """
    import math
    try:
        p = date.fromisoformat(e.price_date)
        s = date.fromisoformat(e.support_date)
        r = datetime.fromisoformat(e.registered_at)
        if r.tzinfo is None or r.utcoffset() is None or s > p or p > r.date():
            return {"state": "INVALID_DATE_OR_REGISTRATION", "range": None}
    except (TypeError, ValueError):
        return {"state": "INVALID_DATE_OR_REGISTRATION", "range": None}
    if tick is None or not math.isfinite(tick) or tick <= 0:
        return {"state": "WAIT_VERIFIED_TICK", "range": None}
    if not all(math.isfinite(x) and x > 0 for x in
               (e.support_low, e.atr14, e.first_resistance, e.close)):
        return {"state": "DATA_INVALID", "range": None}
    if e.right_completed_bars < 2 or not e.support_confirmed:
        return {"state": "WAIT_SUPPORT_CONFIRMATION", "range": None}
    if e.entry_mode not in ("RETEST", "CONFIRMED_RECOVERY"):
        return {"state": "INVALID_ENTRY_MODE", "range": None}
    if e.right_bar_dates:
        try:
            bars = [date.fromisoformat(x) for x in e.right_bar_dates]
            if len(bars) < 2 or bars != sorted(set(bars)) or bars[0] <= s or bars[-1] > p:
                return {"state": "INVALID_RIGHT_BAR_DATES", "range": None}
        except (TypeError, ValueError):
            return {"state": "INVALID_RIGHT_BAR_DATES", "range": None}
    if not e.first_resistance_verified or not e.source_family:
        return {"state": "WAIT_SOURCE_OR_RESISTANCE_EVIDENCE", "range": None}
    stop = math.floor((e.support_low - 0.1 * e.atr14) / tick) * tick
    if stop <= 0:
        return {"state": "DATA_INVALID", "range": None}
    if e.close < stop:
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
    # A retest limit may be below the close; it is not a retrospective fill.
    floor = max(e.support_low, stop + tick)
    if e.entry_mode == "CONFIRMED_RECOVERY":
        floor = max(floor, e.close)
    lower = math.ceil(floor / tick) * tick
    if lower > upper:
        return {"state": "NO_COSTED_2R_RANGE", "range": None, "stop": stop,
                "first_resistance": e.first_resistance}
    result = {"state": "RESEARCH_CONDITIONAL" if e.source_regular_certified else "WAIT_SOURCE_CERTIFICATION",
              "range": [lower, upper], "stop": stop,
              "first_resistance": e.first_resistance,
              "price_date": e.price_date, "registered_at": e.registered_at,
              "support_date": e.support_date, "source_regular_certified": e.source_regular_certified, "buy_approved": False, "source_family": e.source_family, "entry_mode": e.entry_mode}
    return result


def audit_next_open(plan, *, next_session_date=None, next_open=None):
    """Open-only prospective observation, not a broker fill."""
    import math
    if plan.get("range") is None:
        return {"event": "NO_VALID_RANGE", "fill": False}
    if next_session_date is None or next_open is None:
        return {"event": "NEXT_OPEN_MISSING", "fill": False}
    try:
        d = date.fromisoformat(next_session_date)
        r = datetime.fromisoformat(plan["registered_at"]).date()
        if d <= r or not math.isfinite(next_open) or next_open <= 0:
            return {"event": "INVALID_FORWARD_OBSERVATION", "fill": False}
    except (TypeError, ValueError, KeyError):
        return {"event": "INVALID_FORWARD_OBSERVATION", "fill": False}
    lo, hi = plan["range"]
    event = "OPEN_IN_RANGE" if lo <= next_open <= hi else ("OPEN_ABOVE_RANGE" if next_open > hi else "OPEN_BELOW_RANGE")
    return {"event": event, "fill": False}
