"""Bounded current OpenDART snapshots joined to all technical candidates.

Dated matching receipts support descriptive facts, NOT original-document PIT
certification, business-competitiveness assertions or historical selection.
"""
import argparse,hashlib,json,os,re,threading,time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date,datetime,timezone
from pathlib import Path
import requests
from dart_financial_screen import annual_receipt,latest_interim_filing,extract_metric,REVENUE,OPERATING,ASSETS,LIABILITIES,EQUITY
from krx_opendart_financial_v91 import get_corp_codes

CF={'ifrs-full_CashFlowsFromUsedInOperatingActivities','ifrs-full_CashFlowsFromUsedInOperatingActivitiesContinuingOperations'}


def statement_facts(payload,filing,division,year,report_code,corp_code=None):
    if payload.get('status')!='000':raise ValueError('FINANCIAL_API_NOT_AVAILABLE')
    rows=payload.get('list') or []
    if not rows or {str(r.get('rcept_no','')) for r in rows}!={filing['receipt_no']}:
        raise ValueError('FINANCIAL_RECEIPT_MISMATCH_OR_LATER_RESTATEMENT')
    if any(str(r.get('bsns_year'))!=str(year) or r.get('reprt_code')!=report_code or
           r.get('currency')!='KRW' or r.get('fs_div') not in (None,'',division) for r in rows):
        raise ValueError('FINANCIAL_PERIOD_DIVISION_OR_CURRENCY_MISMATCH')
    if corp_code is not None and any(r.get('corp_code')!=corp_code for r in rows):
        raise ValueError('FINANCIAL_CORPORATION_ID_MISMATCH')
    get=lambda ids,section,key='thstrm_amount':extract_metric(rows,ids,section,key)
    revenue=get(REVENUE,'IS');op=get(OPERATING,'IS');assets=get(ASSETS,'BS');liabilities=get(LIABILITIES,'BS');equity=get(EQUITY,'BS')
    previous_key='frmtrm_amount' if report_code=='11011' else 'frmtrm_q_amount'
    prev_revenue=get(REVENUE,'IS',previous_key);prev_op=get(OPERATING,'IS',previous_key)
    cf=get(CF,'CF')
    balance_gap=abs(assets-liabilities-equity)/assets if all(v is not None for v in (assets,liabilities,equity)) and assets>0 else None
    return dict(receipt_no=filing['receipt_no'],published_on=filing['published_on'],
        url='https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+filing['receipt_no'],
        fiscal_year=year,report_code=report_code,fs_div=division,currency='KRW',
        income_period_basis='ANNUAL' if report_code=='11011' else 'SINGLE_QUARTER',
        cashflow_period_basis='FISCAL_YEAR_TO_DATE',
        revenue_krw=revenue,operating_profit_krw=op,previous_comparable_revenue_krw=prev_revenue,
        previous_comparable_operating_profit_krw=prev_op,assets_krw=assets,liabilities_krw=liabilities,
        equity_krw=equity,operating_cashflow_ytd_krw=cf,balance_identity_gap_fraction=balance_gap,
        revenue_increased=None if revenue is None or prev_revenue is None else revenue>prev_revenue,
        operating_profit_increased=None if op is None or prev_op is None else op>prev_op,
        api_snapshot_sha256=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        basis='CURRENT_API_SNAPSHOT_WITH_MATCHING_DATED_RECEIPT_NOT_ORIGINAL_PIT')


def join_quality(entry_review,quality):
    if entry_review['price_asof']!=quality['asof']:raise ValueError('COMPANY_ENTRY_ASOF_MISMATCH')
    by={r['ticker']:r for r in quality['companies']}
    combined=[]
    for row in entry_review.get('geometry_research_pool',entry_review.get('new_research_top2',[])):
        facts=by.get(row['ticker']) or {};latest=facts.get('latest_statement') or {}
        combined.append(dict(row,company_quality_status=facts.get('status','MISSING'),
            financial_facts=latest,company_competitiveness_verified=False,
            observed_positive_core_metrics=facts.get('observed_positive_core_metrics'),
            financial_pit_verified=False,buy_approved=False))
    # Never turn an experimental geometry winner plus a current API snapshot
    # into an original signal or validated new trading model.
    return dict(schema='C3_COMBINED_COMPANY_ENTRY_REVIEW_V1',asof=quality['asof'],
        technical_reviewed=entry_review['reviewed_technical_tickers'],
        company_reviewed=len(quality['companies']),geometry_research_top2=combined[:2],
        all_geometry_company_reviews=combined,
        research_top2_after_documented_positive_facts=[r for r in combined if r['observed_positive_core_metrics'] is True][:2],
        company_status_counts=dict(Counter(r['status'] for r in quality['companies'])),
        final_top2=[],final_candidate_count=None,decision='CASH',buy_approved=False,orders_enabled=False,
        blockers=['REGULAR_ONLY_SOURCE_UNCERTIFIED','EXPERIMENTAL_ENTRY_THRESHOLDS_NOT_PROFITABILITY_VALIDATED',
                  'CURRENT_FINANCIAL_SNAPSHOTS_NOT_ORIGINAL_PIT'],
        original_models_and_stops_unchanged=True,new_retroactive_registration=False)


class BudgetClient:
    def __init__(self,key,max_requests=600,seconds=540):
        self.key=key;self.limit=max_requests;self.seconds=seconds;self.start=time.monotonic()
        self.lock=threading.Lock();self.calls=0;self.audit=[];self.stop=False;self.last_request=0
    def get(self,endpoint,params):
        with self.lock:
            if self.stop:raise ValueError('DART_REVIEW_PROVIDER_STOP')
            if self.calls>=self.limit:raise ValueError('DART_REVIEW_REQUEST_BUDGET')
            if time.monotonic()-self.start>self.seconds:raise ValueError('DART_REVIEW_TIME_BUDGET')
            delay=max(0,.08-(time.monotonic()-self.last_request))
            if delay:time.sleep(delay)
            self.calls+=1;self.last_request=time.monotonic()
        try:
            response=requests.get('https://opendart.fss.or.kr/api/'+endpoint,
                params=dict(params,crtfc_key=self.key),timeout=(8,18),allow_redirects=False)
            if response.status_code!=200:raise ValueError('DART_REVIEW_HTTP_FAILURE')
            payload=response.json()
        except requests.RequestException:raise ValueError('DART_REVIEW_TRANSPORT_FAILURE') from None
        status=str(payload.get('status','UNKNOWN'))
        with self.lock:
            self.audit.append(dict(endpoint=endpoint,sha256=hashlib.sha256(response.content).hexdigest(),
                bytes=len(response.content),status=status,received_at=datetime.now(timezone.utc).isoformat()))
            if status in ('010','011','012','020','901'):self.stop=True
        if status not in ('000','013'):raise ValueError('DART_REVIEW_PROVIDER_REJECTED')
        return payload


def collect(candidates,key=None,client=None,lookup=None):
    asof=candidates['asof'];day=date.fromisoformat(asof);rows=candidates['rows']
    result=dict(schema='C3_COMPANY_QUALITY_FACTS_V1',asof=asof,collected_at=datetime.now(timezone.utc).isoformat(),
        requested=len(rows),companies=[],original_document_pit_verified=False,buy_approved=False,
        selection_use='NEW_RETROSPECTIVE_REVIEW_ONLY_NOT_ORIGINAL_SELECTION_REASON',orders_enabled=False)
    key=key or os.environ.get('OPENDART_API_KEY','')
    if not key and client is None:
        result['companies']=[dict(ticker=r['ticker'],status='MISSING_DART_KEY') for r in rows];return result
    try:
        if lookup is None:
            # Reuse the existing hash-checked 30-day public corporation map.
            # Its cold download must not consume the financial-phase budget.
            from c3_report_context import DartClient
            lookup=DartClient(key,Path(os.environ.get('C3_DART_MAPPING_TMP','/tmp/c3-corp-map'))).mapping()
    except Exception:
        result['companies']=[dict(ticker=r['ticker'],status='CORPORATION_MAP_UNAVAILABLE') for r in rows];return result
    client=client or BudgetClient(key)
    def company(row):
        out=dict(ticker=row['ticker'],name=row['name'],status='FINANCIAL_EVIDENCE_PENDING',
            business_competitiveness_verified=False,financial_pit_verified=False,statements=[],buy_approved=False)
        corp=lookup.get(row['ticker'])
        if not corp:out['status']='NO_CORPORATION_MAPPING';return out
        try:
            filings=client.get('list.json',dict(corp_code=corp,bgn_de=str(day.year-2)+'0101',end_de=asof.replace('-',''),pblntf_ty='A',page_count=100,last_reprt_at='N'))
            if int(filings.get('total_page',0))>1:raise ValueError('DATED_FILING_LIST_TRUNCATED')
            # Same-day date-only releases cannot prove availability at close.
            filings=dict(filings,list=[f for f in filings.get('list',[]) if str(f.get('rcept_dt',''))<asof.replace('-','')])
            choices=[]
            for year in (day.year-1,day.year-2):
                annual=annual_receipt(filings,year,day)
                if annual:
                    choices.append((year,'11011',dict(receipt_no=annual[1],published_on=str(annual[0]))));break
            interim=latest_interim_filing(filings,day)
            annual_year=choices[0][0] if choices else None
            if interim and (annual_year is None or interim['fiscal_year']>annual_year):
                # One newest available statement contains current/previous
                # comparable income plus BS and cash flow. Do not spend two
                # extra requests on superseded annual accounts for every name.
                choices=[]
                choices.append((interim['fiscal_year'],interim['report_code'],dict(receipt_no=interim['receipt_no'],published_on=interim.get('received_on',interim.get('filing_date','')))))
            # The existing parser's exact receipt date comes from the listing.
            dated={f['rcept_no']:str(f['rcept_dt']) for f in filings.get('list',[])}
            for year,code,filing in choices:
                raw_day=dated.get(filing['receipt_no'],'')
                if not re.fullmatch(r'\d{8}',raw_day):raise ValueError('FILING_RECEIPT_DATE_MISSING')
                filing['published_on']=raw_day[:4]+'-'+raw_day[4:6]+'-'+raw_day[6:]
                parsed=None
                for division in ('CFS','OFS'):
                    payload=client.get('fnlttSinglAcntAll.json',dict(corp_code=corp,bsns_year=str(year),reprt_code=code,fs_div=division))
                    if payload.get('status')=='013':continue
                    parsed=statement_facts(payload,filing,division,year,code,corp);break
                if parsed:out['statements'].append(parsed)
            if not out['statements']:raise ValueError('NO_MATCHING_DATED_STATEMENT')
            out['latest_statement']=max(out['statements'],key=lambda s:(s['fiscal_year'],{'11011':4,'11013':1,'11012':2,'11014':3}[s['report_code']]))
            q=out['latest_statement']
            required=('revenue_krw','operating_profit_krw','equity_krw','operating_cashflow_ytd_krw')
            out['observed_positive_core_metrics']=None if any(q.get(k) is None for k in required) else all(q[k]>0 for k in required)
            out['status']='DATED_MATCHING_RECEIPT_SNAPSHOT_NOT_PIT_VERIFIED'
        except Exception as exc:
            code=str(exc)
            out['status']=code if isinstance(exc,ValueError) and re.fullmatch('[A-Z_0-9]{1,100}',code) else type(exc).__name__
        return out
    with ThreadPoolExecutor(max_workers=4) as pool:result['companies']=list(pool.map(company,rows))
    result.update(request_count=client.calls,status_counts=dict(Counter(r['status'] for r in result['companies'])),request_audit=client.audit)
    return result


def reuse_evidence(path,expected_sha,candidates):
    """Explicit same-asof replay only; keep the actual old collection clock."""
    body=Path(path).read_bytes()
    if hashlib.sha256(body).hexdigest()!=expected_sha:raise ValueError('DATED_COMPANY_EVIDENCE_HASH_MISMATCH')
    evidence=json.loads(body)
    wanted={(r['ticker'],r['name']) for r in candidates['rows']}
    actual={(r['ticker'],r['name']) for r in evidence.get('companies',[])}
    if (evidence.get('schema')!='C3_COMPANY_QUALITY_FACTS_V1' or evidence.get('asof')!=candidates['asof'] or
        wanted!=actual or len(actual)!=len(evidence['companies'])):
        raise ValueError('DATED_COMPANY_EVIDENCE_DATE_OR_UNIVERSE_MISMATCH')
    if evidence.get('original_document_pit_verified') is not False:raise ValueError('DATED_COMPANY_EVIDENCE_PIT_SCOPE_MISMATCH')
    evidence.update(reused_evidence_sha256=expected_sha,reused_at=datetime.now(timezone.utc).isoformat(),
        new_api_request_count=0,reuse_is_not_new_collection=True)
    return evidence


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--candidates',required=True);p.add_argument('--entry',required=True);p.add_argument('--outdir',required=True)
    p.add_argument('--reuse-file');p.add_argument('--reuse-sha');a=p.parse_args()
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    candidates=json.loads(Path(a.candidates).read_text())
    result=reuse_evidence(a.reuse_file,a.reuse_sha,candidates) if a.reuse_file else collect(candidates)
    (out/'company_quality.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    combined=join_quality(json.loads(Path(a.entry).read_text()),result)
    (out/'combined_review.json').write_text(json.dumps(combined,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(company_reviewed=len(result['companies']),statuses=result.get('status_counts'),decision='CASH')))


def quality_gate_snapshot(company):
    """Conservative descriptive quality gate; never approves orders or PIT.

    Current API snapshots may describe quality, but cannot certify that the
    statement was available at the historical close. Missing evidence is
    UNKNOWN, not evidence of a financially weak company.
    """
    facts=company.get('latest_statement') or {}
    needed=('revenue_krw','operating_profit_krw','assets_krw',
            'liabilities_krw','equity_krw','operating_cashflow_ytd_krw')
    result=dict(ticker=company.get('ticker'),status='QUALITY_UNVERIFIED',
                entry_quality_eligible=False,buy_approved=False,
                original_document_pit_verified=False,
                evidence_status=company.get('status'),
                reason_codes=[],metrics={})
    if company.get('status')!='DATED_MATCHING_RECEIPT_SNAPSHOT_NOT_PIT_VERIFIED':
        result['reason_codes'].append('DATED_MATCHING_STATEMENT_NOT_AVAILABLE')
        return result
    if any(not isinstance(facts.get(k),(int,float)) or isinstance(facts.get(k),bool)
           for k in needed):
        result['reason_codes'].append('REQUIRED_FINANCIAL_METRIC_MISSING')
        return result
    revenue,profit,assets,debt,equity,cash=(facts[k] for k in needed)
    if assets<=0 or equity<=0 or debt<0 or abs(assets-debt-equity)/assets>0.02:
        result['reason_codes'].append('BALANCE_SHEET_IDENTITY_OR_EQUITY_INVALID')
        return result
    result['metrics']=dict(operating_margin=profit/revenue if revenue>0 else None,
                           debt_to_equity=debt/equity,
                           operating_cashflow_ytd_krw=cash,
                           revenue_increased=facts.get('revenue_increased'),
                           operating_profit_increased=facts.get('operating_profit_increased'))
    previous_revenue=facts.get('previous_comparable_revenue_krw')
    previous_profit=facts.get('previous_comparable_operating_profit_krw')
    comparable=all(isinstance(v,(int,float)) and not isinstance(v,bool)
                   for v in (previous_revenue,previous_profit))
    result['metrics']['comparable_values_verified']=comparable
    if revenue<=0 or profit<=0 or cash<=0:
        result['status']='QUALITY_WEAK'
        result['reason_codes'].append('NONPOSITIVE_REVENUE_PROFIT_OR_CASHFLOW')
    elif not comparable:
        result['reason_codes'].append('COMPARABLE_PERIOD_VALUES_MISSING')
    elif previous_revenue<0:
        result['reason_codes'].append('COMPARABLE_REVENUE_INVALID')
    elif revenue>previous_revenue and profit>previous_profit:
        # Growth is observed, but no trend reversal is established from one pair.
        result['status']='QUALITY_STRONG'
        result['reason_codes'].append('COMPARABLE_REVENUE_AND_PROFIT_IMPROVED')
    elif revenue<previous_revenue or profit<previous_profit:
        result['status']='QUALITY_DECLINING_REVIEW'
        result['reason_codes'].append('COMPARABLE_REVENUE_OR_PROFIT_DECLINED')
    else:
        result['status']='QUALITY_STABLE_REVIEW'
        result['reason_codes'].append('NO_CONFIRMED_GROWTH_OR_DECLINE')
    # Historical PIT and official-price certification remain separate blockers.
    return result
