"""C3 read-only public quote eligibility gate; never manufactures prices."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
TOP2 = {"271560", "026960"}

def validate_public_quote(record, now=None, max_delay_minutes=25):
    """Validate provenance and freshness. Does not imply permission to scrape."""
    now = now or datetime.now(KST)
    try:
        code = str(record["ticker"]).zfill(6)
        source = str(record["source"]).strip()
        license_ok = record["automated_access_permitted"] is True
        price = int(record["price"])
        observed = datetime.fromisoformat(record["observed_at"])
        market = record["market"]
        if observed.tzinfo is None:
            return False, "MISSING_TIMEZONE"
        observed = observed.astimezone(KST)
        now = now.astimezone(KST)
        if code not in TOP2 or not source or not license_ok:
            return False, "SOURCE_NOT_ELIGIBLE"
        if market != "KRX_REGULAR" or observed.weekday() >= 5 or not (time(9) <= observed.time() <= time(15,30)):
            return False, "NOT_KRX_REGULAR"
        if price <= 0:
            return False, "INVALID_PRICE"
        age = now - observed
        if age < timedelta(seconds=-60) or age > timedelta(minutes=max_delay_minutes):
            return False, "STALE_OR_FUTURE"
        return True, "VERIFIED_OBSERVATION"
    except (KeyError, ValueError, TypeError, OverflowError):
        return False, "INVALID_RECORD"

def validate_paper_entry_quote(record, now=None):
    """Stricter gate for paper entries; delayed research observations never fill."""
    ok, reason = validate_public_quote(record, now=now, max_delay_minutes=2)
    if not ok:
        return False, reason
    if record.get("feed_delay_class") != "REALTIME_AUTHORIZED":
        return False, "DELAYED_OR_UNCERTIFIED_FEED"
    if record.get("execution_eligible") is not True:
        return False, "EXECUTION_NOT_AUTHORIZED"
    return True, "PAPER_ENTRY_ELIGIBLE"
