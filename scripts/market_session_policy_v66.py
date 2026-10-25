#!/usr/bin/env python3
"""Pure KST source-time policy after KRX 16:00-20:00 after-market started.

Safe reference cutoff is 20:15 KST, not 15:30 or 16:10. Weekends move
to previous weekday, but this is NOT a Korean exchange holiday calendar.
Data-date, full OHLCV integrity and 09:00-15:30 regular scope must still
be verified against official sources. Never auto-approve orders.
"""
from datetime import date,datetime,time,timedelta
from zoneinfo import ZoneInfo

KST=ZoneInfo("Asia/Seoul")
MARKET_SOURCE_READY_AFTER_KST=time(20,15)

def completed_scan_cutoff_date(now):
    if not isinstance(now,datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("AWARE_DATETIME_REQUIRED_FOR_MARKET_DATE")
    kst=now.astimezone(KST)
    target=kst.date()
    if kst.time().replace(tzinfo=None)<MARKET_SOURCE_READY_AFTER_KST:
        target-=timedelta(days=1)
    while target.weekday()>=5:
        target-=timedelta(days=1)
    return target

def source_policy_metadata(now):
    asof=completed_scan_cutoff_date(now)
    return dict(reference_date_limit=asof.isoformat(),
        krx_aftermarket_end_kst="20:00",
        earliest_final_session_check_kst="20:15",
        history_fetch_policy="WAIT_UNTIL_AFTER_KRX_AFTERMARKET_DO_NOT_TREAT_1610_AS_FINAL",
        market_holiday_calendar_verified=False,
        collection_path_recovery="PYKRX_PER_TICKER_ADJUSTED_TRUE_WITH_OPTIONAL_FDR_FALLBACK",
        source_session_scope_certified=False,
        official_KRX_eod_120bar_reconciled=False,
        trade_approved=False,
        orders_enabled=False)
