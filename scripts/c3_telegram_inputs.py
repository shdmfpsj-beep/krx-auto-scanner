"""Pin report inputs to one Git revision and one KRX unadjusted price family."""
import base64,csv,hashlib,importlib,io,json,os,re,sys,tempfile
from pathlib import Path
from urllib.parse import quote
import requests

REPO='shdmfpsj-beep/krx-auto-scanner'
RESEARCH='research/c3-ledger-integrity-audit-20261104'
ROOT='reports/c3_forward_v8'
EXAMPLE_REF='6118f4914975d53dc0b2fd421b5c4cd120c62deb'
CACHE_REF='5346b41312c4b9eddda9529e11547c56d0e97c1d'
CACHE_SHA='edf8e19a7efa3d3d870ca31eda640a21b6cd144bc05b2e53dcf3705dd49cd9cd'
EXAMPLE_ASOF='2026-11-05'

def digest(body):return hashlib.sha256(body).hexdigest()
def canonical(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

class ServiceError(Exception):
    def __init__(self,status):self.status=status;super().__init__('EXTERNAL_SERVICE_STATUS_'+str(status))

class GitHub:
    def __init__(self,token,repo=REPO):self.token=token;self.repo=repo;self.sources=[]
    def api(self,path,method='GET',payload=None,missing_ok=False):
        headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
        r=requests.request(method,'https://api.github.com/repos/'+self.repo+'/'+path,headers=headers,json=payload,timeout=(10,30),allow_redirects=False)
        if missing_ok and r.status_code==404:return None
        if not 200<=r.status_code<300:raise ServiceError(r.status_code)
        return r.json()
    def head(self,branch):return self.api('git/ref/heads/'+quote(branch,safe='/'))['object']['sha']
    def file(self,path,ref,missing_ok=False):
        r=self.api('contents/'+quote(path,safe='/')+'?ref='+quote(ref,safe=''),missing_ok=missing_ok)
        if r is None:return None
        if r.get('encoding')!='base64' or not r.get('content'):raise ValueError('REPOSITORY_FILE_ENCODING_REJECTED')
        body=base64.b64decode(r['content']);self.sources.append(dict(repository=self.repo,path=path,ref=ref,git_blob_sha=r['sha'],sha256=digest(body),bytes=len(body)))
        return body
    def create(self,path,branch,payload):
        return self.api('contents/'+quote(path,safe='/'),method='PUT',payload={'branch':branch,'message':'research: preserve C3 photo-only delivery evidence','content':base64.b64encode(canonical(payload)+b'\n').decode()})

def build_example(report,history,cache_body,expected_cache_sha=CACHE_SHA):
    if digest(cache_body)!=expected_cache_sha:raise ValueError('PINNED_EXAMPLE_CACHE_HASH_MISMATCH')
    if report.get('source_price_asof')!=EXAMPLE_ASOF or report.get('data_quality_state')!='OFFICIAL_VERIFIED':raise ValueError('EXAMPLE_OFFICIAL_REFERENCE_REQUIRED')
    if history.get('price_asof')!='2026-11-04':raise ValueError('EXAMPLE_HISTORY_DATE_MISMATCH')
    rows={r['Code']:r for r in csv.DictReader(io.StringIO(cache_body.decode('utf-8-sig')))}
    out=json.loads(json.dumps(report));out['example_only']=True
    for r in out['research_top2']:
        t=r['ticker'];raw=rows[t];past=history['chart_bars'][t]
        if raw['Name']!=r['name'] or {'STK':'KOSPI','KSQ':'KOSDAQ'}.get(raw['MarketId'])!=r['market']:raise ValueError('EXAMPLE_IDENTITY_MISMATCH')
        values={k:float(str(raw[c]).replace(',','')) for k,c in [('open','Open'),('high','High'),('low','Low'),('close','Close'),('volume','Volume'),('turnover_krw','Amount')]}
        if values['close']!=float(r.get('reference_close',r['close'])):raise ValueError('EXAMPLE_CLOSE_MISMATCH')
        if past[-1]['date']!='2026-11-04' or values['close']-float(raw['Changes'])!=float(past[-1]['close']):raise ValueError('EXAMPLE_PRICE_REBASE_UNRESOLVED')
        r['chart_bars']=past+[dict(values,date=EXAMPLE_ASOF)]
        r['chart_price_basis']='KRX_UNADJUSTED_AS_TRADED'
    out['input_provenance']={'report_ref':EXAMPLE_REF,'history_ref':EXAMPLE_REF,'current_bar_cache_ref':CACHE_REF,'current_bar_sha256':expected_cache_sha,'ultimate_origin':'KRX','independent_vendor_count':1,'reference_entire_market_comparison':'Previously verified exact official/cache 2769-row control; not repeated here.'}
    return out

def load_example(gh):
    report=json.loads(gh.file(ROOT+'/latest.json',EXAMPLE_REF))
    history=json.loads(gh.file('reports/c3_work7_20261105/current/current_candidates.json',EXAMPLE_REF))
    cache=GitHub(gh.token,'FinanceData/fdr_krx_data_cache')
    body=cache.file('data/listing/krx/2026-11-05.csv',CACHE_REF)
    result=build_example(report,history,body);gh.sources+=cache.sources
    return result

def report_pair(gh):
    ref=gh.head(RESEARCH)
    latest=json.loads(gh.file(ROOT+'/latest.json',ref));summary=json.loads(gh.file(ROOT+'/mobile/summary.json',ref))
    return latest,summary,ref

def frozen_live_bars(gh,report,ref):
    day=report['source_price_asof'];lane=report.get('ledger_lane')
    if lane!='lanes/krx_unadjusted_v12':raise ValueError('UNAPPROVED_IMMUTABLE_PRICE_LANE')
    reader=Path(os.environ.get('C3_ARCHIVE_READER_PATH','engine/scripts')).resolve()
    if not (reader/'c3_supply_v11.py').is_file():raise ValueError('FROZEN_ARCHIVE_READER_MISSING')
    sys.path.insert(0,str(reader));module=importlib.import_module('c3_supply_v11')
    key=os.environ.get('KRX_AUTH_KEY','')
    if not key:raise ValueError('PRIVATE_ARCHIVE_READER_KEY_NOT_CONNECTED')
    with tempfile.TemporaryDirectory(prefix='c3-private-decision-') as tmp:
        root=Path(tmp);envelopes=root/'key_envelopes';envelopes.mkdir()
        listing=gh.api('contents/'+ROOT+'/key_envelopes?ref='+quote(ref,safe=''),missing_ok=True) or []
        if len(listing)>32:raise ValueError('KEY_ENVELOPE_INVENTORY_LIMIT')
        for item in listing:
            if item['type']!='file' or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}\.aesgcm',item['name']):raise ValueError('KEY_ENVELOPE_NAME_REJECTED')
            b=gh.file(ROOT+'/key_envelopes/'+item['name'],ref)
            if len(b)>65536:raise ValueError('KEY_ENVELOPE_SIZE_LIMIT')
            (envelopes/item['name']).write_bytes(b)
        os.environ['C3_KEY_ENVELOPES_DIR']=str(envelopes)
        p=root/'decision.aesgcm';p.write_bytes(gh.file(ROOT+'/'+lane+'/decisions/'+day+'.json',ref))
        record=json.loads(module.open_sealed(p,key))
    payload=record['payload']
    if record['sha256']!=digest(canonical(payload)) or payload['price_asof']!=day:raise ValueError('IMMUTABLE_DECISION_HASH_OR_DATE_MISMATCH')
    frozen=payload['models']['B']
    public=report.get('research_top2')
    if (not isinstance(public,list) or not isinstance(frozen,list) or
        [(r.get('ticker'),r.get('signal_id'),r.get('rank')) for r in public] !=
        [(r.get('ticker'),r.get('signal_id'),r.get('rank')) for r in frozen[:2]]):
        raise ValueError('PUBLIC_AND_FROZEN_CANDIDATE_COUNT_OR_ORDER_MISMATCH')
    by={r['ticker']:r for r in frozen}
    for r in report['research_top2']:
        old=by.get(r['ticker'])
        if old is None or any(old.get(k)!=r.get(k) for k in ('name','signal_id','reference_close','entry_plans','model','rank')):raise ValueError('PUBLIC_REPORT_AND_FROZEN_DECISION_MISMATCH')
        r['chart_bars']=old['chart_bars'];r['chart_price_basis']='KRX_UNADJUSTED_AS_TRADED'
    report['input_provenance']={'research_ref':ref,'decision_payload_sha256':record['sha256'],'ultimate_origin':'KRX','price_basis':'UNADJUSTED_AS_TRADED'}
    # Only the authenticated immutable B-decision may supply original ranks 3+.
    # The v6.12/v6.13 whole-market TOP20 is a DIFFERENT research model and
    # cannot be presented as ranked B-model substitutes.
    model_b=payload.get('models',{}).get('B',[])
    if (len(model_b)>2 and [x.get('rank') for x in model_b]==list(range(1,len(model_b)+1))
            and len({x.get('ticker') for x in model_b})==len(model_b)):
        cands=json.loads(json.dumps(model_b))
        for row in cands:row['chart_price_basis']='KRX_UNADJUSTED_AS_TRADED'
        report['presentation_ranked_pool']=cands
        report['presentation_pool_proof']={
            'schema':'C3_IMMUTABLE_B_POOL_V21',
            'origin':'AUTHENTICATED_FROZEN_C3_B_DECISION',
            'frozen_research_commit':ref,
            'frozen_decision_sha256':record['sha256'],
            'pool_sha256':digest(canonical(cands)),
            'source_run_id':report.get('source_run_id'),
            'source_validation_sha256':report.get('source_validation_sha256'),
            'asof':day,
        }
    return report
