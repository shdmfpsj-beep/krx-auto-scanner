"""C3 v6.53 small GitHub mirrored safety gate. Research-only.

Complete 697x32 empirical audit and 41 local tests live in user conversation ZIP.
This module never certifies historical source vintage or enables orders.
"""
from datetime import date, datetime, time, timedelta, timezone
from math import isfinite

KST=timezone(timedelta(hours=9))

def etf_pdf_vintage_gate(snapshot_date, actual_collected_at, signal_date):
    snap=date.fromisoformat(snapshot_date)
    signal=date.fromisoformat(signal_date)
    collected=datetime.fromisoformat(actual_collected_at.replace("Z","+00:00"))
    if collected.tzinfo is None:
        raise ValueError("COLLECTION_TIME_NEEDS_OFFSET")
    if snap>signal:
        raise ValueError("FUTURE_NOMINAL_SNAPSHOT")
    cutoff=datetime.combine(signal,time(15,30),KST)
    observed_by_D=collected<=cutoff
    return {
        "original_snapshot_date":snap.isoformat(),
        "signal_D_date":signal.isoformat(),
        "observed_by_D_this_system":observed_by_D,
        "publication_vintage_independently_certified":False,
        "eligible_as_strict_live_sector_membership":False,
        "historical_backfill_after_signal_close":not observed_by_D,
        "trade_approved":False,
        "orders_enabled":False,
    }

def after_cost_chart_payoff_ratio(entry,original_daily_stop,recorded_overhead,
                                  buy_fee=0.0015,sell_fee=0.005):
    e,s,t=map(float,(entry,original_daily_stop,recorded_overhead))
    if not all(isfinite(x) and x>0 for x in (e,s,t)):
        raise ValueError("PRICE_NOT_VALID")
    if e<=s or t<=e:raise ValueError("NO_VALID_STRUCTURAL_ENTRY")
    if not (0<=buy_fee<.1 and 0<=sell_fee<.1):
        raise ValueError("BAD_FEE")
    risk=e*(1+buy_fee)-s*(1-sell_fee)
    reward=t*(1-sell_fee)-e*(1+buy_fee)
    return max(0.,reward/risk)
