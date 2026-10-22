#!/usr/bin/env python3
"""Immutable session-separated KRX market observations; NO trading authorization.

An early snapshot from an unscoped daily-quote API does NOT by itself prove
that all fields (notably accumulated volume and high/low) belong exclusively to
the regular auction. Official session-scoped minute bars or an explicitly
session-certified provider are needed before promoting the regular layer.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

KST=ZoneInfo("Asia/Seoul")
REGULAR="KRX_REGULAR_0900_1530"
AFTER="KRX_AFTERMARKET_1600_2000"
SOURCE="PYKRX_DATE_ONLY_UNSCOPED"

def window(phase,now):
    if now.tzinfo is None or now.utcoffset() is None:
        return "TIMEZONE_MISSING"
    t=now.astimezone(KST)
    if t.weekday()>=5:return "NON_WEEKDAY_UNVERIFIED"
    mins=t.hour*60+t.minute
    if phase=="regular":
        # After closing auction, before the 15:40 off-hours closing-price trade.
        return "POST_REGULAR_PRE_OFFHOURS" if 15*60+33<=mins<15*60+40 else "MISSED_REGULAR_ISOLATION_WINDOW"
    if phase=="after":
        return "AFTERMARKET_FINISHED" if 20*60+5<=mins<22*60 else "MISSED_AFTERMARKET_FINAL_WINDOW"
    return "UNKNOWN_PHASE"

def assess_capture(payload):
    if not isinstance(payload,dict):return ["SNAPSHOT_MISSING"]
    blockers=[]
    phase=payload.get("phase")
    expected=("POST_REGULAR_PRE_OFFHOURS" if phase=="regular"
              else "AFTERMARKET_FINISHED" if phase=="after" else "UNKNOWN_PHASE")
    if payload.get("capture_window")!=expected:blockers.append("CAPTURE_WINDOW_NOT_VERIFIED")
    if payload.get("source")!=SOURCE:blockers.append("SOURCE_PROVENANCE_MISMATCH")
    q=payload.get("quality") or {}
    if not isinstance(q.get("checked"),int) or q["checked"]<100:
        blockers.append("INSUFFICIENT_MARKET_COVERAGE")
    if not isinstance(q.get("invalid"),int) or q.get("invalid",999)>0:
        blockers.append("OHLC_SOURCE_INTEGRITY_NOT_PROVEN")
    if payload.get("provider_session_scope_verified") is not True:
        blockers.append("PROVIDER_REGULAR_SESSION_SCOPE_NOT_ATTESTED")
    if phase!="regular":blockers.append("AFTERMARKET_IS_NOT_TRADE_STRATEGY_SOURCE")
    return blockers

def capture(phase,now,markets,provider_session_scope_verified=False):
    from krx_session_probe import new_snapshot
    base=new_snapshot(phase,now,markets)
    base["capture_window"]=window(phase,now)
    base["trade_session"]=REGULAR if phase=="regular" else AFTER
    base["source"]=SOURCE
    base["provider_session_scope_verified"]=bool(provider_session_scope_verified)
    # No unscoped PyKRX daily price may self-certify a regular-session bar.
    if base["provider_session_scope_verified"] and SOURCE=="PYKRX_DATE_ONLY_UNSCOPED":
        raise ValueError("UNSCOPED_SOURCE_CANNOT_CERTIFY_REGULAR_SESSION")
    base["regular_strategy_eligible"]=False
    base["trade_approved"]=False
    base["orders_enabled"]=False
    base["separation_blockers"]=assess_capture(base)
    return base

def split(regular,after):
    """Separate layers without reconstructing or silently replacing OHLC."""
    regular=regular if isinstance(regular,dict) else {}
    after=after if isinstance(after,dict) else {}
    errors=[]
    if regular.get("phase")!="regular":errors.append("REGULAR_SNAPSHOT_MISSING")
    if after.get("phase")!="after":errors.append("AFTERMARKET_SNAPSHOT_MISSING")
    if regular.get("asof")!=after.get("asof"):errors.append("DATE_PAIR_MISMATCH")
    # Snapshot times are observational, not explicit trade timestamps.
    errors+=assess_capture(regular)
    if window_check:=after.get("capture_window")!="AFTERMARKET_FINISHED":
        errors.append("AFTER_CAPTURE_WINDOW_MISSING")
    deltas=[];different=0;outside=0
    if not errors or set(errors)=={"PROVIDER_REGULAR_SESSION_SCOPE_NOT_ATTESTED"}:
        for ticker,r in (regular.get("stocks") or {}).items():
            a=(after.get("stocks") or {}).get(ticker)
            if not a or r.get("market")!=a.get("market"):continue
            if r.get("Close")!=a.get("Close"):
                different+=1
                if len(deltas)<20:
                    deltas.append(dict(ticker=ticker,
                                      snapshot_regular_close=r.get("Close"),
                                      snapshot_after_close=a.get("Close"),
                                      price_change_not_proven_aftermarket_only=True))
            try:
                if a.get("Close") is not None and (
                    a["Close"]>a.get("High",float("inf")) or
                    a["Close"]<a.get("Low",float("-inf"))):
                    outside+=1
            except (TypeError,ValueError):pass
    return dict(schema="krx_session_isolation_v1",asof=regular.get("asof"),
                regular=dict(asof=regular.get("asof"),source=regular.get("source"),
                    capture_window=regular.get("capture_window"),
                    eligible=False,quality=regular.get("quality"),
                    provider_session_scope_verified=regular.get("provider_session_scope_verified",False)),
                after=dict(asof=after.get("asof"),source=after.get("source"),
                    capture_window=after.get("capture_window"),quality=after.get("quality"),
                    strategy_use=False),
                comparison=dict(changed_snapshot_close_count=different,
                    invalid_after_price_vs_high_low_count=outside,
                    examples=deltas,observed_price_differences_are_not_execution_timestamps=True),
                blockers=list(dict.fromkeys(errors)),
                regular_ohlcv_certified=False,
                regular_flow_certified=False,
                source_regular_strategy_ready=False,
                final_buy_approvals=0,decision="CASH")
