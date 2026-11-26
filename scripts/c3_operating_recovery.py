"""Inspect real Actions state; one authorized main push dispatches the real daily workflow."""
import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from c3_delivery_authorization import (RECOVERY_ASOF, RECOVERY_PREFIX, REQUEST_PREFIX, REPOSITORY,
    INDEPENDENT_RELEASE_PREFIX, INDEPENDENT_REQUEST_PREFIX)
from c3_top5_session_policy import session_plan

WORKFLOW = 'c3_top5_daily_telegram.yml'
MORNING_RECOVERY_PREFIX = 'C3 approved morning recovery 20261126'


class GitHub:
    def __init__(self, token): self.token = token
    def call(self, path, method='GET', payload=None, optional=False):
        request = urllib.request.Request('https://api.github.com/repos/' + REPOSITORY + ('/' + path if path else ''),
            method=method, data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Authorization':'Bearer ' + self.token,'Accept':'application/vnd.github+json',
                     'Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
                return json.loads(data) if data else {'http_status':response.status}
        except urllib.error.HTTPError as exc:
            if optional and exc.code in (403,404):return {'http_status':exc.code,'readable':False}
            raise


def diagnose(client, asof=RECOVERY_ASOF):
    repo = client.call('')
    workflow = client.call('actions/workflows/' + WORKFLOW)
    runs = client.call('actions/workflows/' + WORKFLOW + '/runs?per_page=50').get('workflow_runs', [])
    runner_info=client.call('actions/runners',optional=True)
    runner_summary={k:runner_info.get(k) for k in ('total_count','http_status','readable')}
    if 'runners' in runner_info:
        runner_summary.update(online=sum(r.get('status')=='online' for r in runner_info['runners']),busy=sum(bool(r.get('busy')) for r in runner_info['runners']))
    report = dict(repository=REPOSITORY, default_branch=repo.get('default_branch'),
        archived=repo.get('archived'), disabled=repo.get('disabled'),
        main_sha=client.call('git/ref/heads/main').get('object',{}).get('sha'),
        workflow={k:workflow.get(k) for k in ('id','name','path','state','created_at','updated_at')},
        permissions=client.call('actions/permissions',optional=True),
        workflow_permissions=client.call('actions/permissions/workflow',optional=True),
        runners=runner_summary,
        runs=[{k:r.get(k) for k in ('id','event','head_sha','status','conclusion','created_at','run_started_at','updated_at','display_title')} for r in runs],
        receipt_observations={})
    families=('c3_top5_daily','c3_watch5_daily','c3_review_daily') if asof=='20261125' else ('c3_top5_daily','c3_watch5_daily')
    report['target_asof']=asof
    for family in families:
        for day in (asof,datetime.strptime(asof,'%Y%m%d').strftime('%Y-%m-%d')):
            path='receipts/' + family + '/' + day + '.json'
            value=client.call('contents/' + path + '?ref=main',optional=True)
            report['receipt_observations'][path] = dict(exists='content' in value, http_status=value.get('http_status',200))
    report['schedule_event_created_20261125'] = any(r['event']=='schedule' and
        str(r['created_at'])>='2026-11-24T23:00:00Z' for r in report['runs'])
    state=workflow.get('state')
    report['schedule_finding'] = ('WORKFLOW_' + str(state).upper() if state!='active' else
        'EVENT_CREATED' if report['schedule_event_created_20261125'] else
        'ACTIVE_WORKFLOW_NO_EVENT_CAUSE_NOT_ESTABLISHED')
    return report


def release_independent(client, env, event, report, clock=None):
    """One approved release; defer before the existing 21:00 KST source cutoff."""
    clock=clock or datetime.now(timezone.utc)
    local=clock.astimezone(ZoneInfo('Asia/Seoul'))
    title=event.get('head_commit',{}).get('message','').split('\n')[0]
    release=title.startswith(INDEPENDENT_RELEASE_PREFIX) and local.date().isoformat()=='2026-11-25'
    morning=(title.startswith(MORNING_RECOVERY_PREFIX) and local.date().isoformat()=='2026-11-26'
        and local<datetime(2026,11,26,15,30,tzinfo=ZoneInfo('Asia/Seoul')))
    if (env.get('GITHUB_EVENT_NAME')!='push' or env.get('GITHUB_REF_NAME')!='main'
        or env.get('GITHUB_REPOSITORY')!=REPOSITORY or env.get('GITHUB_RUN_ATTEMPT')!='1'
        or not (release or morning)):
        raise ValueError('RECOVERY_EXECUTION_NOT_AUTHORIZED')
    if report.get('default_branch')!='main' or report.get('archived') or report.get('disabled'):
        raise ValueError('RECOVERY_REPOSITORY_NOT_OPERABLE')
    if not env.get('GITHUB_SHA') or report.get('main_sha')!=env['GITHUB_SHA']:
        raise ValueError('RECOVERY_VERIFIED_MAIN_HEAD_CHANGED')
    if report.get('target_asof')!='20261125' or report.get('workflow',{}).get('state')!='active':
        raise ValueError('RECOVERY_WORKFLOW_NOT_ACTIVE_OR_WRONG_TARGET')
    if any(r['http_status'] not in (200,404) for r in report['receipt_observations'].values()):
        raise ValueError('RECOVERY_RECEIPT_STATE_UNVERIFIED')
    if any(r['exists'] for r in report['receipt_observations'].values()):
        return dict(status='BLOCKED_EXISTING_RESERVATION_REVIEW_REQUIRED',automatic_retry=False)
    if session_plan(clock)['asof']!='20261125':
        return dict(status='DEFERRED_TO_EXISTING_SCHEDULE',asof='20261125',
            reason='EXISTING_2100_KST_SOURCE_CUTOFF_NOT_REACHED',source_collected=False,
            next_schedule_kst='2026-11-26T08:00:00+09:00',automatic_retry=False)
    running=[r['id'] for r in report['runs'] if r['status'] in ('queued','in_progress','waiting','requested','pending')]
    if running:return dict(status='WAIT_EXISTING_OPERATING_RUN',run_ids=running,automatic_retry=False)
    request_id=INDEPENDENT_REQUEST_PREFIX+env['GITHUB_RUN_ID']
    response=client.call('actions/workflows/'+WORKFLOW+'/dispatches',method='POST',payload=dict(ref='main',
        inputs=dict(asof='20261125',financial_model='balanced',live_delivery=True,operation_request_id=request_id)))
    if response.get('http_status')!=204:raise ValueError('RECOVERY_DISPATCH_NOT_ACCEPTED')
    return dict(status='DISPATCH_ACCEPTED',asof='20261125',operation_request_id=request_id,
        dispatch_http_status=204,event='workflow_dispatch',automatic_retry=False)


def recover(client, env, event, report, clock=None):
    clock=clock or datetime.now(timezone.utc)
    local=clock.astimezone(ZoneInfo('Asia/Seoul'))
    title=event.get('head_commit',{}).get('message','').split('\n')[0]
    if (env.get('GITHUB_EVENT_NAME')!='push' or env.get('GITHUB_REF_NAME')!='main'
        or env.get('GITHUB_REPOSITORY')!=REPOSITORY or env.get('GITHUB_RUN_ATTEMPT')!='1'
        or not title.startswith(RECOVERY_PREFIX)
        or local.date().isoformat()!='2026-11-25'
        or local>=datetime(2026,11,25,15,30,tzinfo=ZoneInfo('Asia/Seoul'))):
        raise ValueError('RECOVERY_EXECUTION_NOT_AUTHORIZED')
    if report.get('default_branch')!='main' or report.get('archived') or report.get('disabled'):
        raise ValueError('RECOVERY_REPOSITORY_NOT_OPERABLE')
    if not env.get('GITHUB_SHA') or report.get('main_sha')!=env['GITHUB_SHA']:
        raise ValueError('RECOVERY_VERIFIED_MAIN_HEAD_CHANGED')
    if any(r['http_status'] not in (200,404) for r in report['receipt_observations'].values()):
        raise ValueError('RECOVERY_RECEIPT_STATE_UNVERIFIED')
    if any(r['exists'] for r in report['receipt_observations'].values()):
        return dict(status='BLOCKED_EXISTING_RESERVATION_REVIEW_REQUIRED',automatic_retry=False)
    running=[r for r in report['runs'] if r['status'] in ('queued','in_progress','waiting','requested','pending')]
    if running:
        return dict(status='WAIT_EXISTING_OPERATING_RUN',run_ids=[r['id'] for r in running],automatic_retry=False)
    state=report['workflow']['state']
    if state in ('disabled_manually','disabled_inactivity'):
        client.call('actions/workflows/' + WORKFLOW + '/enable',method='PUT')
        report['workflow_after_enable']=client.call('actions/workflows/' + WORKFLOW)
        state=report['workflow_after_enable'].get('state')
    if state!='active':raise ValueError('RECOVERY_WORKFLOW_NOT_ACTIVE')
    request_id=REQUEST_PREFIX + env['GITHUB_RUN_ID']
    payload=dict(ref='main',inputs=dict(asof=RECOVERY_ASOF,financial_model='balanced',
                                      live_delivery=True,operation_request_id=request_id))
    response=client.call('actions/workflows/' + WORKFLOW + '/dispatches',method='POST',payload=payload)
    if response.get('http_status')!=204:raise ValueError('RECOVERY_DISPATCH_NOT_ACCEPTED')
    return dict(status='DISPATCH_ACCEPTED',event='workflow_dispatch',asof=RECOVERY_ASOF,
                operation_request_id=request_id,dispatch_http_status=204,automatic_retry=False,
                dispatched_at=datetime.now(timezone.utc).isoformat())


def recover_after_upstream(client, env, event, report, pause=None, max_waits=12, clock=None):
    """Wait before the first dispatch, never retry an accepted or uncertain POST.

    A late schedule can overlap the verified main release. Refresh reservations
    and head identity after every short wait; existing sends still stop recovery.
    The bound fits the existing five-minute controller timeout.
    """
    import time
    pause=pause or time.sleep
    for attempt in range(max_waits+1):
        result=recover(client,env,event,report,clock)
        if result['status']!='WAIT_EXISTING_OPERATING_RUN' or attempt==max_waits:return result
        pause(10)
        report.update(diagnose(client))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dispatch',action='store_true')
    parser.add_argument('--out',type=Path,default=Path('output/c3_operating_recovery'))
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    result=dict(status='ERROR',checked_at=datetime.now(timezone.utc).isoformat(),automatic_retry=False)
    try:
        event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text()) if args.dispatch else {}
        independent=event.get('head_commit',{}).get('message','').startswith((INDEPENDENT_RELEASE_PREFIX,MORNING_RECOVERY_PREFIX))
        client=GitHub(os.environ['GH_TOKEN']);result['diagnostics']=diagnose(client,'20261125' if independent else RECOVERY_ASOF)
        result['status']='DIAGNOSED'
        if args.dispatch:
            result['recovery']=(release_independent(client,os.environ,event,result['diagnostics']) if independent
                else recover_after_upstream(client,os.environ,event,result['diagnostics']))
            result['status']=result['recovery']['status']
    except Exception as exc:
        result.update(status='ERROR',exception_type=type(exc).__name__,
            reason=str(exc) if type(exc) is ValueError and str(exc).startswith('RECOVERY_') else 'RECOVERY_FAILURE_NO_AUTOMATIC_RETRY')
        if isinstance(exc,urllib.error.HTTPError):result['http_status']=exc.code
    (args.out/'operating_diagnostics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C3_OPERATING_RECOVERY',json.dumps(result,ensure_ascii=False))
    raise SystemExit(1 if result['status']=='ERROR' else 0)


if __name__=='__main__':main()
