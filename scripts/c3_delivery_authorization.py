"""One explicitly approved manual recovery; ordinary manual previews stay DRY_RUN."""
from datetime import datetime, timezone
import re
from c3_top5_session_policy import session_plan

RECOVERY_ASOF = '20261124'
RECOVERY_PREFIX = 'C3 approved operational recovery 20261125'
REQUEST_PREFIX = 'approved-recovery-20261125-'
REPOSITORY = 'shdmfpsj-beep/krx-auto-scanner'
INDEPENDENT_RELEASE_PREFIX = 'C3 approved independent financial release 20261125'
INDEPENDENT_REQUEST_PREFIX = 'approved-independent-release-20261125-'


def validate_current_signal(asof, expiry, clock=None):
    clock=clock or datetime.now(timezone.utc)
    try:
        deadline=datetime.fromisoformat(expiry)
        if deadline.utcoffset() is None or deadline<=clock or session_plan(clock)['asof']!=asof:raise ValueError()
    except (ValueError,TypeError):raise ValueError('MANUAL_RECOVERY_DATE_OR_VALIDITY_MISMATCH') from None


def approved_manual_delivery(env, asof, expiry, clock=None):
    if str(env.get('C3_MANUAL_LIVE_DELIVERY', '')).lower() != 'true':
        return False
    clock = clock or datetime.now(timezone.utc)
    if (env.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or env.get('GITHUB_REF_NAME') != 'main'
            or env.get('GITHUB_REPOSITORY') != REPOSITORY
            or env.get('C3_FINANCIAL_MODEL') != 'balanced'
            or env.get('C3_MANUAL_ASOF')!=asof):
        raise ValueError('MANUAL_RECOVERY_CONTEXT_NOT_AUTHORIZED')
    request=env.get('C3_OPERATION_REQUEST_ID','')
    original=asof==RECOVERY_ASOF and re.fullmatch(re.escape(REQUEST_PREFIX)+r'\d+',request)
    release=(asof=='20261125' and env.get('C3_APPROVAL_POLICY')=='INDEPENDENT_ISSUER_FINANCIAL_APPROVAL_V2'
        and re.fullmatch(re.escape(INDEPENDENT_REQUEST_PREFIX)+r'\d+',request))
    if not (original or release):raise ValueError('MANUAL_RECOVERY_CONTEXT_NOT_AUTHORIZED')
    validate_current_signal(asof,expiry,clock)
    return True
