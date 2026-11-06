"""Recover existing source caches and inspect bulk/date provenance, read only."""
import argparse,csv,gzip,hashlib,io,json,os,subprocess,time,zipfile
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import urllib.request
from c3_supply_v11 import now,write,digest,open_sealed,seal,transport,rows_from_frame,compare,completed_day


def extract_zip(body,root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        if any(Path(n).is_absolute() or '..' in Path(n).parts for n in z.namelist()):raise ValueError('ARCHIVE_PATH_REJECTED')
        z.extractall(root)


def date_fields(doc):
    out={}
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if k in ('BAS_DD','TRD_DD','trdDd','basDd','date','localTradedAt','localDate','bizdate','bizDate','tradeDate','dataDate','CURRENT_DATETIME','CURRENT_TIME') and isinstance(v,(str,int)):out.setdefault(k,set()).add(str(v))
                elif isinstance(v,(dict,list)):walk(v)
        elif isinstance(x,list):
            for y in x:walk(y)
    walk(doc);return {k:sorted(v)[:10] for k,v in out.items()}


def run(outdir):
    import FinanceDataReader as fdr
    import pandas as pd
    root=Path(outdir);pub=root/'public';private=root/'private';pub.mkdir(parents=True,exist_ok=True);private.mkdir(exist_ok=True)
    body=subprocess.check_output(['gh','api','repos/shdmfpsj-beep/krx-auto-scanner/actions/artifacts/13450358932/zip'],timeout=60)
    if digest(body)!='7a67a5371e10f666d6e099f3e1fba6d056258a4a9b40d54285e7769807be26c0':raise ValueError('PROBE_SOURCE_HASH_MISMATCH')
    extract_zip(body,root/'input');key=os.environ['KRX_AUTH_KEY'];plain=open_sealed(root/'input/private_market_data.aesgcm',key);extract_zip(plain,private/'sample_cache')
    # Public SDK source reveals which transport the library actually uses.
    import FinanceDataReader.krx.listing as listing
    for name,module in [('fdr_krx_listing',listing)]:
        p=Path(module.__file__);(pub/(name+'_source.py')).write_text(p.read_text())
    original=urllib.request.urlopen;observed=[]
    def traced(req,*args,**kwargs):
        url=req.full_url if isinstance(req,urllib.request.Request) else str(req);started=now();r=original(req,*args,**kwargs);b=r.read(12*1024*1024+1)
        if len(b)>12*1024*1024:raise ValueError('PUBLIC_RESPONSE_TOO_LARGE')
        params=parse_qs(urlsplit(url).query)
        if isinstance(req,urllib.request.Request) and req.data:
            try:params.update(parse_qs(req.data.decode()))
            except (ValueError,UnicodeError):pass
        try:j=json.loads(b);shape=sorted(j) if isinstance(j,dict) else [];dates=date_fields(j)
        except (ValueError,UnicodeError):shape=[];dates={}
        observed.append(dict(host=urlsplit(url).hostname,path=urlsplit(url).path,method=req.get_method() if isinstance(req,urllib.request.Request) else 'GET',request_fields=sorted(params),requested_dates={k:v for k,v in params.items() if k in ('trdDd','basDd','strtDd','endDd')},http_status=r.getcode(),bytes=len(b),sha256=digest(b),json_keys=shape,date_fields=dates,started_at=started,received_at=now()))
        p=private/'bulk_wire'/str(len(observed));p.parent.mkdir(exist_ok=True);p.write_bytes(b)
        class Response(io.BytesIO):
            headers=r.headers;url=r.geturl();status=r.getcode()
            def getcode(self):return self.status
            def geturl(self):return self.url
            def info(self):return self.headers
        r.close();return Response(b)
    urllib.request.urlopen=traced;bulk=[]
    try:
        for market in ('KOSPI','KOSDAQ'):
            trace=[];before=len(observed)
            try:
                with transport(private,'FDR_BULK',market) as trace:df=fdr.StockListing(market)
                p=private/(market+'_bulk.csv');df.to_csv(p,index=False)
                bulk.append(dict(market=market,rows=len(df),columns=list(df.columns),http=observed[before:],received_at=now(),sha256=digest(p.read_bytes()),source_date_not_inferred_from_filename=True))
            except Exception as e:bulk.append(dict(market=market,error_type=type(e).__name__,http=observed[before:]))
    finally:urllib.request.urlopen=original
    write(pub/'bulk_source_provenance.json',bulk)
    extra=[]
    import requests
    for ticker in ('005930','036930'):
        urls=[('NAVER_NEW_CHART','https://api.stock.naver.com/chart/domestic/item/'+ticker+'/day',dict(startDateTime='202611040000',endDateTime='202611052359')),('NAVER_DAILY_PRICE','https://api.stock.naver.com/stock/'+ticker+'/price',{})]
        for label,url,params in urls:
            trace=[]
            try:
                with transport(private,label,ticker) as trace:
                    res=requests.get(url,params=params);res.raise_for_status();j=res.json()
                write(private/(label+'_'+ticker+'.json'),j)
                shape=sorted(j) if isinstance(j,dict) else 'list'
                sample=j[0] if isinstance(j,list) and j else next((v[0] for v in j.values() if isinstance(v,list) and v),{}) if isinstance(j,dict) else {}
                extra.append(dict(route=label,ticker=ticker,status='JSON_RECEIVED',shape=shape,row_fields=sorted(sample) if isinstance(sample,dict) else [],date_fields=date_fields(j),transport=trace))
            except Exception as e:extra.append(dict(route=label,ticker=ticker,status='FAILED',error_type=type(e).__name__,transport=trace))
    write(pub/'extra_public_paths.json',extra)
    # The operating artifact retains complete OHLCV only for stage-pass names.
    run='42024764636';aid='13416241119';b=subprocess.check_output(['gh','api','repos/shdmfpsj-beep/krx-auto-scanner/actions/artifacts/'+aid+'/zip'],timeout=60)
    if digest(b)!='c18ae45329a63edd4717e9f56186c68c259ef8fc6d50b13d5417a152295f86cd':raise ValueError('OPERATING_SOURCE_HASH_MISMATCH')
    names=('c3_premove_history_v1.csv.gz','c3_premove_observation_status_v1.json','c3_source_observations_v1.jsonl','c3_source_runtime_v1.json')
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        for n in names:
            p=private/'operating'/n;p.parent.mkdir(exist_ok=True);p.write_bytes(z.read(n))
    status=json.loads((private/'operating/c3_premove_observation_status_v1.json').read_text());history=private/'operating/c3_premove_history_v1.csv.gz'
    if digest(history.read_bytes())!=status['output_sha256'][history.name]:raise ValueError('OPERATING_HISTORY_HASH_MISMATCH')
    with gzip.open(history,'rt',encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    write(pub/'operating_ohlcv_recovery.json',dict(source_run=run,artifact_id=aid,rows=len(rows),tickers=len({r['ticker'] for r in rows}),first=min(r['date'] for r in rows),latest=max(r['date'] for r in rows),history_sha256=digest(history.read_bytes()),filtered_subset_not_full_market=True,selection_bias=True,actual_turnover_present=False,regular_only_certified=False))
    archive=seal(private,root/'private_market_data.aesgcm',key);write(pub/'archive_manifest.json',archive)
    write(pub/'summary.json',dict(run_id=os.environ.get('GITHUB_RUN_ID'),generated_at=now(),bulk=bulk,extra_routes=extra,archive=archive,new_signals=0,current_action='CASH',orders_enabled=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);a=p.parse_args();run(a.outdir)
