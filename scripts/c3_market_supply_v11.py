"""Date-locked KRX mirror fallback. Distinct provenance, never NAVER splicing."""
import argparse,csv,io,json,os,re,time
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from c3_supply_v11 import digest,write,now,completed_day
from c3_runtime_v10 import quality

CACHE_REPO='FinanceData/fdr_krx_data_cache'
FIELDS=('market','ticker','name','asof','open','high','low','close','volume','turnover_krw','valid_daily_bar','action_boundary')


def number(v):
    import math
    n=float(str(v).replace(',',''))
    if not math.isfinite(n):raise ValueError('NONFINITE_PRICE')
    return n


def normalize_cache(body,day):
    rows=[];seen=set();excluded=[]
    for r in csv.DictReader(io.StringIO(body.decode('utf-8-sig'))):
        market={'STK':'KOSPI','KSQ':'KOSDAQ'}.get(r.get('MarketId'))
        if market is None:excluded.append(r.get('Code'));continue
        ticker=r['Code']
        if not re.fullmatch('[A-Z0-9]{6}',ticker):raise ValueError('CACHE_SECURITY_CODE_FORMAT')
        if ticker in seen:raise ValueError('CACHE_DUPLICATE_SECURITY')
        seen.add(ticker)
        vals={k:number(r[c]) for k,c in [('open','Open'),('high','High'),('low','Low'),('close','Close'),('volume','Volume'),('turnover_krw','Amount')]}
        o,h,l,c,v,t=(vals[k] for k in ('open','high','low','close','volume','turnover_krw'))
        valid=0<l<=min(o,c)<=max(o,c)<=h and v>0 and t>0
        rows.append(dict(vals,market=market,ticker=ticker,name=r['Name'],asof=day,valid_daily_bar=valid,action_boundary='',previous_reference=c-number(r['Changes'])))
    if not rows:raise ValueError('CACHE_EMPTY')
    return rows,excluded


def control_check(control,cached):
    a={r['ticker']:r for r in control};b={r['ticker']:r for r in cached}
    missing=sorted(a.keys()-b.keys());extra=sorted(b.keys()-a.keys());bad=[];names=[]
    for t in sorted(a.keys()&b.keys()):
        fields=[k for k in ('open','high','low','close','volume','turnover_krw') if number(a[t][k])!=number(b[t][k])]
        if a[t]['market']!=b[t]['market']:fields.append('market')
        if fields:bad.append(dict(ticker=t,fields=fields))
        if a[t]['name']!=b[t]['name']:names.append(t)
    return dict(rows=len(a),compared=len(a.keys()&b.keys()),missing=missing,extra=extra,mismatches=bad,name_differences=names,complete_match=bool(a) and not(missing or extra or bad))


def retrieve(url,audit,private=None):
    headers={'User-Agent':'C3-ReadOnly-Research/11','Accept':'application/json,text/csv,*/*'}
    if url.startswith('https://api.github.com/') and os.environ.get('GH_TOKEN'):headers['Authorization']='Bearer '+os.environ['GH_TOKEN']
    req=Request(url,headers=headers)
    for attempt in (1,2):
        begin=time.monotonic();status=None;body=b'';failure=None
        try:
            with urlopen(req,timeout=25) as r:body=r.read(8*1024*1024+1);status=r.getcode()
        except HTTPError as exc:
            status=exc.code;body=exc.read(8*1024*1024+1)
            failure='ACCESS_REJECTED_NO_BYPASS' if status in (401,403) else 'RATE_LIMITED' if status==429 else 'HTTP_SERVICE_ERROR'
        except (URLError,TimeoutError,OSError):failure='NETWORK_UNAVAILABLE'
        if len(body)>8*1024*1024:failure='SUPPLY_RESPONSE_TOO_LARGE'
        audit.append(dict(url=url,http_status=status,attempt=attempt,status=failure or 'RECEIVED',received_at=now(),sha256=digest(body),bytes=len(body),seconds=time.monotonic()-begin))
        if private:
            p=Path(private)/(str(len(audit))+'.bin');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
            write(Path(private)/'transport.json',audit)
        if failure is None:return body
        if attempt==1 and (status==429 or (status or 0)>=500 or failure=='NETWORK_UNAVAILABLE'):time.sleep(1)
        else:raise ValueError(failure)


def mirror(day,control_dir,outdir,private_dir=None,previous_day=None):
    """Independent control CHECK, not an assertion of independent data vendors.

    The mirror and direct API share KRX as ultimate origin. Current-day direct
    official corroboration remains pending when the primary API is empty.
    """
    audit=[];out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    if day>completed_day():raise ValueError('FUTURE_OR_UNFINISHED_EOD')
    meta=json.loads((Path(control_dir)/'krx_v65_collect_status.json').read_text());control=[]
    if not meta.get('krx_eod_authenticated') or meta['asof']>=day:raise ValueError('DATED_PRIOR_OFFICIAL_CONTROL_REQUIRED')
    for m in ('KOSPI','KOSDAQ'):
        p=Path(control_dir)/(m+'_official.csv')
        if digest(p.read_bytes())!=meta['market_file_sha256'][m]:raise ValueError('OFFICIAL_CONTROL_HASH_MISMATCH')
        with p.open(encoding='utf-8-sig') as f:control+=list(csv.DictReader(f))
    clock=json.loads(retrieve('https://data.krx.co.kr/comm/bldAttendant/executeForResourceBundle.cmd?baseName=krx.mdc.i18n.component&key=B128.bld',audit,private_dir))
    value=clock['result']['output'][0]['max_work_dt']
    if not re.fullmatch('[0-9]{8}',value):raise ValueError('EXCHANGE_DATE_CLOCK_SCHEMA')
    last=value[:4]+'-'+value[4:6]+'-'+value[6:]
    if day>last:raise ValueError('MIRROR_SESSION_NOT_PUBLISHED_BY_EXCHANGE_CLOCK')
    commit=json.loads(retrieve('https://api.github.com/repos/'+CACHE_REPO+'/commits/master',audit,private_dir))
    pin=commit['sha']
    if not re.fullmatch('[0-9a-f]{40}',pin):raise ValueError('CACHE_PIN_INVALID')
    if datetime.fromisoformat(commit['commit']['committer']['date'].replace('Z','+00:00'))>datetime.now(timezone.utc):raise ValueError('CACHE_COMMIT_IN_FUTURE')
    def fetch(d):return retrieve('https://raw.githubusercontent.com/'+CACHE_REPO+'/'+pin+'/data/listing/krx/'+d+'.csv',audit,private_dir)
    old,_=normalize_cache(fetch(meta['asof']),meta['asof']);check=control_check(control,old)
    if not check['complete_match']:
        write(out/'supply_validation.json',dict(status='CONFLICT',control=check,transport=audit));raise ValueError('MIRROR_OFFICIAL_CONTROL_CONFLICT')
    rows,excluded=normalize_cache(fetch(day),day);q=quality(rows,control,day)
    if q['errors']:
        write(out/'supply_validation.json',dict(status='CONFLICT',quality=q,transport=audit));raise ValueError('MIRROR_CURRENT_QUALITY_REJECTED')
    if previous_day is None:raise ValueError('PREVIOUS_OBSERVED_SESSION_REQUIRED')
    if previous_day>=day:raise ValueError('PREVIOUS_SESSION_REQUIRED')
    previous,_=normalize_cache(fetch(previous_day),previous_day) if previous_day!=meta['asof'] else (old,[])
    oldby={r['ticker']:r for r in previous};rebases=[]
    for r in rows:
        if r['ticker'] in oldby and abs(r['previous_reference']-number(oldby[r['ticker']]['close']))>1e-6:
            r['action_boundary']='1';rebases.append(r['ticker'])
    evidence=dict(official_control_complete_match=True,control_asof=meta['asof'],control=check,control_file_hashes=meta['market_file_sha256'],cache_repository=CACHE_REPO,cache_commit=pin,cache_commit_date=commit['commit']['committer']['date'],exchange_max_work_dt=last,requested_cache_day=day,previous_session_checked=previous_day,quality=q,reference_rebase_candidates=rebases,corporate_actions_not_inferred=True,ultimate_upstream_family='KRX',independent_upstream_count=1,current_direct_official_confirmation=False,current_independent_vendor_confirmation=False,validation_scope='FULL_PRIOR_OFFICIAL_CONTROL_PLUS_EXCHANGE_DATE_AND_PINNED_SAME_BASIS_MIRROR')
    files={};hashes={}
    for market in ('KOSPI','KOSDAQ'):
        p=out/(market+'_research.csv')
        with p.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction='ignore');w.writeheader();w.writerows(r for r in rows if r['market']==market)
        files[market]=p.name;hashes[market]=digest(p.read_bytes())
    evidence.update(current_market_file_sha256=hashes,current_rows=len(rows))
    proof=digest(json.dumps(evidence,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
    manifest=dict(schema='C3_SUPPLY_SNAPSHOT_V11',asof=day,retrieval_utc=audit[-1]['received_at'],status='RESEARCH_VALIDATED',data_quality_state='RESEARCH_VALIDATED',source_provider='FINANCEDATA_KRX_CACHE',research_dataset_validated=True,krx_eod_authenticated=False,official_dataset_usable=False,official_market_rows=len(rows),price_files=files,market_file_sha256=hashes,price_basis='UNADJUSTED_AS_TRADED',independent_1530_regular_session_certified=False,trade_approved=False,orders_enabled=False,validation=evidence,validation_sha256=proof,response_diagnostics=[],transport=audit,excluded_other_market_rows=len(excluded))
    write(out/'krx_v65_collect_status.json',manifest);write(out/'supply_validation.json',dict(manifest,price_files=None))
    return manifest


def validated_manifest(meta):
    if meta.get('schema')!='C3_SUPPLY_SNAPSHOT_V11' or not meta.get('research_dataset_validated') or meta.get('data_quality_state')!='RESEARCH_VALIDATED':return False
    v=meta.get('validation',{});expected=digest(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
    check=v.get('control',{});q=v.get('quality',{})
    return bool(expected==meta.get('validation_sha256') and
        v.get('official_control_complete_match') and check.get('complete_match') and
        check.get('rows',0)>0 and check.get('rows')==check.get('compared') and
        not any(check.get(k) for k in ('missing','extra','mismatches')) and
        v.get('cache_repository')==CACHE_REPO and re.fullmatch('[0-9a-f]{40}',v.get('cache_commit','')) and
        v.get('requested_cache_day')==meta.get('asof') and v.get('exchange_max_work_dt','')>=meta['asof'] and
        q.get('status')=='QUALITY_GATE_PASSED' and set(q.get('markets',{}))=={'KOSPI','KOSDAQ'} and not q.get('errors') and
        meta.get('price_basis')=='UNADJUSTED_AS_TRADED' and
        v.get('current_market_file_sha256')==meta.get('market_file_sha256') and v.get('current_rows')==meta.get('official_market_rows') and
        v.get('control_asof','')<=v.get('previous_session_checked','')<meta['asof'])


def source_usable(meta):
    return bool((meta.get('krx_eod_authenticated') and meta.get('official_dataset_usable') and meta.get('official_market_rows',0)>0 and set(meta.get('market_file_sha256',{}))=={'KOSPI','KOSDAQ'}) or validated_manifest(meta))


def price_path(folder,meta,market):
    name=meta.get('price_files',{}).get(market) if meta.get('price_files') else market+'_official.csv'
    if not name or Path(name).name!=name:raise ValueError('PRICE_FILE_OUTSIDE_SNAPSHOT')
    return Path(folder)/name


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--asof',required=True);p.add_argument('--control',required=True);p.add_argument('--outdir',required=True);p.add_argument('--previous-session',required=True);p.add_argument('--private',default=None);a=p.parse_args();m=mirror(a.asof,a.control,a.outdir,a.private,previous_day=a.previous_session);print(json.dumps({k:m[k] for k in ('asof','status','official_market_rows','source_provider')}))
