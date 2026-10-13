#!/usr/bin/env python3
"""v9.4 research-only: conservatively reconcile ORIGINAL DART filing tables vs API snapshots,
and collect dated forward-expectation disclosure *leads* visible as of signal dates.

Does not approve historical PIT data or generate orders. Never prints authentication secrets.
"""
from __future__ import annotations
import argparse
import collections
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import zipfile
from datetime import date, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
import warnings
from bs4 import XMLParsedAsHTMLWarning
import exchange_calendars as xcals

warnings.filterwarnings('ignore', category=XMLParsedAsHTMLWarning)

try:
    import krx_opendart_financial_v91 as v91
    import krx_opendart_pit_audit_v93 as v93
except ImportError as exc:
    raise SystemExit('Place v9.4 alongside v9.1 and v9.3 under scripts/') from exc

KEY_RE = re.compile(r'[A-Za-z0-9]{40}\Z')
COLUMNS = ['ticker','receipt_no','filing_date','available_date','fs_div','metric','api_value_krw',
           'original_value_krw','delta_krw','status','document_sha256','source_url','note']
CANDIDATE_COLUMNS = ['ticker','signal_date','signal_score','selection_status','receipt_no',
                     'financial_available_date','candidate_source']
EVENT_COLUMNS = ['ticker','signal_date','receipt_no','filing_date','first_usable_session','report_name',
                 'event_type','is_amendment','source_url','evidence_status','asof_eligible']
SUMMARY_NAME = 'v94_forward_pit_summary.json'

EVENT_PATTERNS = (
    ('SUPPLY_CONTRACT', re.compile(r'공급계약|단일판매|수주계약|판매계약')),
    ('CAPEX', re.compile(r'신규시설투자|시설투자|유형자산취득|생산설비')),
    ('EARNINGS_PREVIEW', re.compile(r'잠정실적|영업\s*\(잠정\)\s*실적|영업실적|매출액또는손익구조')),
    ('FORECAST_DISCLOSURE', re.compile(r'영업실적전망|매출액전망|전망공시|공정공시')),
    ('NEW_BUSINESS', re.compile(r'신규사업|주요사항보고서\(영업|사업양수|합병결정')),
)
METRICS = [('revenue_amount_krw','revenue','income'),
           ('op_profit_amount_krw','op_profit','income'),
           ('liabilities_amount_krw','liabilities','balance'),
           ('equity_amount_krw','equity','balance')]
ALIASES = {
    'revenue': {'매출액','매출','수익(매출액)','영업수익'},
    'op_profit': {'영업이익','영업이익(손실)','영업손실'},
    'liabilities': {'부채총계'},
    'equity': {'자본총계'},
}


def read_csv(path:Path):
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def read_zip_csv(z: zipfile.ZipFile, path:str):
    if path not in z.namelist():
        return []
    return list(csv.DictReader(io.StringIO(z.read(path).decode('utf-8-sig'))))


def textnorm(s):
    return re.sub(r'\s+', '', str(s or '')).replace('－','-')


def num_krw(raw):
    s=textnorm(raw).replace(',','').replace('−','-')
    neg=s.startswith('(') and s.endswith(')')
    if neg:s=s[1:-1]
    if s.startswith('△') or s.startswith('▲'):
        neg=True; s=s[1:]
    if not re.fullmatch(r'-?\d+', s):
        return None
    return -abs(int(s)) if neg else int(s)


def select_group(soup, code, fs_div):
    tail={'CFS':{'income':['{XBRL}IS1','{XBRL}IS'], 'balance':['{XBRL}BS']},
          'OFS':{'income':['{XBRL}IS_S1','{XBRL}IS_S'], 'balance':['{XBRL}BS_S1']}}
    candidates=[]
    for group in soup.find_all('table-group'):
        kind = group.get('aclass','').upper()
        if kind in {x.upper() for x in tail[fs_div][code]}:
            candidates.append(group)
    if len(candidates)!=1:
        return None
    return candidates[0]


def read_financial_table(doc_xml:bytes,fs_div:str,report_code:str):
    """Parse one uniquely identified XBRL table per statement; fail closed on ambiguity.
    Does not infer units or derive numbers from unrelated narrative sections.
    """
    soup=BeautifulSoup(doc_xml.decode('utf-8-sig','replace'),'html.parser')
    fields={}
    for section in ('income','balance'):
        group=select_group(soup,section,fs_div)
        if group is None:
            return {}, 'MISSING_OR_MULTIPLE_XBRL_'+section.upper()
        txt=textnorm(group.get_text(' ',strip=True)[:1200])
        if '(단위:원)' in txt or '(단위：원)' in txt:
            unit=1
        elif '(단위:천원)' in txt:
            unit=1000
        elif '(단위:백만원)' in txt:
            unit=1000000
        else:
            return {},'AMBIGUOUS_UNIT_'+section.upper()
        want=('revenue','op_profit') if section=='income' else ('liabilities','equity')
        for row in group.find_all('tr'):
            cells=row.find_all(['td','th'],recursive=False)
            if len(cells)<3:continue
            label=textnorm(cells[0].get_text(' ',strip=True))
            for field in want:
                if label not in {textnorm(x) for x in ALIASES[field]}:continue
                if field in fields: return {},'DUPLICATE_ACCOUNT_'+field
                nums=[num_krw(c.get_text(' ',strip=True)) for c in cells[1:]]
                if section=='balance':
                    if len(nums)!=2 or any(n is None for n in nums):
                        return {},'AMBIGUOUS_BALANCE_COLUMNS_'+field
                    fields[field]= (nums[0]*unit,nums[1]*unit)
                else:
                    if report_code=='11011' and len(nums)==2:
                        ix=(0,1)
                    elif report_code in ('11013','11012','11014') and len(nums)==4:
                        ix=(1,3) # YTD and prior YTD, not quarterly column
                    else:
                        return {},'AMBIGUOUS_INCOME_COLUMNS_'+field
                    if any(nums[i] is None for i in ix):
                        return {},'NON_NUMERIC_ACCOUNT_'+field
                    fields[field]=(nums[ix[0]]*unit,nums[ix[1]]*unit)
    if set(fields)!=set(ALIASES):
        return fields,'MISSING_REQUIRED_ACCOUNT'
    return fields,'PARSED'


def read_original_archive(blob,receipt):
    if len(blob)>30_000_000 or not zipfile.is_zipfile(io.BytesIO(blob)):
        return None,'INVALID_ARCHIVE'
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        members=[p for p in z.infolist() if p.filename.lower().endswith('.xml')]
        if len(members)!=1 or len(z.infolist())>30 or members[0].file_size>25_000_000:
            return None,'UNEXPECTED_ARCHIVE_STRUCTURE'
        if Path(members[0].filename).name != f'{receipt}.xml':
            return None,'RECEIPT_FILE_MISMATCH'
        return z.read(members[0]),'OK'


def metric_comparison(row,blob,cal):
    """A raw-value exact match can be verified per receipt, not a full report PIT certification."""
    receipt=row['receipt_no']
    document,status=read_original_archive(blob,receipt)
    if status!='OK':
        return [{'ticker':row['ticker'],'receipt_no':receipt,'status':status,'metric':'ARCHIVE',
                 'note':'No numeric comparison performed'}]
    sha=hashlib.sha256(blob).hexdigest()
    try: available=v93.krx_next_session(row['filing_date'],cal)
    except ValueError: available=''
    parsed,parse_status=read_financial_table(document,row['fs_div'],row['report_code'])
    result=[]
    for key,field,_ in METRICS:
        api=num_krw(row.get(key,''))
        found=parsed.get(field)
        original=found[0] if found else None
        if parse_status!='PARSED': state='UNVERIFIED_'+parse_status
        elif api is None:state='API_AMOUNT_MISSING'
        elif api==original:state='EXACT_MATCH'
        else:state='MISMATCH'
        result.append({'ticker':row['ticker'],'receipt_no':receipt,'filing_date':row['filing_date'],
                'available_date':available,'fs_div':row['fs_div'],'metric':key,
                'api_value_krw':api if api is not None else '',
                'original_value_krw':original if original is not None else '',
                'delta_krw':api-original if api is not None and original is not None else '',
                'status':state,'document_sha256':sha,'source_url':row.get('source_url',''),
                'note':'Raw filing XBRL statement only; not global PIT approval'})
    return result


def load_financial(path, report_zip=None):
    if report_zip:
        with zipfile.ZipFile(report_zip) as z:
            data=read_zip_csv(z,'v93_financial_calendar_adjusted_provisional.csv')
        if data:return data
    result=read_csv(Path(path))
    if not result: raise ValueError('Missing v9.3 calendar-adjusted financial data')
    return result


def load_candidates(path=None,candidate_zip=None):
    if candidate_zip:
        with zipfile.ZipFile(candidate_zip) as z:
            return read_zip_csv(z,'v90_pit_candidate_audit.csv')
    if path:
        return read_csv(Path(path))
    return []


def recent_candidates(candidate_rows,financial_rows,ticker=None,limit=8):
    """Signal-aware selection; only financial rows already usable at chart signal date."""
    fidx=collections.defaultdict(list)
    for r in financial_rows:
        if re.fullmatch(r'\d{14}',r.get('receipt_no','')):
            fidx[r['ticker']].append(r)
    selection=[]
    for c in candidate_rows:
        if ticker and c.get('ticker')!=ticker:continue
        if c.get('selection_status')!='MISSING_ASOF_SECTOR':continue
        sig=c.get('signal_date','')
        try:date.fromisoformat(sig)
        except ValueError:continue
        found=[f for f in fidx.get(c['ticker'],[]) if f.get('available_date','') and f['available_date']<=sig]
        if not found:continue
        rec=max(found,key=lambda x:(x['available_date'],x['filing_date']))
        selection.append({'ticker':c['ticker'],'signal_date':sig,'signal_score':c.get('signal_score','0'),
                          'selection_status':c['selection_status'],'receipt_no':rec['receipt_no'],
                          'financial_available_date':rec['available_date'],'candidate_source':'v90_charts_ONLY_not_strict_strategy'})
    selection.sort(key=lambda x:(-int(x.get('signal_score') or 0),x['ticker'],x['signal_date']))
    seen=set();output=[]
    for s in selection:
        if s['receipt_no'] in seen:continue
        seen.add(s['receipt_no']);output.append(s)
        if len(output)>=limit:break
    return output


def choose_archives(financial, candidates, ticker, max_documents):
    idx={}
    for r in sorted(financial,key=lambda x:x.get('fs_div')!='CFS'):
        idx.setdefault((r['ticker'],r['receipt_no']),r)
    if ticker:
        rows=list({receipt:r for (t,receipt),r in idx.items() if t==ticker}.values())
        rows.sort(key=lambda x:x['filing_date'])
        # Prefer candidate-as-of if possible, else oldest archived originals for baseline reproducibility.
        chosen=[]
        for c in candidates:
            k=(c['ticker'],c['receipt_no'])
            if k in idx and idx[k] not in chosen:chosen.append(idx[k])
        return (chosen+ [r for r in rows if r not in chosen])[:max_documents]
    return [idx[k] for k in [(c['ticker'],c['receipt_no']) for c in candidates] if k in idx][:max_documents]


def get_archive(key,receipt):
    params=urllib.parse.urlencode({'crtfc_key':key,'rcept_no':receipt})
    req=urllib.request.Request(v91.ROOT+'document.xml?'+params,headers={'User-Agent':'KRX-Forward-PIT/9.4'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=90) as res:
                return res.read(30_000_001)
        except (urllib.error.URLError,TimeoutError):
            if attempt==2:raise
            time.sleep(2*(attempt+1))


def read_archives_from_bundle(bundle_path):
    if not bundle_path:return {}
    d={}
    with zipfile.ZipFile(bundle_path) as z:
        for fn in z.namelist():
            mat=re.fullmatch(r'v93_original_archives/(\d{14})\.zip',fn)
            if mat:d[mat.group(1)]=z.read(fn)
    return d


def reconcile(args, financial, cands, cal):
    all_selected=choose_archives(financial,cands,args.ticker,100000)
    old_attempts_path=Path(args.outdir)/'v94_archive_attempts.json'
    old_attempts=json.loads(old_attempts_path.read_text(encoding='utf-8')) if old_attempts_path.exists() else {'attempts':[]}
    completed={x['receipt_no'] for x in old_attempts.get('attempts',[]) if x.get('status')=='COMPARED'}
    selected=[r for r in all_selected if r['receipt_no'] not in completed][:args.max_documents]
    bundle=read_archives_from_bundle(args.archive_bundle)
    if args.archive_bundle and not os.environ.get('OPENDART_API_KEY','').strip():
        # Offline artifact replays: do not attempt network for unrelated receipts.
        selected=[r for r in selected if r['receipt_no'] in bundle]
    key=os.environ.get('OPENDART_API_KEY','').strip()
    if args.mode=='verify' and not KEY_RE.fullmatch(key) and any(x['receipt_no'] not in bundle for x in selected):
        raise ValueError('OPENDART_API_KEY must be configured for downloading missing original archives')
    out=Path(args.outdir)
    records=read_csv(out/'v94_original_numeric_reconciliation.csv')
    attempts=list(old_attempts.get('attempts',[]))
    for i,r in enumerate(selected):
        receipt=r['receipt_no']
        try:
            blob=bundle[receipt] if receipt in bundle else get_archive(key,receipt)
            result=metric_comparison(r,blob,cal)
            # Keep only latest set of field records for this receipt if retried.
            records=[x for x in records if x.get('receipt_no')!=receipt]+result
            a={'ticker':r['ticker'],'receipt_no':receipt,
               'status':'COMPARED' if len(result)==4 else 'NOT_COMPARED',
               'exact_match_fields':sum(x['status']=='EXACT_MATCH' for x in result)}
            attempts=[x for x in attempts if x.get('receipt_no')!=receipt]+[a]
        except (urllib.error.URLError, TimeoutError, zipfile.BadZipFile,ValueError):
            a={'ticker':r['ticker'],'receipt_no':receipt,'status':'ARCHIVE_FETCH_FAILED','exact_match_fields':0}
            attempts=[x for x in attempts if x.get('receipt_no')!=receipt]+[a]
        if receipt not in bundle and i<len(selected)-1:time.sleep(1)
    v91.atomic_csv(out/'v94_original_numeric_reconciliation.csv',records,COLUMNS)
    v91.atomic_json(out/'v94_archive_attempts.json',{'attempts':attempts,'strict_pit_approved':False})
    return {'documents_attempted_this_run':len(selected),'documents_attempted_total':len(attempts),
            'documents_four_fields_exact_total':sum(x['exact_match_fields']==4 for x in attempts),
            'field_status_counts':dict(collections.Counter(x['status'] for x in records)),
            'selection_basis':'candidate_priority' if cands else ('explicit_ticker' if args.ticker else 'no_candidate_file')}


def classify_event(name):
    if re.search(r'기재정정|첨부정정|정정신고|\[정정\]|\(정정\)|^\s*정정',name): amended=True
    else: amended=False
    for label,pattern in EVENT_PATTERNS:
        if pattern.search(textnorm(name)):
            return label, amended
    return None,amended


def build_event_row(d, ticker,signal_date,cal):
    name=str(d.get('report_nm',''))
    tag,amend=classify_event(name)
    if not tag:return None
    receipt=str(d.get('rcept_no',''));raw_day=str(d.get('rcept_dt',''))
    if not re.fullmatch(r'\d{14}',receipt) or not re.fullmatch(r'\d{8}',raw_day):return None
    filing=f'{raw_day[:4]}-{raw_day[4:6]}-{raw_day[6:8]}'
    if receipt[:8]!=raw_day:return None
    try:first=v93.krx_next_session(filing,cal)
    except ValueError:return None
    return {'ticker':ticker,'signal_date':signal_date,'receipt_no':receipt,'filing_date':filing,
            'first_usable_session':first,'report_name':name,'event_type':tag,'is_amendment':str(amend),
            'source_url':'https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+receipt,
            'evidence_status':'TITLE_ONLY_NO_CONTRACT_VALUE_OR_EARNINGS_FORECAST_VERIFIED',
            'asof_eligible':str(first<=signal_date)}


def select_event_tickers(financial,candidates,ticker,max_companies,asof):
    fcorp={r['ticker']:r.get('corp_code') for r in financial if r.get('corp_code')}
    selected=[]
    if ticker:
        if ticker not in fcorp:raise ValueError('Unknown ticker or missing corporate mapping')
        return [(ticker,fcorp[ticker],asof or date.today().isoformat())]
    for c in candidates:
        t=c['ticker']
        if t in fcorp and t not in [x[0] for x in selected]:
            selected.append((t,fcorp[t],c['signal_date']))
        if len(selected)>=max_companies:break
    return selected


def collect_events(args,financial,candidates,cal,client=None):
    key=os.environ.get('OPENDART_API_KEY','').strip()
    if client is None and not KEY_RE.fullmatch(key):
        raise ValueError('OPENDART_API_KEY must be configured for event collection')
    picks=select_event_tickers(financial,candidates,args.ticker,args.max_companies,args.asof)
    events=[];errs=[];attempt=0
    for ticker,cc,signal in picks:
        cutoff=date.fromisoformat(signal)
        begin=cutoff-timedelta(days=args.lookback_days)
        if begin.year<2015:begin=date(2015,1,1)
        params={'corp_code':cc,'bgn_de':begin.strftime('%Y%m%d'),
                'end_de':cutoff.strftime('%Y%m%d'),'last_reprt_at':'N',
                'page_count':'100','sort':'date','sort_mth':'desc'}
        for page in range(1,args.max_pages+1):
            params['page_no']=str(page)
            try:
                payload= client(cc,params) if client is not None else v91.get_json(key,'list.json',params)
                attempt+=1
                status=str(payload.get('status',''))
                if status=='013':break
                if status!='000':raise RuntimeError('Non-success DART status')
                for d in payload.get('list',[]):
                    r=build_event_row(d,ticker,signal,cal)
                    if r and r['asof_eligible']=='True':events.append(r)
                pages=int(payload.get('total_page','1'))
                if page>=pages:break
                if page==args.max_pages:
                    errs.append({'ticker':ticker,'status':'INCOMPLETE_PAGINATION'});break
                time.sleep(0.5)
            except (RuntimeError,ValueError,urllib.error.URLError,TimeoutError):
                errs.append({'ticker':ticker,'status':'API_ERROR_OR_RATE_LIMIT'});break
        time.sleep(0.5 if client is None else 0)
    dedup={(x['ticker'],x['signal_date'],x['receipt_no']):x for x in events}
    events=sorted(dedup.values(),key=lambda x:(x['ticker'],x['signal_date'],x['filing_date'],x['receipt_no']))
    v91.atomic_csv(Path(args.outdir)/'v94_forward_event_leads.csv',events,EVENT_COLUMNS)
    v91.atomic_json(Path(args.outdir)/'v94_event_attempts.json',{'attempts':attempt,'companies':len(picks),'errors':errs,
        'note':'Only as-of disclosed report titles, NOT quantified contract wins or future earnings estimates.'})
    return {'companies_checked':len(picks),'listed_events':len(events),'api_pages':attempt,
            'event_types':dict(collections.Counter(x['event_type'] for x in events)),
            'warnings':errs,'title_only':True}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['verify','events','plan'],default='plan')
    p.add_argument('--financial',default='reports/v93_financial_calendar_adjusted_provisional.csv')
    p.add_argument('--report-zip',default=None,help='Offline v9.3 report ZIP')
    p.add_argument('--candidate-file',default='config/v94_signal_candidates_reference.csv')
    p.add_argument('--candidate-zip',default=None,help='Offline v9.0 scan report ZIP')
    p.add_argument('--archive-bundle',default=None,help='Offline v9.3 archive_sample artifact ZIP')
    p.add_argument('--ticker',default='')
    p.add_argument('--max-documents',type=int,default=6)
    p.add_argument('--max-companies',type=int,default=4)
    p.add_argument('--asof',default='')
    p.add_argument('--lookback-days',type=int,default=180)
    p.add_argument('--max-pages',type=int,default=5)
    p.add_argument('--outdir',default='reports')
    args=p.parse_args()
    if not 1<=args.max_documents<=12 or not 1<=args.max_companies<=10 or not 30<=args.lookback_days<=365 or not 1<=args.max_pages<=10:
        p.error('Batch limits invalid')
    if args.ticker and not re.fullmatch(r'\d{6}',args.ticker):p.error('Ticker must be six digits')
    if args.asof:
        try:date.fromisoformat(args.asof)
        except ValueError:p.error('asof must be YYYY-MM-DD')
        if date.fromisoformat(args.asof)>date.today():p.error('Future asof not permitted')
    try:
        out=Path(args.outdir);out.mkdir(exist_ok=True,parents=True)
        fin=load_financial(args.financial,args.report_zip)
        cr=load_candidates(args.candidate_file,args.candidate_zip)
        if args.mode!='plan' and not cr and not args.ticker:
            raise ValueError('Missing candidate signals file; provide --candidate-file or --ticker')
        chosen=recent_candidates(cr,fin,args.ticker,limit=2000)
        cal=xcals.get_calendar('XKRX')
        status={'version':'9.4-original-numeric-and-forward-expectation',
                'mode':args.mode,'strict_pit_approved':False,
                'candidate_source_available':bool(cr),'candidate_count':len(cr),
                'financial_rows':len(fin),'financial_tickers':len({r['ticker'] for r in fin}),
                'source_data_research_only':True,
                'warnings':['Raw original numeric matches do not certify original publication vintage or full PIT.',
                            'Disclosure report title is NOT evidence of contract amount, earnings revision or profit growth.',
                            'Only research universe; never use as live order signal or verified backtest gate.']}
        v91.atomic_csv(out/'v94_candidate_financial_priority.csv',chosen,CANDIDATE_COLUMNS)
        if args.mode=='verify':status['verification']=reconcile(args,fin,chosen,cal)
        elif args.mode=='events':status['events']=collect_events(args,fin,chosen,cal)
        else:
            status['selected_receipts']=[r['receipt_no'] for r in choose_archives(fin,chosen,args.ticker,args.max_documents)]
        v91.atomic_json(out/SUMMARY_NAME,status)
        print(json.dumps(status,ensure_ascii=False))
    except (OSError,RuntimeError,ValueError,zipfile.BadZipFile) as e:
        print('v9.4 failed:',type(e).__name__,str(e) if isinstance(e,ValueError) else '(details suppressed)',file=sys.stderr)
        raise SystemExit(1)

if __name__=='__main__':main()
