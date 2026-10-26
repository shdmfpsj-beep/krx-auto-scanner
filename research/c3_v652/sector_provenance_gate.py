"""C3 v6.52 — strict-research ETF composition evidence gate. NO BUY.

A dated-query ETF membership file does not certify the original publication
vintage. Never use historical PDF backfill as a live as-of stock classification.
Standalone core: full 30-test empirical research and compact exact-source CSVs
are delivered in C3_v652_업종주도력_수익성검증_연구자료.zip.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from math import isfinite

RESEARCH_VINTAGE = "PROVIDER_DATED_NOT_INDEPENDENT_VINTAGE_VERIFIED"
RESEARCH_STATUS = "PROVIDER_DATED_PROXY_NOT_STRICT_PIT"

def checked_day(value):
    if not isinstance(value,str):
        raise ValueError("DAY_REQUIRED")
    if date.fromisoformat(value).isoformat()!=value:
        raise ValueError("NON_CANONICAL_DATE")
    return value

def most_recent_group_snapshot(ticker:str, on_date:str, membership:list[dict],
                               sector_evidence:list[dict]):
    """Pick complete ETF latest snapshot first; test member only AFTER that.
    Never silently carry forward membership that later disappeared.
    Exactly D-date sector evidence, no D+1 future price or performance used.
    """
    on_date=checked_day(on_date)
    if not ticker or not isinstance(membership,list) or not isinstance(sector_evidence,list):
        raise ValueError("INVALID_RESEARCH_INPUT")
    latest={}
    for row in membership:
        group=str(row["sector_id"])
        snap=checked_day(row["snapshot_date"])
        if row.get("point_in_time_status")!=RESEARCH_VINTAGE:
            raise ValueError("UNVERIFIED_OR_MIXED_MEMBERSHIP_PROVENANCE")
        if snap<=on_date and (group not in latest or snap>latest[group]):
            latest[group]=snap
    selected={}
    for row in membership:
        group=row["sector_id"]
        if row["ticker"]==ticker and group in latest and row["snapshot_date"]==latest[group]:
            selected[group]=row
    result=[]
    for e in sector_evidence:
        if checked_day(e["date"])!=on_date:
            continue
        if e["membership_status"]!=RESEARCH_STATUS:
            raise ValueError("INCONSISTENT_VINTAGE_STATUS")
        if e.get("live_selection_authorized",False) not in (False,0,"False"):
            raise ValueError("LIVE_SELECTION_FORBIDDEN")
        if e["sector_id"] not in selected or e["sector_id"]=="HEALTH":
            continue
        rs=float(e.get("rs_5d_pp",float("nan")))
        breadth=float(e.get("breadth_up_5d_pct",float("nan")))
        result.append({
            "group":e["sector_id"],"etf":str(e["etf"]).zfill(6),
            "latest_snapshot_date":latest[e["sector_id"]],
            "relative_strength_5d_pp":rs if isfinite(rs) else None,
            "group_advancing_members_5d_pct":breadth if isfinite(breadth) else None,
            "strict_original_publication_vintage_verified":False,
            "is_exhaustive_industry_classification":False,
            "is_non_biotech_issuer_verified":False,
            "is_KRX_regular_only_verified":False,
            "orders_enabled":False,"trade_approved":False
        })
    return sorted(result,key=lambda x:x["group"])

def research_decision(matches:list[dict], market_provenance_verified:bool=False):
    """Synthetic input flags do NOT certify the market or constitute trade permission."""
    return {
        "etf_proxy_groups":len(matches),
        "classification_status":"ETF_DATED_PROXY_NOT_STRICT_PIT" if matches else "UNCLASSIFIED",
        "upside_probability_calibrated":False,
        "independently_verified_trades":0,
        "market_regular_only_certified":False,
        "source_publication_time_authenticated":False,
        "historical_sector_ETF_backfill_not_proof":True,
        "cash_or_wait":True,
        "trade_approved":False,"orders_enabled":False
    }
