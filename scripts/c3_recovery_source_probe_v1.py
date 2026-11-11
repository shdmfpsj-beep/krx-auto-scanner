"""Date-pinned source recovery. No orders, signals, Git writes or Telegram calls."""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import tempfile
import requests
from datetime import date,datetime,timedelta,timezone
from pathlib import Path

from c3_telegram_inputs import GitHub,canonical
from kiwoom_daily_readonly import post,check_ok,diagnostic_codes

TARGET='2026-11-11'
PRIOR_CACHE_SHA='3dc4b25f7bd1f8c2c42bdce6e916fd9838d07685ae57311e97127c6b997c4baa'
ALLOWED_CHART_IDS=('ka10081','ka11081')


def digest(value):return hashlib.sha256(value).hexdigest()


def strict_source_post(path,headers,body):
    """Documented OAuth/chart requests only, redirects and retries disabled."""
    api_id=headers.get('api-id')
    if not (path=='/oauth2/token' or path=='/api/dostk/chart' and api_id in ALLOWED_CHART_IDS):
        raise ValueError('READ_ONLY_ENDPOINT_REQUIRED')
    h=dict(headers,Accept='application/json')
    if path=='/oauth2/token':h['api-id']='au10001'
    response=requests.post('https://api.kiwoom.com'+path,headers=h,json=body,
                           timeout=(10,25),allow_redirects=False)
    raw=response.content
    try:payload=response.json()
    except ValueError:payload=None
    kind='JSON_OBJECT' if isinstance(payload,dict) else 'HTML' if raw.lstrip().startswith(b'<') else 'NON_JSON'
    if response.status_code!=200 or not isinstance(payload,dict):
        raise RuntimeError('KIWOOM_HTTP_REJECTED http_status='+str(response.status_code)+
                           ' body_kind='+kind+' body_sha256='+digest(raw))
    return payload,dict(response.headers)


def kiwoom_probe(env=None,send=strict_source_post):
    env=env if env is not None else os.environ
    key=env.get('KIWOOM_APP_KEY','').strip();secret=env.get('KIWOOM_APP_SECRET','').strip()
    out={'app_key_present':bool(key),'app_secret_present':bool(secret),'read_only':True,
         'status':'MISSING_CREDENTIAL_PAIR','regular_market_wide_certified':False,'requests':0}
    if not key or not secret:return out
    try:
        out['requests']+=1
        reply,_=send('/oauth2/token',{'Content-Type':'application/json;charset=UTF-8'},
                     {'grant_type':'client_credentials','appkey':key,'secretkey':secret})
        check_ok(reply)
        token=reply.get('token')
        if not token:raise ValueError('KIWOOM_TOKEN_MISSING')
        out.update(status='TOKEN_ACCEPTED',token_received=True)
        out['chart_probes']=[]
        for api_id in ALLOWED_CHART_IDS:
            out['requests']+=1
            body,_=send('/api/dostk/chart',{'Content-Type':'application/json;charset=UTF-8',
                'authorization':'Bearer '+token,'api-id':api_id,'cont-yn':'N','next-key':''},
                {'stk_cd':'005930','base_dt':'20261111','upd_stkpc_tp':'0'})
            code,embedded=diagnostic_codes(body)
            arrays={k:v for k,v in body.items() if isinstance(v,list)}
            out['chart_probes'].append({'api_id':api_id,'return_code':code,'embedded_code':embedded,
                'row_keys':{k:sorted(v[0]) if v and isinstance(v[0],dict) else [] for k,v in arrays.items()},
                'rows':{k:len(v) for k,v in arrays.items()},'body_sha256':digest(canonical(body)),
                'single_security_probe_only':True})
    except Exception as exc:
        text=str(exc)
        # Existing adapter emits only numerical error codes and field names.
        out['status']='AUTH_OR_CHART_REQUEST_FAILED'
        out['error_type']=type(exc).__name__
        out['diagnostic']=text if re.fullmatch(r'[A-Z_0-9 =,a-z\-]{1,250}',text) and not any(s and s in text for s in (key,secret)) else 'PROVIDER_REJECTED_OR_UNAVAILABLE'
    return out


def execute(outdir,target=TARGET,probe_configured_broker=False):
    if date.fromisoformat(target).isoformat()!=target:raise ValueError('CANONICAL_TARGET_REQUIRED')
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    result={'schema':'C3_EMERGENCY_SOURCE_PROBE_V1','target_day':target,
        'started_at':datetime.now(timezone.utc).isoformat(),'status':'SOURCE_BLOCKED',
        'registered_signals':0,'telegram_send_attempts':0,'orders_enabled':False,
        'regular_only_certified':False,'quality_reused_only_on_exact_hash':True}
    try:
        # This is the already approved pinned diagnostic implementation.
        from c3_eod_source_v9 import collect_day
        with tempfile.TemporaryDirectory(prefix='c3-private-source-') as tmp:
            for day in (target,(date.fromisoformat(target)-timedelta(days=1)).isoformat()):
                item=collect_day(day,Path(tmp)/day,os.environ.get('KRX_AUTH_KEY'))
                result.setdefault('official_probes',[]).append(item)
        cache=GitHub(os.environ.get('GH_TOKEN',''),'FinanceData/fdr_krx_data_cache')
        ref=cache.head('master');raw=cache.file('data/listing/krx/'+target+'.csv',ref,missing_ok=True)
        if raw:
            rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
            counts={m:sum(r.get('MarketId')==k for r in rows) for m,k in [('KOSPI','STK'),('KOSDAQ','KSQ'),('KONEX','KNX')]}
            fp=digest(raw)
            result['cache']={'ref':ref,'sha256':fp,'raw_rows':len(rows),'market_rows':counts,
                'target_rows':counts['KOSPI']+counts['KOSDAQ'],
                'same_as_earlier_validated_source':target==TARGET and fp==PRIOR_CACHE_SHA,
                'prior_quality_evidence':'43024113052 / 13874303493',
                'regular_only_certified':False,'aftermarket_scope_not_relabelled':True,
                'received_at':datetime.now(timezone.utc).isoformat()}
        else:result['cache']={'status':'TARGET_NOT_PUBLISHED'}
        result['kiwoom']=(kiwoom_probe() if probe_configured_broker else {
            'status':'NOT_RETRIED_DEVICE_AUTHORIZATION_REQUIRED',
            'previous_observed_code':'8050','previous_evidence_run_id':'43066493622',
            'requests':0,'regular_market_wide_certified':False})
        result['kis']={'app_key_present':bool(os.environ.get('KIS_APP_KEY')),
                       'app_secret_present':bool(os.environ.get('KIS_APP_SECRET')),
                       'regular_market_wide_certified':False}
    except Exception as exc:
        result.update(status='PROBE_TRANSPORT_FAILED',error_type=type(exc).__name__)
    result['completed_at']=datetime.now(timezone.utc).isoformat()
    (out/'source_recovery.json').write_bytes(canonical(result)+b'\n')
    print(json.dumps({k:result.get(k) for k in ('target_day','status','telegram_send_attempts','orders_enabled')},ensure_ascii=False))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);p.add_argument('--date',default=TARGET)
    p.add_argument('--probe-configured-broker',action='store_true',help='Only after resolving the observed device authorization error')
    a=p.parse_args();r=execute(a.outdir,a.date,a.probe_configured_broker)
    raise SystemExit(1 if r['status']=='PROBE_TRANSPORT_FAILED' else 0)
