"""Read-only KRX regular-session admission: 09:00-15:30 KST only.

KRX after-market trade prices may influence daily high/low while official
regular close stays unchanged. A date-only vendor endpoint is NOT proof of
session-scoped OHLC, even when fetched at 15:45. No fail-open interpolation.
"""
from datetime import datetime,time
from zoneinfo import ZoneInfo

KST=ZoneInfo("Asia/Seoul")
MIN_REGULAR_STOCK_BARS=100
ALLOWED_CUTOFF=time(16,0)

def _dt(value):
    try:
        obj=datetime.fromisoformat(value)
        return obj.astimezone(KST) if obj.tzinfo and obj.utcoffset() is not None else None
    except (ValueError,TypeError,AttributeError):
        return None

def evaluate(snapshot, target_asof):
    reasons=[]
    s=snapshot if isinstance(snapshot,dict) else {}
    if s.get("schema")!="krx_session_probe_v1" or s.get("phase")!="regular":
        reasons.append("REGULAR_SNAPSHOT_MISSING")
    if s.get("asof")!=target_asof:
        reasons.append("REGULAR_ASOF_MISMATCH")
    started=_dt(s.get("started_at_kst") or s.get("captured_at_kst"))
    ended=_dt(s.get("captured_at_kst"))
    if (not started or not ended or started.date()!=ended.date() or
        started.weekday()>4 or
        not time(15,35)<=started.timetz().replace(tzinfo=None)<ALLOWED_CUTOFF or
        not time(15,35)<=ended.timetz().replace(tzinfo=None)<ALLOWED_CUTOFF or
        ended<started):
        reasons.append("REGULAR_CAPTURE_WINDOW_UNVERIFIED")
    if s.get("window")!="REGULAR_WINDOW":
        reasons.append("REGULAR_CAPTURE_WINDOW_UNVERIFIED")
    quality=s.get("quality") if isinstance(s.get("quality"),dict) else {}
    checked=quality.get("checked")
    invalid=quality.get("invalid")
    if (isinstance(checked,bool) or not isinstance(checked,int) or
        checked<MIN_REGULAR_STOCK_BARS or
        isinstance(invalid,bool) or not isinstance(invalid,int) or invalid<0):
        reasons.append("REGULAR_PRICE_NOT_READY")
    elif invalid>0:
        reasons.append("REGULAR_OHLC_CONFLICT")
    scope=s.get("provider_session_scope")
    if scope!="REGULAR_ONLY_EXPLICIT_PROVIDER_CERTIFIED":
        reasons.append("MARKET_SOURCE_SESSION_UNVERIFIED")
    # Scope metadata should not be self-certification by the model or by a
    # generic date-only vendor. Allow explicit certification only via an
    # allowlisted, session-scoped provider method independently reviewed.
    if s.get("source")=="pykrx_get_market_ohlcv_date_only":
        reasons.append("REGULAR_DATE_ONLY_FEED_CANNOT_CERTIFY_SCOPE")
    if s.get("orders_enabled") is not False or s.get("trade_approved") is not False:
        reasons.append("REGULAR_SOURCE_NOT_READ_ONLY")
    blockers=list(dict.fromkeys(reasons))
    return dict(schema="krx_regular_admission_v1",target_asof=target_asof,
        source=s.get("source"),provider_session_scope=scope,
        source_coverage=checked,invalid_bars=invalid,
        source_observation_verified=(not blockers),
        session_provenance_verified=(not blockers),
        sector_money_flow_regular_verified=False,
        history_65_regular_sessions_verified=False,
        research_top3_status="PENDING_DATA_VALIDATION",
        research_top5_status="PENDING_DATA_VALIDATION",
        approved_buy_count=0,trade_approved=False,decision="CASH",
        blockers=blockers)
