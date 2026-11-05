"""Bounded live data-path comparison. No ranking, signals, orders or alerts.

Market payloads stay in a sealed private archive. Public outputs are transport
metadata, counts, source code and validation outcomes, not redistributed feeds.
"""
import argparse,ast,contextlib,csv,gzip,hashlib,importlib.metadata,inspect,io,json,math,os,re,time,zipfile
from collections import Counter
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlsplit

KST=timezone(timedelta(hours=9));FIELDS=('open','high','low','close','volume','turnover_krw')
FAMILIES={'PYKRX_ADJUSTED':'NAVER','PYKRX_UNADJUSTED':'KRX_WEB','FDR_NAVER':'NAVER','FDR_KRX':'KRX_WEB','FDR_YAHOO':'YAHOO','NAVER_JSON':'NAVER','YAHOO_CHART':'YAHOO','DAUM':'DAUM'}


def now():return datetime.now(timezone.utc).isoformat()
def digest(b):return hashlib.sha256(b).hexdigest()
def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def completed_day(clock=None):
    local=(clock or datetime.now(timezone.utc)).astimezone(KST);d=local.date()
    if local.hour*60+local.minute<930:d-=timedelta(days=1)
    while d.weekday()>=5:d-=timedelta(days=1)
    return d.isoformat()


def rows_from_frame(frame,ticker,market,end):
    if frame is None or frame.empty:raise ValueError('EMPTY_DATAFRAME')
    aliases={'open':('Open','시가'),'high':('High','고가'),'low':('Low','저가'),'close':('Close','종가'),'volume':('Volume','거래량'),'turnover_krw':('Amount','거래대금','Value')}
    columns={k:next((c for c in cc if c in frame.columns),None) for k,cc in aliases.items()}
    if any(columns[k] is None for k in FIELDS[:5]):raise ValueError('OHLCV_SCHEMA_MISSING')
    rows=[];seen=set()
    for index,r in frame.iterrows():
        day=index.strftime('%Y-%m-%d') if hasattr(index,'strftime') else str(index)[:10]
        if re.fullmatch('[0-9]{8}',day):day=day[:4]+'-'+day[4:6]+'-'+day[6:]
        if day>end:continue
        if day in seen:raise ValueError('DUPLICATE_DAILY_BAR')
        seen.add(day);values={k:float(r[c]) if c is not None and r[c] is not None else None for k,c in columns.items()}
        if any(v is not None and not math.isfinite(v) for v in values.values()):raise ValueError('NONFINITE_BAR')
        o,h,l,c,v=(values[k] for k in FIELDS[:5]);valid=0<l<=min(o,c)<=max(o,c)<=h and v>0
        halt=c>0 and v==0 and min(o,h,l)>=0
        rows.append(dict(values,ticker=ticker,market=market,date=day,valid_ohlcv=valid,halt_like=halt,invalid_data=not(valid or halt)))
    if not rows:raise ValueError('NO_COMPLETED_DAILY_BAR')
    return rows


def compare(a,b,days):
    aa={(r['ticker'],r['date']):r for r in a if r['date'] in days};bb={(r['ticker'],r['date']):r for r in b if r['date'] in days};counts=Counter();details=[]
    for key in sorted(set(aa)|set(bb)):
        if key not in aa or key not in bb:counts['MISSING_COUNTERPART']+=1;continue
        x,y=aa[key],bb[key];bad=[f for f in FIELDS[:5] if x.get(f)!=y.get(f)]
        money=(x.get('turnover_krw')==y.get('turnover_krw')) if x.get('turnover_krw') is not None and y.get('turnover_krw') is not None else None
        counts['MISMATCH' if bad else 'MATCH_OHLCV']+=1
        counts['TURNOVER_MATCH' if money else 'TURNOVER_MISMATCH' if money is False else 'TURNOVER_UNAVAILABLE']+=1
        details.append(dict(ticker=key[0],date=key[1],different_fields=bad,turnover_equal=money))
    return dict(counts=dict(counts),comparisons=details)


def quality_state(rows,evidence):
    if evidence.get('unresolved_conflict'):return 'CONFLICT'
    if not rows:return 'UNAVAILABLE'
    if any(r.get('close') is None for r in rows):return 'UNAVAILABLE'
    if any(any(r.get(k) is None for k in FIELDS[:5]) for r in rows):return 'CLOSE_ONLY'
    if any(r.get('invalid_data') for r in rows):return 'CONFLICT'
    if evidence.get('official_authenticated') and evidence.get('date_and_coverage_verified'):return 'OFFICIAL_VERIFIED'
    if len(set(evidence.get('independent_families',[])))>=2 and evidence.get('current_ohlcv_exact_match') and evidence.get('price_basis_verified') and evidence.get('date_and_coverage_verified'):return 'RESEARCH_VALIDATED'
    return 'OHLCV_UNVERIFIED'


def choose_source(candidates,require_turnover=True):
    """Select one intact dataset; never fill a field from another price basis."""
    for state in ('OFFICIAL_VERIFIED','RESEARCH_VALIDATED'):
        for c in candidates:
            if c['state']!=state or not c.get('whole_universe_verified'):continue
            if require_turnover and any(r.get('turnover_krw') is None for r in c['rows']):continue
            return c
    return None


def classify_error(trace,exc):
    statuses={r.get('http_status') for r in trace}
    if 429 in statuses:return 'RATE_LIMITED'
    if statuses&{401,403}:return 'ACCESS_REJECTED_NO_BYPASS'
    if any(r.get('logout_marker') for r in trace):return 'SESSION_REQUIRED_LOGOUT_NO_BYPASS'
    if any((s or 0)>=400 for s in statuses):return 'HTTP_ERROR'
    if isinstance(exc,TimeoutError):return 'TIMEOUT'
    label=str(exc)
    return label if re.fullmatch('[A-Z0-9_]{1,80}',label) else 'SCHEMA_OR_LIBRARY_ERROR:'+type(exc).__name__


@contextlib.contextmanager
def transport(root,route,identity,pause=1.):
    import requests
    original=requests.sessions.Session.request;records=[];last=[0.]
    def traced(session,method,url,**kwargs):
        if len(records)>=8:raise ValueError('PER_TASK_REQUEST_BUDGET')
        delay=pause-(time.monotonic()-last[0])
        if delay>0:time.sleep(delay)
        last[0]=time.monotonic();kwargs['timeout']=min(float(kwargs.get('timeout') or 20),20) if isinstance(kwargs.get('timeout',20),(int,float)) else (10,20)
        started=now();r=original(session,method,url,**kwargs);body=r.content
        try:j=r.json();keys=sorted(j)[:30] if isinstance(j,dict) else []
        except ValueError:keys=[]
        record=dict(method=method,host=urlsplit(url).hostname,path=urlsplit(url).path,http_status=r.status_code,content_type=r.headers.get('Content-Type'),bytes=len(body),sha256=digest(body),json_keys=keys,started_at=started,received_at=now(),logout_marker=body==b'LOGOUT')
        records.append(record)
        p=Path(root)/'wire'/route/identity/(str(len(records))+'.bin');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
        return r
    requests.sessions.Session.request=traced
    try:yield records
    finally:requests.sessions.Session.request=original


def load_route(route,sample,start,end):
    import pandas as pd
    import requests
    ticker=sample['ticker'];market=sample['market'];symbol=ticker+('.KS' if market=='KOSPI' else '.KQ')
    if route.startswith('PYKRX'):
        from pykrx import stock
        frame=stock.get_market_ohlcv_by_date(start.replace('-',''),end.replace('-',''),ticker,adjusted=route=='PYKRX_ADJUSTED')
    elif route.startswith('FDR_'):
        import FinanceDataReader as fdr
        prefix={'FDR_NAVER':'NAVER:'+ticker,'FDR_KRX':'KRX:'+ticker,'FDR_YAHOO':'YAHOO:'+symbol}[route]
        frame=fdr.DataReader(prefix,start,end)
    elif route=='NAVER_JSON':
        r=requests.get('https://api.finance.naver.com/siseJson.naver',params=dict(symbol=ticker,requestType=1,startTime=start.replace('-',''),endTime=end.replace('-',''),timeframe='day'));r.raise_for_status();j=ast.literal_eval(r.text.strip())
        frame=pd.DataFrame(j[1:],columns=[str(s).strip() for s in j[0]]);frame.index=pd.to_datetime(frame.pop('날짜').astype(str))
    elif route=='YAHOO_CHART':
        first=int(datetime.fromisoformat(start).replace(tzinfo=KST).timestamp());last=int((datetime.fromisoformat(end).replace(tzinfo=KST)+timedelta(days=1)).timestamp())
        r=requests.get('https://query1.finance.yahoo.com/v8/finance/chart/'+symbol,params=dict(period1=first,period2=last,interval='1d',events='div,splits'));r.raise_for_status();j=r.json()['chart']['result'][0];q=j['indicators']['quote'][0]
        frame=pd.DataFrame({k.title():v for k,v in q.items()},index=[datetime.fromtimestamp(t,timezone.utc).astimezone(KST) for t in j['timestamp']])
    elif route=='DAUM':
        r=requests.get('https://finance.daum.net/api/charts/A'+ticker+'/days',params=dict(limit=30,adjusted='false'));r.raise_for_status();j=r.json()['data']
        names={'Open':'openingPrice','High':'highPrice','Low':'lowPrice','Close':'tradePrice','Volume':'candleAccTradeVolume','Amount':'candleAccTradePrice'}
        frame=pd.DataFrame([{k:x.get(v) for k,v in names.items()} for x in j],index=pd.to_datetime([x['date'][:10] for x in j]))
    else:raise ValueError('UNKNOWN_ROUTE')
    return rows_from_frame(frame,ticker,market,end)


def encrypt_bytes(payload,key):
    """Owner-only market bytes; the existing key is neither stored nor logged."""
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not key:raise ValueError('PRIVATE_ARCHIVE_KEY_NOT_CONNECTED')
    nonce=os.urandom(12);derived=HKDF(algorithm=hashes.SHA256(),length=32,salt=b'C3_SUPPLY_V11_PRIVATE_ARCHIVE',info=b'NONCOMMERCIAL_PERSONAL_RESEARCH').derive(key.encode())
    return b'C3V11GCM1'+nonce+AESGCM(derived).encrypt(nonce,payload,b'C3_V11_MARKET_DATA')


def seal(root,outfile,key):
    """Keep provider data out of public git/artifacts in plaintext."""
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(Path(root).rglob('*')):
            if p.is_file():z.write(p,str(p.relative_to(root)))
    payload=stream.getvalue();sealed=encrypt_bytes(payload,key);Path(outfile).write_bytes(sealed)
    return dict(format='C3V11GCM1_AES256GCM_HKDF_SHA256',plaintext_sha256=digest(payload),ciphertext_sha256=digest(sealed),bytes=len(sealed),key_persisted=False,public_plaintext_market_data=False)


def open_sealed(path,key):
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    b=Path(path).read_bytes()
    if b[:9]!=b'C3V11GCM1':raise ValueError('SEALED_ARCHIVE_FORMAT')
    derived=HKDF(algorithm=hashes.SHA256(),length=32,salt=b'C3_SUPPLY_V11_PRIVATE_ARCHIVE',info=b'NONCOMMERCIAL_PERSONAL_RESEARCH').derive(key.encode())
    return AESGCM(derived).decrypt(b[9:21],b[21:],b'C3_V11_MARKET_DATA')


def run(outdir,sample_file):
    from c3_eod_source_v9 import collect_day
    from c3_selection_scope_v5 import read_csv
    root=Path(outdir);pub=root/'public';private=root/'private';pub.mkdir(parents=True,exist_ok=True);private.mkdir(exist_ok=True)
    start='2026-11-04';end=completed_day();requested=sorted(set([start,'2026-11-05',end]));requested=[d for d in requested if d<=end];sample=json.loads(Path(sample_file).read_text())['sample'];began=time.monotonic();datasets={};official=[];official_meta=[]
    for day in requested:
        m=collect_day(day,private/'official'/day,os.environ.get('KRX_AUTH_KEY'));official_meta.append(m)
        if m['official_dataset_usable']:
            for market in ('KOSPI','KOSDAQ'):
                for r in read_csv(private/'official'/day/(market+'_official.csv')):
                    official.append(dict({k:float(r[k]) for k in FIELDS},ticker=r['ticker'],market=market,date=r['asof']))
    write(pub/'official_status.json',official_meta)
    outcomes=[];all_transport=[]
    for route in FAMILIES:
        collected=[];failures=0;route_start=time.monotonic()
        for item in sample:
            ticker=item['ticker'];started=now();trace=[]
            if route in ('FDR_YAHOO','YAHOO_CHART'):
                outcomes.append(dict(route=route,ticker=ticker,status='NOT_EXECUTED_TERMS_REQUIRE_PRIOR_PERMISSION'));continue
            if failures>=2:
                outcomes.append(dict(route=route,ticker=ticker,status='NOT_ATTEMPTED_CIRCUIT_OPEN'));continue
            try:
                with transport(private,route,ticker) as trace:rows=load_route(route,item,start,end)
                collected+=rows;write(private/'normalized'/route/(ticker+'.json'),rows);latest=max(r['date'] for r in rows)
                outcomes.append(dict(route=route,ticker=ticker,status='OHLCV_RECEIVED',latest=latest,rows=len(rows),valid=sum(r['valid_ohlcv'] for r in rows),halt_like=sum(r['halt_like'] for r in rows),invalid=sum(r['invalid_data'] for r in rows),turnover_present=sum(r['turnover_krw'] is not None for r in rows),started_at=started,received_at=now(),network_calls=len(trace),sha256=digest(json.dumps(rows,sort_keys=True).encode())))
                failures=0
            except Exception as e:
                status=classify_error(trace,e)
                failures=failures+1 if status in ('RATE_LIMITED','ACCESS_REJECTED_NO_BYPASS','SESSION_REQUIRED_LOGOUT_NO_BYPASS','TIMEOUT') or status.startswith('SCHEMA_OR_LIBRARY_ERROR') else 0
                outcomes.append(dict(route=route,ticker=ticker,status=status,started_at=started,received_at=now(),network_calls=len(trace)))
            all_transport += [dict(x,route=route,ticker=ticker) for x in trace]
        datasets[route]=collected;write(pub/'progress.json',dict(completed_route=route,elapsed_seconds=time.monotonic()-began))
        print(json.dumps(dict(completed_route=route,rows=len(collected),elapsed_seconds=round(time.monotonic()-began,1))),flush=True)
        write(pub/(route+'_summary.json'),dict(route=route,family=FAMILIES[route],elapsed_seconds=time.monotonic()-route_start,network_calls=sum(r.get('network_calls',0) for r in outcomes if r['route']==route),results=[r for r in outcomes if r['route']==route],vs_official=compare(collected,[r for r in official if r['ticker'] in {s['ticker'] for s in sample}],requested),regular_only_certified=False,adjustment_basis_certified=False,bulk_permission_confirmed=False))
    comparisons={}
    for a,b in [('PYKRX_ADJUSTED','FDR_NAVER'),('FDR_NAVER','NAVER_JSON'),('FDR_NAVER','YAHOO_CHART'),('NAVER_JSON','DAUM')]:comparisons[a+'__'+b]=dict(independent_vendor_path=FAMILIES[a]!=FAMILIES[b],result=compare(datasets[a],datasets[b],requested))
    write(pub/'comparisons.json',comparisons);write(pub/'transport.json',all_transport)
    import FinanceDataReader as fdr
    from pykrx import stock
    runtime=dict(python=__import__('sys').version,packages={n:importlib.metadata.version(n) for n in ('pykrx','finance-datareader','pandas','cryptography')},adapters={})
    for label,fn in [('pykrx_period',stock.get_market_ohlcv_by_date),('pykrx_cross_section',stock.get_market_ohlcv_by_ticker),('fdr_dispatch',fdr.DataReader)]:
        text=inspect.getsource(inspect.unwrap(fn));runtime['adapters'][label]=dict(module=fn.__module__,sha256=digest(text.encode()));(pub/(label+'_source.txt')).write_text(text)
    write(pub/'runtime.json',runtime)
    auxiliary=[]
    for label,func in [('FDR_LISTING',lambda:fdr.StockListing('KRX-DESC')),('FDR_KOSPI_LIST',lambda:fdr.StockListing('KOSPI')),('FDR_KOSDAQ_LIST',lambda:fdr.StockListing('KOSDAQ')),('FDR_KOSPI_INDEX',lambda:fdr.DataReader('KS11',start,end)),('FDR_KOSDAQ_INDEX',lambda:fdr.DataReader('KQ11',start,end))]:
        trace=[]
        try:
            with transport(private,label,'universe') as trace:frame=func()
            frame.to_csv(private/(label+'.csv'));auxiliary.append(dict(route=label,status='RECEIVED',rows=len(frame),columns=list(frame.columns),network_calls=len(trace),received_at=now(),sha256=digest((private/(label+'.csv')).read_bytes())))
        except Exception as e:auxiliary.append(dict(route=label,status=classify_error(trace,e),network_calls=len(trace)))
        all_transport += [dict(x,route=label) for x in trace]
    for day in requested:
        for market in ('KOSPI','KOSDAQ'):
            trace=[]
            try:
                with transport(private,'PYKRX_CROSS_SECTION',day+market) as trace:frame=stock.get_market_ohlcv_by_ticker(day.replace('-',''),market=market)
                frame.to_csv(private/(day+'_'+market+'_cross.csv'));auxiliary.append(dict(route='PYKRX_CROSS_SECTION',date=day,market=market,status='RECEIVED' if not frame.empty else 'EMPTY',rows=len(frame),network_calls=len(trace)))
            except Exception as e:auxiliary.append(dict(route='PYKRX_CROSS_SECTION',date=day,market=market,status=classify_error(trace,e),network_calls=len(trace)))
            all_transport += [dict(x,route='PYKRX_CROSS_SECTION') for x in trace]
    broker=dict(route='KIWOOM_KRX_DAILY',credentials_present=bool(os.environ.get('KIWOOM_APP_KEY') and os.environ.get('KIWOOM_APP_SECRET')),status='NOT_EXECUTED_CREDENTIAL_PAIR_MISSING')
    if broker['credentials_present']:
        try:
            from kiwoom_daily_readonly import fetch_daily
            rows=fetch_daily('005930',end.replace('-',''),max_pages=1);write(private/'kiwoom.json',rows);broker.update(status='RECEIVED',rows=len(rows),latest=rows[-1]['Date'] if rows else None)
        except Exception as e:broker['status']=str(e) if re.fullmatch(r'[A-Za-z0-9_: =.-]{1,240}',str(e)) else type(e).__name__
    auxiliary.append(broker)
    auxiliary.append(dict(route='FSC_API',status='NOT_EXECUTED_SERVICE_KEY_MISSING' if not os.environ.get('FSC_SERVICE_KEY') else 'KEY_PRESENT_ADAPTER_PENDING',credentials_present=bool(os.environ.get('FSC_SERVICE_KEY')),upstream_family='KRX_DELAYED_PUBLIC_AGENCY_NOT_INDEPENDENT_EXCHANGE',public_redistribution_allowed=False))
    write(pub/'auxiliary.json',auxiliary);write(pub/'transport.json',all_transport)
    archive=seal(private,root/'private_market_data.aesgcm',os.environ.get('KRX_AUTH_KEY'));write(pub/'archive_manifest.json',archive)
    result=dict(schema='C3_SUPPLY_V11_EXPERIMENT',run_id=os.environ.get('GITHUB_RUN_ID','LOCAL'),generated_at=now(),requested_dates=requested,sample_tickers=len(sample),future_eod_not_requested=True,elapsed_seconds=time.monotonic()-began,network_calls=len(all_transport)+sum(len(m['response_diagnostics']) for m in official_meta),independent_libraries_are_not_independent_upstreams=True,current_action='CASH',new_signals=0,orders_enabled=False,archive=archive)
    write(pub/'summary.json',result);print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);p.add_argument('--sample',default='config/c3_supply_v11_sample.json');a=p.parse_args();run(a.outdir,a.sample)
