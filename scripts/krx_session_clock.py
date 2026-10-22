"""Conservative KRX full-session day selection for read-only reports.

Since Sep 14 2026 the KRX after-market continues until 20:00 KST.
16:00 is the *regular-session* post-close point, not completion of the
full day's extended price tape. This weekday heuristic does NOT
replace actual KRX holiday/calendar and source-quality verification.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST=ZoneInfo("Asia/Seoul")
AFTERMARKET_FULL_SESSION_CUTOFF=(20,10)

def nominal_last_completed_krx_session(now_kst:datetime)->str:
    if now_kst.tzinfo is None or now_kst.utcoffset() is None:
        raise ValueError("KST_TZ_AWARE_DATETIME_REQUIRED")
    now=now_kst.astimezone(KST)
    d=now.date()
    if d.weekday()>=5 or (now.hour,now.minute)<AFTERMARKET_FULL_SESSION_CUTOFF:
        d-=timedelta(days=1)
    while d.weekday()>=5:
        d-=timedelta(days=1)
    return d.isoformat()
