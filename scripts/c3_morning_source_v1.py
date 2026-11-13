"""Date-pinned morning KRX/cache agreement. Daily scope never implies BUY.

The exchange calendar is a reference; paired observed board calendars must
agree. An empty target response never changes the target to an older date.
"""
import argparse,csv,hashlib,io,json,math,os,time
from collections import Counter
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from c3_telegram_inputs import GitHub,canonical

KST=ZoneInfo('Asia/Seoul')
FIELDS=('open','high','low','close','volume','turnover_krw')
REPOSITORY='shdmfpsj-beep/krx-auto-scanner'
SOURCE_WAKEUP_WORKFLOW='KRX official independent daily source probe (no trading)'


def sha(body):return hashlib.sha256(body).hexdigest()


def trigger_context(env=None,event=None):
    """A trusted completed probe wakes a fresh collection, never a trade."""
    env=os.environ if env is None else env;name=env.get('GITHUB_EVENT_NAME','LOCAL_UNSPECIFIED')
    if event is None:
        path=env.get('GITHUB_EVENT_PATH');event=json.loads(Path(path).read_text()) if path and Path(path).is_file() else {}
    result=dict(event=name,cron=event.get('schedule'),observed_code_sha=env.get('GITHUB_SHA'),
        approved_original_registration_allowed=name in ('schedule','workflow_dispatch') and
            env.get('GITHUB_REPOSITORY')==REPOSITORY and env.get('GITHUB_REF')=='refs/heads/main')
    if name=='workflow_run':
        upstream=event.get('workflow_run') or {};rid=upstream.get('id')
        if (env.get('GITHUB_REPOSITORY')!=REPOSITORY or env.get('GITHUB_REF')!='refs/heads/main' or
            upstream.get('name')!=SOURCE_WAKEUP_WORKFLOW or upstream.get('head_branch')!='main' or
            (upstream.get('head_repository') or {}).get('full_name')!=REPOSITORY or
            upstream.get('status')!='completed' or upstream.get('event') not in ('schedule','push','workflow_dispatch') or
            upstream.get('conclusion') not in ('success','failure','timed_out') or
            isinstance(rid,bool) or not isinstance(rid,int) or rid<=0):
            raise ValueError('UNTRUSTED_OR_INCOMPLETE_SOURCE_WAKEUP')
        result.update(mode='COMPLETION_RESEARCH_RECOVERY',upstream_run_id=str(rid),
            upstream_name=upstream['name'],upstream_conclusion=upstream['conclusion'],
            upstream_created_at=upstream.get('created_at'),upstream_head_sha=upstream.get('head_sha'),
            upstream_is_wakeup_not_source_validation=True,approved_original_registration_allowed=False)
    return result


def require_official_collection(manifest,day):
    if (manifest.get('asof')!=day or manifest.get('official_dataset_usable') is not True or
        not isinstance(manifest.get('official_market_rows'),int) or isinstance(manifest['official_market_rows'],bool) or manifest['official_market_rows']<=0):
        raise ValueError('OFFICIAL_COLLECTION_EMPTY_OR_WRONG_DAY')


def normalized_hash(rows):
    cooked=[]
    for r in rows:
        cooked.append(dict(ticker=r['ticker'],name=r['name'],market=r['market'],
            asof=r['asof'],**{k:float(r[k]) for k in FIELDS}))
    return sha(canonical(sorted(cooked,key=lambda r:r['ticker'])))


def prior_session(clock,calendar=None):
    import exchange_calendars as xc
    local=clock.astimezone(KST);today=local.date()
    # Even if a delayed morning job executes after today's close, it cannot
    # silently switch the requested report to today's data.
    cal=calendar or xc.get_calendar('XKRX',start=str(today-timedelta(days=400)),end=str(today+timedelta(days=10)))
    cutoff=today-timedelta(days=1)
    target=cal.date_to_session(str(cutoff),direction='previous').strftime('%Y-%m-%d')
    return dict(requested_day=target,report_day_kst=str(today),
        calendar_name='XKRX_REFERENCE_WITH_OBSERVED_BOARD_CROSSCHECK',
        calendar_version=xc.__version__,calendar_is_official_attestation=False,
        today_is_reference_session=bool(cal.is_session(str(today))),
        expected_entry_session=cal.date_to_session(str(date.fromisoformat(target)+timedelta(days=1)),direction='next').strftime('%Y-%m-%d'))


def verify_calendar(target,observed,today):
    if set(observed)!={'KOSPI','KOSDAQ'}:raise ValueError('OBSERVED_BOARD_CALENDAR_INCOMPLETE')
    latest={m:max((d for d in dates if d<today),default=None) for m,dates in observed.items()}
    if any(d!=target for d in latest.values()):raise ValueError('REFERENCE_AND_OBSERVED_SESSION_MISMATCH')
    return latest


def cache_rows(raw,day):
    rows=[];seen=set();excluded=Counter()
    for x in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))):
        market={'STK':'KOSPI','KSQ':'KOSDAQ'}.get(x.get('MarketId'))
        if market is None:
            if x.get('MarketId')!='KNX':raise ValueError('UNKNOWN_CACHE_MARKET')
            excluded['KONEX']+=1;continue
        ticker=x['Code']
        if ticker in seen:raise ValueError('DUPLICATE_CACHE_CODE')
        seen.add(ticker)
        r=dict(ticker=ticker,name=x['Name'],market=market,asof=day)
        r.update({k:float(str(x[c]).replace(',','')) for k,c in zip(FIELDS,('Open','High','Low','Close','Volume','Amount'))})
        rows.append(r)
    return rows,dict(excluded)


def compare(official,cached,day):
    a={r['ticker']:r for r in official};b={r['ticker']:r for r in cached}
    if len(a)!=len(official) or len(b)!=len(cached):raise ValueError('DUPLICATE_SOURCE_CODE')
    if set(a)!=set(b):raise ValueError('OFFICIAL_CACHE_UNIVERSE_MISMATCH')
    errors=[]
    for t,r in a.items():
        s=b[t]
        if r['asof']!=day or s['asof']!=day:raise ValueError('SOURCE_DATE_MISMATCH')
        for k in ('name','market')+FIELDS:
            if (r[k]!=s[k] if k in ('name','market') else float(r[k])!=float(s[k])):errors.append((t,k))
    if errors:raise ValueError('OFFICIAL_CACHE_FIELD_MISMATCH')
    return dict(compared_rows=len(a),markets=dict(Counter(r['market'] for r in official)),
        normalized_rows_sha256=normalized_hash(official),mismatch_count=0)


def bounded_target(day,root,key,collect,pause=time.sleep,attempts=2):
    if not 1<=attempts<=2:raise ValueError('SOURCE_RETRY_LIMIT')
    receipts=[];manifest=None
    for attempt in range(attempts):
        manifest=collect(day,root,key)
        receipts.append({k:manifest.get(k) for k in ('asof','status','retrieval_utc','official_market_rows','raw_response_sha256','response_diagnostics')})
        if manifest.get('official_dataset_usable') is True:break
        if attempt+1<attempts:pause(2)
    return manifest,receipts


def execute(outdir,requested=None,clock=None,recover=None):
    from c3_source_recovery_v1 import run as recover_actual
    explicit_clock=clock is not None;clock=clock or datetime.now(timezone.utc);out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    result=dict(schema='C3_MORNING_OFFICIAL_SOURCE_V1',checked_at=clock.isoformat(),status='SOURCE_UNAVAILABLE',
        ready=False,research_ready=False,indices_ready=False,regular_only_certified=False,buy_approved=False,
        orders_enabled=False,decision='CASH',attempts=[],source_scope='DAILY_REGULAR_SCOPE_UNCERTIFIED',
        registration_window='OPEN' if clock.astimezone(KST).hour<9 else 'CLOSED')
    try:
        result['trigger']=trigger_context()
        plan=prior_session(clock);result.update(plan);day=requested or plan['requested_day'];result['requested_day']=day
        if date.fromisoformat(day)>=clock.astimezone(KST).date():raise ValueError('MORNING_SOURCE_MUST_PRECEDE_TODAY')
        data=(recover or recover_actual)(day,out/'recovery',attempts=2)
        result.update(source_status=data['status'],research_ready=data['research_ready'],indices_ready=data['indices_ready'],
            source_run_id=os.environ.get('GITHUB_RUN_ID'),attempts=data.get('attempts',[]),
            collected_rows=data.get('rows',0),markets=data.get('markets',{}),compared_rows=data.get('comparison',{}).get('compared_rows'),source_quality=data.get('quality'),
            normalized_rows_sha256=data.get('normalized_rows_sha256'),final_collection_at=data.get('data_received_at'),
            cache_ref=data.get('cache',{}).get('ref'),cache_sha256=data.get('cache',{}).get('raw_sha256'),
            excluded_markets=data.get('cache',{}).get('excluded'),official_raw_response_sha256=data['official'].get('raw_response_sha256'),
            response_diagnostics=data['official'].get('response_diagnostics'),internal_quality_not_session_authentication=True)
        if data['indices_ready']:
            observed={}
            for m in ('KOSPI','KOSDAQ'):
                with (out/'recovery/indices'/(m+'_index.csv')).open() as f:observed[m]=[r['date'] for r in csv.DictReader(f)]
            if requested is None:result['observed_latest_sessions']=verify_calendar(day,observed,plan['report_day_kst'])
            elif any(day not in observed[m] for m in observed):raise ValueError('REQUESTED_DAY_NOT_OBSERVED_IN_BOTH_BOARDS')
        if data.get('approved_source_ready') and data['indices_ready']:
            result.update(status='OFFICIAL_CACHE_MATCHED',ready=True)
        else:
            result['status']='RESEARCH_SOURCE_AVAILABLE' if data['research_ready'] else 'SOURCE_UNAVAILABLE'
            result['blocker']='OFFICIAL_OR_BENCHMARK_GATE_NOT_COMPLETE'
    except Exception as exc:
        message=str(exc)
        result['blocker']=message if isinstance(exc,ValueError) and __import__('re').fullmatch('[A-Z_0-9]{1,110}',message) else type(exc).__name__
    if not explicit_clock:result['registration_window']='OPEN' if datetime.now(timezone.utc).astimezone(KST).hour<9 else 'CLOSED'
    (out/'morning_source.json').write_bytes(canonical(result)+b'\n')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:
            for key,value in dict(ready=str(result['ready']).lower(),research_ready=str(result['research_ready']).lower(),indices_ready=str(result['indices_ready']).lower(),
                source_day=result.get('requested_day',''),run_id=os.environ.get('GITHUB_RUN_ID',''),registration_window=result['registration_window'],
                registration_trigger_allowed=str(result.get('trigger',{}).get('approved_original_registration_allowed',False)).lower()).items():f.write(key+'='+str(value)+'\n')
    print(json.dumps({k:result.get(k) for k in ('status','requested_day','compared_rows','ready','research_ready','blocker')}))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);p.add_argument('--date');p.add_argument('--require-data',action='store_true');a=p.parse_args();r=execute(a.outdir,a.date)
    if a.require_data and not r['research_ready']:raise SystemExit(2)
