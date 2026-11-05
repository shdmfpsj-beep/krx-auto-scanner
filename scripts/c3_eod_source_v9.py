"""Read-only official EOD diagnostics compatible with the existing v6.5 adapter.

Retain independent market/date/HTTP/schema evidence on failure. Never persist
request credentials or raw error bodies, and never label an empty result a
holiday, a bad key, or a publishing delay without evidence.
"""
import argparse,hashlib,json,os,re
from datetime import date,datetime,timezone,timedelta
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError,URLError

from krx_official_eod_v65 import BASE_URL,MARKETS,MARKET_FIELDS,COLLECT_SCHEMA,normalize_payload,write_csv

KST=timezone(timedelta(hours=9));LIMIT=5*1024*1024


def utc_now():return datetime.now(timezone.utc).isoformat()
def digest(body):return hashlib.sha256(body).hexdigest()


def scrub(value,key):
    s=str(value)
    if key:s=re.sub(re.escape(key),'[REDACTED]',s,flags=re.I)
    s=re.sub(r'[A-Za-z0-9+/=_-]{24,}','[REDACTED_TOKEN]',s)
    return s[:160]


def fetch(market,day,key,opener=urlopen,clock=utc_now):
    key=(key or '').strip()
    endpoint=MARKETS[market];query={'basDd':day.replace('-','')};started=clock()
    info=dict(market=market,asof=day,endpoint=endpoint,method='GET',query=query,credential_present=bool(key),
        request_header_names=['AUTH_KEY','Accept'],started_at=started,http_status=None,content_type=None,body_sha256=None,
        body_bytes=0,json_top_keys=[],outblock_type=None,outblock_rows=None,status='AUTH_KEY_NOT_CONNECTED',provider_error={})
    if not key:return None,info
    if any(c.isspace() for c in key):info['status']='AUTH_KEY_FORMAT_INVALID';return None,info
    req=Request(BASE_URL+endpoint+'?'+urlencode(query),headers={'AUTH_KEY':key,'Accept':'application/json'},method='GET')
    body=b''
    try:
        with opener(req,timeout=20) as response:
            info['http_status']=response.getcode();info['content_type']=scrub(response.headers.get('Content-Type',''),key)[:100];body=response.read(LIMIT+1)
    except HTTPError as exc:
        info['http_status']=exc.code;body=exc.read(LIMIT+1)
    except (URLError,TimeoutError,OSError) as exc:
        info.update(status='NETWORK_UNAVAILABLE',error_type=type(exc).__name__,received_at=clock());return None,info
    info.update(body_bytes=len(body),body_sha256=digest(body),received_at=clock())
    if len(body)>LIMIT:info['status']='RESPONSE_TOO_LARGE';return None,info
    try:doc=json.loads(body.decode('utf-8'))
    except (ValueError,UnicodeDecodeError):doc=None
    if isinstance(doc,dict):
        info['json_top_keys']=[scrub(k,key) for k in sorted(doc)][:20]
        for field in ('error','error_code','error_message','message','respCode','respMsg','rsp_cd','rsp_msg','RESULT_CODE','RESULT_MSG'):
            if field in doc and isinstance(doc[field],(str,int,float)):info['provider_error'][field]=scrub(doc[field],key)
        block=doc.get('OutBlock_1');info['outblock_type']=type(block).__name__;info['outblock_rows']=len(block) if isinstance(block,list) else None
    if info['http_status'] in (401,403):info['status']='AUTH_OR_SERVICE_APPROVAL_REJECTED';return None,info
    if info['http_status']==429:info['status']='RATE_LIMITED';return None,info
    if info['http_status']!=200:info['status']='HTTP_SERVICE_ERROR';return None,info
    if doc is None:info['status']='NON_JSON_RESPONSE';return None,info
    if not isinstance(doc,dict) or 'OutBlock_1' not in doc:info['status']='OUTBLOCK_MISSING_OR_PROVIDER_ERROR';return None,info
    if not isinstance(doc['OutBlock_1'],list):info['status']='OUTBLOCK_WRONG_TYPE';return None,info
    if not doc['OutBlock_1']:info['status']='OUTBLOCK_EMPTY';return None,info
    info['status']='NONEMPTY_OFFICIAL_JSON';return doc,info


def collect_day(day,outdir,key,now=None,opener=urlopen):
    if date.fromisoformat(day).isoformat()!=day:raise ValueError('CANONICAL_DATE_REQUIRED')
    now=now or datetime.now(timezone.utc);local=now.astimezone(KST)
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    manifest=dict(schema=COLLECT_SCHEMA,asof=day,retrieval_utc=now.isoformat(),api_reference_base=BASE_URL,endpoints=list(MARKETS.values()),
        authentication_secret_persisted=False,krx_eod_authenticated=False,official_dataset_usable=False,independent_1530_regular_session_certified=False,
        session_scope_includes_aftermarket_verified=False,source_price_authorized_for_trading=False,trade_approved=False,orders_enabled=False,decision='CASH',
        official_market_rows=0,unmatched_nonshort_codes=0,market_file_sha256={},raw_response_sha256={},response_diagnostics=[],price_basis='UNADJUSTED_AS_REPORTED',quality={})
    if day>local.date().isoformat() or (day==local.date().isoformat() and local.hour*60+local.minute<15*60+30):
        manifest['status']='SESSION_NOT_COMPLETED_NO_REQUEST'
    else:
        results={};nonshort=0
        for market in MARKETS:
            doc,info=fetch(market,day,key,opener)
            if info['body_sha256']:manifest['raw_response_sha256'][market]=info['body_sha256']
            if doc is not None:
                try:
                    rows,opaque=normalize_payload(doc,day,market);results[market]=rows;nonshort+=opaque;info['normalized_rows']=len(rows);info['status']='NORMALIZED'
                except ValueError as exc:info['status']=scrub(str(exc),key)
            manifest['response_diagnostics'].append(info)
        if len(results)==2 and not ({r['ticker'] for r in results['KOSPI']}&{r['ticker'] for r in results['KOSDAQ']}):
            for market,rows in results.items():
                p=root/(market+'_official.csv');write_csv(p,rows,MARKET_FIELDS);manifest['market_file_sha256'][market]=digest(p.read_bytes())
                manifest['quality'][market]=dict(rows=len(rows),valid_daily_bars=sum(r['valid_daily_bar'] for r in rows),
                    invalid_or_halt_bars=sum(not r['valid_daily_bar'] for r in rows),unique_tickers=len({r['ticker'] for r in rows}),all_dates_matched=True)
            manifest.update(status='OFFICIAL_EOD_AVAILABLE_SESSION_SCOPE_UNCERTIFIED',krx_eod_authenticated=True,official_dataset_usable=True,
                official_market_rows=sum(len(r) for r in results.values()),unmatched_nonshort_codes=nonshort)
        else:
            manifest['status']='OFFICIAL_MARKETS_NOT_COMPLETE'
            manifest['successful_partial_markets']=sorted(results)
            if len(results)==2:manifest['status']='OFFICIAL_SECURITY_IN_MULTIPLE_MARKETS'
    if not manifest['official_dataset_usable']:
        for market in MARKETS:
            p=root/(market+'_official.csv')
            if p.exists():p.unlink()
    (root/'krx_v65_collect_status.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


def run(days,outdir,key,now=None,opener=urlopen):
    if not days or len(days)!=len(set(days)):raise ValueError('EMPTY_OR_DUPLICATE_REQUEST_DATES')
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True);rows=[]
    for day in sorted(days):rows.append(collect_day(day,root/day,key,now,opener))
    available=[r['asof'] for r in rows if r['official_dataset_usable']]
    summary=dict(schema='C3_EOD_DIAGNOSTICS_V9',generated_at=utc_now(),dates=[dict(asof=r['asof'],status=r['status'],rows=r['official_market_rows'],
        response_diagnostics=r['response_diagnostics'],quality=r['quality']) for r in rows],latest_available_asof=max(available) if available else None,
        secret_recorded=False,regular_only_certified=False,orders_enabled=False)
    for current in summary['dates']:
        if current['asof'] not in available and available and any(d<current['asof'] for d in available):current['control_interpretation']='EARLIER_DATE_WORKS_TARGET_NOT_AVAILABLE;NO_PROVEN_EXACT_PUBLICATION_CAUSE'
    if available:
        latest=max(available);codes={}
        import csv
        for day in available:
            got=set()
            for market in MARKETS:
                with (root/day/(market+'_official.csv')).open(encoding='utf-8-sig') as f:got.update(r['ticker'] for r in csv.DictReader(f))
            codes[day]=got
        earliest=min(available);summary['membership_change']=dict(before=earliest,after=latest,missing_vs_before=sorted(codes[earliest]-codes[latest]),new_vs_before=sorted(codes[latest]-codes[earliest]),cause_not_inferred=True)
    (root/'eod_diagnostics.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--asof',nargs='+',required=True);p.add_argument('--outdir',required=True);a=p.parse_args()
    result=run(a.asof,a.outdir,os.environ.get('KRX_AUTH_KEY'))
    print(json.dumps(dict(dates=[{k:r[k] for k in ('asof','status','rows')} for r in result['dates']],latest_available_asof=result['latest_available_asof'],secret_recorded=False)))
