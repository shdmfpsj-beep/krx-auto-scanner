"""Research-only invocation, completed-session planning and report handoff guards."""
import json,re
from datetime import datetime,timezone,timedelta
from pathlib import Path

REPOSITORY='shdmfpsj-beep/krx-auto-scanner'
BRANCH='research/c3-ledger-integrity-audit-20261104'
KST=timezone(timedelta(hours=9))


def invocation(repo,ref,event,mode,engine_sha,upstream=None):
    if repo!=REPOSITORY or not re.fullmatch('[a-f0-9]{40}',engine_sha):raise ValueError('REPOSITORY_OR_PIN_INVALID')
    if ref=='refs/heads/'+BRANCH:
        if event not in ('push','workflow_dispatch') or mode not in ('research_direct','research_smoke'):raise ValueError('RESEARCH_INVOCATION_NOT_ALLOWED')
    elif ref=='refs/heads/main':
        if mode!='approved_daily' or event not in ('schedule','workflow_run','workflow_dispatch'):raise ValueError('DAILY_CALLER_NOT_ALLOWED')
        if event=='workflow_run':
            u=upstream or {}
            if u.get('name')!='KRX daily candidate scan' or u.get('head_branch')!='main' or u.get('conclusion')!='success' or u.get('repository')!=REPOSITORY:raise ValueError('UPSTREAM_NOT_SUCCESSFUL_MAIN_SCANNER')
    else:raise ValueError('UNAPPROVED_REF')
    return dict(event=event,mode=mode,engine_sha=engine_sha,upstream=upstream,
        automatic_event_observed=event in ('schedule','workflow_run') and mode=='approved_daily',
        calendar_schedule_deployed_claimed=False,source_of_truth='GITHUB_EVENT_CONTEXT_NOT_USER_REQUEST_DATE',orders_enabled=False)


def collection_plan(now,index_dates,cached_dates):
    if now.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    local=now.astimezone(KST);today=local.date().isoformat();closed=[d for d in index_dates if d<today or (d==today and local.hour*60+local.minute>=930)]
    if not closed:raise ValueError('NO_COMPLETED_BENCHMARK_SESSION')
    expected=max(closed);missing=[d for d in closed if d>'2026-11-04' and d not in cached_dates]
    requested=sorted(set(missing[:4]+[expected]))
    return dict(today=today,expected_completed_session=expected,requested_dates=requested,missing_index_sessions=missing,
        request_budget_dates=5,current_session_not_yet_completed=local.hour*60+local.minute<930,
        calendar_is_observed_index_sessions_not_independent_krx_calendar=True,not_a_new_decision_for_old_dates=True)


def already_current(report,expected,pipeline_hash):
    return bool(report and report.get('data_quality_state') in (None,'OFFICIAL_VERIFIED') and report.get('source_price_asof')==expected and not report.get('errors') and
        report.get('source_hashes',{}).get('pipeline_code')==pipeline_hash)


def registration_window(price_day,now):
    """Late EOD may inform a real decision before the next possible open.

    A weekday deadline is deliberately conservative on holidays. It cannot
    extend registration beyond an already possible market open.
    """
    local=now.astimezone(KST);day=local.date().isoformat()
    if price_day<'2026-11-06':return 'SOURCE_BEFORE_FORWARD_START'
    if price_day>day:return 'FUTURE_PRICE_SESSION'
    if price_day==day:return 'SAME_COMPLETED_SESSION' if local.hour*60+local.minute>=930 else 'SESSION_NOT_COMPLETED'
    opening=datetime.fromisoformat(price_day).date()+timedelta(days=1)
    while opening.weekday()>=5:opening+=timedelta(days=1)
    deadline=datetime.combine(opening,datetime.min.time(),tzinfo=KST).replace(hour=9)
    return 'DELAYED_BEFORE_NEXT_POSSIBLE_OPEN' if local<deadline else 'PAST_NEXT_POSSIBLE_OPEN'


def handoff(summary,markdown):
    needed=('generated_at','source_run_id','source_price_asof','preview_price_asof','new_registered_signals','research_top2_is_registered_today','performance','errors','current_action')
    if any(k not in summary for k in needed):raise ValueError('SUMMARY_CONTRACT_INCOMPLETE')
    if summary['current_action']!='CASH' or summary.get('orders_enabled') is not False:raise ValueError('UNAPPROVED_LIVE_ACTION')
    if summary['source_price_asof'] is None and summary['new_registered_signals']>0:raise ValueError('SIGNALS_WITHOUT_FRESH_SOURCE')
    if not all(s in markdown for s in ('CASH','기준','가상매매','신규')):raise ValueError('MOBILE_REPORT_CONTRACT_INCOMPLETE')
    return dict(files_read=True,summary_schema_valid=True,markdown_present=True,source_price_asof=summary['source_price_asof'],
        preview_price_asof=summary['preview_price_asof'],run_id=summary['source_run_id'],new_signals=summary['new_registered_signals'],
        automatic_chatgpt_delivery_observed=False)
