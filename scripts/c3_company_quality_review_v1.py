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


def statement_facts(payload,filing,division,year,report_code):
    if payload.get('status')!='000':raise ValueError('FINANCIAL_API_NOT_AVAILABLE')
    rows=payload.get('list') or []
    if not rows or {str(r.get('rcept_no','')) for r in rows}!={filing['receipt_no']}:
        raise ValueError('FINANCIAL_RECEIPT_MISMATCH_OR_LATER_RESTATEMENT')
    if any(str(r.get('bsns_year'))!=str(year) or r.get('reprt_code')!=report_code or
           r.get('currency')!='KRW' or r.get('fs_div') not in (None,'',division) for r in rows):
        raise ValueError('FINANCIAL_PERIOD_DIVISION_OR_CURRENCY_MISMATCH')
    get=lambda ids,section,key='thstrm_amount':extract_metric(rows,ids,section,key)
    revenue=get(REVENUE,'IS');op=get(OPERATING,'IS');assets=get(ASSETS,'BS');liabilities=get(LIABILITIES,'BS');equity=get(EQUITY,'BS')
    previous_key='frmtrm_amount' if report_code=='11011' else 'frmtrm_q_amount'
    prev_revenue=get(REVENUE,'IS',previous_key);prev_op=get(OPERATING,'IS',previous_key)
    cf=get(CF,'CF')
    balance_gap=abs(assets-liabilities-equity)/assets if all(v is not None for v in (assets,liabilities,equity)) and assets>0 else None
    return dict(receipt_no=filing['receipt_no'],published_on=filing['published_on'],
        url='https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+filing['receipt_no'],
        fiscal_year=year,report_code=report_code,fs_div=division,currency='KRW',
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
    for row in entry_review.get('new_research_top2',[]):
        facts=by.get(row['ticker']) or {};latest=facts.get('latest_statement') or {}
        combined.append(dict(row,company_quality_status=facts.get('status','MISSING'),
            financial_facts=latest,company_competitiveness_verified=False,
            financial_pit_verified=False,buy_approved=False))
    # Never turn an experimental geometry winner plus a current API snapshot
    # into an original signal or validated new trading model.
    return dict(schema='C3_COMBINED_COMPANY_ENTRY_REVIEW_V1',asof=quality['asof'],
        technical_reviewed=entry_review['reviewed_technical_tickers'],
        company_reviewed=len(quality['companies']),geometry_research_top2=combined,
        company_status_counts=dict(Counter(r['status'] for r in quality['companies'])),
        final_top2=[],final_candidate_count=None,decision='CASH',buy_approved=False,orders_enabled=False,
        blockers=['REGULAR_ONLY_SOURCE_UNCERTIFIED','EXPERIMENTAL_ENTRY_THRESHOLDS_NOT_PROFITABILITY_VALIDATED',
                  'CURRENT_FINANCIAL_SNAPSHOTS_NOT_ORIGINAL_PIT'],
        original_models_and_stops_unchanged=True,new_retroactive_registration=False)


class BudgetClient:
    def __init__(self,key,max_requests=600,seconds=240):
        self.key=key;self.limit=max_requests;self.seconds=seconds;self.start=time.monotonic()
        self.lock=threading.Lock();self.calls=0;self.audit=[];self.stop=False;self.last_request=0
    def get(self,endpoint,params):
        with self.lock:
            if self.stop or self.calls>=self.limit or time.monotonic()-self.start>self.seconds:
                raise ValueError('DART_REVIEW_BUDGET_OR_PROVIDER_STOP')
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
    client=client or BudgetClient(key)
    try:lookup=lookup if lookup is not None else get_corp_codes(key)
    except Exception:
        result['companies']=[dict(ticker=r['ticker'],status='CORPORATION_MAP_UNAVAILABLE') for r in rows];return result
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
            if interim:
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
                    parsed=statement_facts(payload,filing,division,year,code);break
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


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--candidates',required=True);p.add_argument('--entry',required=True);p.add_argument('--outdir',required=True);a=p.parse_args()
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    result=collect(json.loads(Path(a.candidates).read_text()))
    (out/'company_quality.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    combined=join_quality(json.loads(Path(a.entry).read_text()),result)
    (out/'combined_review.json').write_text(json.dumps(combined,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(company_reviewed=len(result['companies']),statuses=result.get('status_counts'),decision='CASH')))
