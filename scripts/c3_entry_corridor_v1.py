"""Research-only C3 entry corridors: stop first, first resistance next, no 3% leash.

This module accepts independently confirmed daily-bar geometry only. It does
not establish regular-session price provenance, brokerage fills or BUY authority.
"""
import math
from practical_entry_quotes_v619 import krx_round, tick

SCHEMA = 'C3_ENTRY_CORRIDOR_V1_RESEARCH_ONLY'
ROUND_TRIP_COST = .0065


def _positive(*values):
    return all(isinstance(x, (int, float)) and not isinstance(x, bool)
               and math.isfinite(x) and x > 0 for x in values)


def _net_r(entry, stop, first_resistance):
    return (first_resistance - entry * (1 + ROUND_TRIP_COST)) / (
        entry - stop + entry * ROUND_TRIP_COST)


def build_corridors(*, asof, close, atr14, confirmed_support,
                    structural_stop, verified_first_resistance,
                    support_confirmed_at, resistance_source,
                    regular_only_certified=False):
    """Create two *alternative* watch corridors from completed daily-bar evidence.

    Do not add together the modes. Continuation needs a future completed
    confirmation and next-session recheck. No synthetic fill is asserted.
    """
    base = dict(schema=SCHEMA, asof=asof, status='NO_CORRIDOR', corridors=[],
                buy_approved=False, orders_enabled=False,
                regular_only_certified=bool(regular_only_certified),
                alternative_modes_not_split_orders=True)
    if not _positive(close, atr14, confirmed_support, structural_stop,
                     verified_first_resistance):
        return dict(base, reason='MISSING_FINITE_POSITIVE_PRICE_EVIDENCE')
    if not support_confirmed_at or support_confirmed_at > asof or not resistance_source:
        return dict(base, reason='UNCONFIRMED_SUPPORT_OR_RESISTANCE_PROVENANCE')
    if not (structural_stop < confirmed_support <= close < verified_first_resistance):
        return dict(base, reason='INVALID_STOP_SUPPORT_OVERHEAD_ORDER')
    if atr14 / close > .12:
        return dict(base, reason='VOLATILITY_OVER_12PCT_PRICE_REVIEW')
    stop = krx_round(structural_stop, 'down')
    overhead = krx_round(verified_first_resistance, 'down')
    if overhead <= close or stop >= confirmed_support:
        return dict(base, reason='GRID_REMOVED_FIRST_RESISTANCE_OR_STOP')

    # 2R net of 0.65% modeled round-trip friction:
    # (overhead-entry-cost)/(entry-stop+cost) >= 2
    # -> entry <= (overhead+2*stop)/(3*(1+cost_fraction)).
    max_entry_2r = (overhead + 2 * stop) / (3 * (1 + ROUND_TRIP_COST))
    risk_caps = [('PRIMARY_UP_TO_5PCT', stop / .95, .05),
                 ('FLEX_UP_TO_8PCT', stop / .92, .08)]
    modes = [('SUPPORT_RETEST', confirmed_support - .25 * atr14,
              confirmed_support + .60 * atr14, 'NEXT_SESSION_LIMIT_TOUCH_NOT_FILL'),
             ('STRENGTH_CONFIRMATION', max(close - .20 * atr14,
                                           confirmed_support + .30 * atr14),
              close + .30 * atr14, 'FUTURE_CONFIRMED_CLOSE_AND_NEXT_SESSION_ONLY')]
    rows = []
    for mode, lo, hi, trigger in modes:
        for tier, max_by_risk, max_risk in risk_caps:
            floor = max(lo, stop + tick(stop))
            cap = min(hi, max_entry_2r, max_by_risk,
                      close if mode == 'SUPPORT_RETEST' else close + .30 * atr14,
                      overhead - tick(overhead))
            if floor > cap:
                continue
            low = krx_round(floor, 'up')
            high = krx_round(cap, 'down')
            if low > high or low <= stop or high >= overhead:
                continue
            risk = (high - stop) / high
            reward = _net_r(high, stop, overhead)
            if risk > max_risk + 1e-10 or reward < 2 - 1e-10:
                continue
            # The flexible tier only extends quotes not offered by primary.
            if tier == 'FLEX_UP_TO_8PCT' and any(
                x['mode'] == mode and x['high_krw'] >= high for x in rows):
                continue
            if tier == 'FLEX_UP_TO_8PCT':
                earlier = [x for x in rows if x['mode'] == mode]
                if earlier:
                    low = max(low, krx_round(
                        earlier[-1]['high_krw'] + tick(earlier[-1]['high_krw']), 'up'))
                    if low > high:
                        continue
            rows.append(dict(
                mode=mode, tier=tier, low_krw=low, high_krw=high,
                stop_krw=stop, first_resistance_krw=overhead,
                risk_at_high_pct=round(100 * risk, 2),
                first_resistance_net_r_at_high=round(reward, 3),
                support_confirmed_at=support_confirmed_at,
                resistance_source=resistance_source, trigger=trigger,
                actual_fill_confirmed=False, buy_approved=False))
    if not rows:
        return dict(base, reason='NO_PRICE_ZONE_WITH_2R_AND_8PCT_RISK')
    return dict(
        base, status='WATCH_CORRIDORS_RESEARCH_ONLY',
        reason=('REGULAR_SESSION_UNVERIFIED' if not regular_only_certified
                else 'REQUIRES_CURRENT_RECONFIRMATION_AND_INSTRUMENT_GATE'),
        structural_stop_krw=stop, overhead_krw=overhead, corridors=rows)
