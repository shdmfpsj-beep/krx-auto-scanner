#!/usr/bin/env python3
"""v9.4.2: retryable original-number reconciliation + conservative DART event recovery.

Strict PIT remains false. This is research-only; no orders, score, or auto strategy activation.
Requires original v9.1/v9.3/v9.4/v9.4.1 modules installed alongside this file.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, os, re, time, urllib.error, zipfile
from datetime import date, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
import exchange_calendars as xcals
import krx_forward_pit_v94 as old
import krx_forward_pit_v941 as prev
import krx_opendart_financial_v91 as v91
import krx_opendart_pit_audit_v93 as v93

EVENT_FIELDS=prev.EV_COLS+['event_polarity','possible_growth_catalyst','is_cancellation','is_negative_revision','research_signal_approved']
VERIFY_FIELDS=old.COLUMNS
RECEIPT=re.compile(r'^20\d{12}$')
NEGATIVE_CONTRACT=re.compile(r'(?:계약|수주).*(?:해지|취소|철회|중단|종료)|(?:해지|취소|철회).*(?:계약|수주)')
NEGATIVE_CAPEX=re.compile(r'(?:시설투자|신규시설투자|설비투자).*(?:취소|철회|중단|축소)')
AMEND=prev.AMENDED_RE
CANONICAL_XBRL={
  'CFS':{'income':{'{XBRL}IS_C1':'{XBRL}IS1','{XBRL}IS_C':'{XBRL}IS1'},
         'balance':{'{XBRL}BS_C':'{XBRL}BS'}},
  'OFS':{'income':{'{XBRL}IS_S1':'{XBRL}IS_S1','{XBRL}IS_S':'{XBRL}IS_S1'},
         'balance':{'{XBRL}BS_S':'{XBRL}BS_S1'}},
}

def classify_event(name):
    s=old.textnorm(name)
    amended=bool(AMEND.search(s))
    subsidiary='자회사의주요경영사항' in s
    if NEGATIVE_CONTRACT.search(s) or '단일판매ㆍ공급계약해지' in s:
        kind,polar='SUPPLY_TERMINATION','NEGATIVE_EVENT'
    elif NEGATIVE_CAPEX.search(s):
        kind,polar='CAPEX_CANCELLATION','NEGATIVE_EVENT'
    else:
        kind,_,_=prev.classify(name)
        if kind=='SUPPLY_CONTRACT': polar='UNCERTAIN_UNTIL_ORIGINAL'
        elif kind=='CAPEX': polar='UNCERTAIN_UNTIL_ORIGINAL'
        elif kind=='FORECAST_DISCLOSURE':polar='FORECAST_NOT_PROVEN_REVISION'
        elif kind=='EARNINGS_ACTUAL':polar='HISTORICAL_ACTUAL'
        else:polar='NOT_ASSESSED'
    if amended: polar='AMENDMENT_NOT_NEW_CATALYST'
    return kind,polar,amended,subsidiary

def normalize_event(row,cal):
    base=prev.normalize_event(row,cal)
    kind,polarity,amend,subsidiary=classify_event(row.get('report_name',''))
    base['event_type']=kind
    base['is_amendment']=str(amend)
    base['is_subsidiary']=str(subsidiary)
    iscancel=kind in ('SUPPLY_TERMINATION','CAPEX_CANCELLATION')
    isfresh=base['freshness']=='FRESH_0_10_SESSIONS' and base['asof_eligible']=='True'
    base.update(event_polarity=polarity, is_cancellation=str(iscancel),
         is_negative_revision=str(iscancel),
         possible_growth_catalyst=str(isfresh and not amend and not iscancel and not subsidiary and kind in ('SUPPLY_CONTRACT','CAPEX','FORECAST_DISCLOSURE')),
         research_signal_approved='False')
    if iscancel and not amend:base['freshness']='NEGATIVE_EVENT_NOT_GROWTH'
    if amend:base['freshness']='CORRECTION_NOT_NEW_CATALYST'
    base['evidence_status']='TITLE_ONLY_NEEDS_ORIGINAL_REVIEW'
    return {k:base.get(k,'') for k in EVENT_FIELDS}

def original_numeric(xml:bytes, fs_div:str, report_code:str):
    """Normalize ONLY exact known statement class aliases, then use strict v9.4 table parser.
    Never guess statement period, a numeric column, unit or account from nearby text.
    """
    if fs_div not in CANONICAL_XBRL:
        return {},'BAD_FS_DIV',{}
    soup=BeautifulSoup(xml.decode('utf-8-sig','replace'),'html.parser')
    mappings={}; counts={};diag={'format':'explicit_XBRL_class_v942','mapped':{}}
    for section in ('income','balance'):
        groups=soup.find_all('table-group')
        # Count canonical and previous aliases together. Duplicate statement tables are never guessed.
        known={x.upper() for x in (['{XBRL}IS1','{XBRL}IS'] if section=='income' else ['{XBRL}BS'])} if fs_div=='CFS' else (
            {x.upper() for x in (['{XBRL}IS_S1','{XBRL}IS_S'] if section=='income' else ['{XBRL}BS_S1'])})
        aliases={k.upper():v for k,v in CANONICAL_XBRL[fs_div][section].items()}
        matches=[(g,aliases.get(str(g.get('aclass','')).upper())) for g in groups
                 if str(g.get('aclass','')).upper() in known or str(g.get('aclass','')).upper() in aliases]
        diag[section+'_group_count']=len(matches)
        if len(matches)!=1:return {},'AMBIGUOUS_'+section.upper()+'_XBRL_GROUP',diag
        group,target=matches[0]
        if target is not None:
            group['aclass']=target
            diag['mapped'][section]=target
    fields,status=old.read_financial_table(soup.encode('utf-8'),fs_div,report_code)
    diag['strict_parse_status']=status
    return fields,status,diag

def compare_archive(row,blob,cal):
    receipt=row['receipt_no']
    xml,astatus=old.read_original_archive(blob,receipt)
    if astatus!='OK':return [],{'archive_status':astatus}
    fields,status,diag=original_numeric(xml,row['fs_div'],row['report_code'])
    sha=hashlib.sha256(blob).hexdigest()
    try: available=v93.krx_next_session(row['filing_date'],cal)
    except (ValueError,KeyError):available=''
    result=[]
    for api_key,field,_ in old.METRICS:
        api=old.num_krw(row.get(api_key,'')); vals=fields.get(field)
        orig=vals[0] if vals else None
        if status!='PARSED':st='UNVERIFIED_'+status
        elif api is None:st='UNVERIFIED_API_AMOUNT_MISSING'
        elif orig==api:st='EXACT_MATCH'
        else:st='MISMATCH'
        result.append(dict(ticker=row['ticker'],receipt_no=receipt,filing_date=row['filing_date'],available_date=available,
            fs_div=row['fs_div'],metric=api_key,api_value_krw=api if api is not None else '',
            original_value_krw=orig if orig is not None else '',delta_krw=(api-orig if api is not None and orig is not None else ''),
            status=st,document_sha256=sha,source_url=row.get('source_url',''),
            note='Original receipt exact amount reconciliation only; global PIT not certified'))
    return result,dict(diag,archive_status='OK')

def read_json(path,default):
    p=Path(path)
    if not p.exists():return default
    return json.loads(p.read_text(encoding='utf-8'))

def write_csv(path,rows,columns):v91.atomic_csv(Path(path),rows,columns)
def write_json(path,data):v91.atomic_json(Path(path),data)

def verify(args,fin,cands,cal):
    out=Path(args.outdir)
    old_records=old.read_csv(out/'v941_original_numeric_reconciliation.csv')
    saved=old.read_csv(out/'v942_original_numeric_reconciliation.csv')
    state=read_json(out/'v942_original_attempts.json',{'attempts':[]})
    attempts=state['attempts'];counts={x['receipt_no']:int(x.get('attempt_count',0)) for x in attempts}
    # The configured v94_signal_candidates_reference.csv is a CHART-SIGNAL file.
    # It has no receipt_no. Resolve the most recent as-of-eligible financial
    # disclosure first; otherwise legacy choose_archives raises KeyError.
    # Always recompute the receipt from the as-of financial dataset, even if
    # a candidate row happens to contain an untrusted receipt_no field.
    receipt_candidates=old.recent_candidates(cands,fin,args.ticker or None,
                                              limit=max(2000,len(cands)))
    raw_source=old.choose_archives(fin,receipt_candidates,args.ticker,100000)
    source=list({r['receipt_no']:r for r in raw_source}.values())
    # Use only strict all-four evidence, NOT the old 'COMPARED' state marker.
    queue=[r for r in source if not prev.receipt_verified(old_records,r['receipt_no']) and
           not prev.receipt_verified(saved,r['receipt_no']) and counts.get(r['receipt_no'],0)<args.max_retries]
    selection=queue[:args.max_documents]
    archive=old.read_archives_from_bundle(args.archive_bundle)
    key=os.getenv('OPENDART_API_KEY','').strip()
    if any(x['receipt_no'] not in archive for x in selection) and not old.KEY_RE.fullmatch(key):
        raise ValueError('DART Secret unavailable; key value never printed')
    diagnostics=[]
    for row in selection:
        receipt=row['receipt_no'];records=[]
        try:
            blob=archive[receipt] if receipt in archive else old.get_archive(key,receipt)
            records,diag=compare_archive(row,blob,cal)
            st='VERIFIED_FOUR' if prev.receipt_verified(records,receipt) else (
                'NUMERIC_MISMATCH' if any(x['status']=='MISMATCH' for x in records) else 'UNVERIFIED_RETRYABLE')
        except (ValueError,TimeoutError,urllib.error.URLError,zipfile.BadZipFile) as exc:
            diag={'exception_type':type(exc).__name__};st='FETCH_FAILED_RETRYABLE'
        if records:saved=[x for x in saved if x['receipt_no']!=receipt]+records
        attempts=[x for x in attempts if x['receipt_no']!=receipt]+[
           {'ticker':row['ticker'],'receipt_no':receipt,'status':st,'attempt_count':counts.get(receipt,0)+1}]
        diagnostics.append({'ticker':row['ticker'],'receipt_no':receipt,'status':st,'details':diag})
        if receipt not in archive:time.sleep(args.delay_seconds)
    write_csv(out/'v942_original_numeric_reconciliation.csv',saved,VERIFY_FIELDS)
    write_json(out/'v942_original_attempts.json',{'attempts':attempts,'strict_pit_approved':False})
    write_json(out/'v942_original_parser_diagnostics.json',{'documents':diagnostics,'strict_pit_approved':False})
    return dict(attempted=len(selection),verified_four_this_run=sum(x['status']=='VERIFIED_FOUR' for x in diagnostics),
         verified_four_cumulative=sum(prev.receipt_verified(saved,r['receipt_no']) for r in source),
         statuses=dict(collections.Counter(x['status'] for x in diagnostics)),remaining_eligible=len(queue)-len(selection))

def events(args,fin,cands,cal,client=None):
    out=Path(args.outdir)
    historical=old.read_csv(out/'v941_forward_event_leads.csv')
    saved=old.read_csv(out/'v942_forward_event_leads.csv')
    rows={ (r['ticker'],r['signal_date'],r['receipt_no']):normalize_event(r,cal)
          for r in historical+saved if r.get('ticker') and r.get('signal_date') and r.get('receipt_no')}
    prev_state=read_json(out/'v941_event_collection_state.json',{'attempts':[]})['attempts']
    done={(a['ticker'],a['signal_date']) for a in prev_state if a['status']=='SUCCESS'}
    state=read_json(out/'v942_event_collection_state.json',{'attempts':[]})
    attempts=state['attempts']
    counts={(a['ticker'],a['signal_date']):int(a.get('attempt_count',0)) for a in attempts}
    done|={(a['ticker'],a['signal_date']) for a in attempts if a['status']=='SUCCESS'}
    # Event-title searches can include chart signals even without financial receipts.
    # Unlike original-number verification they do not require receipt_no.
    queue=[p for p in prev.relevant_company_queue(fin,cands,args.ticker,args.asof) if (p[0],p[2]) not in done and
           counts.get((p[0],p[2]),0)<args.max_retries]
    chosen=queue[:args.max_companies]
    key=os.getenv('OPENDART_API_KEY','').strip()
    if chosen and client is None and not old.KEY_RE.fullmatch(key):raise ValueError('DART Secret unavailable')
    problems=[];pages=0; completed=0
    for ticker,corp_code,signal in chosen:
        signalday=date.fromisoformat(signal)
        begin=max(signalday-timedelta(days=args.lookback_days),date(2015,1,1))
        q={'corp_code':corp_code,'bgn_de':begin.strftime('%Y%m%d'),'end_de':signalday.strftime('%Y%m%d'),
            'last_reprt_at':'N','page_count':'100','sort':'date','sort_mth':'desc'}
        ok=True;found=[];total=None
        for page in range(1,args.max_pages+1):
            q['page_no']=str(page)
            try:
                reply=client(corp_code,dict(q)) if client is not None else v91.get_json(key,'list.json',q)
                pages+=1;code=str(reply.get('status',''))
                if code=='013':
                    if total is not None and page<=total:
                        ok=False;problems.append({'ticker':ticker,'signal_date':signal,'issue':'PAGE_MISSING_013'})
                    break
                if code!='000':raise RuntimeError('DART_STATUS_'+code)
                total=int(reply.get('total_page','0'))
                if total<page:raise RuntimeError('INCONSISTENT_TOTAL_PAGE')
                for item in reply.get('list',[]):
                    r=prev.from_dart_list(item,ticker,signal,cal)
                    if r and r['asof_eligible']=='True':found.append(normalize_event(r,cal))
                if page>=total:break
                if page==args.max_pages:ok=False;problems.append({'ticker':ticker,'signal_date':signal,'issue':'INCOMPLETE_PAGINATION'})
            except (RuntimeError,ValueError,urllib.error.URLError,TimeoutError) as exc:
                ok=False;problems.append({'ticker':ticker,'signal_date':signal,'issue':type(exc).__name__});break
            if client is None:time.sleep(args.delay_seconds)
        for r in found:rows[(r['ticker'],r['signal_date'],r['receipt_no'])]=r
        ky=(ticker,signal)
        attempts=[a for a in attempts if (a['ticker'],a['signal_date'])!=ky]+[
            {'ticker':ticker,'signal_date':signal,'status':'SUCCESS' if ok else 'RETRYABLE','attempt_count':counts.get(ky,0)+1}]
        if ok:completed+=1
        if client is None:time.sleep(args.delay_seconds)
    result=sorted(rows.values(),key=lambda x:(x['ticker'],x['signal_date'],x['receipt_no']))
    write_csv(out/'v942_forward_event_leads.csv',result,EVENT_FIELDS)
    write_json(out/'v942_event_collection_state.json',{'attempts':attempts,'strict_pit_approved':False})
    return dict(queried=len(chosen),successful_queries=completed,pages=pages,stored_events=len(result),
        canceled_or_terminated=sum(x['is_cancellation']=='True' for x in result),
        title_only_possible_growth=sum(x['possible_growth_catalyst']=='True' for x in result),
        numeric_growth_signals_approved=0,pending_queries_after_this_batch=len(queue)-len(chosen),warnings=problems)

def audit(args,cal):
    out=Path(args.outdir)
    legacy=old.read_csv(out/'v941_forward_event_leads.csv')
    current=old.read_csv(out/'v942_forward_event_leads.csv')
    if not current:
        current=[normalize_event(r,cal) for r in legacy]
        write_csv(out/'v942_forward_event_leads.csv',current,EVENT_FIELDS)
    vs=old.read_csv(out/'v942_original_numeric_reconciliation.csv')
    return dict(events_total=len(current),negative_or_canceled=sum(x.get('is_cancellation')=='True' for x in current),
        future_company_guidance_titles=sum(x['event_type']=='FORECAST_DISCLOSURE' for x in current),
        numeric_growth_signals_approved=0,original_receipts_verified=len({x['receipt_no'] for x in vs if prev.receipt_verified(vs,x['receipt_no'])}),
        strict_pit_approved=False)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('full','verify','events','audit'),default='full')
    p.add_argument('--financial',default='reports/v93_financial_calendar_adjusted_provisional.csv')
    p.add_argument('--candidate-file',default='config/v94_signal_candidates_reference.csv')
    p.add_argument('--outdir',default='reports')
    p.add_argument('--archive-bundle',default='')
    p.add_argument('--ticker',default='');p.add_argument('--asof',default='')
    p.add_argument('--max-documents',type=int,default=6);p.add_argument('--max-companies',type=int,default=18)
    p.add_argument('--max-pages',type=int,default=10);p.add_argument('--max-retries',type=int,default=2)
    p.add_argument('--lookback-days',type=int,default=180);p.add_argument('--delay-seconds',type=float,default=0.5)
    args=p.parse_args(argv)
    if args.ticker and not re.fullmatch(r'\d{6}',args.ticker):p.error('Ticker must be 6 digits')
    if args.asof:
        try:now=date.fromisoformat(args.asof)
        except ValueError:p.error('asof must be valid YYYY-MM-DD')
        if now>date.today():p.error('Future asof rejected')
    if not 1<=args.max_documents<=12 or not 1<=args.max_companies<=30 or not 1<=args.max_pages<=20 or not 1<=args.max_retries<=3 or not 30<=args.lookback_days<=365 or not 0<=args.delay_seconds<=5:
        p.error('Bad batch guard')
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    fin=old.read_csv(Path(args.financial)); candidates=old.read_csv(Path(args.candidate_file))
    if not fin or not candidates:raise SystemExit('Historical input data missing; research run refused')
    cal=xcals.get_calendar('XKRX')
    receipt_candidates=old.recent_candidates(candidates,fin,args.ticker or None,
                                             limit=max(2000,len(candidates)))
    result={'version':'9.4.2-receipt-fix','mode':args.mode,
        'raw_chart_candidates':len(candidates),'asof_receipt_candidates':len(receipt_candidates),
        'strict_pit_approved':False,'stock_order_approved':False,
        'note':'Source amount comparison by historical receipt only, not complete PIT. Company forecasts are not analyst consensus.'}
    if args.mode in ('full','verify'):result['verify']=verify(args,fin,candidates,cal)
    if args.mode in ('full','events'):result['events']=events(args,fin,candidates,cal)
    result['audit']=audit(args,cal)
    write_json(out/'v942_research_summary.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':main()
