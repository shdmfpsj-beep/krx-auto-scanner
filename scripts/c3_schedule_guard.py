"""Admit one real daily operation; recover missing events without retrying sends."""
import argparse
import base64
import hashlib
import io
import json
import os
import re
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from c3_operating_recovery import GitHub, REPOSITORY, WORKFLOW
from c3_top5_session_policy import session_plan, KST

RECOVERY_WORKFLOW='c3_operating_recovery.yml'
RECOVERY_CRONS={'47 22 * * 1-5','27 23 * * 1-5'}
PREFIX='scheduled-recovery-'
ACTIVE={'queued','in_progress','waiting','requested','pending'}


def marker(client,path):
    value=client.call('contents/'+path+'?ref=main',optional=True)
    if value.get('http_status')==404:return None
    if 'content' not in value:raise ValueError('GUARD_RECEIPT_STATE_UNVERIFIED')
    try:return json.loads(base64.b64decode(value['content'],validate=False))
    except (ValueError,TypeError,KeyError):raise ValueError('GUARD_RECEIPT_INTEGRITY') from None


def archive_outcome(client,run):
    artifacts=client.call('actions/runs/'+str(run['id'])+'/artifacts?per_page=100').get('artifacts',[])
    matches=[a for a in artifacts if a['name']=='c3-top5-daily-classic-per-stock' and not a.get('expired')]
    if len(matches)!=1:raise ValueError('GUARD_PRIOR_ARTIFACT_UNVERIFIED')
    item=matches[0];expected=item.get('digest','')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',expected):raise ValueError('GUARD_PRIOR_ARCHIVE_DIGEST_MISSING')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    request=urllib.request.Request('https://api.github.com/repos/'+REPOSITORY+'/actions/artifacts/'+str(item['id'])+'/zip',
        headers={'Authorization':'Bearer '+client.token,'Accept':'application/vnd.github+json'})
    try:
        with urllib.request.build_opener(NoRedirect).open(request,timeout=30) as response:binary=response.read(100_000_001)
    except urllib.error.HTTPError as error:
        if error.code!=302:raise ValueError('GUARD_PRIOR_ARCHIVE_HTTP') from None
        url=error.headers.get('Location','');host=urlparse(url).hostname or ''
        if not url.startswith('https://') or not host.endswith(('.blob.core.windows.net','.actions.githubusercontent.com','.githubusercontent.com','.amazonaws.com')):
            raise ValueError('GUARD_PRIOR_ARCHIVE_REDIRECT')
        # Never forward repository credentials to the artifact storage host.
        with urllib.request.urlopen(url,timeout=60) as response:binary=response.read(100_000_001)
    if len(binary)>100_000_000 or hashlib.sha256(binary).hexdigest()!=expected[7:]:raise ValueError('GUARD_PRIOR_ARCHIVE_INTEGRITY')
    names=['execution_outcome.json','receipt.json','financial_selection_research.json','delivery_result.json','watch_delivery_result.json','review_delivery_result.json']
    with zipfile.ZipFile(io.BytesIO(binary)) as source:
        if any(Path(n).is_absolute() or '..' in Path(n).parts for n in source.namelist()):raise ValueError('GUARD_PRIOR_ARCHIVE_PATH')
        result={}
        for name in names:
            if source.getinfo(name).file_size>5_000_000:raise ValueError('GUARD_PRIOR_RESULT_SIZE')
            result[name]=json.loads(source.read(name))
    return result


def completed_state(data,asof):
    outcome,receipt,selection=[data[n+'.json'] for n in ('execution_outcome','receipt','financial_selection_research')]
    if receipt.get('asof')!=asof:return 'OTHER_DATE'
    if outcome.get('asof')!=asof or selection.get('asof')!=asof:raise ValueError('GUARD_PRIOR_RESULT_DATE_MISMATCH')
    if outcome.get('program_status')!='COMPLETED' or outcome.get('operational_status') not in ('TOP5_READY','CASH_NO_ELIGIBLE'):
        return 'BLOCKED_PREVIOUS_HOLD_OR_ERROR'
    preview=False
    for family,name in [('top5','delivery_result'),('watch5','watch_delivery_result'),('review','review_delivery_result')]:
        result=data[name+'.json'];photos=result.get('photos',[])
        count=selection['selected_count'] if family=='top5' else len(result.get('selected',[]))
        status=result.get('status')
        if result.get('asof')!=asof or result.get('telegram_photos_sent',0)!=len(photos):raise ValueError('GUARD_PRIOR_DELIVERY_INTEGRITY')
        if status=='DRY_RUN' and not photos:preview=preview or bool(count);continue
        if count==0 and status in ('CASH','EMPTY','NOT_APPLICABLE') and not photos:continue
        if status!='SENT' or count!=len(photos) or not photos:return 'BLOCKED_PREVIOUS_SEND_UNCERTAIN'
        if any(type(p.get('telegram_message_id')) is not int or p['telegram_message_id']<=0 or
            p.get('destination_matches') is not True or not re.fullmatch(r'[0-9a-f]{64}',p.get('image_sha256','')) for p in photos):
            raise ValueError('GUARD_PRIOR_SEND_EVIDENCE_INVALID')
    return 'PREVIEW_ONLY' if preview else 'SKIP_COMPLETED'


def assess(client,env,clock=None,recover=False,load_archive=archive_outcome):
    clock=clock or datetime.now(timezone.utc)
    event=env.get('GITHUB_EVENT_NAME')
    preview=not recover and event=='workflow_dispatch' and str(env.get('C3_MANUAL_LIVE_DELIVERY','')).lower()!='true'
    if (not preview and env.get('GITHUB_REF_NAME')!='main') or env.get('GITHUB_REPOSITORY')!=REPOSITORY:
        raise ValueError('GUARD_MAIN_CONTEXT_REQUIRED')
    if recover and (event!='schedule' or env.get('GITHUB_RUN_ATTEMPT')!='1'):
        raise ValueError('GUARD_RECOVERY_CONTEXT_NOT_AUTHORIZED')
    if not recover and event not in ('schedule','workflow_dispatch'):raise ValueError('GUARD_EVENT_NOT_AUTHORIZED')
    plan=session_plan(clock,env.get('C3_MANUAL_ASOF','') if not recover else '')
    result=dict(asof=plan['asof'],entry_valid_until=plan['entry_valid_until'],execute=False,status='CHECKING',
        checked_at=clock.isoformat(),automatic_retry=False,orders_enabled=False)
    if preview:
        return dict(result,status='PREVIEW_ONLY',execute=True)
    if datetime.fromisoformat(plan['entry_valid_until'])<=clock:raise ValueError('GUARD_SIGNAL_EXPIRED')
    if env.get('GITHUB_RUN_ATTEMPT','1')!='1':raise ValueError('GUARD_RETRY_REQUIRES_REVIEW')
    if not recover and event=='workflow_dispatch':
        from c3_delivery_authorization import approved_manual_delivery
        if not approved_manual_delivery(env,plan['asof'],plan['entry_valid_until'],clock):raise ValueError('GUARD_MANUAL_NOT_AUTHORIZED')
    workflow=client.call('actions/workflows/'+WORKFLOW)
    if workflow.get('state')!='active':raise ValueError('GUARD_WORKFLOW_NOT_ACTIVE')
    run_list=client.call('actions/workflows/'+WORKFLOW+'/runs?per_page=100');runs=run_list.get('workflow_runs',[])
    own=str(env.get('GITHUB_RUN_ID',''))
    running=[r['id'] for r in runs if str(r['id'])!=own and r.get('head_branch','main')=='main' and r['status'] in ACTIVE
        and (recover or int(r['id'])<int(own or '0'))]
    if running:return dict(result,status='SKIP_RUNNING',source_run_ids=running)
    for family in ('c3_top5_daily','c3_watch5_daily','c3_review_daily'):
        for day in (plan['asof'],datetime.strptime(plan['asof'],'%Y%m%d').strftime('%Y-%m-%d')):
            for suffix in ('.json','.sent.json'):
                path='receipts/'+family+'/'+day+suffix;observed=marker(client,path)
                if observed is not None:
                    if str(observed.get('asof','')).replace('-','')!=plan['asof']:raise ValueError('GUARD_RECEIPT_DATE_MISMATCH')
                    return dict(result,status='SKIP_EXISTING_DELIVERY_RESERVATION',reservation_path=path,source_run_id=observed.get('run_id'))
    since=datetime.strptime(plan['asof']+'210000','%Y%m%d%H%M%S').replace(tzinfo=KST)
    relevant=[r for r in runs if str(r['id'])!=own and r.get('head_branch','main')=='main' and
        r.get('event') in ('schedule','workflow_dispatch') and datetime.fromisoformat(r['created_at'].replace('Z','+00:00'))>=since]
    if len(runs)>=100 and datetime.fromisoformat(runs[-1]['created_at'].replace('Z','+00:00'))>=since:
        raise ValueError('GUARD_RUN_HISTORY_INCOMPLETE')
    for run in relevant:
        if run['status']!='completed':
            if not recover and int(run['id'])>int(own or '0'):continue
            return dict(result,status='SKIP_RUNNING',source_run_id=run['id'])
        # An explicitly dated different target is not today's operation.
        title=run.get('display_title','');dated=re.search(r'C3 TOP5 \+ WATCH5 (\d{8})',title)
        if dated and dated.group(1)!=plan['asof']:continue
        if run.get('conclusion')!='success':return dict(result,status='BLOCKED_PREVIOUS_FAILED_RUN',source_run_id=run['id'])
        state=completed_state(load_archive(client,run),plan['asof'])
        if state not in ('OTHER_DATE','PREVIEW_ONLY'):return dict(result,status=state,source_run_id=run['id'])
    return dict(result,status='RUN',execute=True)


def recover_missing(client,env,event,clock=None,load_archive=archive_outcome):
    if event.get('schedule') not in RECOVERY_CRONS:raise ValueError('GUARD_RECOVERY_CRON_NOT_APPROVED')
    result=assess(client,env,clock,recover=True,load_archive=load_archive)
    if not result['execute']:return result
    path='receipts/c3_dispatch_daily/'+result['asof']+'.json'
    if marker(client,path) is not None:return dict(result,execute=False,status='SKIP_EXISTING_OR_UNCERTAIN_DISPATCH',reservation_path=path)
    request_id=PREFIX+result['asof']+'-'+env['GITHUB_RUN_ID']
    reservation=dict(asof=result['asof'],run_id=env['GITHUB_RUN_ID'],operation_request_id=request_id,
        state='RESERVED_BEFORE_DISPATCH_NO_AUTOMATIC_RETRY',created_at=result['checked_at'])
    try:
        reserved=client.call('contents/'+path,method='PUT',payload=dict(branch='main',message='Reserve one missing C3 daily dispatch '+result['asof'],
            content=base64.b64encode(json.dumps(reservation).encode()).decode()))
        if reserved.get('content',{}).get('path')!=path or not re.fullmatch(r'[0-9a-f]{40}',reserved.get('content',{}).get('sha','')):
            raise ValueError('GUARD_DISPATCH_RESERVATION_UNVERIFIED')
    except urllib.error.HTTPError as error:
        if error.code in (409,422):return dict(result,execute=False,status='SKIP_EXISTING_OR_UNCERTAIN_DISPATCH',reservation_path=path)
        raise
    response=client.call('actions/workflows/'+WORKFLOW+'/dispatches',method='POST',payload=dict(ref='main',
        inputs=dict(asof=result['asof'],financial_model='balanced',live_delivery=True,operation_request_id=request_id)))
    if response.get('http_status')!=204:raise ValueError('GUARD_DISPATCH_NOT_ACCEPTED_NO_RETRY')
    return dict(result,status='DISPATCH_ACCEPTED',reservation_path=path,operation_request_id=request_id,dispatch_http_status=204)


def verify_parent(env,asof,client=None):
    match=re.fullmatch(re.escape(PREFIX+asof+'-')+r'(\d+)',env.get('C3_OPERATION_REQUEST_ID',''))
    if not match:raise ValueError('GUARD_RECOVERY_PARENT_INVALID')
    client=client or GitHub(env.get('GH_TOKEN',''))
    run=client.call('actions/runs/'+match.group(1))
    if (run.get('event')!='schedule' or run.get('run_attempt')!=1 or run.get('head_branch')!='main' or run.get('path')!='.github/workflows/'+RECOVERY_WORKFLOW
        or run.get('repository',{}).get('full_name')!=REPOSITORY):raise ValueError('GUARD_RECOVERY_PARENT_INVALID')
    reservation=marker(client,'receipts/c3_dispatch_daily/'+asof+'.json')
    if not reservation or reservation.get('run_id')!=match.group(1) or reservation.get('operation_request_id')!=env['C3_OPERATION_REQUEST_ID']:
        raise ValueError('GUARD_RECOVERY_PARENT_RESERVATION_MISMATCH')
    return True


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--recover',action='store_true');args=parser.parse_args()
    root=Path('output/c3_schedule_guard');root.mkdir(parents=True,exist_ok=True)
    try:
        client=GitHub(os.environ['GH_TOKEN'])
        result=(recover_missing(client,os.environ,json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())) if args.recover else assess(client,os.environ))
    except Exception as error:
        result=dict(status='ERROR_STATE_UNVERIFIED',execute=False,automatic_retry=False,exception_type=type(error).__name__,
            reason=str(error) if type(error) is ValueError and str(error).startswith('GUARD_') else 'GUARD_FAILURE_NO_AUTOMATIC_RETRY')
    (root/'admission.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as stream:stream.write('execute='+str(result['execute']).lower()+'\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as stream:stream.write('### C3 daily admission / missing-event recovery\n\n'+json.dumps(result,ensure_ascii=False)+'\n')
    print('C3_SCHEDULE_GUARD',json.dumps(result,ensure_ascii=False))
    raise SystemExit(1 if result['status']=='ERROR_STATE_UNVERIFIED' else 0)


if __name__=='__main__':main()
