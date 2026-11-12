"""Cancel one observed obsolete queued sender; never send or edit receipts."""
import argparse,json,os,time,urllib.request,urllib.error
from pathlib import Path

REPO='shdmfpsj-beep/krx-auto-scanner'
TARGET=43097349217
OLD_HEAD='f25b10c5cd6052236a0c3bacba0c00396487af5c'


def eligible(run):
    return bool(run.get('id')==TARGET and run.get('name')=='C3 TOP2 Telegram notification' and
        run.get('event')=='schedule' and run.get('head_sha')==OLD_HEAD and run.get('head_branch')=='main' and
        run.get('status')=='queued' and run.get('repository',{}).get('full_name')==REPO)


def retire(call,pause=time.sleep):
    path='actions/runs/'+str(TARGET)
    run=call('GET',path)
    if run.get('status')=='completed':
        return dict(status='ALREADY_COMPLETED_NO_ACTION',run_id=TARGET,conclusion=run.get('conclusion'),cancel_requests=0,telegram_requests=0)
    if not eligible(run):return dict(status='NOT_CANCELLED_GUARD_MISMATCH',run_id=TARGET,cancel_requests=0,telegram_requests=0)
    attempts=[]
    for endpoint in ('cancel','force-cancel'):
        try:
            call('POST',path+'/'+endpoint);attempts.append(dict(endpoint=endpoint,result='ACCEPTED'));break
        except urllib.error.HTTPError as exc:
            attempts.append(dict(endpoint=endpoint,http_status=exc.code))
            check=call('GET',path)
            if check.get('status')=='completed':
                return dict(status='CANCELLED' if check.get('conclusion')=='cancelled' else 'COMPLETED_AFTER_CANCEL_REQUEST',run_id=TARGET,conclusion=check.get('conclusion'),cancel_requests=len(attempts),attempts=attempts,telegram_requests=0)
            # One documented force-cancel attempt, still guarded to this exact
            # obsolete queued run. Never force-cancel an active execution.
            if exc.code==409 and endpoint=='cancel' and eligible(check):continue
            jobs=call('GET',path+'/jobs?per_page=100')
            return dict(status='BLOCKED_GITHUB_CANCEL_CONFLICT' if exc.code==409 else 'CANCEL_API_FAILED',
                run_id=TARGET,observed_status=check.get('status'),observed_conclusion=check.get('conclusion'),
                observed_jobs=jobs.get('total_count'),cancel_requests=len(attempts),attempts=attempts,telegram_requests=0)
    for i in range(3):
        check=call('GET',path)
        if check.get('status')=='completed':
            return dict(status='CANCELLED' if check.get('conclusion')=='cancelled' else 'COMPLETED_AFTER_CANCEL_REQUEST',run_id=TARGET,conclusion=check.get('conclusion'),cancel_requests=len(attempts),attempts=attempts,telegram_requests=0)
        if i<2:pause(1)
    return dict(status='CANCEL_REQUESTED_NOT_YET_CONFIRMED',run_id=TARGET,cancel_requests=len(attempts),attempts=attempts,telegram_requests=0)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
    if os.environ.get('GITHUB_REPOSITORY')!=REPO or os.environ.get('GITHUB_REF')!='refs/heads/main' or os.environ.get('GITHUB_EVENT_NAME')!='push':
        raise ValueError('MAIN_DEPLOYMENT_ONLY')
    def call(method,path):
        req=urllib.request.Request('https://api.github.com/repos/'+REPO+'/'+path,method=method,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
        with urllib.request.urlopen(req,timeout=25) as f:
            raw=f.read();return json.loads(raw) if raw else {}
    answer=retire(call);out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(answer,indent=2)+'\n');print(json.dumps(answer))
    if answer['status'] not in ('CANCELLED','ALREADY_COMPLETED_NO_ACTION','COMPLETED_AFTER_CANCEL_REQUEST'):raise SystemExit(1)
