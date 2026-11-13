"""Bounded real-date source recovery. Cache availability never certifies BUY."""
import argparse,csv,hashlib,io,json,math,os,re
from collections import Counter
from datetime import datetime,timezone,timedelta
from pathlib import Path
from c3_telegram_inputs import GitHub,canonical
from c3_morning_source_v1 import cache_rows,compare,normalized_hash


def write(path,doc):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(canonical(doc)+b'\n')


def validate(rows,day):
    from c3_runtime_v10 import quality
    if not rows or any(r['asof']!=day for r in rows):raise ValueError('ACTUAL_SOURCE_DAY_REQUIRED')
    q=quality(rows,[],day)
    if q['errors']:raise ValueError('SOURCE_INTERNAL_QUALITY_FAILED')
    return q


def cache(day,out,gh):
    ref=gh.head('master');path='data/listing/krx/'+day+'.csv';raw=gh.file(path,ref)
    rows,excluded=cache_rows(raw,day);quality=validate(rows,day)
    out.mkdir(parents=True,exist_ok=True);(out/'original.csv').write_bytes(raw)
    return rows,dict(provider='FINANCEDATA_KRX_DATED_CACHE',repository=gh.repo,path=path,ref=ref,
        received_at=datetime.now(timezone.utc).isoformat(),raw_sha256=hashlib.sha256(raw).hexdigest(),
        rows=len(rows),markets=dict(Counter(r['market'] for r in rows)),excluded=excluded,
        quality=quality,git_source=gh.sources[-1],price_basis='UNADJUSTED_AS_REPORTED_CACHE',
        regular_only_certified=False,independent_provider_from_krx=False)


def official_rows(root):
    rows=[]
    for market in ('KOSPI','KOSDAQ'):
        with (root/(market+'_official.csv')).open(encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                for k in ('open','high','low','close','volume','turnover_krw'):r[k]=float(r[k])
                rows.append(r)
    return rows


def pykrx_probe(day,out,names):
    from pykrx import stock
    result=dict(provider='PYKRX_KRX_FULL_MARKET',asof=day,rows=0,markets={},regular_only_certified=False)
    allrows=[]
    for market in ('KOSPI','KOSDAQ'):
        try:
            from unittest.mock import patch
            import requests
            original=requests.sessions.Session.request
            def bounded(session,*args,**kwargs):
                kwargs.setdefault('timeout',(5,20));return original(session,*args,**kwargs)
            with patch.object(requests.sessions.Session,'request',bounded):
                df=stock.get_market_ohlcv_by_ticker(day.replace('-',''),market=market)
            raw=df.to_csv().encode();(out/(market+'_pykrx.csv')).write_bytes(raw)
            result['markets'][market]=dict(rows=len(df),raw_sha256=hashlib.sha256(raw).hexdigest())
            for t,r in df.iterrows():
                if str(t) not in names:raise ValueError('PYKRX_CODE_NOT_IN_DATED_CACHE')
                allrows.append(dict(ticker=str(t),name=names[str(t)],market=market,asof=day,
                    **{k:float(r[c]) for k,c in [('open','시가'),('high','고가'),('low','저가'),('close','종가'),('volume','거래량'),('turnover_krw','거래대금')]}))
        except Exception as exc:result['markets'][market]=dict(status='FAILED',error_type=type(exc).__name__)
    result['rows']=len(allrows)
    result['status']='FULL_MARKET_OBSERVED' if len(result['markets'])==2 and all(v.get('rows',0)>0 for v in result['markets'].values()) else 'SOURCE_UNAVAILABLE'
    return allrows,result


def public_krx_probe(day):
    import requests
    result={}
    for market,mkt in [('KOSPI','STK'),('KOSDAQ','KSQ')]:
        try:
            response=requests.post('https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd',
                data=dict(bld='dbms/MDC/STAT/standard/MDCSTAT01501',mktId=mkt,trdDd=day.replace('-',''),money='1',share='1',csvxls_isNo='false'),
                headers={'User-Agent':'Mozilla/5.0','Referer':'https://data.krx.co.kr/'},timeout=(5,20))
            body=response.content
            try:doc=response.json()
            except ValueError:doc={}
            rows=doc.get('OutBlock_1',[]) if isinstance(doc,dict) else []
            result[market]=dict(http_status=response.status_code,rows=len(rows) if isinstance(rows,list) else 0,
                response_sha256=hashlib.sha256(body).hexdigest(),json_keys=list(doc)[:10],received_at=datetime.now(timezone.utc).isoformat())
        except Exception as exc:result[market]=dict(status='FAILED',error_type=type(exc).__name__)
    return result


def run(day,out,control=None,attempts=1):
    from c3_eod_source_v9 import collect_day
    from c3_morning_source_v1 import bounded_target
    from c3_daily_research_v8 import collect_indices
    from c3_morning_provider_probe_v1 import probe
    out.mkdir(parents=True,exist_ok=True);clock=datetime.now(timezone.utc)
    if day>=clock.astimezone(timezone(timedelta(hours=9))).date().isoformat():raise ValueError('COMPLETED_PRIOR_DATE_REQUIRED')
    gh=GitHub(os.environ['GH_TOKEN']);key=os.environ.get('KRX_AUTH_KEY')
    manifest,receipts=bounded_target(day,out/'official',key,lambda d,p,k:collect_day(d,p,k,now=clock),attempts=attempts)
    result=dict(schema='C3_ACTUAL_SOURCE_RECOVERY_V1',asof=day,started_at=clock.isoformat(),source_run_id=os.environ.get('GITHUB_RUN_ID'),
        official=manifest,attempts=receipts,regular_only_certified=False,financial_pit_verified=False,buy_approved=False,orders_enabled=False,telegram_requests=0,
        status='SOURCE_UNAVAILABLE',research_ready=False,approved_source_ready=False,rows=0)
    if control:result['official_control']=collect_day(control,out/'control',key,now=clock)
    cached=[]
    # Exact-day post-close prefetch is a research input, not an approval.
    # Fresh official KRX below must still match every identity and price field.
    try:
        from c3_early_source_v1 import load_prefetch
        cached,proof=load_prefetch(day,out/'cache',gh,key);result['cache']=proof
    except Exception as exc:
        result['early_archive']=dict(status='UNAVAILABLE_OR_REJECTED',error_type=type(exc).__name__)
        try:cached,proof=cache(day,out/'cache',GitHub(os.environ['GH_TOKEN'],'FinanceData/fdr_krx_data_cache'));result['cache']=proof
        except Exception as exc:result['cache']=dict(status='FAILED',error_type=type(exc).__name__)
    chosen=[]
    if manifest['official_dataset_usable']:
        chosen=official_rows(out/'official');result['quality']=validate(chosen,day)
        if cached:
            try:result['comparison']=compare(chosen,cached,day);result['status']='OFFICIAL_VERIFIED';result['approved_source_ready']=True
            except ValueError as exc:
                result.update(status='SOURCE_CONFLICT',comparison={'status':'MISMATCH','reason':str(exc)});chosen=[]
                if result['cache'].get('early_archive_used'):
                    result['early_archive_comparison']=result['comparison']
                    try:
                        fresh,proof=cache(day,out/'fresh-cache',GitHub(os.environ['GH_TOKEN'],'FinanceData/fdr_krx_data_cache'))
                        matched=compare(official_rows(out/'official'),fresh,day)
                        result.update(cache=proof,comparison=matched,status='OFFICIAL_VERIFIED',approved_source_ready=True)
                        chosen=official_rows(out/'official')
                    except Exception as failure:
                        result['fresh_cache_after_revision']=dict(status='REJECTED',error_type=type(failure).__name__)
        else:result['status']='SINGLE_SOURCE_UNVERIFIED'
    elif cached:
        chosen=cached;result['quality']=result['cache']['quality'];result['status']='SINGLE_SOURCE_UNVERIFIED'
        alt,altproof=pykrx_probe(day,out,{r['ticker']:r['name'] for r in cached});result['pykrx']=altproof
        if altproof['status']=='FULL_MARKET_OBSERVED':
            try:result['alternative_comparison']=compare(alt,cached,day);result['status']='CROSS_SOURCE_MATCHED_RESEARCH'
            except ValueError as exc:result['alternative_comparison']=dict(status='MISMATCH',reason=str(exc))
        result['public_krx']=public_krx_probe(day)
    if chosen:
        result.update(research_ready=True,rows=len(chosen),markets=dict(Counter(r['market'] for r in chosen)),
            normalized_rows_sha256=normalized_hash(chosen),data_received_at=datetime.now(timezone.utc).isoformat(),
            price_basis='UNADJUSTED_AS_REPORTED',corporate_actions_adjusted=False,session_scope='DAILY_REGULAR_SCOPE_UNCERTIFIED')
        write(out/'normalized_market.json',dict(asof=day,source_status=result['status'],rows=chosen,normalized_rows_sha256=result['normalized_rows_sha256']))
    try:
        result['indices']=collect_indices(out/'indices',day)
        result['indices_ready']=all(v['end']==day for v in result['indices']['series'].values())
    except Exception as exc:result.update(indices_ready=False,index_error_type=type(exc).__name__)
    result['existing_broker_probe']=probe(day.replace('-',''))
    try:
        wf=gh.api('actions/workflows/408546189');runs=gh.api('actions/workflows/408546189/runs?per_page=12')
        result['morning_workflow']=dict(id=wf['id'],name=wf['name'],state=wf['state'],path=wf['path'],
            runs=[{k:r.get(k) for k in ('id','event','created_at','status','conclusion','head_sha','html_url')} for r in runs['workflow_runs']])
    except Exception as exc:result['morning_workflow']=dict(status='LOOKUP_FAILED',error_type=type(exc).__name__)
    result['finished_at']=datetime.now(timezone.utc).isoformat();write(out/'collection.json',result)
    print(json.dumps({k:result.get(k) for k in ('asof','status','research_ready','approved_source_ready','rows','markets','indices_ready')},ensure_ascii=False))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--date',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--control');a=p.parse_args();run(a.date,a.out,a.control)
