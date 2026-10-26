#!/usr/bin/env python3
"""C3 research: causal daily OHLC event replay, integer shares, no broker API.

All marks/fills are price proxies. No data attestation, investment approval or
independent out-of-sample profitability is implied by successful execution.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
import hashlib
import json
import math
from typing import Any

SCHEMA = 'C3_V637_CAUSAL_PAPER_ONLY'
ENTRIES = ('OPEN_CAPPED', 'RETEST_2D', 'CONFIRM_D2')
EXITS = ('STRUCT_D5', 'LEGACY_TRAIL7_D12', 'STRUCT_ATR_D12')
REGIMES = ('ALL', 'BENCH_TREND')


def iso_day(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError('INVALID_ISO_DATE')
    return value


def finite_positive(*values):
    return all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in values)


def tick(price):
    if not finite_positive(price):
        raise ValueError('BAD_PRICE')
    for top, step in ((2000, 1), (5000, 5), (20000, 10), (50000, 50),
                      (200000, 100), (500000, 500), (math.inf, 1000)):
        if price < top:
            return step


def floor_tick(price):
    p = math.floor(price / tick(price)) * tick(price)
    if p <= 0:
        raise ValueError('NONPOSITIVE_ROUNDED_PRICE')
    return int(p)


@dataclass(frozen=True)
class Costs:
    buy: float = .0015
    sell: float = .005

    def __post_init__(self):
        if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v < .03
               for v in (self.buy, self.sell)):
            raise ValueError('INVALID_COSTS')

    @property
    def label(self):
        return round((self.buy + self.sell) * 100, 4)


BASE_COST = Costs()
STRESS_COST = Costs(.003, .0065)


@dataclass(frozen=True)
class Policy:
    entry: str = 'OPEN_CAPPED'
    exit: str = 'STRUCT_ATR_D12'
    regime: str = 'ALL'
    initial_cash: float = 1_000_000.
    risk_fraction: float = .01
    gap_low: float = .98
    gap_high: float = 1.025
    retest_atr: float = .25
    confirm_cap: float = 1.015
    trail_atr: float = 2.
    limit_penetration_ticks: int = 1
    require_rr2: bool = False

    def __post_init__(self):
        if self.entry not in ENTRIES or self.exit not in EXITS or self.regime not in REGIMES:
            raise ValueError('UNDECLARED_POLICY')
        if not finite_positive(self.initial_cash, self.risk_fraction,
                               self.gap_low, self.gap_high, self.confirm_cap,
                               self.retest_atr, self.trail_atr):
            raise ValueError('INVALID_POLICY_NUMBER')
        if not 0 < self.risk_fraction <= .03 or not 0 < self.gap_low <= 1 <= self.gap_high:
            raise ValueError('INVALID_RISK_OR_GAP')
        if type(self.limit_penetration_ticks) is not int or self.limit_penetration_ticks < 1:
            raise ValueError('LIMIT_MUST_TRADE_THROUGH_AT_LEAST_ONE_TICK')

    def digest(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


def share_qty(equity, cash, cap, stop, costs=BASE_COST, risk_fraction=.01):
    """Quantity fixed using the submitted cap, including cash fees, before fill."""
    if not finite_positive(equity, cash, cap, stop, risk_fraction):
        return 0
    if not 0 < stop < cap or risk_fraction > .03:
        return 0
    debit = cap * (1 + costs.buy)
    damage = debit - stop * (1 - costs.sell)
    return max(0, min(math.floor(cash / debit),
                      math.floor(equity * risk_fraction / damage)))


def net_rr(entry, stop, resistance, costs=BASE_COST):
    if not finite_positive(entry, stop, resistance) or not stop < entry < resistance:
        return None
    risk = entry * (1 + costs.buy) - stop * (1 - costs.sell)
    reward = resistance * (1 - costs.sell) - entry * (1 + costs.buy)
    return reward / risk


def maximum_entry_rr2(stop, resistance, costs=BASE_COST):
    if not finite_positive(stop, resistance) or stop >= resistance:
        return None
    return (resistance + 2 * stop) * (1 - costs.sell) / (3 * (1 + costs.buy))


def resistance_clusters(history, entry, atr, min_touches=2):
    """D-confirmed swing highs only: two right-hand candles must be complete.

    Adjacent peaks in one move count once. Unknown/open-sky resistance returns
    None, never an invented target. Price clusters are research annotations,
    not independent proof of a future executable target.
    """
    if not finite_positive(entry, atr) or len(history) < 7:
        return None
    pivots = []
    for i in range(2, len(history) - 2):
        h = history[i]['high']
        if h > max(b['high'] for b in history[i-2:i]) and h >= max(b['high'] for b in history[i+1:i+3]):
            pivots.append((i, history[i]['date'], h))
    groups = []
    tolerance = max(atr * .3, entry * .005)
    for idx, day, price in sorted(pivots, key=lambda x: x[2]):
        if not groups or price - groups[-1][0][2] > tolerance:
            groups.append([])
        if not groups[-1] or all(abs(idx - p[0]) >= 3 for p in groups[-1]):
            groups[-1].append((idx, day, price))
    valid = [g for g in groups if len(g) >= min_touches and min(p[2] for p in g) > entry]
    if not valid:
        return None
    g = min(valid, key=lambda x: min(p[2] for p in x))
    return {'price': min(p[2] for p in g), 'touches': len(g),
            'pivot_dates': [p[1] for p in g], 'confirmed_through': history[-1]['date']}


def confirmed_daily_stop(history, atr, max_age_sessions=20):
    """Most recent 2-left/2-right confirmed daily pivot; D-only evidence.

    A confirmed numerical pivot still needs contextual chart review before a
    live swing-stop decision. No pivot is fabricated when the history lacks one.
    """
    if not finite_positive(atr) or len(history)<5:
        return None
    found=[]
    for i in range(max(2,len(history)-max_age_sessions),len(history)-2):
        lo=history[i]['low']
        if lo<min(b['low'] for b in history[i-2:i]) and lo<=min(b['low'] for b in history[i+1:i+3]):
            found.append((i,lo))
    if not found:return None
    i,lo=found[-1];raw=lo-.15*atr
    if raw<=0 or raw>=history[-1]['close']:return None
    return dict(stop=floor_tick(raw),pivot_date=history[i]['date'],pivot_low=lo,
                confirmation_date=history[i+2]['date'],known_through=history[-1]['date'])


def _validate_bar(bar):
    iso_day(bar['date'])
    o, h, l, c = (bar[k] for k in ('open', 'high', 'low', 'close'))
    if not finite_positive(o, h, l, c) or not 0 < l <= min(o, c) <= max(o, c) <= h:
        raise ValueError('INVALID_OHLC')


def make_pending(signal, policy, costs, equity, cash, idx):
    if signal.get('requires_confirmed_pivot') is True and not signal.get('confirmed_pivot_evidence'):
        return None, 'NO_CONFIRMED_DAILY_PIVOT'
    close, stop, atr = (float(signal[k]) for k in ('signal_close', 'stopD', 'atr14'))
    if not finite_positive(close, stop, atr) or stop >= close:
        return None, 'BAD_D_GEOMETRY'
    stop = floor_tick(stop)
    cap = floor_tick(close * policy.gap_high if policy.entry != 'RETEST_2D'
                     else close - policy.retest_atr * atr)
    resistance = signal.get('resistance')
    if policy.require_rr2:
        rcap = maximum_entry_rr2(stop, resistance, costs)
        if rcap is None:
            return None, 'NO_DATED_RESISTANCE'
        cap = min(cap, floor_tick(rcap))
    if cap <= stop:
        return None, 'RR_OR_LIMIT_BELOW_STOP'
    qty = share_qty(equity, cash, cap, stop, costs, policy.risk_fraction)
    if qty < 1:
        return None, 'LESS_THAN_ONE_PRECOMMITTED_SHARE'
    return dict(signal=dict(signal), stop=stop, cap=cap, qty=qty,
                submitted_idx=idx, expires_idx=idx+(1 if policy.entry == 'OPEN_CAPPED' else 2),
                confirmed=False, order_decision_date=signal['asof']), None


def pending_step(pending, bar, idx, policy, costs, equity, cash):
    """Returns (fill, still_pending, reason). Called on one arriving bar only."""
    p = dict(pending)
    age = idx - p['submitted_idx']
    sig = p['signal']
    if age < 1:
        raise ValueError('SAME_DAY_ENTRY_FORBIDDEN')
    op = bar['open']
    closeD = sig['signal_close']
    if not policy.gap_low - 1e-12 <= op / closeD <= policy.gap_high + 1e-12:
        return None, None, 'GAP_CANCEL_NO_REPLACEMENT'
    if op <= p['stop']:
        return None, None, 'OPEN_THROUGH_STRUCTURE'
    if policy.entry == 'CONFIRM_D2' and age == 1:
        span = bar['high'] - bar['low']
        # Completion of D1 is required. This creates a D2 order, never D1 fill.
        ok = (bar['low'] > p['stop'] and bar['low'] <= closeD and span > 0
              and bar['close'] >= max(op, closeD)
              and (bar['close'] - bar['low']) / span >= .65)
        if not ok:
            return None, None, 'D1_RETEST_NOT_CONFIRMED'
        cap = floor_tick(min(bar['close'] * policy.confirm_cap, closeD * policy.gap_high))
        if policy.require_rr2:
            cap = min(cap, floor_tick(maximum_entry_rr2(p['stop'], sig['resistance'], costs)))
        p.update(cap=cap, qty=share_qty(equity, cash, cap, p['stop'], costs, policy.risk_fraction),
                 confirmed=True, order_decision_date=bar['date'])
        if p['qty'] < 1:
            return None, None, 'CONFIRMED_ORDER_ZERO_QTY'
        return None, p, 'D1_CONFIRMED_D2_ORDER'
    if policy.entry == 'CONFIRM_D2' and not p['confirmed']:
        raise ValueError('CONFIRM_WITHOUT_D1_CLOSE')
    if policy.entry in ('OPEN_CAPPED', 'CONFIRM_D2'):
        fill_price = op if op <= p['cap'] else None
    else:
        # A limit touched exactly once at the day's low is NOT a paper fill.
        # At open a resting order may receive a better price above structure.
        fill_price = min(op, p['cap']) if op <= p['cap'] else (
            p['cap'] if bar['low'] <= p['cap'] - policy.limit_penetration_ticks*tick(p['cap']) else None)
    if fill_price is not None:
        return dict(price=fill_price, qty=p['qty'], stop=p['stop'],
                    cap=p['cap'], order_decision_date=p['order_decision_date'],
                    signal=sig, entry_idx=idx, entry_date=bar['date']), None, 'PAPER_FILL_PROXY'
    if bar['low'] <= p['stop']:
        return None, None, 'SUPPORT_BROKEN_BEFORE_FILL'
    if idx >= p['expires_idx']:
        return None, None, 'EXPIRED_UNFILLED'
    return None, p, 'RESTING_UNFILLED'


def exit_step(position, bar, idx, policy):
    """Only previously available stop is active during this bar.

    The current high/ATR/close can update tomorrow's stop, never today's stop.
    Returns (exit_price, reason, next_position).
    """
    p = dict(position)
    age = idx - p['entry_idx'] + 1
    active_stop = p['active_stop']
    if bar['open'] <= active_stop:
        return bar['open'], 'STRUCT_OR_PRIOR_TRAIL_STOP', p
    if p.get('exit_next_open'):
        return bar['open'], 'WEAK_D5_EXIT_D6_OPEN', p
    if bar['low'] <= active_stop:
        return active_stop, 'STRUCT_OR_PRIOR_TRAIL_STOP', p
    maxdays = 5 if policy.exit == 'STRUCT_D5' else 12
    if age >= maxdays:
        return bar['close'], 'PREPLANNED_HORIZON_CLOSE_PROXY', p
    p['peak_high'] = max(p['peak_high'], bar['high'])
    p['peak_close'] = max(p['peak_close'], bar['close'])
    if policy.exit == 'LEGACY_TRAIL7_D12':
        p['active_stop'] = max(active_stop, floor_tick(p['peak_high'] * .93))
    elif policy.exit == 'STRUCT_ATR_D12':
        # Profit activation is close-confirmed, not an intrabar high touch.
        initial_r = p['price'] - p['stop']
        if bar['close'] >= p['price'] + initial_r:
            p['trail_active'] = True
        atr = bar.get('atr14')
        if p['trail_active'] and finite_positive(atr):
            p['active_stop'] = max(active_stop, floor_tick(p['peak_close'] - policy.trail_atr * atr))
        if age == 5 and bar.get('ma5') is not None:
            # Causal time stop: decide D5 close, execute only at D6 open.
            p['exit_next_open'] = bool(bar['close'] < p['price'] + initial_r
                                       and bar['close'] < bar['ma5'])
    return None, None, p


def replay(sessions, prices, signals, policy=Policy(), costs=BASE_COST):
    sessions = [iso_day(d) for d in sessions]
    if sessions != sorted(set(sessions)):
        raise ValueError('SESSIONS_NOT_STRICTLY_ORDERED')
    if not sessions:
        raise ValueError('EMPTY_SESSIONS')
    byday = {}
    for s in signals:
        day = iso_day(s['asof'])
        if day in byday:
            raise ValueError('MULTIPLE_PRESELECTED_TICKERS_SAME_DAY')
        if day not in sessions:
            raise ValueError('SIGNAL_NOT_IN_SESSIONS')
        byday[day] = dict(s)
    cash = float(policy.initial_cash)
    position = pending = None
    trades, events, daily = [], [], []
    last_exit = ''
    halted = False
    equity = cash
    for idx, day in enumerate(sessions):
        mark = None
        if not halted and (position is not None or pending is not None):
            ticker = position['signal']['ticker'] if position else pending['signal']['ticker']
            bar = prices.get(ticker, {}).get(day)
            if bar is None:
                # Cannot infer a missed fill or a trading suspension from no row.
                halted = True
                events.append(dict(date=day, ticker=ticker, event='HALT_MISSING_BAR'))
            else:
                _validate_bar(bar)
                if position:
                    prev = position['last_close']
                    if not .65 <= bar['open'] / prev <= 1.35:
                        halted = True
                        events.append(dict(date=day, ticker=ticker, event='HALT_CORPORATE_ACTION_OR_PRICE_GAP'))
                    else:
                        mark = bar['close']
                elif pending:
                    fill, pending, reason = pending_step(pending, bar, idx, policy, costs, equity, cash)
                    events.append(dict(date=day, ticker=ticker, event=reason))
                    if fill:
                        debit = fill['price'] * fill['qty'] * (1 + costs.buy)
                        if debit > cash + 1e-8:
                            raise AssertionError('CASH_OVERSPEND')
                        cash -= debit
                        active = (max(fill['stop'], floor_tick(fill['price'] * .93))
                                  if policy.exit == 'LEGACY_TRAIL7_D12' else fill['stop'])
                        position = dict(**fill, debit=debit, active_stop=active,
                                        peak_high=fill['price'], peak_close=fill['price'],
                                        trail_active=False, last_close=fill['price'],
                                        planned_risk=debit - fill['qty'] * fill['stop'] * (1-costs.sell))
                        mark = bar['close']
                if position and not halted:
                    px, reason, position = exit_step(position, bar, idx, policy)
                    position['last_close'] = bar['close']
                    if px is not None:
                        credit = position['qty'] * px * (1 - costs.sell)
                        pnl = credit - position['debit']
                        cash += credit
                        trades.append(dict(asof=position['signal']['asof'], ticker=ticker,
                                           order_decision_date=position['order_decision_date'],
                                           entry_date=position['entry_date'], exit_date=day,
                                           entry=position['price'], stop=position['stop'],
                                           submitted_cap=position['cap'], qty=position['qty'],
                                           exit_price=px, reason=reason, pnl_krw=pnl,
                                           net_pct=100*pnl/position['debit'],
                                           planned_risk_krw=position['planned_risk'],
                                           hold_sessions=idx-position['entry_idx']+1,
                                           contact_not_fill=True, trade_approved=False, orders_enabled=False))
                        events.append(dict(date=day, ticker=ticker, event='PAPER_EXIT', reason=reason))
                        position = None
                        last_exit = day
        if halted:
            daily.append(dict(date=day, equity_krw=None, cash_krw=cash,
                              position_ticker=position['signal']['ticker'] if position else None,
                              complete=False))
            break
        equity = cash + (position['qty'] * mark * (1-costs.sell) if position else 0.)
        if cash < -1e-7:
            raise AssertionError('NEGATIVE_CASH')
        signal = byday.get(day)
        if signal:
            if position or pending:
                reason = 'ONE_SLOT_BUSY_OR_RESERVED'
            elif day <= last_exit:
                reason = 'NO_SAME_EXIT_DAY_RESELECTION'
            elif policy.regime == 'BENCH_TREND' and signal.get('market_trend') is not True:
                reason = 'BENCH_TREND_FILTER'
            else:
                pending, reason = make_pending(signal, policy, costs, equity, cash, idx)
                reason = reason or 'D_CLOSE_ORDER_FROZEN'
            events.append(dict(date=day, ticker=signal['ticker'], event=reason))
        daily.append(dict(date=day, equity_krw=equity, cash_krw=cash,
                          position_ticker=position['signal']['ticker'] if position else None,
                          pending_ticker=pending['signal']['ticker'] if pending else None,
                          complete=True))
    closed_pnl = sum(t['pnl_krw'] for t in trades)
    open_pnl = equity - policy.initial_cash - closed_pnl if not halted else None
    peak = policy.initial_cash
    mdd = 0.
    for r in daily:
        if r['equity_krw'] is not None:
            peak = max(peak, r['equity_krw'])
            mdd = min(mdd, 100 * (r['equity_krw']/peak - 1))
    summary = dict(schema=SCHEMA, **asdict(policy), policy_hash=policy.digest(),
                   cost_pct=costs.label, signal_days=len(signals), closed_trades=len(trades),
                   open_position_count=int(position is not None), pending_count=int(pending is not None),
                   closed_pnl_krw=closed_pnl, open_liquidation_pnl_krw=open_pnl,
                   final_equity_krw=equity if not halted else None,
                   account_roi_pct=100*(equity/policy.initial_cash-1) if not halted else None,
                   daily_liquidation_mdd_pct=mdd if not halted else None,
                   daily_marks_complete=not halted, final_mark_date=daily[-1]['date'],
                   halted=halted, economic_total_return_verified=False,
                   historical_regular_only_verified=False, independent_forward_trades=0,
                   trade_approved=False, orders_enabled=False)
    return dict(summary=summary, trades=trades, events=events, daily=daily,
                open_position=position, pending_order=pending)


def purge_training_intervals(rows, validation_start, validation_end, embargo_sessions=0, sessions=None):
    """Return only intervals closed strictly before validation, plus embargo.

    Expansion uses past data only. Future training data is never admitted.
    """
    lo, hi = iso_day(validation_start), iso_day(validation_end)
    if lo > hi or embargo_sessions < 0:
        raise ValueError('INVALID_VALIDATION_WINDOW')
    cutoff = lo
    if embargo_sessions:
        if not sessions or lo not in sessions:
            raise ValueError('EMBARGO_NEEDS_EXCHANGE_SESSIONS')
        idx = sessions.index(lo) - embargo_sessions
        cutoff = sessions[max(0, idx)]
    return [dict(r) for r in rows if iso_day(r['exit_date']) < cutoff
            and iso_day(r['asof']) < cutoff]
