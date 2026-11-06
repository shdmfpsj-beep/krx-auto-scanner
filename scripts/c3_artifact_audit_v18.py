"""Resolve dated audit inputs by content and digest; never replace missing history."""
import argparse,hashlib,io,json,os,re,shutil,subprocess,tempfile,zipfile
from datetime import datetime,timedelta,timezone
from pathlib import Path,PurePosixPath

REPO='shdmfpsj-beep/krx-auto-scanner'
LAYOUTS={
    'freeze':('frozen_v63_manifest.json','frozen_v63_signals.json'),
    'market':('meta.json','KOSPI.csv','KOSDAQ.csv'),
    'forward':('forward_v63_status.json','forward_v63_all.csv'),
    'recovery':('status.json','candidates.csv','candidate_daily_history_v52.csv')}
WORKFLOWS={'freeze':'forward_freeze_v63.yml','market':'forward_market_slice_v63.yml',
           'forward':'forward_watch_v63.yml','recovery':'krx_recovery_scan.yml'}


class SourceUnavailable(ValueError):
    pass


def sha(body):return hashlib.sha256(body).hexdigest()
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def gh(path,binary=False):
    # No polling or retry for absent/deleted artifacts. Transport is bounded.
    try:
        p=subprocess.run(['gh','api','repos/'+REPO+'/'+path],capture_output=True,timeout=60)
    except subprocess.TimeoutExpired:raise SourceUnavailable('GITHUB_REQUEST_TIMEOUT')
    if p.returncode:
        code='GITHUB_PERMISSION_REJECTED' if b'403' in p.stderr or b'401' in p.stderr else 'GITHUB_RESOURCE_UNAVAILABLE'
        raise SourceUnavailable(code)
    return p.stdout if binary else json.loads(p.stdout)


def safe_archive(body,metadata):
    if len(body)>100*1024*1024:raise ValueError('ARTIFACT_ARCHIVE_TOO_LARGE')
    actual=sha(body);declared=metadata.get('digest')
    if declared and declared!='sha256:'+actual:raise ValueError('ARTIFACT_ARCHIVE_DIGEST_MISMATCH')
    z=zipfile.ZipFile(io.BytesIO(body));total=0
    for member in z.infolist():
        p=PurePosixPath(member.filename);mode=member.external_attr>>16
        if p.is_absolute() or '..' in p.parts or '\\' in member.filename or mode&0o170000==0o120000:
            raise ValueError('UNSAFE_ARTIFACT_MEMBER')
        total+=member.file_size
        if member.file_size>120*1024*1024 or total>250*1024*1024:raise ValueError('ARTIFACT_EXPANDED_TOO_LARGE')
    if len(z.namelist())!=len(set(z.namelist())):raise ValueError('DUPLICATE_ARTIFACT_MEMBER')
    return z,actual


class Resolver:
    def __init__(self,reader=gh,downloader=None):
        self.reader=reader;self.downloader=downloader or (lambda i:gh('actions/artifacts/'+str(i)+'/zip',True));self.events=[]

    def inventory(self,run_id,role):
        if not re.fullmatch(r'[0-9]{8,14}',str(run_id)):raise ValueError('INVALID_RUN_ID')
        run=self.reader('actions/runs/'+str(run_id))
        if run.get('id')!=int(run_id) or run.get('path')!='.github/workflows/'+WORKFLOWS[role] or run.get('conclusion')!='success' or run.get('status')!='completed' or run.get('head_branch')!='main':
            raise ValueError('WRONG_OR_UNSUCCESSFUL_SOURCE_RUN')
        if run.get('head_repository',{}).get('full_name',REPO)!=REPO:raise ValueError('FOREIGN_SOURCE_REPOSITORY')
        items=[]
        for page in range(1,6):
            data=self.reader(f'actions/runs/{run_id}/artifacts?per_page=100&page={page}');items+=data['artifacts']
            if len(data['artifacts'])<100:break
        else:raise ValueError('ARTIFACT_INVENTORY_PAGE_LIMIT')
        for a in items:
            if a.get('workflow_run',{}).get('id')!=int(run_id):raise ValueError('ARTIFACT_RUN_ID_MISMATCH')
        if not items:raise SourceUnavailable('SOURCE_ARTIFACT_ABSENT')
        active=[a for a in items if not a.get('expired') and a.get('size_in_bytes',0)>0]
        if not active:raise SourceUnavailable('SOURCE_ARTIFACT_EXPIRED_OR_EMPTY')
        if len(active)>4:raise ValueError('AMBIGUOUS_ARTIFACT_INVENTORY')
        return active

    def download(self,run_id,role,outdir):
        candidates=self.inventory(run_id,role);matches=[];root=Path(outdir)
        for a in candidates:
            z,digest=safe_archive(self.downloader(a['id']),a)
            names=set(z.namelist());folders={str(PurePosixPath(n).parent) for n in names}
            relevant=[p for p in folders if all(str(PurePosixPath(p)/f) in names for f in LAYOUTS[role])]
            if relevant:matches.append((a,z,digest,relevant))
        if not matches:raise SourceUnavailable('SOURCE_ARTIFACT_REQUIRED_FILES_ABSENT')
        if len(matches)!=1:raise ValueError('AMBIGUOUS_ARTIFACT_CONTENT')
        a,z,digest,folders=matches[0];root.mkdir(parents=True,exist_ok=True);z.extractall(root)
        receipt=dict(run_id=str(run_id),role=role,artifact_id=a['id'],artifact_name=a['name'],
            archive_sha256=digest,github_digest_verified=bool(a.get('digest')),expires_at=a.get('expires_at'),
            file_sha256={n:sha(z.read(n)) for n in sorted(z.namelist()) if not n.endswith('/')})
        self.events.append(receipt);write(root/'artifact_receipt_v18.json',receipt)
        return root,[root/p for p in sorted(folders)]

    def recovery(self,manifest,outdir):
        run=manifest['source_run_ids']['recovery_run_id'];day=manifest['asof']
        root,folders=self.download(run,'recovery',outdir)
        if len(folders)!=1:raise ValueError('AMBIGUOUS_RECOVERY_LAYOUT')
        folder=folders[0];status=json.loads((folder/'status.json').read_text())
        if status.get('market_data_date')!=day or status.get('scan_complete') is not True or status.get('data_date_verified') is not True:
            raise ValueError('RECOVERY_TRADE_DAY_OR_COMPLETENESS_MISMATCH')
        for name,key in [('status.json','recovery_status'),('candidate_daily_history_v52.csv','recovery_history')]:
            expected=manifest['source_sha256'].get(key)
            if not expected or sha((folder/name).read_bytes())!=expected:raise ValueError('RECOVERY_FROZEN_SOURCE_HASH_MISMATCH')
        return folder


def recent_runs(role,reader):
    return [r for r in reader('actions/workflows/'+WORKFLOWS[role]+'/runs?branch=main&status=success&per_page=40')['workflow_runs'] if r.get('conclusion')=='success']


def audit(outdir,reader=gh,resolver=None):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True);resolver=resolver or Resolver(reader);unavailable=[];completed=[]
    cache=root/'inputs';freeze=[];markets={};forward={};frozen_by_day={}
    for role in ('freeze','market','forward'):
        runs=recent_runs(role,reader)
        if role=='forward':runs=runs[:1]
        for run in runs:
            try:
                _,folders=resolver.download(run['id'],role,cache/role/str(run['id']))
                for folder in folders:
                    if role=='freeze':
                        from forward_ledger_v63 import verify_snapshot
                        m=json.loads((folder/'frozen_v63_manifest.json').read_text());s=json.loads((folder/'frozen_v63_signals.json').read_text());verify_snapshot(m,s)
                        if datetime.fromisoformat(m['asof']).date()<datetime.now(timezone.utc).date()-timedelta(days=25):continue
                        old=frozen_by_day.get(m['asof'])
                        if old and old['frozen_payload_sha256']!=m['frozen_payload_sha256']:raise ValueError('CONFLICTING_FROZEN_SAME_DAY_HASH')
                        if not old:
                            freeze.append((m,folder));frozen_by_day[m['asof']]=m
                    elif role=='market':
                        m=json.loads((folder/'meta.json').read_text());day=m['asof']
                        from source_consensus_v64 import records_from_v18
                        records_from_v18(folder,day)
                        if day in markets and markets[day][1]['sha256']!=m['sha256']:raise ValueError('CONFLICTING_MARKET_SNAPSHOTS')
                        markets.setdefault(day,(folder,m))
                    else:
                        m=json.loads((folder/'forward_v63_status.json').read_text());forward.setdefault(m['asof'],(folder,m))
            except SourceUnavailable as exc:unavailable.append(dict(role=role,run_id=str(run['id']),status=str(exc)))
    if not freeze:unavailable.append(dict(status='NO_USABLE_FROZEN_DATED_INPUTS'))
    for manifest,folder in freeze:
        day=manifest['asof'];target=root/day;target.mkdir(exist_ok=True)
        result=dict(asof=day,recovery_run_id=manifest['source_run_ids']['recovery_run_id'],trade_approved=False,decision='CASH')
        try:
            recovery=resolver.recovery(manifest,cache/'recovery'/str(result['recovery_run_id']))
            if day not in markets or day not in forward:raise SourceUnavailable('MATCHING_DATED_MARKET_OR_FORWARD_ABSENT')
            if forward[day][1].get('frozen_payload_sha256')!=manifest['frozen_payload_sha256']:raise ValueError('FORWARD_FREEZE_HASH_MISMATCH')
            for script,args in [
                ('source_consensus_v64.py',['--recovery',recovery,'--market-day',markets[day][0],'--freeze',folder,'--outdir',target/'consensus']),
                ('forward_source_gate_v64.py',['--freeze',folder,'--source-audit',target/'consensus','--forward',forward[day][0],'--outdir',target/'gate'])]:
                subprocess.run(['python',str(Path(__file__).with_name(script)),*map(str,args)],check=True,timeout=120)
            result.update(status='DATED_AUDIT_COMPLETED_UNCERTIFIED',independent_regular_only_certified=False);completed.append(day)
        except SourceUnavailable as exc:
            result.update(status=str(exc),historical_source_recovered=False);unavailable.append(result)
        write(target/'availability.json',result)
    summary=dict(schema='C3_ARTIFACT_AUDIT_V18',status='COMPLETED' if completed and not unavailable else 'SOURCE_INPUTS_UNAVAILABLE' if not completed else 'PARTIAL',
        audit_completed_days=sorted(set(completed)),unavailable=unavailable,downloads=resolver.events,
        trade_approved=False,orders_enabled=False,telegram_sends=0,archive_retention_days=90)
    write(root/'availability_summary.json',summary);return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);p.add_argument('--probe-manifest');args=p.parse_args()
    if args.probe_manifest:
        m=json.loads(Path(args.probe_manifest).read_text());r=Resolver();result=dict(asof=m['asof'],run_id=m['source_run_ids']['recovery_run_id'])
        try:r.recovery(m,Path(args.outdir)/'recovery');result['status']='RECOVERED_EXACT_FROZEN_HASHES'
        except SourceUnavailable as exc:result.update(status=str(exc),historical_source_recovered=False,download_attempts=0)
        write(Path(args.outdir)/'availability_summary.json',result)
    else:result=audit(args.outdir)
    print(json.dumps(result,ensure_ascii=False))
