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


def sha(body):return hashlib.sha256(body).hexdigest()


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


def execute(outdir,requested=None,clock=None):
    from c3_daily_research_v8 import collect_indices
    from c3_eod_source_v9 import collect_day
    from c3_runtime_v10 import quality
    clock=clock or datetime.now(timezone.utc);out=Path(outdir);private=out/'private';private.mkdir(parents=True,exist_ok=True)
    result=dict(schema='C3_MORNING_OFFICIAL_SOURCE_V1',checked_at=clock.isoformat(),
        status='SOURCE_UNAVAILABLE',ready=False,regular_only_certified=False,
        buy_approved=False,orders_enabled=False,decision='CASH',attempts=[],
        source_scope='OFFICIAL_DAILY_ALL_SESSIONS_NOT_REGULAR_ONLY')
    try:
        plan=prior_session(clock);result.update(plan)
        day=requested or plan['requested_day'];result['requested_day']=day
        if date.fromisoformat(day)>=clock.astimezone(KST).date():raise ValueError('MORNING_SOURCE_MUST_PRECEDE_TODAY')
        collect_indices(private/'indices',str(clock.astimezone(KST).date()-timedelta(days=1)))
        observed={m:[r['date'] for r in csv.DictReader((private/'indices'/(m+'_index.csv')).open())]
                  for m in ('KOSPI','KOSDAQ')}
        if requested is None:result['observed_latest_sessions']=verify_calendar(day,observed,plan['report_day_kst'])
        elif any(day not in observed[m] for m in observed):raise ValueError('REQUESTED_DAY_NOT_OBSERVED_IN_BOTH_BOARDS')
        manifest,receipts=bounded_target(day,private/'official',os.environ.get('KRX_AUTH_KEY'),collect_day)
        result['attempts']=receipts
        if not manifest.get('official_dataset_usable'):raise ValueError('OFFICIAL_TARGET_UNAVAILABLE_NO_FALLBACK')
        official=[]
        for market in ('KOSPI','KOSDAQ'):
            with (private/'official'/(market+'_official.csv')).open(encoding='utf-8-sig') as f:official+=list(csv.DictReader(f))
        for row in official:
            for k in FIELDS:row[k]=float(row[k])
        gh=GitHub(os.environ.get('GH_TOKEN',''),'FinanceData/fdr_krx_data_cache');ref=gh.head('master')
        raw=gh.file('data/listing/krx/'+day+'.csv',ref)
        cache,excluded=cache_rows(raw,day);agreement=compare(official,cache,day)
        q=quality(official,cache,day)
        if q['errors']:raise ValueError('OFFICIAL_SOURCE_INTERNAL_QUALITY_FAILED')
        result.update(agreement,status='OFFICIAL_CACHE_MATCHED',ready=True,cache_ref=ref,
            cache_sha256=sha(raw),excluded_markets=excluded,source_quality=q,
            official_raw_response_sha256=manifest['raw_response_sha256'],
            final_collection_at=manifest['retrieval_utc'],internal_quality_not_session_authentication=True)
    except Exception as exc:
        # Preserve failure evidence; never print transport URLs/keys or raw bodies.
        import re
        message=str(exc)
        result['blocker']=message if isinstance(exc,ValueError) and re.fullmatch('[A-Z_0-9]{1,110}',message) else type(exc).__name__
    (out/'morning_source.json').write_bytes(canonical(result)+b'\n')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:
            f.write('ready='+str(result['ready']).lower()+'\nsource_day='+str(result.get('requested_day',''))+'\nrun_id=\n')
    print(json.dumps({k:result.get(k) for k in ('status','requested_day','compared_rows','ready','blocker')}))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);p.add_argument('--date');a=p.parse_args();execute(a.outdir,a.date)
