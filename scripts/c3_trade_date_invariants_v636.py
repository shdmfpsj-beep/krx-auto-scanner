"""C3 v6.36 research: no-time-travel paper-trade invariants. No trading APIs."""
from __future__ import annotations
from datetime import date
import re
SCHEMA="C3_V636_ISO_CHRONOLOGY_NO_ORDERS"
ISO=re.compile(r"^\d{4}-\d{2}-\d{2}$")
def require_iso(d):
    if not isinstance(d,str) or not ISO.fullmatch(d):
        raise ValueError("BAD_ASOF_DATE_OR_PANDAS_METHOD_REFERENCE")
    try:date.fromisoformat(d)
    except ValueError as e:raise ValueError("NON_CALENDAR_DAY") from e
    return d

def audit_chronology(records):
    """Records are one model's already selected filled hypothetical trades."""
    if not isinstance(records,(list,tuple)):raise TypeError("RECORDS_MUST_BE_LIST")
    normalized=[]
    for r in records:
        signal=require_iso(r.get("asof"))
        exitday=require_iso(r.get("exit_date"))
        if exitday<signal:raise ValueError("EXIT_BEFORE_SIGNAL")
        normalized.append((signal,exitday))
    normalized.sort()
    prev=""
    for signal,exitday in normalized:
        if prev and signal<=prev:
            raise ValueError("OVERLAPPING_C3_SINGLE_STOCK_POSITIONS")
        prev=exitday
    return {"schema":SCHEMA,"trades":len(normalized),
       "chronology_verified_for_declared_records":True,
       "source_regular_only_certified":False,
       "real_broker_fills_verified":False,
       "trade_approved":False,"orders_enabled":False}
