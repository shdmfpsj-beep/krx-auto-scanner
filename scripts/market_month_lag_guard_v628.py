#!/usr/bin/env python3
"""v6.28 DATE-AWARE market context for next-session research, NOT BUY authority.

All monthly filters use only the PREVIOUS fully completed calendar month.
Daily filter uses ONLY the completed signal-day close, never next-day data.
KRX 069500 is a KOSPI200 proxy; KOSDAQ and verified regular-only price
provenance require a separate source. No orders, no broker calls.
"""
from __future__ import annotations
from datetime import date,timedelta
from math import isfinite
from statistics import mean

SCHEMA="C3_V628_LAGGED_MARKET_CONTEXT_READ_ONLY"
GATES=("PREVIOUS_MONTH_POSITIVE","PREVIOUS_MONTH_ABOVE_MA20",
       "PREVIOUS_MONTH_ABOVE_MA60","SIGNAL_DAY_ABOVE_MA20",
       "SIGNAL_DAY_RETURN5_POSITIVE","SIGNAL_DAY_NOT_2PCT_DROP")

def _month_before(asof):
    first=date.fromisoformat(asof[:7]+"-01")
    return (first-timedelta(days=1)).isoformat()[:7]

def _validate(rows):
    out=[];prev=None
    for r in rows:
        d=str(r["date"])
        date.fromisoformat(d)
        c=float(r["close"])
        if not isfinite(c) or c<=0 or (prev is not None and d<=prev):
            raise ValueError("BAD_OR_UNSORTED_069500_DAILY_HISTORY")
        out.append((d,c));prev=d
    return out

def market_context(bars,signal_asof):
    """User chooses stock using completed session D; D+1 is unavailable.

    Future bars supplied in an archive are *explicitly discarded* before
    computing the signal date filters; monthly filters are more lagged.
    All flags are descriptive research context, not verified BUY decisions.
    """
    date.fromisoformat(signal_asof)
    data=[x for x in _validate(bars) if x[0]<=signal_asof]
    if not data:raise ValueError("NO_ASOF_069500_HISTORY")
    previous=_month_before(signal_asof)
    months=sorted(set(d[:7] for d,_ in data))
    if previous not in months:raise ValueError("MISSING_PREVIOUS_COMPLETED_MONTH")
    j=max(i for i,(d,_) in enumerate(data) if d[:7]==previous)
    if j<60:raise ValueError("INSUFFICIENT_MONTH_END_HISTORY")
    monthbefore=_month_before(previous+"-01")
    if monthbefore not in months:raise ValueError("MISSING_PRE_PREVIOUS_MONTH")
    k=max(i for i,(d,_) in enumerate(data) if d[:7]==monthbefore)
    prev_date,close=data[j];one_month_ret=100*(close/data[k][1]-1)
    ma20=mean(c for _,c in data[j-19:j+1])
    ma60=mean(c for _,c in data[j-59:j+1])
    prev_only={
       "PREVIOUS_MONTH_POSITIVE":one_month_ret>0,
       "PREVIOUS_MONTH_ABOVE_MA20":close>ma20,
       "PREVIOUS_MONTH_ABOVE_MA60":close>ma60}
    # Completed signal day EXACTLY available, else daily label unknown.
    last_idx=len(data)-1
    daily_ok=data[last_idx][0]==signal_asof and last_idx>=20
    daily={
       "SIGNAL_DAY_ABOVE_MA20":(data[last_idx][1]>
           mean(c for _,c in data[last_idx-19:last_idx+1])) if daily_ok else None,
       "SIGNAL_DAY_RETURN5_POSITIVE":
           (data[last_idx][1]>data[last_idx-5][1]) if daily_ok else None,
       "SIGNAL_DAY_NOT_2PCT_DROP":
           (data[last_idx][1]/data[last_idx-1][1]-1>-.02) if daily_ok else None}
    out=dict(schema=SCHEMA,stock_signal_day=signal_asof,
      last_completed_month=previous,market_observation_asof=prev_date,
      prior_month_return_pct=round(one_month_ret,5),
      source_market_proxy="KOSPI200_ETF_069500_NOT_ALL_KRX",
      previous_month_gates=prev_only,daily_completed_signal_gates=daily,
      certified_regular_session_price=False,
      after_hours_is_separately_excluded_verified=False,
      trade_approved=False,orders_enabled=False)
    return out
