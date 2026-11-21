"""Existing XKRX reference calendar, cross-checked by the actual KRX collector."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')

def session_plan(clock, manual_asof='', calendar=None):
    import exchange_calendars as xc
    local = clock.astimezone(KST)
    # Keep the existing 21:00 collection cutoff; replace weekday arithmetic
    # with the same pinned calendar already used by the morning source adapter.
    cutoff = local.date() - timedelta(days=1 if local.hour < 21 else 0)
    manual = str(manual_asof or '').strip()
    day = datetime.strptime(manual, '%Y%m%d').date() if manual else None
    if day and (day > cutoff or day.strftime('%Y%m%d') != manual):
        raise ValueError('MANUAL_ASOF_NOT_COMPLETED')
    first = min(cutoff, day) if day else cutoff
    cal = calendar or xc.get_calendar('XKRX', start=str(first-timedelta(days=400)),
                                      end=str(local.date()+timedelta(days=40)))
    if day and not cal.is_session(str(day)):
        raise ValueError('MANUAL_ASOF_NOT_KRX_SESSION')
    target = cal.date_to_session(str(day or cutoff), direction='previous')
    entry_session = cal.next_session(target)
    valid_until = cal.session_close(entry_session).tz_convert('Asia/Seoul').isoformat()
    return dict(asof=target.strftime('%Y%m%d'),
                entry_session=entry_session.strftime('%Y%m%d'),
                entry_valid_until=valid_until,
                calendar_name='XKRX_REFERENCE_WITH_ACTUAL_KRX_DATE_CHECK',
                calendar_version=xc.__version__, calendar_is_official_attestation=False)
