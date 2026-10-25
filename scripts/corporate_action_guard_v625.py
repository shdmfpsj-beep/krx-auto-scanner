#!/usr/bin/env python3
"""C3 v6.25 corporate-action safety layer. Read-only, never authorizes orders.

Point-in-time event inventory MUST be timestamped and source-verified.
Historical price-only stop losses across distributions are NOT shareholder
total returns. D-date selection and D+1 preopen cancel are kept separate.
"""
from datetime import date,datetime
from zoneinfo import ZoneInfo
import math

KST=ZoneInfo("Asia/Seoul")
SCHEMA="C3_V625_CORPORATE_ACTION_PRICE_INTEGRITY_NO_ORDERS"
EVENTS={"SPECIAL_DIVIDEND","EX_RIGHTS","STOCK_SPLIT","REVERSE_SPLIT",
        "MERGER","CAPITAL_REDUCTION","SPINOFF","DELISTING","RIGHTS_OFFERING"}

def ts(value):
    d=datetime.fromisoformat(value)
    if d.tzinfo is None:
        raise ValueError("EXPLICIT_KST_TIMESTAMP_REQUIRED")
    return d.astimezone(KST)

def event_risk(ticker,signal_cutoff_kst,preopen_cutoff_kst,
               potential_holding_dates,events,source_inventory_complete=False):
    signal=ts(signal_cutoff_kst)
    preopen=ts(preopen_cutoff_kst)
    if signal>=preopen:
        raise ValueError("SIGNAL_MUST_PRECEDE_NEXT_OPEN")
    dates=[date.fromisoformat(d) for d in potential_holding_dates]
    if not dates or len(dates)>12 or dates!=sorted(set(dates)):
        raise ValueError("INVALID_TRADING_CALENDAR")
    relevant=[]
    for e in events:
        if str(e.get("ticker","")).zfill(6)!=str(ticker).zfill(6):
            continue
        if e.get("type") not in EVENTS:
            raise ValueError("UNKNOWN_EVENT_TYPE")
        effective=date.fromisoformat(e["ex_date"])
        public=ts(e["public_ts_kst"])
        if not e.get("primary_source_ref"):
            raise ValueError("EVENT_SOURCE_REQUIRED")
        if effective not in dates:
            continue
        relevant.append(dict(type=e["type"],ex_date=effective.isoformat(),
            public=public.isoformat(),known_on_signal_day=public<=signal,
            known_before_next_open=public<=preopen,
            primary_source_ref=e["primary_source_ref"]))
    on_d=[e for e in relevant if e["known_on_signal_day"]]
    before_d1=[e for e in relevant if e["known_before_next_open"]]
    status=("CANCEL_UNADJUSTED_CORPORATE_ACTION" if before_d1 else
       "UNKNOWN_CORPORATE_ACTION_COVERAGE" if not source_inventory_complete else
       "NO_DISCLOSED_ACTION_IN_VERIFIED_INVENTORY")
    return dict(schema=SCHEMA,ticker=str(ticker).zfill(6),status=status,
        known_at_signal=on_d,known_at_preopen=before_d1,
        source_inventory_complete=bool(source_inventory_complete),
        total_return_adjusted_and_PIT_verified=False,
        broker_fill_verified=False,trade_approved=False,orders_enabled=False)

def suspicious_gap(previous_close,next_open,threshold_pct=-35.0):
    a=float(previous_close);b=float(next_open)
    if not all(math.isfinite(z) and z>0 for z in (a,b)):
        raise ValueError("INVALID_PRICE")
    pct=100*(b/a-1)
    return dict(price_only_gap_pct=round(pct,3),
        corporate_action_investigation_required=pct<=threshold_pct,
        no_hindsight_trade_cancellation=True,
        dividend_cash_entitlement_unverified=True)

def verified_total_cash_return(entry,exit_cash,dividend_cash=None,
                               entitlement_verified=False,fee_pct=.65):
    if not entitlement_verified or dividend_cash is None:return None
    vals=(entry,exit_cash,dividend_cash,fee_pct)
    if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in vals):
        return None
    if entry<=0 or exit_cash<0 or dividend_cash<0 or fee_pct<0:
        return None
    return round(100*((exit_cash+dividend_cash)/entry-1)-fee_pct,3)
