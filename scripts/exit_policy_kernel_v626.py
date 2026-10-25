#!/usr/bin/env python3
"""C3 v6.26: predeclared stop-first 5-session exit cashflow. READ ONLY."""
from __future__ import annotations
from datetime import datetime
from math import isfinite
SCHEMA="C3_V626_RESEARCH_STOP_FIRST_EXIT_KERNEL"
MODES=("STOP_TRAIL7","STOP_TRAIL5","STOP_TARGET1P5R","STOP_TARGET2R",
       "STOP_TARGET10PCT","STOP_TARGET15PCT","STOP_PARTIAL10_TRAIL7")

def published_before_next_open(public_ts,first_next_date,ex_date,future_dates):
    """Known public filing can cancel at D+1 preopen; unknown future cannot."""
    ts=datetime.fromisoformat(public_ts)
    if ts.tzinfo is None:raise ValueError("PUBLIC_TIMESTAMP_REQUIRES_TIMEZONE")
    cutoff=datetime.fromisoformat(first_next_date+"T08:35:00+09:00")
    return ex_date in future_dates and ts<=cutoff

def exit_sim(future,entry,stop,mode,fee_pct=.65):
    """Pessimistic single-bar STOP before target, previous-session trailing peak.

    Never assert a broker fill from OHLC high or low contact.
    Partial 10pct harvest is an idealized 50pct price-contact scenario.
    """
    if mode not in MODES:raise ValueError("UNPREDECLARED_EXIT")
    if not all(isfinite(float(x)) for x in (entry,stop,fee_pct)):
        raise ValueError("NAN_EXIT_ARGUMENT")
    if not 0<stop<entry or fee_pct<0 or len(future)!=5:
        raise ValueError("INVALID_EXIT_GEOMETRY_OR_FUTURE")
    peak=float(entry);remaining=1.0;gross=0.0;partial=False
    for bar in future:
        op,hi,lo,close=[float(bar[k]) for k in ("Open","High","Low","Close")]
        if not all(isfinite(x) for x in (op,hi,lo,close)) or not (
          0<lo<=min(op,close)<=max(op,close)<=hi):
            raise ValueError("INVALID_OHLC")
        trailing=.95 if mode=="STOP_TRAIL5" else .93
        threshold=max(stop,peak*trailing) if mode in (
          "STOP_TRAIL7","STOP_TRAIL5","STOP_PARTIAL10_TRAIL7") else stop
        if lo<=threshold:
            gross+=remaining*100*(min(op,threshold)/entry-1)
            return dict(net_pct=round(gross-fee_pct,4),reason="STOP_FIRST",
                exit_date=bar["Date"],partial_happened=partial,
                broker_fill_verified=False,trade_approved=False,orders_enabled=False)
        if mode in ("STOP_TARGET1P5R","STOP_TARGET2R"):
            r=1.5 if mode=="STOP_TARGET1P5R" else 2.0
            target=entry+r*(entry-stop)
        elif mode=="STOP_TARGET10PCT":target=entry*1.10
        elif mode=="STOP_TARGET15PCT":target=entry*1.15
        else:target=None
        if target is not None and hi>=target:
            gross+=remaining*100*(target/entry-1)
            return dict(net_pct=round(gross-fee_pct,4),reason="PROXY_TARGET_TOUCH",
                exit_date=bar["Date"],partial_happened=partial,
                broker_fill_verified=False,trade_approved=False,orders_enabled=False)
        if mode=="STOP_PARTIAL10_TRAIL7" and not partial and hi>=entry*1.10:
            partial=True;remaining=.5;gross+=5.0
        if mode in ("STOP_TRAIL7","STOP_TRAIL5","STOP_PARTIAL10_TRAIL7"):
            peak=max(peak,hi)
    gross+=remaining*100*(float(future[-1]["Close"])/entry-1)
    return dict(net_pct=round(gross-fee_pct,4),reason="FIFTH_CLOSE",
        exit_date=future[-1]["Date"],partial_happened=partial,
        broker_fill_verified=False,trade_approved=False,orders_enabled=False)
