#!/usr/bin/env python3
"""v9.3: conservative PIT calendar audit + provisional earnings recovery + original archive probe.

NEVER claims point-in-time verified numbers. Never overwrites legacy v9.1 data.
Financial snapshots can contain subsequent restatements. Archive download != number verification.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, io, json, os, re, sys, time, urllib.request, urllib.parse, urllib.error, zipfile
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
import exchange_calendars as xcals

# Existing v9.1 lives alongside this file in GitHub scripts/.
import krx_opendart_financial_v91 as legacy

BASE_FIELDS = legacy.SCHEMA
EXTRA_FIELDS = ['prior_revenue_amount_krw','prior_op_profit_amount_krw','earnings_transition','revenue_growth_status',
                'balance_sheet_status','pit_numeric_status','calendar_source','original_available_date','date_check_status']
FIELDS = BASE_FIELDS + EXTRA_FIELDS
REPAIR_FIELDS = FIELDS
AUDIT_FIELDS = ['ticker','year','report_code','filing_date','receipt_no','status','count','recommended_action']
PRIORITIES = {'RECEIPT_MISMATCH':0,'MISSING_ACCOUNT':1,'MISSING_OR_INVALID_FINANCIAL_AMOUNT':2,
              'NONCOMPARABLE_PREVIOUS_YEAR':3,'NO_VERIFIABLE_ACCOUNTS':4}


def read_csv_file(p):
    if not p.exists(): return []
    with p.open('r', encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))


def read_input_reports(outdir:Path, source_zip:str|None):
    names=['v91_financial_pit_provisional.csv','v91_financial_collection_audit.csv','v91_financial_collection_state.json']
    if source_zip:
        with zipfile.ZipFile(source_zip) as z:
            for name in names:
                if name not in z.namelist():raise RuntimeError(f'Report ZIP missing expected {name}')
            def rows(name):return list(csv.DictReader(io.StringIO(z.read(name).decode('utf-8-sig'))))
            return rows(names[0]),rows(names[1]),json.loads(z.read(names[2]).decode('utf-8'))
    row=read_csv_file(outdir/names[0]); audit=read_csv_file(outdir/names[1]); statefile=outdir/names[2]
    if not row or not audit or not statefile.exists():raise RuntimeError('v9.1 data missing; first run v9.2 collector, or supply --source-zip')
    return row,audit,json.loads(statefile.read_text(encoding='utf-8'))


def krx_next_session(d:str,calendar):
    """Conservative daily backtest: exclude filing date, use next XKRX calendar session.
    Unknown one-off market closures still require independent KRX verification.
    """
    x=date.fromisoformat(d)
    for n in range(1,22):
        nextday=x+timedelta(days=n)
        if calendar.is_session(nextday.isoformat()):return nextday.isoformat()
    raise ValueError(f'No XKRX session after {d}')


def date_validate(rec,cal):
    v=dict(rec)
    v['original_available_date']=v.get('available_date','')
    v['calendar_source']='exchange_calendars:XKRX; daily next session; historical official KRX crosscheck needed'
    try:
        filing=v['filing_date']; date.fromisoformat(filing)
        receipt=v['receipt_no']
        if not re.fullmatch(r'\d{14}',receipt) or receipt[:8]!=filing.replace('-',''):
            v['date_check_status']='RECEIPT_DATE_CONFLICT';v['available_date']='';return v
        v['available_date']=krx_next_session(filing,cal)
        v['date_check_status']='XKRX_NEXT_SESSION_COMPUTED' if v['available_date']!=v['original_available_date'] else 'XKRX_ORIGINAL_DATE_MATCH'
    except (ValueError,KeyError):
        v['available_date']='';v['date_check_status']='UNRESOLVED_DATE'
    return v


def detect_missing(state, financial_rows, audit):
    done=set(state.get('completed_tickers',[]))
    have={x.get('ticker','') for x in financial_rows}
    missing=sorted(done-have)
    reasons=collections.defaultdict(collections.Counter)
    for a in audit:
        t=a.get('ticker','')
        if t in missing:reasons[t][a.get('status','UNKNOWN')]+=1
    return missing, reasons


def build_report(root:Path,source_zip=None):
    root.mkdir(parents=True,exist_ok=True)
    original, audit,state=read_input_reports(root,source_zip)
    recovered=read_csv_file(root/'v93_financial_recovered_provisional.csv')
    missing, reason_counter=detect_missing(state,original,audit)
    cal=xcals.get_calendar('XKRX')
    # Do not promote any provisional row to strict PIT; verify original numeric vintage separately.
    pool={(x['ticker'],x['receipt_no'],x['fs_div']):x for x in original}
    for r in recovered:
        k=(r['ticker'],r['receipt_no'],r['fs_div'])
        if k not in pool:pool[k]=r
    transformed=[]
    date_changed=collections.Counter()
    for r in sorted(pool.values(),key=lambda v:(v['ticker'],v['filing_date'],v['receipt_no'])):
        v=date_validate(r,cal)
        v['pit_numeric_status']='UNVERIFIED_CURRENT_API_SNAPSHOT_NOT_ORIGINAL'
        # Ensure missing extra attributes stay explicit but do NOT invent estimates.
        for fld in EXTRA_FIELDS:v.setdefault(fld,'')
        transformed.append(v)
        date_changed[v['date_check_status']]+=1
    legacy.atomic_csv(root/'v93_financial_calendar_adjusted_provisional.csv',transformed,FIELDS)
    detail=[]
    for ticker in missing:
        counts=reason_counter[ticker]
        reason=';'.join(f'{k}:{v}' for k,v in sorted(counts.items(),key=lambda pair:(PRIORITIES.get(pair[0],9),pair[0])))
        detail.append({'ticker':ticker,'audit_reasons':reason,'reason_count':sum(counts.values()),
                       'recovered_rows':sum(x['ticker']==ticker for x in recovered),
                       'needs_specialized_financial_account_mapping':any(x in counts for x in ('MISSING_ACCOUNT','MISSING_OR_INVALID_FINANCIAL_AMOUNT')),
                       'needs_original_vintage_review':counts.get('RECEIPT_MISMATCH',0)>0,
                       'needs_turnaround_recovery':counts.get('NONCOMPARABLE_PREVIOUS_YEAR',0)>0})
    legacy.atomic_csv(root/'v93_missing_ticker_diagnosis.csv',detail,
                      ['ticker','audit_reasons','reason_count','recovered_rows','needs_specialized_financial_account_mapping',
                       'needs_original_vintage_review','needs_turnaround_recovery'])
    # Source counts quantify *records*, not number of independently affected filings.
    ac=collections.Counter(a.get('status','UNKNOWN') for a in audit)
    actual_recovered={x['ticker'] for x in recovered}
    s={'version':'9.3-audit','strict_pit_approved':False,'original_verification_completed':False,
       'source':'uploaded v9.2 report ZIP' if source_zip else 'GitHub reports/v9.1 files',
       'universe_processed':len(set(state.get('completed_tickers',[]))),
       'universe_target_in_v92_status':len(set(state.get('completed_tickers',[]))),
       'original_provisional_rows':len(original),'original_funded_tickers':len({v['ticker'] for v in original}),
       'zero_original_rows_tickers':len(missing),'zero_original_rows_codes':missing,
       'recovered_rows':len(recovered),'recovered_distinct_tickers':len(actual_recovered),
       'combined_provisional_rows':len(transformed),'combined_distinct_tickers':len({v['ticker'] for v in transformed}),
       'calendar_changed_rows':date_changed['XKRX_NEXT_SESSION_COMPUTED'],
       'calendar_same_rows':date_changed['XKRX_ORIGINAL_DATE_MATCH'],
       'calendar_invalid_rows':sum(v for k,v in date_changed.items() if k not in ('XKRX_NEXT_SESSION_COMPUTED','XKRX_ORIGINAL_DATE_MATCH')),
       'calendar_method':'XKRX next session after disclosure date, NOT confirmed against KRX unscheduled closures',
       'audit_status_counts':dict(ac),'risk_notes':[
          'The 258-company price-cache universe is not the full historical KRX market.',
          'OpenDART current API data may contain amendments unavailable at historical signals.',
          'Downloading an original document archive does not validate financial numbers.',
          'No data in this package are approved to replace config/v90_financial_pit.csv.'
       ]}
    legacy.atomic_json(root/'v93_pit_quality_summary.json',s)
    return s


def split_amount(rec,rep):
    if rep=='11011':return legacy.cash(rec.get('thstrm_amount')),legacy.cash(rec.get('frmtrm_amount'))
    cur=legacy.cash(rec.get('thstrm_add_amount')); prior=legacy.cash(rec.get('frmtrm_add_amount'))
    if rep=='11013':
        if cur is None:cur=legacy.cash(rec.get('thstrm_amount'))
        if prior is None:prior=legacy.cash(rec.get('frmtrm_q_amount'))
    return cur,prior


def transition(current,prior):
    if current is None or prior is None:return 'PRIOR_OR_CURRENT_MISSING'
    if prior<0 and current>0:return 'LOSS_TO_PROFIT'
    if prior==0 and current>0:return 'ZERO_TO_PROFIT'
    if prior>0 and current<=0:return 'PROFIT_TO_LOSS_OR_ZERO'
    if prior<0 and current<=0:
        return 'LOSS_NARROWING' if current>prior else ('LOSS_WIDENING' if current<prior else 'LOSS_UNCHANGED')
    if prior==0 and current<=0:return 'ZERO_TO_LOSS_OR_ZERO'
    return 'PROFIT_CONTINUES'


def metric_recover(rows,report_code,fs):
    rev=legacy.pick_account(rows,{'매출액','매출','수익(매출액)','영업수익'},
        {'ifrs-full_revenue','ifrs_revenue','ifrs-full_revenuefromcontractswithcustomers'},fs,'is')
    op=legacy.pick_account(rows,{'영업이익','영업이익(손실)','영업손실'},
        {'dart_operatingincomeloss','ifrs-full_profitlossfromoperatingactivities'},fs,'is')
    li=legacy.pick_account(rows,{'부채총계'},{'ifrs-full_liabilities','ifrs_liabilities'},fs,'bs')
    eq=legacy.pick_account(rows,{'자본총계'},{'ifrs-full_equity','ifrs_equity'},fs,'bs')
    if rev is None or op is None:return None,'MISSING_INCOME_STATEMENT_ACCOUNTS'
    found=[x for x in (rev,op,li,eq) if x is not None]
    if any((x.get('currency') or 'KRW').upper() not in ('KRW','원') for x in found):
        return None,'NON_KRW'
    cr,pr=split_amount(rev,report_code);co,po=split_amount(op,report_code)
    if cr is None or cr<=0 or co is None:return None,'MISSING_CURRENT_IS_AMOUNT'
    liabilities=legacy.cash(li.get('thstrm_amount')) if li else None
    equity=legacy.cash(eq.get('thstrm_amount')) if eq else None
    has_bs=(liabilities is not None and equity is not None and equity>0)
    return {'revenue_yoy_pct':round(100*(cr/pr-1),4) if pr is not None and pr>0 else '',
            'op_profit_yoy_pct':round(100*(co/po-1),4) if po is not None and po>0 else '',
            'op_margin_pct':round(100*co/cr,4),
            'debt_ratio_pct':round(100*liabilities/equity,4) if has_bs else '',
            'revenue_amount_krw':cr,'op_profit_amount_krw':co,
            'liabilities_amount_krw':liabilities if liabilities is not None else '',
            'equity_amount_krw':equity if equity is not None else '',
            'prior_revenue_amount_krw':pr if pr is not None else '',
            'prior_op_profit_amount_krw':po if po is not None else '',
            'earnings_transition':transition(co,po),
            'revenue_growth_status':'COMPARABLE' if pr is not None and pr>0 else 'NO_POSITIVE_PRIOR_REVENUE',
            'balance_sheet_status':'COMPLETE' if has_bs else 'INCOMPLETE',
           },'OK'


def repair_missing(root:Path, max_tickers:int):
    orig,audit,state=read_input_reports(root,None)
    missing,_=detect_missing(state,orig,audit)
    records=read_csv_file(root/'v93_financial_recovered_provisional.csv')
    fixed={r['ticker'] for r in records}
    attempted_path=root/'v93_repair_attempt_state.json'
    attempted=json.loads(attempted_path.read_text(encoding='utf-8')) if attempted_path.exists() else {}
    # Repeat only unattempted zeros. Failures are logged for investigation, not silently marked valid.
    todo=[t for t in missing if t not in fixed and t not in attempted][:max_tickers]
    if not todo:
        result={'selected':[],'note':'No new unattempted missing tickers. See v93_repair_attempt_state.json.'}
        return result
    key=os.environ.get('OPENDART_API_KEY','').strip()
    if not re.fullmatch(r'[A-Za-z0-9]{40}',key):raise RuntimeError('OPENDART_API_KEY missing/malformed (secret not shown)')
    corp=legacy.get_corp_codes(key)
    rec_index={(r['ticker'],r['receipt_no'],r['fs_div']):r for r in records}
    result={'selected':todo,'per_ticker':{},'strict_pit_approved':False}
    for ticker in todo:
        code=corp.get(ticker)
        info={'saved':0,'reasons':collections.Counter(),'errors':[]}
        if not code:
            info['reasons']['NO_CORP_MAPPING']+=1
        else:
            for yr in (2023,2024,2025,2026):
                try:
                    today=date.today()
                    endpoint=f'{min(yr+1,today.year)}0630' if yr<today.year else today.strftime('%Y%m%d')
                    data=legacy.get_json(key,'list.json',{'corp_code':code,'bgn_de':f'{yr}0101','end_de':endpoint,
                                             'pblntf_ty':'A','last_reprt_at':'N','page_count':'100'})
                    if str(data.get('status'))=='013':continue
                    if int(data.get('total_page',1))>1:
                        info['reasons']['PAGINATION_NOT_RECONCILED']+=1;continue
                    originals=legacy.parse_original_filings(data.get('list',[]),yr)
                    for f in originals:
                        for fs in ('CFS','OFS'):
                            body=legacy.get_json(key,'fnlttSinglAcntAll.json',{'corp_code':code,'bsns_year':str(yr),
                                                      'reprt_code':f['report_code'],'fs_div':fs})
                            if str(body.get('status'))=='013':continue
                            rows=body.get('list',[])
                            receipts={str(x.get('rcept_no','')) for x in rows if x.get('rcept_no')}
                            if receipts!={f['receipt_no']}:
                                info['reasons']['RECEIPT_MISMATCH']+=1;continue
                            metric,status=metric_recover(rows,f['report_code'],fs)
                            if metric is None:
                                info['reasons'][status]+=1;continue
                            rec={**metric,'ticker':ticker,'corp_code':code,'filing_date':f['filing_date'],
                                 'available_date':legacy.next_calendar_day(f['filing_date']),
                                 'report_year':yr,'report_code':f['report_code'],'receipt_no':f['receipt_no'],
                                 'fs_div':fs,'source_url':'https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+f['receipt_no'],
                                 'validation_status':'RECOVERED_PROVISIONAL_NOT_PIT_VERIFIED'}
                            ik=(ticker,f['receipt_no'],fs)
                            rec_index[ik]=rec
                            info['saved']+=1
                            break
                except (RuntimeError,ValueError,urllib.error.URLError,TimeoutError):
                    info['errors'].append(f'REQUEST_FAILED_YEAR_{yr}')
                    break
        legacy.atomic_csv(root/'v93_financial_recovered_provisional.csv',
                sorted(rec_index.values(),key=lambda r:(r['ticker'],r['filing_date'],r['receipt_no'])),REPAIR_FIELDS)
        info['reasons']=dict(info['reasons'])
        attempted[ticker]=info
        legacy.atomic_json(attempted_path,attempted)
        result['per_ticker'][ticker]=info
    return result


def archive_probe(root:Path,limit:int,ticker:str|None):
    rows,_,_=read_input_reports(root,None)
    key=os.environ.get('OPENDART_API_KEY','').strip()
    if not re.fullmatch(r'[A-Za-z0-9]{40}',key):raise RuntimeError('OPENDART_API_KEY missing/malformed (secret not shown)')
    unique={}
    for row in sorted(rows,key=lambda v:(v['ticker']!='083450',v['filing_date']),reverse=False):
        if ticker and row['ticker']!=ticker:continue
        unique.setdefault(row['receipt_no'],row)
    selected=list(unique.values())[:limit]
    (root/'v93_original_archives').mkdir(exist_ok=True)
    audit=[]
    for r in selected:
        receipt=r['receipt_no']
        result={'ticker':r['ticker'],'receipt_no':receipt,'status':'NOT_YET_CHECKED','numeric_vintage_verified':False}
        try:
            url=legacy.ROOT+'document.xml?'+urllib.parse.urlencode({'crtfc_key':key,'rcept_no':receipt})
            req=urllib.request.Request(url,headers={'User-Agent':'KRX-PIT-original-document-audit/9.3'})
            with urllib.request.urlopen(req,timeout=65) as response:
                data=response.read(30_000_001)
            if len(data)>30_000_000:result['status']='ARCHIVE_TOO_LARGE'
            elif not zipfile.is_zipfile(io.BytesIO(data)):
                # avoid API error message and secret accidentally appearing in logs.
                result['status']='NOT_A_ZIP_POSSIBLE_API_STATUS'
            else:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    names=z.namelist()
                    if len(names)>250 or sum(x.file_size for x in z.infolist())>250_000_000:
                        result['status']='ZIP_SIZE_LIMIT'
                    else:
                        filename=root/'v93_original_archives'/f'{receipt}.zip'
                        filename.write_bytes(data)
                        result.update(status='ARCHIVE_FETCHED_NEEDS_NUMERIC_RECONCILIATION',
                                      sha256=hashlib.sha256(data).hexdigest(),files=len(names),bytes=len(data))
        except (urllib.error.URLError,TimeoutError,RuntimeError):
            result['status']='REQUEST_FAILED_OR_TIMEOUT'
        audit.append(result)
        time.sleep(1)
    legacy.atomic_json(root/'v93_original_archive_manifest.json',
                       {'strict_pit_approved':False,'original_numeric_values_verified':False,
                        'archives':audit,'note':'ZIP hash proves obtained bytes for receipt, not historical numeric verification.'})
    return audit


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir',default='reports');p.add_argument('--source-zip',default=None)
    p.add_argument('--mode',choices=['audit','repair_missing','archive_sample'],default='audit')
    p.add_argument('--max-tickers',type=int,default=20)
    p.add_argument('--max-documents',type=int,default=2)
    p.add_argument('--ticker',default=None)
    args=p.parse_args()
    if not 1<=args.max_tickers<=20 or not 1<=args.max_documents<=5:p.error('batch limit out of bounds')
    if args.ticker and not re.fullmatch(r'\d{6}',args.ticker):p.error('ticker must be 6 digits')
    try:
        root=Path(args.outdir)
        if args.mode=='repair_missing':
            if args.source_zip:raise RuntimeError('Repair mode must use committed reports/ state (no external ZIP)')
            print(json.dumps(repair_missing(root,args.max_tickers),ensure_ascii=False,default=str))
        if args.mode=='archive_sample':
            if args.source_zip:raise RuntimeError('Archive mode must use committed reports/ state')
            print(json.dumps(archive_probe(root,args.max_documents,args.ticker),ensure_ascii=False))
        summary=build_report(root,args.source_zip)
        print(json.dumps(summary,ensure_ascii=False))
    except Exception as e:
        # Do not print urllib exception objects or URLs (they may embed the API secret).
        print('v9.3 failed:',type(e).__name__,str(e) if isinstance(e,(ValueError,FileNotFoundError)) else '',file=sys.stderr)
        sys.exit(1)

if __name__=='__main__':main()
