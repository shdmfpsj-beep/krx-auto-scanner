"""C3 v6.57 — prior-completed-D stock price timing math, research-only.

This is a compact standalone GitHub safeguard; full 2,640 row empirical
replay and 37 test locally reproducible ZIP are not implied to run in CI.
The 2023 KRX standard stock tick grid used here requires separate verification
for issuer, venue and order type on any future actual trading day.
No broker, account capital, quantity or actual BUY functionality.
"""
from __future__ import annotations
from datetime import date
from math import isfinite, floor

def korea_cash_stock_price_grid_2023(price:float)->int:
    if not isfinite(price) or price<=0:raise ValueError("INVALID_BID")
    return (1 if price<2000 else
            5 if price<5000 else
            10 if price<20000 else
            50 if price<50000 else
            100 if price<200000 else
            500 if price<500000 else 1000)

def price_grid_floor(price:float)->int:
    return int(floor(price/korea_cash_stock_price_grid_2023(price))*
               korea_cash_stock_price_grid_2023(price))

def frozen_D_research_prices(ticker:str,asof:str,close:float,
                             original_structural_stop:float,ATR14:float,
                             true_documented_overhead:float|None=None,
                             pre_D_known_support:float|None=None,
                             support_proven_asof:str|None=None):
    if len(ticker)!=6 or not ticker.isdigit():raise ValueError("INVALID_TICKER")
    if date.fromisoformat(asof).isoformat()!=asof:raise ValueError("INVALID_DATE")
    if not all(isfinite(z) and z>0 for z in
               (close,original_structural_stop,ATR14)) or close<=original_structural_stop:
        raise ValueError("D_STRUCTURE_INVALID")
    if true_documented_overhead is not None and not (isfinite(true_documented_overhead)
        and true_documented_overhead>close):
        raise ValueError("OVERHEAD_WRONG_OR_NOT_ABOVE_D")
    if pre_D_known_support is not None:
        if support_proven_asof is None or date.fromisoformat(support_proven_asof)>date.fromisoformat(asof):
            raise ValueError("PIT_SUPPORT_UNVERIFIED_OR_FUTURE")
    def valid_bid(p):
        v=price_grid_floor(p)
        return v if v>original_structural_stop else None
    support=pre_D_known_support if pre_D_known_support is not None and (
        original_structural_stop<pre_D_known_support<close and
        close-pre_D_known_support<=0.75*ATR14) else None
    return {"ticker":ticker,"signal_day_D":asof,
        "D_close":close,"structural_stop_unchanged":original_structural_stop,
        "recorded_first_overhead_or_none":true_documented_overhead,
        "D_close_resting_limit_research":valid_bid(close),
        "ATR10_resting_limit_research":valid_bid(close-0.10*ATR14),
        "ATR25_resting_limit_research":valid_bid(close-0.25*ATR14),
        "D_prior_support_resting_limit_research":valid_bid(support) if support else None,
        "support_IS_ACTUAL_volume_profile":False,
        "actual_order_submitted":False,"broker_fill_verified":False,
        "exchange_KRX_venue_data_certified":False,
        "trade_approved":False,"orders_enabled":False}
