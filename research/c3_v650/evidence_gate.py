"""C3 v6.50. Read-only cross-provider historical price conflict and stale-plan gate.

Full report & 33-test runner are in the conversation C3_v650 ZIP.
No broker, no account management, no automatic quotes, no trade authority.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date, datetime
from statistics import median
from math import isfinite

def validate_session(day):
    if not isinstance(day,str) or len(day)!=10:
        raise ValueError("DATE_NOT_ISO")
    if date.fromisoformat(day).isoformat()!=day:
        raise ValueError("DATE_NOT_CANONICAL")
    return day

def price_conflicts(observations):
    """Do not compare delayed intraday quote snapshots with official daily closes."""
    groups=defaultdict(dict)
    for x in observations:
        validate_session(x["session"])
        p=float(x["close"])
        if not isfinite(p) or p<=0:
            raise ValueError("BAD_CLOSE")
        if not x.get("provider") or not str(x.get("url","")).startswith("https://"):
            raise ValueError("MISSING_PROVENANCE")
        key=(x["ticker"],x["session"])
        old=groups[key].get(x["provider"])
        if old is not None and old!=p:
            raise ValueError("SAME_PROVIDER_CONTRADICTION")
        groups[key][x["provider"]]=p
    result=[]
    for (ticker,day),prices in sorted(groups.items()):
        if len(prices)<2:
            continue
        spread=max(prices.values())-min(prices.values())
        result.append({"ticker":ticker,"session":day,
            "provider_closes":dict(sorted(prices.items())),
            "exact_agreement":spread==0,
            "spread_krw":spread,
            "spread_pct":100*spread/median(prices.values()),
            "material_gt_half_percent":spread/median(prices.values())>0.005,
            "precise_levels_quarantined":spread!=0})
    return result

def old_plan_status(ticker,created_on,stop_floor,observations,
                    quote_time,quote_price):
    validate_session(created_on)
    dt=datetime.fromisoformat(quote_time)
    if dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_TIMEZONE_REQUIRED")
    now=dt.date().isoformat()
    if now<created_on or stop_floor<=0 or quote_price<=0:
        raise ValueError("INVALID_DATE_OR_PRICE")
    for x in observations:
        if x["ticker"]!=ticker or validate_session(x["session"])>now:
            raise ValueError("WRONG_TICKER_OR_FUTURE_BAR")
    new_days=sorted({x["session"] for x in observations
                     if created_on<x["session"]<=now})
    latest=new_days[-1] if new_days else None
    under={x["provider"] for x in observations
           if x["session"]==latest and float(x["close"])<stop_floor}
    status=("ARCHIVED_PLAN_BROKEN" if len(under)>=2 else
        "INTRADAY_UNCONFIRMED_BREAK" if quote_price<stop_floor else
        "FRESH_ANALYSIS_REQUIRED")
    return {"schema":"C3_V650_GH_CORE_READ_ONLY","ticker":ticker,
      "old_plan_created_on":created_on,"last_observed_session":latest,
      "price_conflicts":price_conflicts(observations),
      "archived_plan_status":status,"independent_providers_below_old_floor":sorted(under),
      "current_entry":None,"current_stop":None,"current_targets":None,
      "verified_poc":False,"price_origin_certified":False,
      "broker_fills_verified":False,"trade_approved":False,"orders_enabled":False}
