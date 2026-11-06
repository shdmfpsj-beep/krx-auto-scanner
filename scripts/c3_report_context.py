"""Dated, post-selection company research. Never changes C3 scores or orders.

Use the existing free OpenDART key and existing corporation-code reader. No
paid API, news inference, or unbounded market-wide financial backfill. API
snapshots can be restated: they are report context, never historical signals.
"""
import copy, hashlib, json, os, re, time, calendar
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import requests

BASE = 'https://opendart.fss.or.kr/api/'
SCHEMA = 'C3_POST_SELECTION_COMPANY_CONTEXT_V1'
DEFAULT_CURATED = Path(__file__).resolve().parents[1] / 'config/c3_company_context_verified.json'
PERIODS = {'11013': (3, 1), '11012': (6, 2), '11014': (9, 3), '11011': (12, 4)}


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def amount(value):
    s = str(value or '').replace(',', '').strip()
    if re.fullmatch(r'\(-?\d+\)', s):
        s = '-' + s[1:-1]
    return int(s) if re.fullmatch(r'-?\d+', s) else None


def quarter(year, code):
    return f'{year}.{PERIODS[code][1]}Q'


def publication_ok(item, asof, max_age=None):
    """Date-only same-day documents cannot prove pre-decision availability."""
    try:
        published = date.fromisoformat(item['published_on'])
        cutoff = date.fromisoformat(asof)
        return published < cutoff and (max_age is None or (cutoff - published).days <= max_age)
    except (ValueError, TypeError, KeyError):
        return False


class DartClient:
    def __init__(self, key, outdir, session=None):
        self.key, self.root = key, Path(outdir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.requests, self.audit = 0, []
        self.started = time.monotonic()

    def fetch(self, endpoint, params):
        if self.requests >= 28 or time.monotonic() - self.started > 180:
            raise ValueError('DART_REPORT_CONTEXT_REQUEST_BUDGET')
        self.requests += 1
        time.sleep(.15)
        try:
            r = self.session.get(BASE + endpoint, params={'crtfc_key': self.key, **{k:v for k,v in params.items() if k!='crtfc_key'}}, timeout=(8, 25), allow_redirects=False)
            if r.status_code != 200:
                raise ValueError('DART_CONTEXT_HTTP_' + str(r.status_code))
            body = r.content
        except requests.RequestException:
            raise ValueError('DART_CONTEXT_TRANSPORT_FAILURE') from None
        # Never save a request URL, headers, query parameters, or exception text.
        self.audit.append({'endpoint':endpoint, 'sha256':hashlib.sha256(body).hexdigest(), 'bytes':len(body), 'received_at':datetime.now(timezone.utc).isoformat()})
        if endpoint.endswith('.json'):
            obj = json.loads(body)
            status = str(obj.get('status', 'UNKNOWN'))
            if status not in ('000', '013'):
                raise ValueError('DART_CONTEXT_STATUS_' + (status if re.fullmatch(r'\d{3}',status) else 'UNKNOWN'))
            name = f'{self.requests:02}_{endpoint}'
            # API responses contain public company information, no authentication.
            (self.root / name).write_bytes(body)
        return body

    def json(self, endpoint, **params):
        return json.loads(self.fetch(endpoint+'.json', params))

    def mapping(self):
        path=Path(os.environ.get('C3_DART_CORP_CACHE','.cache/c3-dart/corp_codes.json'))
        if path.is_file():
            try:
                cached=json.loads(path.read_text())
                if cached.get('sha256')==digest(cached['mapping']) and 0 <= (datetime.now(timezone.utc)-datetime.fromisoformat(cached['collected_at'])).total_seconds()<30*86400:
                    return cached['mapping']
            except (ValueError,KeyError,TypeError):pass
        from krx_opendart_financial_v91 import get_corp_codes
        mapping=get_corp_codes(self.key, fetch=self.fetch)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({'mapping':mapping,'sha256':digest(mapping),'collected_at':datetime.now(timezone.utc).isoformat()}))
        return mapping

    def company(self, ticker, corp, asof):
        identity=self.json('company',corp_code=corp)
        if identity.get('stock_code')!=ticker:raise ValueError('DART_CONTEXT_CORPORATE_IDENTITY_MISMATCH')
        cutoff = (date.fromisoformat(asof)-timedelta(days=1)).strftime('%Y%m%d')
        filings=[]
        for page in (1, 2):
            obj=self.json('list',corp_code=corp,bgn_de=f'{int(asof[:4])-1}0101',end_de=cutoff,pblntf_ty='A',page_count=100,page_no=page,last_reprt_at='N')
            filings.extend(obj.get('list') or [])
            if page >= int(obj.get('total_page', 1)):
                break
        for page in (1,2):
            obj=self.json('list',corp_code=corp,bgn_de=(date.fromisoformat(asof)-timedelta(days=28)).strftime('%Y%m%d'),end_de=cutoff,page_count=100,page_no=page,last_reprt_at='N')
            filings.extend(obj.get('list') or [])
            if page >= int(obj.get('total_page',1)):break
        filings=list({r.get('rcept_no'):r for r in filings}.values())
        filings=[r for r in filings if re.fullmatch(r'\d{14}',str(r.get('rcept_no',''))) and re.fullmatch(r'\d{8}',str(r.get('rcept_dt',''))) and str(r['rcept_dt']) <= cutoff]
        if any(r.get('stock_code') not in (None,'',ticker) for r in filings):
            raise ValueError('DART_CONTEXT_CORPORATE_IDENTITY_MISMATCH')
        periodic={}
        for r in filings:
            m=re.search(r'(사업|반기|분기)보고서\s*\((\d{4})\.(\d{2})\)',r.get('report_nm',''))
            if not m:continue
            year,month=int(m[2]),int(m[3])
            code={3:'11013',6:'11012',9:'11014',12:'11011'}.get(month)
            if code and int(asof[:4])-1 <= year <= int(asof[:4]):
                key=(year,code)
                if key not in periodic or r['rcept_no'] > periodic[key]['rcept_no']:periodic[key]=r
        periods=[]
        # Five most recent reports cover four quarters, including FY minus Q3.
        for (year,code),filing in sorted(periodic.items(),key=lambda x:(x[0][0],PERIODS[x[0][1]][0]),reverse=True)[:5]:
            obj=self.json('fnlttSinglAcntAll',corp_code=corp,bsns_year=year,reprt_code=code,fs_div='CFS')
            rows=obj.get('list') or []
            if not rows:continue
            periods.append(parse_statement(rows,year,code,filings,asof))
        recent=[]
        for r in sorted(filings,key=lambda x:x['rcept_no'],reverse=True):
            published=f"{r['rcept_dt'][:4]}-{r['rcept_dt'][4:6]}-{r['rcept_dt'][6:8]}"
            if (date.fromisoformat(asof)-date.fromisoformat(published)).days <= 28:
                recent.append({'title':r['report_nm'],'published_on':published,'receipt_no':r['rcept_no'],'url':'https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+r['rcept_no'],'title_only':True})
        return {'ticker':ticker,'corp_code':corp,'status':'COLLECTED','periodic_statements':periods,'quarters':quarter_series(periods),'recent_disclosures':recent,'historical_signal_use_allowed':False}


def parse_statement(rows, year, code, filings, asof):
    receipts={r['rcept_no']:r for r in filings}
    ids={str(r.get('rcept_no','')) for r in rows}
    if len(ids)!=1 or next(iter(ids)) not in receipts:
        raise ValueError('DART_FINANCIAL_RECEIPT_NOT_IN_DATED_FILINGS')
    receipt=next(iter(ids));filing=receipts[receipt]
    if filing['rcept_dt'] >= asof.replace('-',''):
        raise ValueError('DART_FINANCIAL_FUTURE_OR_SAME_DAY_RECEIPT')
    month=PERIODS[code][0]
    if date(year,month,calendar.monthrange(year,month)[1]).strftime('%Y%m%d') >= filing['rcept_dt']:
        raise ValueError('DART_FINANCIAL_UNFINISHED_REPORTING_PERIOD')
    if any(str(r.get('bsns_year',year))!=str(year) or r.get('reprt_code',code)!=code or r.get('fs_div','CFS')!='CFS' for r in rows):
        raise ValueError('DART_FINANCIAL_PERIOD_OR_SCOPE_MISMATCH')

    def account(names, ids, statements):
        matches=[r for r in rows if r.get('sj_div') in statements and (r.get('account_id') in ids or re.sub(r'\s+','',r.get('account_nm','')) in names)]
        if not matches:return None
        if any(r.get('currency','KRW') not in ('KRW','원') for r in matches):raise ValueError('DART_FINANCIAL_CURRENCY_MISMATCH')
        values={(amount(r.get('thstrm_amount')),amount(r.get('thstrm_add_amount')),amount(r.get('frmtrm_q_amount'))) for r in matches}
        if len(values)!=1:raise ValueError('DART_FINANCIAL_AMBIGUOUS_ACCOUNT')
        a,b,c=next(iter(values));return {'amount_krw':a,'ytd_krw':b,'prior_quarter_krw':c}
    revenue=account({'매출액','수익(매출액)','영업수익'}, {'ifrs-full_Revenue'}, ('IS','CIS'))
    op=account({'영업이익','영업이익(손실)','영업손익'}, {'dart_OperatingIncomeLoss'}, ('IS','CIS'))
    cf=account({'영업활동현금흐름','영업활동으로인한현금흐름'}, {'ifrs-full_CashFlowsFromUsedInOperatingActivities'}, ('CF',))
    debt=account({'부채총계'}, {'ifrs-full_Liabilities'}, ('BS',));equity=account({'자본총계'}, {'ifrs-full_Equity'}, ('BS',))
    if not revenue or not op or revenue['amount_krw'] is None or op['amount_krw'] is None:raise ValueError('DART_FINANCIAL_REQUIRED_ACCOUNT_MISSING')
    return {'period':quarter(year,code),'year':year,'report_code':code,'fs_div':'CFS','revenue':revenue,'operating_profit':op,'operating_cashflow_ytd_krw':cf['amount_krw'] if cf else None,'debt_ratio_pct':100*debt['amount_krw']/equity['amount_krw'] if debt and equity and debt['amount_krw'] is not None and equity['amount_krw'] and equity['amount_krw']>0 else None,'receipt_no':receipt,'published_on':f"{filing['rcept_dt'][:4]}-{filing['rcept_dt'][4:6]}-{filing['rcept_dt'][6:8]}",'url':'https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+receipt,'basis':'CURRENT_API_SNAPSHOT_POST_SELECTION_ONLY'}


def quarter_series(statements):
    out=[]
    for s in statements:
        record={k:s[k] for k in ('period','fs_div','published_on','url','receipt_no')}
        for key in ('revenue','operating_profit'):
            v=s[key]['amount_krw'];prior=s[key]['prior_quarter_krw']
            if s['report_code']=='11011':
                q3=next((p for p in statements if p['year']==s['year'] and p['report_code']=='11014'),None)
                if not q3 or q3[key]['ytd_krw'] is None:v=None
                else:v-=q3[key]['ytd_krw']
                prior=None
            record[key+'_krw']=v
            record[key+'_yoy_pct']=100*(v/prior-1) if v is not None and prior is not None and prior>0 else None
            if key=='operating_profit':record['profit_transition']='LOSS_TO_PROFIT' if v is not None and v>0 and prior is not None and prior<0 else None
        record['provisional']=False
        if record['revenue_krw'] is not None and record['operating_profit_krw'] is not None:out.append(record)
    return sorted(out,key=lambda r:r['period'])[-4:]


def attach_context(report, outdir, client=None, curated_path=DEFAULT_CURATED):
    """Only add company_context fields; candidate ranks, prices and plans stay frozen."""
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    asof=report['source_price_asof'];curated=json.loads(Path(curated_path).read_text())
    selection_hash=digest(report['research_top2'])
    evidence={'schema':SCHEMA,'price_asof':asof,'collected_at':datetime.now(timezone.utc).isoformat(),'selection_hash_before':selection_hash,'selection_use':'POST_SELECTION_ONLY_NOT_A_SCORING_INPUT','companies':{},'errors':[]}
    mapping={t:v['corp_code'] for t,v in curated.get('companies',{}).items() if re.fullmatch(r'\d{8}',v.get('corp_code',''))}
    if client:
        try:
            if any(r['ticker'] not in mapping for r in report['research_top2']):mapping.update(client.mapping())
        except Exception as e:evidence['errors'].append({'stage':'corp_mapping','type':type(e).__name__,'reason':str(e) if isinstance(e,ValueError) and re.fullmatch(r'[A-Z_0-9]+',str(e)) else 'DART_MAPPING_UNAVAILABLE'})
        # The 3.6 MB public corporation download can be slow on a cold runner.
        # It is cached separately; the financial request budget starts afterwards.
        client.started=time.monotonic()
    for row in report['research_top2']:
        ticker=row['ticker'];item=copy.deepcopy(curated.get('companies',{}).get(ticker,{}));sources=item.get('sources',{})
        allowed={key for key,src in sources.items() if publication_ok(src,asof)}
        item['business']=[f for f in item.get('business',[]) if set(f.get('source_ids',[])) and set(f['source_ids'])<=allowed]
        item['events']=[f for f in item.get('events',[]) if set(f.get('source_ids',[])) and set(f['source_ids'])<=allowed and publication_ok(f,asof,28)]
        item['quarters']=[f for f in item.get('quarters',[]) if publication_ok(f,asof) and set(f.get('source_ids',[]))<=allowed]
        item['sources']={k:v for k,v in sources.items() if k in allowed}
        item.update(selection_use='POST_SELECTION_ONLY',collected_at=evidence['collected_at'],price_asof=asof,ticker=ticker,corp_code=mapping.get(ticker),missing=['INVESTOR_FLOW_NOT_COLLECTED','SECTOR_STRENGTH_NOT_COLLECTED'],dart_status='KEY_NOT_CONNECTED' if not client else 'NOT_COLLECTED')
        if client and ticker in mapping:
            try:
                dart=client.company(ticker,mapping[ticker],asof);item['dart']=dart;item['dart_status']=dart['status']
                merged={q['period']:q for q in dart['quarters']}
                # Independently reviewed company preliminary releases can be newer
                # than periodic DART filings. Preserve their explicit provisional tag.
                for q in item['quarters']:
                    if q['period'] not in merged:merged[q['period']]=q
                item['quarters']=sorted(merged.values(),key=lambda q:q['period'])[-4:]
            except Exception as e:
                reason=str(e) if isinstance(e,ValueError) and re.fullmatch(r'[A-Z_0-9]+',str(e)) else 'DART_CONTEXT_UNAVAILABLE'
                item['dart_status']=reason;evidence['errors'].append({'ticker':ticker,'stage':'company','type':type(e).__name__,'reason':reason})
        elif client:item['dart_status']='CORPORATE_CODE_UNAVAILABLE'
        if not item['quarters']:item['missing'].append('VERIFIED_QUARTERLY_FINANCIALS_UNAVAILABLE')
        item['content_sha256']=digest(item);row['company_context']=item;evidence['companies'][ticker]=item
    after=[{k:v for k,v in r.items() if k!='company_context'} for r in report['research_top2']]
    evidence['selection_hash_after']=digest(after)
    if evidence['selection_hash_after']!=selection_hash:raise ValueError('REPORT_ENRICHMENT_CHANGED_SELECTION')
    evidence['request_audit']=client.audit if client else []
    (root/'company_context.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    return report
