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
                structural_stop=executable(stop, 'up') if stop is not None and stop>0 else None, raw_low=lo, raw_high=hi,
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


def audit_archived_zone(candidate, bars):
    """Recheck the unchanged zone formula against the archived real OHLCV.

    Diagnostic prices are not executable approval; 5% and other gates remain
    authoritative. Rounded published MA/ATR values are never calculation inputs.
    """
    from statistics import mean
    if len(bars)!=60:
        raise ValueError('SOURCE_GEOMETRY_REQUIRES_60_BARS')
    ma20 = mean(b['close'] for b in bars[-20:])
    tr = [max(bars[i]['high']-bars[i]['low'], abs(bars[i]['high']-bars[i-1]['close']),
              abs(bars[i]['low']-bars[i-1]['close'])) for i in range(1,len(bars))]
    atr = mean(tr[-14:])
    lows = [b['low'] for b in bars]
    pivots = [lows[i] for i in range(35,58) if all(lows[i]<lows[j] for j in (i-2,i-1,i+1,i+2))]
    nearby = [p for p in pivots if ma20-1.5*atr<=p<=ma20+.5*atr]
    support = max(nearby) if nearby else None
    if support!=candidate.get('pivot_support') or abs(atr-candidate.get('atr14',atr))>.011:
        raise ValueError('SOURCE_GEOMETRY_INDICATOR_MISMATCH')
    zone = entry_zone(support,ma20,atr)
    if candidate.get('geometry_validated') and (
        zone['entry_low']!=candidate.get('entry_low') or zone['entry_high']!=candidate.get('entry_high') or
        zone['structural_stop']!=candidate.get('stop_ref')):
        raise ValueError('SOURCE_VALID_GEOMETRY_CHANGED')
    high,stop = zone['entry_high'],zone['structural_stop']
    risk = (high-stop)/high*100 if high and stop is not None else None
    if risk is not None and candidate.get('risk_pct') is not None and abs(risk-candidate['risk_pct'])>.011:
        raise ValueError('SOURCE_GEOMETRY_RISK_MISMATCH')
    return dict(code=candidate['code'],ma5=mean(b['close'] for b in bars[-5:]),
                ma10=mean(b['close'] for b in bars[-10:]),ma20=ma20,ma60=mean(b['close'] for b in bars),
                atr14=atr,pivot_support=support,**zone,
                computed_risk_pct=risk,original_geometry_validated=candidate.get('geometry_validated'),
                selection_rules_changed=False)
