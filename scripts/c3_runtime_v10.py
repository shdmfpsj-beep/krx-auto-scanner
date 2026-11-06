"""Research operations guards. No strategy, orders, or notification changes."""
import argparse,csv,gzip,hashlib,json,math,os,re,subprocess,zipfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.request import Request,urlopen

from c3_data_quality_v17 import classify_bar

REPO='shdmfpsj-beep/krx-auto-scanner'


def sha(body):return hashlib.sha256(body).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def validate_scanner(run,jobs,artifacts):
    """A successful workflow may contain a failed continue-on-error collector."""
    if run.get('name')!='KRX daily candidate scan' or run.get('path')!='.github/workflows/daily.yml' or run.get('head_branch')!='main' or run.get('conclusion')!='success' or run.get('status')!='completed' or run.get('repository',{}).get('full_name')!=REPO or run.get('head_repository',{}).get('full_name',REPO)!=REPO:
        raise ValueError('UPSTREAM_NOT_SUCCESSFUL_MAIN_SCANNER')
    good=[]
    for job in jobs.get('jobs',[]):
        steps={s['name']:s.get('conclusion') for s in job.get('steps',[])}
        if job.get('run_id')==run['id'] and job.get('conclusion')=='success' and all(steps.get(s)=='success' for s in ('Collect and screen','Test and record C3 screening timestamps','Upload report artifact')):good.append(job['id'])
    if not good:raise ValueError('UPSTREAM_COLLECTION_NOT_SUCCESSFUL_OR_SKIPPED')
    found=[a for a in artifacts.get('artifacts',[]) if a.get('name')=='krx-scan-report' and a.get('workflow_run',{}).get('id')==run['id'] and a.get('size_in_bytes',0)>0 and not a.get('expired')]
    if len(found)!=1:raise ValueError('UPSTREAM_ARTIFACT_MISSING_EXPIRED_OR_AMBIGUOUS')
    return dict(status='VALIDATED_COLLECTION_AND_ARTIFACT',run_id=str(run['id']),head_sha=run['head_sha'],event=run['event'],job_ids=good,artifact_id=found[0]['id'],artifact_expires_at=found[0].get('expires_at'),validated_at=now(),prices_not_implicitly_certified=True)


def api(path):
    req=Request('https://api.github.com/repos/'+REPO+'/'+path,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
    with urlopen(req,timeout=25) as f:return json.load(f)


def scanner(run_id='',reader=api):
    if run_id and not re.fullmatch(r'[0-9]{8,14}',str(run_id)):raise ValueError('UPSTREAM_RUN_ID_INVALID')
    runs=[reader('actions/runs/'+str(run_id))] if run_id else reader('actions/workflows/daily.yml/runs?branch=main&status=success&per_page=10').get('workflow_runs',[])
    rejected=[]
    for run in runs:
        try:
            jobs=reader('actions/runs/'+str(run['id'])+'/jobs?per_page=100');arts=reader('actions/runs/'+str(run['id'])+'/artifacts?per_page=100')
            return dict(validate_scanner(run,jobs,arts),rejected_prior_runs=rejected)
        except ValueError as e:
            rejected.append(dict(run_id=str(run['id']),reason=str(e)))
            if run_id:raise
    raise ValueError('NO_GENUINELY_COMPLETED_SCANNER_WITH_ARTIFACT')


def quality(prices,baseline,day):
    """A coverage alarm is not a reconstructed official listing census."""
    rows=list(prices.values()) if isinstance(prices,dict) else prices
    old=list(baseline.values()) if isinstance(baseline,dict) else baseline
    seen=set();markets={};errors=[]
    for r in rows:
        if r['ticker'] in seen:errors.append('DUPLICATE_SECURITY')
        seen.add(r['ticker'])
        if r['asof']!=day:errors.append('WRONG_SOURCE_DATE')
    for m in ('KOSPI','KOSDAQ'):
        rr=[r for r in rows if r['market']==m];a={r['ticker'] for r in old if r['market']==m};b={r['ticker'] for r in rr};invalid=[];halt=0
        for r in rr:
            state=classify_bar(r)
            valid=state=='VALID_TRADED_BAR';halted=state=='NO_TRADES_OBSERVED'
            if halted:halt+=1
            elif not valid:invalid.append(r['ticker'])
        if not b:errors.append('MARKET_EMPTY:'+m)
        if a and len(a&b)/len(a)<.95:errors.append('SUSPICIOUS_COVERAGE_LOSS:'+m)
        if invalid:errors.append('INVALID_OHLC:'+m)
        markets[m]=dict(rows=len(rr),baseline_rows=len(a),retained_baseline_fraction=len(a&b)/len(a) if a else None,newly_observed=sorted(b-a),no_longer_observed=sorted(a-b),invalid_ohlc=invalid,halt_like=halt,listing_or_delisting_cause_confirmed=False)
    if any(r['market'] not in markets for r in rows):errors.append('UNKNOWN_MARKET')
    return dict(status='QUALITY_GATE_PASSED' if not errors else 'QUALITY_GATE_REJECTED',errors=sorted(set(errors)),markets=markets,full_current_listing_census_verified=False,coverage_alarm_floor=.95,asof=day)


def quarantine(folder,ledger,outdir,audit):
    """Retain actual adjusted closes independently; never splice into EOD OHLC."""
    folder=Path(folder);status=json.loads((folder/'status.json').read_text());runtime_path=folder/'c3_source_runtime_v1.json';runtime=json.loads(runtime_path.read_text());universe=json.loads((folder/'c3_universe_capture_v1.json').read_text())
    if str(runtime['run_context']['GITHUB_RUN_ID'])!=audit['run_id']:raise ValueError('OPERATING_RUN_ID_MISMATCH')
    if not status.get('scan_complete') or not status.get('data_date_verified') or universe.get('reference_date')!=status.get('market_data_date'):raise ValueError('OPERATING_SOURCE_INCOMPLETE_OR_UNDATED')
    day=status['market_data_date'];by={};wrong=[]
    for line in (folder/'c3_source_observations_v1.jsonl').read_text().splitlines():
        r=json.loads(line);t=r['ticker']
        if t not in set(universe['tickers']):continue
        if t in by:raise ValueError('OPERATING_DUPLICATE_RECEIPT')
        if r['runtime_manifest_sha256']!=sha(runtime_path.read_bytes()):raise ValueError('OPERATING_RUNTIME_HASH_MISMATCH')
        if r['latest_observed_date']!=day:wrong.append(t);continue
        value=float(r['latest_raw_close'])
        if not math.isfinite(value) or value<=0:wrong.append(t);continue
        if r['request'].get('adjusted') is not True or r['source_label']!='pykrx' or not r['route'].get('trace_completed') or r['route'].get('actual_provider_calls')!=[{'module':'pykrx.website.naver.wrap','function':'get_market_ohlcv_by_date'}]:raise ValueError('OPERATING_PRICE_PROVIDER_OR_BASIS_CHANGED')
        if datetime.fromisoformat(r['response_received_at_utc'])>datetime.now(timezone.utc):raise ValueError('FUTURE_OPERATING_RECEIPT')
        by[t]=dict(ticker=t,close=value,received_at=r['response_received_at_utc'],raw_history_sha256=r['raw_response_csv_sha256'])
    local=datetime.now(timezone(timedelta(hours=9)))
    if day>local.date().isoformat() or (day==local.date().isoformat() and local.hour*60+local.minute<930):raise ValueError('OPERATING_SESSION_NOT_COMPLETED')
    if not by:raise ValueError('OPERATING_CLOSE_RECEIPTS_EMPTY')
    payload=dict(schema='C3_PROVISIONAL_CLOSE_RECEIPTS_V10',price_asof=day,provider='PYKRX_NAVER',price_basis='ADJUSTED_TRUE_AS_REQUESTED',regular_only_certified=False,source_run_id=audit['run_id'],source_artifact_id=audit['artifact_id'],source_runtime_sha256=sha(runtime_path.read_bytes()),rows=by,not_a_full_ohlcv_dataset=True,turnover_available=False,used_for_selection=False,used_for_paper_fills=False,used_for_certified_returns=False,orders_enabled=False)
    body=canonical(dict(payload=payload,sha256=sha(canonical(payload))));dest=Path(ledger)/'provisional'/day/(sha(body)+'.json.gz');dest.parent.mkdir(parents=True,exist_ok=True)
    packed=gzip.compress(body,mtime=0)
    if dest.exists():
        if dest.read_bytes()!=packed:raise ValueError('PROVISIONAL_RECEIPT_CONFLICT')
    else:
        with dest.open('xb') as f:f.write(packed)
    result=dict(status='PROVISIONAL_CLOSE_ONLY_UNAPPROVED',source_run_id=audit['run_id'],source_artifact_id=audit['artifact_id'],source_price_asof=day,rows=len(by),universe_rows=len(universe['tickers']),missing_or_invalid=sorted(set(universe['tickers'])-set(by)),last_received_at=max((r['received_at'] for r in by.values()),default=None),price_basis=payload['price_basis'],provider=payload['provider'],record_path=str(dest.relative_to(Path(ledger))),record_sha256=sha(packed),regular_only_certified=False,ohlcv_and_turnover_complete=False,used_for_selection=False,used_for_paper_fills=False,used_for_certified_returns=False)
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True);(out/'provisional_status.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return result


def download_scanner(audit,outdir):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    # gh handles the signed cross-host redirect without forwarding the API
    # Authorization header to blob storage. urllib's default redirect did not.
    body=subprocess.check_output(['gh','api','repos/'+REPO+'/actions/artifacts/'+str(audit['artifact_id'])+'/zip'],timeout=60)
    if len(body)>60*1024*1024:raise ValueError('SCANNER_ARCHIVE_TOO_LARGE')
    p=root/'source.zip';p.write_bytes(body)
    required={'status.json','c3_source_runtime_v1.json','c3_universe_capture_v1.json','c3_source_observations_v1.jsonl'}
    with zipfile.ZipFile(p) as z:
        if not required<=set(z.namelist()):raise ValueError('SCANNER_RECEIPTS_NOT_AVAILABLE')
        for n in required:
            if z.getinfo(n).file_size>8*1024*1024:raise ValueError('SCANNER_MEMBER_TOO_LARGE')
            z.extract(n,root)
    (root/'archive_sha256.txt').write_text(sha(body)+'\n');return root


def probe_free(day,outdir,control):
    """Separate KRX website cross-section experiment; never an implicit fallback."""
    import inspect
    import requests
    from pykrx import stock
    root=Path(outdir)/day;root.mkdir(parents=True,exist_ok=True);parts=[];allrows=[]
    for market in ('KOSPI','KOSDAQ'):
        started=now();transport=[];original=requests.sessions.Session.request
        def traced(session,method,url,**kwargs):
            from urllib.parse import urlsplit
            r=original(session,method,url,**kwargs)
            try:keys=sorted(r.json()) if isinstance(r.json(),dict) else []
            except ValueError:keys=[]
            data=kwargs.get('data') or {};data=data if isinstance(data,dict) else {}
            transport.append(dict(method=method,host=urlsplit(url).hostname,path=urlsplit(url).path,request_fields=sorted(data),date_parameter=data.get('trdDd'),http_status=r.status_code,content_type=r.headers.get('Content-Type'),body_bytes=len(r.content),body_sha256=sha(r.content),json_keys=keys,received_at=now()))
            return r
        try:
            requests.sessions.Session.request=traced
            df=stock.get_market_ohlcv_by_ticker(day.replace('-',''),market=market)
            rows=[]
            for ticker,r in df.iterrows():
                rows.append(dict(ticker=str(ticker),market=market,asof=day,**{k:float(r[col]) for k,col in [('open','시가'),('high','고가'),('low','저가'),('close','종가'),('volume','거래량'),('turnover_krw','거래대금')]}))
            if rows:
                p=root/(market+'_website.csv')
                with p.open('w',newline='') as f:
                    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
                allrows+=rows
            parts.append(dict(market=market,status='PROVISIONAL_PUBLIC_WEBSITE' if rows else 'PUBLIC_WEBSITE_EMPTY',rows=len(rows),started_at=started,received_at=now()))
        except Exception as e:parts.append(dict(market=market,status='PUBLIC_WEBSITE_FAILED',error_type=type(e).__name__,started_at=started,received_at=now()))
        finally:
            requests.sessions.Session.request=original
            parts[-1]['transport']=transport
    source=inspect.getsource(inspect.unwrap(stock.get_market_ohlcv_by_ticker))
    old={r['ticker']:r for r in control if r['asof']==day}
    compared=[r for r in allrows if r['ticker'] in old];mismatches=[r['ticker'] for r in compared if any(float(r[k])!=float(old[r['ticker']][k]) for k in ('open','high','low','close','volume','turnover_krw'))]
    result=dict(asof=day,provider='PYKRX_KRX_WEBSITE_SINGLE_DATE_CROSS_SECTION',module=stock.get_market_ohlcv_by_ticker.__module__,adapter_sha256=sha(source.encode()),adjusted_history_not_requested=True,session_scope_certified=False,parts=parts,rows=len(allrows),control_comparison_count=len(compared),control_mismatches=mismatches,quality=quality(allrows,control,day),used_for_selection=False,used_for_paper_fills=False,orders_enabled=False)
    (root/'public_source_status.json').write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--upstream-run-id',default='');p.add_argument('--outdir',required=True);p.add_argument('--ledger',default='');a=p.parse_args();root=Path(a.outdir);root.mkdir(parents=True,exist_ok=True)
    audit=scanner(a.upstream_run_id);(root/'upstream_validation.json').write_text(json.dumps(audit,indent=2)+'\n')
    if a.ledger:quarantine(download_scanner(audit,root/'operating'),a.ledger,root,audit)
    print(json.dumps(audit))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('run_id='+audit['run_id']+'\n')

