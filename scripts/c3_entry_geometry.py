"""Executable support zones. An empty intersection is not a buy range."""
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import math


def tick(price):
    return (1 if price < 2000 else 5 if price < 5000 else 10 if price < 20000
            else 50 if price < 50000 else 100 if price < 200000
            else 500 if price < 500000 else 1000)


def executable(price, direction):
    if price is None:
        return None
    if not math.isfinite(price) or price <= 0 or direction not in ('up', 'down'):
        raise ValueError('INVALID_EXECUTABLE_PRICE')
    value = Decimal(str(price))
    unit = tick(price)
    mode = ROUND_CEILING if direction == 'up' else ROUND_FLOOR
    while True:
        rounded = int((value / unit).to_integral_value(rounding=mode)) * unit
        if tick(rounded) == unit:
            return rounded
        unit = tick(rounded)


def entry_zone(support, ma20, atr):
    """Preserve the existing pivot/ATR formula and directional tick rounding.

    A pivot above MA20 + .25 ATR conflicts with the existing entry ceiling.
    Preserve attempted bounds as evidence, but publish no executable zone.
    Do not swap prices, choose another pivot, expand the cap or raise the stop.
    """
    lo = max(support, ma20 - .5 * atr) if support is not None else None
    hi = min(ma20 + .25 * atr, lo + .6 * atr) if lo is not None else None
    stop = support - .5 * atr if support is not None else None
    rounded_lo, rounded_hi = executable(lo, 'up'), executable(hi, 'down')
    reason = ('NO_NEARBY_CONFIRMED_SUPPORT' if support is None else
              'EMPTY_ENTRY_INTERSECTION' if lo >= hi else
              'NO_EXECUTABLE_TICK_INTERVAL' if rounded_lo >= rounded_hi else None)
    return dict(entry_low=rounded_lo if reason is None else None,
                entry_high=rounded_hi if reason is None else None,
                structural_stop=executable(stop, 'up'), raw_low=lo, raw_high=hi,
                raw_stop=stop, attempted_low=rounded_lo, attempted_high=rounded_hi,
                rejection_reason=reason)


def sanitize_archived_geometry(candidate):
    """Apply the same no-inversion contract to an immutable older KRX archive.

    No price or signal is recalculated from rounded archived indicators.
    """
    row = dict(candidate)
    lo, hi = row.get('entry_low'), row.get('entry_high')
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo >= hi:
        row.update(attempted_entry_low=lo, attempted_entry_high=hi,
                   attempted_risk_pct=row.get('risk_pct'), entry_low=None,
                   entry_high=None, risk_pct=None, geometry_validated=False,
                   entry_ready=False, entry_status='WATCH', status='PASS_RISK_GEOMETRY')
        row['rejection_reasons'] = list(dict.fromkeys(row.get('rejection_reasons', []) +
            ['INVALID_ENTRY_ZONE', 'EMPTY_ENTRY_INTERSECTION']))
    return row
