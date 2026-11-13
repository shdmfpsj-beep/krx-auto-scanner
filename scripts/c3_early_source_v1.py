"""Post-close price prefetch. Research archive only; never a signal or BUY gate."""
import argparse,base64,gzip,hashlib,json,os,re,tempfile,time
from collections import Counter
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo
from c3_telegram_inputs import GitHub,RESEARCH,canonical,ServiceError
from c3_morning_source_v1 import cache_rows,normalized_hash,FIELDS,compare

PREFIX='reports/c3_early_source_v1/'
FDR='FinanceData/fdr_krx_data_cache'
KST=ZoneInfo('Asia/Seoul')
WAKEUPS=('Free v6.4 daily date-locked source audit and forward quarantine',
         'C3 morning prior-close read-only observation (NO ORDERS)')

def stamp():return datetime.now(timezone.utc).isoformat()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def clock(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) else value
    if result.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    return result.astimezone(timezone.utc)
def write(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(canonical(obj)+b'\n')

def trusted_wakeup(event,repository):
    r=event.get('workflow_run') or {}
    return bool(repository=='shdmfpsj-beep/krx-auto-scanner' and r.get('name') in WAKEUPS and
        r.get('head_branch')=='main' and (r.get('head_repository') or {}).get('full_name')==repository and
        r.get('status')=='completed' and r.get('event') in ('schedule','push','workflow_dispatch') and
        r.get('conclusion') in ('success','failure','timed_out'))

def session_context(now,day=None):
    import exchange_calendars as xc
    now=clock(now);today=now.astimezone(KST).date()
    cal=xc.get_calendar('XKRX',start=str(today-timedelta(days=500)),end=str(today+timedelta(days=10)))
    if day is None:
        session=cal.date_to_session(str(today),direction='previous')
        if cal.session_close(session).to_pydatetime()>now:
            session=cal.previous_session(session)
    else:
        if not cal.is_session(day):raise ValueError('NOT_A_REFERENCE_TRADING_DAY')
        session=cal.date_to_session(day)
    close=cal.session_close(session).to_pydatetime()
    if close>now:raise ValueError('SESSION_NOT_COMPLETED_AT_CUTOFF')
    return dict(day=session.strftime('%Y-%m-%d'),reference_close_at=close.isoformat(),
        reference_calendar='XKRX',calendar_version=xc.__version__,calendar_is_official_attestation=False)

def quality(rows,day):
    from c3_source_recovery_v1 import validate
    result=validate(rows,day)
    if set(Counter(r['market'] for r in rows))!={'KOSPI','KOSDAQ'}:raise ValueError('BOTH_BOARDS_REQUIRED')
    if any(not re.fullmatch(r'[0-9A-Z]{6}',r['ticker']) or not r['name'] for r in rows):raise ValueError('SOURCE_IDENTITY_INVALID')
    return result

def eligibility(meta,cutoff):
    boundary=clock(cutoff);context=session_context(boundary,meta['asof'])
    if clock(meta['snapshot_commit_at'])>boundary or clock(meta['file_commit_at'])>boundary:raise ValueError('FUTURE_COMMIT_AT_REPLAY_CUTOFF')
    if clock(meta['file_commit_at'])<clock(context['reference_close_at']):raise ValueError('PRE_CLOSE_FILE_VERSION')
    return context

def fdr_snapshot(day,cutoff=None,snapshot=None,gh=None):
    """Read a dated file's commit, not the unrelated repository HEAD timestamp."""
    gh=gh or GitHub(os.environ['GH_TOKEN'],FDR);cutoff=clock(cutoff or stamp())
    path='data/listing/krx/'+day+'.csv'
    query='commits?path='+quote(path,safe='')+'&per_page=1&until='+quote(cutoff.isoformat(),safe='')
    if snapshot:query+='&sha='+quote(snapshot,safe='')
    versions=gh.api(query)
    if not versions:raise ValueError('DATED_FILE_NOT_PUBLISHED_AT_CUTOFF')
    changed=versions[0];snapshot=snapshot or changed['sha']
    revision=gh.api('commits/'+snapshot)
    if clock(revision['commit']['committer']['date'])>cutoff:raise ValueError('FUTURE_COMMIT_AT_REPLAY_CUTOFF')
    raw=gh.file(path,snapshot);rows,excluded=cache_rows(raw,day)
    meta=dict(schema='C3_EARLY_PRICE_SNAPSHOT_V1',asof=day,provider='FDR_DATED_CSV',repository=FDR,path=path,
        snapshot_commit=snapshot,snapshot_commit_at=revision['commit']['committer']['date'],
        file_commit=changed['sha'],file_commit_at=changed['commit']['committer']['date'],
        availability_evidence='GIT_COMMIT_TIMESTAMP_NOT_SERVER_PUBLICATION_ATTESTATION',
        cutoff_at=cutoff.isoformat(),collected_at=stamp(),raw_sha256=sha(raw),raw_bytes=len(raw),
        normalized_rows_sha256=normalized_hash(rows),rows=len(rows),markets=dict(Counter(r['market'] for r in rows)),
        excluded=excluded,quality=quality(rows,day),source_status='SINGLE_SOURCE_UNVERIFIED',
        price_basis='UNADJUSTED_AS_REPORTED_FDR',corporate_actions_adjusted=False,
        price_date_assertion='DATED_FILE_NOT_OFFICIAL_DAY_ATTESTATION',regular_only_certified=False,
        financial_pit_verified=False,buy_approved=False,orders_enabled=False,telegram_requests=0)
    meta.update(eligibility(meta,cutoff));return raw,rows,meta

def differences(left,right):
    a={r['ticker']:r for r in left};b={r['ticker']:r for r in right};changed={}
    for k in ('name','market')+FIELDS:
        changed[k]=sum(a[t][k]!=b[t][k] for t in a.keys()&b.keys())
    exact=sum(all(a[t][k]==b[t][k] for k in ('name','market')+FIELDS) for t in a.keys()&b.keys())
    return dict(left_rows=len(a),right_rows=len(b),added_codes=sorted(b.keys()-a.keys()),
        removed_codes=sorted(a.keys()-b.keys()),matched_rows=exact,
        match_rate_pct=100*exact/max(len(a),len(b),1),changed_fields=changed)

def blob_bytes(gh,tree,path):
    if path not in tree:return None
    return base64.b64decode(gh.api('git/blobs/'+tree[path])['content'])

def unseal(raw,key):
    from c3_supply_v11 import open_sealed
    with tempfile.TemporaryDirectory(prefix='c3-early-check-') as root:
        p=Path(root)/'source.aesgcm';p.write_bytes(raw);return gzip.decompress(open_sealed(p,key))

def publish(raw,rows,meta,gh=None,key=None):
    """Append content addressed encrypted objects; never write the original ledger."""
    from c3_supply_v11 import encrypt_bytes
    gh=gh or GitHub(os.environ['GH_TOKEN']);key=key or os.environ.get('KRX_AUTH_KEY')
    if not key:raise ValueError('ARCHIVE_KEY_REQUIRED')
    eligibility(meta,meta['cutoff_at']);quality(rows,meta['asof'])
    if sha(raw)!=meta['raw_sha256'] or normalized_hash(rows)!=meta['normalized_rows_sha256']:raise ValueError('ARCHIVE_INPUT_HASH_MISMATCH')
    payload=canonical(dict(asof=meta['asof'],rows=rows));pdigest=sha(payload)
    price_path=PREFIX+'objects/'+pdigest+'.aesgcm';raw_path=PREFIX+'raw/'+sha(raw)+'.aesgcm'
    version_path=PREFIX+'versions/'+meta['asof']+'/'+meta['file_commit']+'-'+sha(raw)+'.json'
    pointer=PREFIX+'days/'+meta['asof']+'.json'
    for attempt in range(3):
        head=gh.head(RESEARCH);commit=gh.api('git/commits/'+head);inventory=gh.api('git/trees/'+head+'?recursive=1')
        if inventory.get('truncated'):raise ValueError('ARCHIVE_TREE_TRUNCATED')
        tree={r['path']:r['sha'] for r in inventory['tree'] if r['type']=='blob'};entries=[]
        for path,body in ((price_path,payload),(raw_path,raw)):
            old=blob_bytes(gh,tree,path)
            if old is not None:
                if unseal(old,key)!=body:raise ValueError('IMMUTABLE_EARLY_OBJECT_CONFLICT')
            else:
                sealed=encrypt_bytes(gzip.compress(body,mtime=0),key)
                blob=gh.api('git/blobs',method='POST',payload={'content':base64.b64encode(sealed).decode(),'encoding':'base64'})
                entries.append(dict(path=path,mode='100644',type='blob',sha=blob['sha']))
        previous=blob_bytes(gh,tree,pointer);previous=json.loads(previous) if previous else None
        state='FIRST_VERSION';diff=None
        if previous:
            if previous['normalized_rows_sha256']==meta['normalized_rows_sha256']:
                state='UNCHANGED' if previous['raw_sha256']==meta['raw_sha256'] else 'RAW_REVISION_PRICE_UNCHANGED'
            else:
                state='PRICE_REVISION'
                past=json.loads(unseal(blob_bytes(gh,tree,previous['price_object']),key))
                diff=differences(past['rows'],rows)
        version=dict(meta,price_object=price_path,price_payload_sha256=pdigest,raw_object=raw_path)
        if version_path not in tree:entries.append(dict(path=version_path,mode='100644',type='blob',content=(canonical(version)+b'\n').decode()))
        else:
            recorded=json.loads(blob_bytes(gh,tree,version_path))
            if any(recorded[k]!=version[k] for k in ('asof','raw_sha256','normalized_rows_sha256','price_object','file_commit')):raise ValueError('IMMUTABLE_EARLY_VERSION_CONFLICT')
            version=recorded
        # Historical replays cannot roll a newer observation back.
        advance=not previous or clock(version['file_commit_at'])>clock(previous['file_commit_at'])
        if advance:entries.append(dict(path=pointer,mode='100644',type='blob',content=(canonical(version)+b'\n').decode()))
        receipt=dict(schema='C3_EARLY_ARCHIVE_RECEIPT_V1',asof=meta['asof'],recorded_at=stamp(),
            source_run_id=os.environ.get('GITHUB_RUN_ID','local'),source_run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT','1'),
            version_path=version_path,normalized_rows_sha256=meta['normalized_rows_sha256'],raw_sha256=meta['raw_sha256'],
            state=state,price_difference=diff,latest_advanced=advance,regular_only_certified=False,buy_approved=False,telegram_requests=0)
        receipt_path=PREFIX+'observations/'+meta['asof']+'/'+str(receipt['source_run_id'])+'-'+str(receipt['source_run_attempt'])+'.json'
        if receipt_path not in tree:entries.append(dict(path=receipt_path,mode='100644',type='blob',content=(canonical(receipt)+b'\n').decode()))
        if not entries:return dict(receipt,status='ALREADY_RECORDED',commit=head)
        if any(not e['path'].startswith(PREFIX) for e in entries):raise ValueError('NONRESEARCH_ARCHIVE_WRITE')
        created=gh.api('git/trees',method='POST',payload={'base_tree':commit['tree']['sha'],'tree':entries})
        new=gh.api('git/commits',method='POST',payload={'parents':[head],'tree':created['sha'],'message':'data: preserve post-close prefetch '+meta['asof']+' (research only, no send)'})
        try:gh.api('git/refs/heads/'+RESEARCH,method='PATCH',payload={'sha':new['sha'],'force':False})
        except ServiceError:
            if attempt==2:raise
            continue
        return dict(receipt,status='ARCHIVED',commit=new['sha'])
    raise ValueError('ARCHIVE_RETRY_EXHAUSTED')

def load_prefetch(day,out,gh=None,key=None):
    """Exact-day encrypted snapshot for morning comparison with fresh official data."""
    gh=gh or GitHub(os.environ['GH_TOKEN']);key=key or os.environ.get('KRX_AUTH_KEY');ref=gh.head(RESEARCH)
    raw=gh.file(PREFIX+'days/'+day+'.json',ref,missing_ok=True)
    if raw is None:raise ValueError('NO_EARLY_ARCHIVE_FOR_REQUESTED_DAY')
    meta=json.loads(raw)
    if meta.get('asof')!=day or meta.get('provider')!='FDR_DATED_CSV':raise ValueError('EARLY_ARCHIVE_DAY_OR_PROVIDER_MISMATCH')
    eligibility(meta,stamp())
    for field,folder in [('price_object','objects/'),('raw_object','raw/')]:
        if not re.fullmatch(re.escape(PREFIX+folder)+r'[a-f0-9]{64}\.aesgcm',meta[field]):raise ValueError('EARLY_ARCHIVE_OBJECT_PATH_INVALID')
    sealed=gh.file(meta['price_object'],ref);payload=unseal(sealed,key)
    if sha(payload)!=meta['price_payload_sha256']:raise ValueError('EARLY_ARCHIVE_PAYLOAD_HASH_MISMATCH')
    doc=json.loads(payload);rows=doc['rows']
    if doc['asof']!=day or normalized_hash(rows)!=meta['normalized_rows_sha256']:raise ValueError('EARLY_ARCHIVE_PRICE_HASH_OR_DATE_MISMATCH')
    rawcsv=unseal(gh.file(meta['raw_object'],ref),key)
    if sha(rawcsv)!=meta['raw_sha256']:raise ValueError('EARLY_ARCHIVE_RAW_HASH_MISMATCH')
    parsed,excluded=cache_rows(rawcsv,day);compare(rows,parsed,day);q=quality(rows,day)
    out=Path(out);out.mkdir(parents=True,exist_ok=True);(out/'original.csv').write_bytes(rawcsv)
    return rows,dict(provider='FINANCEDATA_KRX_EARLY_ARCHIVE',repository=FDR,path=meta['path'],ref=meta['file_commit'],
        received_at=stamp(),raw_sha256=meta['raw_sha256'],rows=len(rows),markets=meta['markets'],excluded=excluded,
        quality=q,early_archive_used=True,early_archive_ref=ref,early_collected_at=meta['collected_at'],
        file_commit_at=meta['file_commit_at'],price_basis=meta['price_basis'],regular_only_certified=False)

def capture(out,day=None,cutoff=None,snapshot=None,persist=False,attempts=2):
    if not 1<=attempts<=2:raise ValueError('EARLY_RETRY_LIMIT')
    now=clock(cutoff or stamp());context=session_context(now,day);day=context['day'];errors=[]
    for n in range(attempts):
        try:
            raw,rows,meta=fdr_snapshot(day,now,snapshot)
            out=Path(out);out.mkdir(parents=True,exist_ok=True);(out/'original.csv').write_bytes(raw)
            write(out/'normalized_market.json',dict(asof=day,rows=rows,normalized_rows_sha256=normalized_hash(rows)))
            result=dict(meta,status='PREFETCHED_RESEARCH_ONLY',attempts=n+1,prior_errors=errors)
            if persist:result['publication']=publish(raw,rows,meta)
            write(out/'prefetch.json',result);return result
        except (ValueError,ServiceError) as exc:
            errors.append(dict(attempt=n+1,error_type=type(exc).__name__,reason=str(exc)[:150]))
            if n+1<attempts:time.sleep(2)
    result=dict(schema='C3_EARLY_SOURCE_RESULT_V1',asof=day,status='PREFETCH_HELD_SOURCE_NOT_READY',rows=0,
        attempts=attempts,errors=errors,collected_at=stamp(),regular_only_certified=False,buy_approved=False,telegram_requests=0)
    write(Path(out)/'prefetch.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--date');p.add_argument('--cutoff');p.add_argument('--snapshot');p.add_argument('--publish',action='store_true');a=p.parse_args()
    r=capture(a.out,a.date,a.cutoff,a.snapshot,a.publish)
    print(json.dumps({k:r.get(k) for k in ('asof','status','rows','markets','file_commit','file_commit_at','publication')},ensure_ascii=False))
    if r['status']!='PREFETCHED_RESEARCH_ONLY':raise SystemExit(2)
