#!/usr/bin/env python3
"""v9.4.1: fail-closed DART original audit, correct event taxonomy, research-only event evidence.

Strict historical PIT is NEVER certified by this script. No live trade orders.
Requires v9.1/v9.3/v9.4 modules alongside this script.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, io, json, os, re, sys, time, urllib.error, zipfile
from datetime import date, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
import exchange_calendars as xcals
import krx_forward_pit_v94 as old
import krx_opendart_financial_v91 as v91
import krx_opendart_pit_audit_v93 as v93

EV_COLS=['ticker','signal_date','receipt_no','filing_date','first_usable_session','report_name',
         'event_type','is_amendment','is_subsidiary','source_url','sessions_since_first_usable',
         'freshness','evidence_status','asof_eligible']
NUM_COLS=['ticker','signal_date','receipt_no','event_type','report_name','metric','raw_value',
          'value_krw','unit','period','evidence_status','source_url','archive_sha256','note']
VERIFY_COLS=old.COLUMNS
TYPE_PATTERNS=[
 ('FORECAST_DISCLOSURE',r'영업실적.*전망|매출액.*전망|영업이익.*전망|실적전망'),
 ('EARNINGS_ACTUAL',r'매출액또는손익구조|잠정실적|영업\(잠정\)실적|연결재무제표기준영업.*실적(?!.*전망)'),
 ('SUPPLY_CONTRACT',r'단일판매|공급계약|수주계약|판매계약'),
 ('CAPEX',r'신규시설투자|시설투자|유형자산취득|생산설비'),
 ('NEW_BUSINESS',r'신규사업|사업양수|합병결정'),
 ('OTHER_FAIR_DISCLOSURE',r'공정공시|수시공시의무관련사항'),
]
AMENDED_RE=re.compile(r'기재정정|첨부정정|정정신고|\[정정\]|\(정정\)|^정정')
RAW_UNIT_RE=re.compile(r'\(\s*단위\s*[:：]\s*(억\s*원|백만\s*원|천\s*원|원)\s*\)')
METRIC_LABELS={
 'SUPPLY_CONTRACT':{'contract_amount_krw':{'계약금액','계약금액(원)','계약금액(천원)'}},
 'CAPEX':{'investment_amount_krw':{'투자금액','투자금액(원)','투자금액(천원)'}},
 'FORECAST_DISCLOSURE':{'forecast_revenue_krw':{'매출액','예상매출액'},'forecast_operating_profit_krw':{'영업이익','예상영업이익'}},
}


def dump_json(p,obj):v91.atomic_json(Path(p),obj)
def dump_csv(p,rows,cols):v91.atomic_csv(Path(p),rows,cols)
def read_json(p,default):
 p=Path(p)
 if not p.exists():return default
 return json.loads(p.read_text(encoding='utf-8'))


def classify(name):
 """Forward forecast first, actual past earning separate, amendments not fresh."""
 s=old.textnorm(name)
 amended=bool(AMENDED_RE.search(s))
 subsidiary='자회사의주요경영사항' in s
 for k,pattern in TYPE_PATTERNS:
  if re.search(pattern,s):return k,amended,subsidiary
 return 'NOT_RESEARCH_EVENT',amended,subsidiary


def session_age(first, signal, cal):
 if first>signal:return -1
 try:return max(0,len(cal.sessions_in_range(first,signal))-1)
 except Exception:return -1


def normalize_event(d,cal):
 r=dict(d); cat,amend,subsidiary=classify(r.get('report_name',''))
 r['event_type']=cat
 r['is_amendment']=str(amend)
 r['is_subsidiary']=str(subsidiary)
 first=r.get('first_usable_session','');sig=r.get('signal_date','')
 age=session_age(first,sig,cal)
 r['sessions_since_first_usable']=age if age>=0 else ''
 r['asof_eligible']=str(age>=0)
 r['freshness']=('CORRECTION_NOT_NEW_CATALYST' if amend else
                 'FRESH_0_10_SESSIONS' if 0<=age<=10 else
                 'OLDER_THAN_10_SESSIONS' if age>10 else 'NOT_YET_AVAILABLE')
 r['evidence_status']='TITLE_ONLY_NOT_NUMERICALLY_VERIFIED'
 return {k:r.get(k,'') for k in EV_COLS}


def from_dart_list(item,ticker,signal,cal):
 receipt=str(item.get('rcept_no',''));day=str(item.get('rcept_dt',''))
 if not re.fullmatch(r'\d{14}',receipt) or not re.fullmatch(r'\d{8}',day) or receipt[:8]!=day:return None
 try:
  filing=date.fromisoformat(f'{day[:4]}-{day[4:6]}-{day[6:]}').isoformat()
  first=v93.krx_next_session(filing,cal)
 except ValueError:return None
 row={'ticker':ticker,'signal_date':signal,'receipt_no':receipt,'filing_date':filing,
      'first_usable_session':first,'report_name':item.get('report_nm',''),
      'source_url':f'https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}'}
 r=normalize_event(row,cal)
 return r if r['event_type']!='NOT_RESEARCH_EVENT' and r['asof_eligible']=='True' else None


def unique_events(rows):
 return sorted({(r['ticker'],r['signal_date'],r['receipt_no']):r for r in rows}.values(),
               key=lambda r:(r['ticker'],r['signal_date'],r['receipt_no']))


def read_original_numeric(doc,fs_div,report_code):
 """Extend v9.4 class parser only for unique indexed XBRL IS/BS groups.
 Never select arbitrarily among duplicate tables or infer missing unit/period.
 """
 fields,status=old.read_financial_table(doc,fs_div,report_code)
 if status=='PARSED':return fields,status,{'parser':'v94_exact'}
 soup=BeautifulSoup(doc.decode('utf-8-sig','replace'),'html.parser')
 info={'parser':'v941_indexed_class','group_classes':collections.Counter(g.get('aclass','') for g in soup.find_all('table-group'))}
 changed=False
 for section in ('IS','BS'):
  want=('revenue','op_profit') if section=='IS' else ('liabilities','equity')
  # If already matched exactly, do not rewrite or merge it.
  if old.select_group(soup,'income' if section=='IS' else 'balance',fs_div):continue
  opt=[]
  for g in soup.find_all('table-group'):
   cl=str(g.get('aclass','')).upper()
   is_standalone='_S' in cl
   if (fs_div=='OFS')!=is_standalone:continue
   if not re.fullmatch(r'\{XBRL\}'+section+r'(?:[1-9]|_S[1-9]?)',cl):continue
   labels={old.textnorm(c.get_text(' ',strip=True)) for tr in g.find_all('tr') for c in tr.find_all(['td','th'],recursive=False)[:1]}
   if all(any(old.textnorm(a) in labels for a in old.ALIASES[k]) for k in want):opt.append(g)
  if len(opt)!=1:return {},status,dict(info,extension_failure=f'AMBIGUOUS_{section}_GROUPS_{len(opt)}')
  opt[0]['aclass']='{XBRL}'+ ('IS1' if section=='IS' else 'BS') if fs_div=='CFS' else '{XBRL}'+('IS_S1' if section=='IS' else 'BS_S1')
  changed=True
 if not changed:return {},status,info
 parsed,parsed_status=old.read_financial_table(str(soup).encode('utf-8'),fs_div,report_code)
 return parsed,('PARSED_EXTENDED_CLASS' if parsed_status=='PARSED' else parsed_status),info


def compare_archive(row,blob,cal):
 receipt=row['receipt_no'];xml,status=old.read_original_archive(blob,receipt)
 if status!='OK':return [{'ticker':row['ticker'],'receipt_no':receipt,'metric':'ARCHIVE','status':'UNVERIFIED_'+status,'note':'Archive not compared'}], {'archive_status':status}
 fields,pstatus,diag=read_original_numeric(xml,row['fs_div'],row['report_code'])
 sha=hashlib.sha256(blob).hexdigest()
 available=v93.krx_next_session(row['filing_date'],cal)
 results=[]
 for apikey,k,_ in old.METRICS:
  api=old.num_krw(row.get(apikey,'')); rec=fields.get(k)
  orig=rec[0] if rec else None
  st=('EXACT_MATCH' if pstatus.startswith('PARSED') and api is not None and orig==api else
      'MISMATCH' if pstatus.startswith('PARSED') and api is not None and orig is not None else
      'UNVERIFIED_'+pstatus)
  results.append({'ticker':row['ticker'],'receipt_no':receipt,'filing_date':row['filing_date'],
     'available_date':available,'fs_div':row['fs_div'],'metric':apikey,'api_value_krw':api if api is not None else '',
     'original_value_krw':orig if orig is not None else '', 'delta_krw':api-orig if api is not None and orig is not None else '',
     'status':st,'document_sha256':sha,'source_url':row.get('source_url',''),
     'note':'v9.4.1 exact receipt numeric only; report vintage and historical PIT not certified'})
 return results,dict(diag,parse_status=pstatus,archive_status='OK')


def receipt_verified(rows,receipt):
 rec=[r for r in rows if r.get('receipt_no')==receipt and r.get('metric') in {m[0] for m in old.METRICS}]
 return len(rec)==4 and {r['metric'] for r in rec}=={m[0] for m in old.METRICS} and all(r.get('status')=='EXACT_MATCH' for r in rec)


def run_verify(args,fin,cands,cal):
 out=Path(args.outdir)
 # Existing v9.4 COMPARED marker is intentionally untrusted.
 previous=old.read_csv(out/'v94_original_numeric_reconciliation.csv')
 records=old.read_csv(out/'v941_original_numeric_reconciliation.csv')
 state=read_json(out/'v941_original_attempts.json',{'attempts':[]})
 attempts=state['attempts'];counts={x['receipt_no']:x.get('attempt_count',0) for x in attempts}
 archive=old.read_archives_from_bundle(args.archive_bundle)
 src=old.choose_archives(fin,cands,args.ticker,100000)
 queue=[r for r in src if not receipt_verified(records,r['receipt_no']) and
        not receipt_verified(previous,r['receipt_no']) and counts.get(r['receipt_no'],0)<args.max_retries]
 selected=queue[:args.max_documents]
 key=os.getenv('OPENDART_API_KEY','').strip()
 if any(r['receipt_no'] not in archive for r in selected) and not old.KEY_RE.fullmatch(key):
  raise ValueError('OPENDART_API_KEY missing or malformed; no credentials printed')
 diagnostics=[]
 for r in selected:
  receipt=r['receipt_no'];diag={};comp=[]
  try:
   blob=archive[receipt] if receipt in archive else old.get_archive(key,receipt)
   comp,diag=compare_archive(r,blob,cal)
   status=('VERIFIED_ALL_FOUR' if receipt_verified(comp,receipt) else
      'NUMERIC_MISMATCH' if any(x['status']=='MISMATCH' for x in comp) else 'UNVERIFIED_RETRYABLE')
  except (ValueError,TimeoutError,urllib.error.URLError,zipfile.BadZipFile) as exc:
   status='FETCH_FAILED_RETRYABLE';diag={'failure_type':type(exc).__name__}
  if comp: records=[x for x in records if x.get('receipt_no')!=receipt]+comp
  attempts=[x for x in attempts if x['receipt_no']!=receipt]+[{'receipt_no':receipt,'ticker':r['ticker'],
           'status':status,'attempt_count':counts.get(receipt,0)+1}]
  diagnostics.append({'ticker':r['ticker'],'receipt_no':receipt,'status':status,'table_diagnostics':dict(diag)})
  if receipt not in archive:time.sleep(args.delay_seconds)
 dump_csv(out/'v941_original_numeric_reconciliation.csv',records,VERIFY_COLS)
 dump_json(out/'v941_original_attempts.json',{'attempts':attempts,'strict_pit_approved':False})
 dump_json(out/'v941_parser_diagnostics.json',{'documents':diagnostics,'note':'Only XBRL class IDs and parse status, no secret or full filing content'})
 return {'attempted_this_run':len(selected),'new_verified_all_four':sum(x['status']=='VERIFIED_ALL_FOUR' for x in diagnostics),
         'remaining_untried_or_retryable':max(0,len(queue)-len(selected)),
         'prior_v94_compared_zero_field_not_trusted':True,
         'statuses':dict(collections.Counter(x['status'] for x in diagnostics))}


def relevant_company_queue(fin,cands,ticker,asof):
 corp={r['ticker']:r['corp_code'] for r in fin if r.get('corp_code')}
 if ticker:
  if ticker not in corp:raise ValueError('Ticker has no company mapping')
  return [(ticker,corp[ticker],asof or date.today().isoformat())]
 # one chosen as-of date per ticker, not a survivor-selected later event date
 out=[]; seen=set()
 for c in cands:
  t=c['ticker']
  if t in corp and t not in seen:
   out.append((t,corp[t],c['signal_date']));seen.add(t)
 return out


def run_events(args,fin,cands,cal,client=None):
 out=Path(args.outdir);key=os.getenv('OPENDART_API_KEY','').strip()
 if client is None and not old.KEY_RE.fullmatch(key):raise ValueError('OPENDART_API_KEY unavailable')
 existing=old.read_csv(out/'v941_forward_event_leads.csv')
 # Migrate v9.4 title leads, recategorizing forecast vs historical actual (not a verified numeric signal).
 legacy=old.read_csv(out/'v94_forward_event_leads.csv')
 existing=unique_events([normalize_event(x,cal) for x in existing+legacy if x.get('first_usable_session') and x.get('signal_date')])
 state=read_json(out/'v941_event_collection_state.json',{'attempts':[]}); attempts=state['attempts']
 counter={(x['ticker'],x['signal_date']):int(x.get('attempt_count',0)) for x in attempts}
 done={(x['ticker'],x['signal_date']) for x in attempts if x['status']=='SUCCESS'}
 queue=[p for p in relevant_company_queue(fin,cands,args.ticker,args.asof)
        if (p[0],p[2]) not in done and counter.get((p[0],p[2]),0)<args.max_retries]
 chosen=queue[:args.max_companies]
 errors=[]; pages=0;added=[]
 for ticker,cc,signal in chosen:
  cutoff=date.fromisoformat(signal);begin=max(cutoff-timedelta(days=args.lookback_days),date(2015,1,1))
  p={'corp_code':cc,'bgn_de':begin.strftime('%Y%m%d'),'end_de':cutoff.strftime('%Y%m%d'),
     'last_reprt_at':'N','page_count':'100','sort':'date','sort_mth':'desc'}
  ok=True
  for i in range(1,args.max_pages+1):
   p['page_no']=str(i)
   try:
    data=client(cc,p) if client else v91.get_json(key,'list.json',p)
    pages+=1;stat=str(data.get('status',''))
    if stat=='013':break
    if stat!='000':raise RuntimeError('DART_STATUS_'+stat)
    for item in data.get('list',[]):
     rr=from_dart_list(item,ticker,signal,cal)
     if rr:added.append(rr)
    if i>=int(data.get('total_page','1')):break
    if i==args.max_pages:ok=False;errors.append({'ticker':ticker,'status':'INCOMPLETE_PAGINATION'})
   except (ValueError,RuntimeError,urllib.error.URLError,TimeoutError) as e:
    ok=False;errors.append({'ticker':ticker,'status':type(e).__name__});break
   time.sleep(args.delay_seconds)
  k=(ticker,signal)
  attempts=[a for a in attempts if (a['ticker'],a['signal_date'])!=k]
  attempts.append({'ticker':ticker,'signal_date':signal,'status':'SUCCESS' if ok else 'RETRYABLE',
                   'attempt_count':counter.get(k,0)+1})
  time.sleep(args.delay_seconds)
 final=unique_events(existing+added)
 dump_csv(out/'v941_forward_event_leads.csv',final,EV_COLS)
 dump_json(out/'v941_event_collection_state.json',{'attempts':attempts,'strict_pit_approved':False})
 return {'companies_this_run':len(chosen),'total_distinct_ticker_signal_queries_done':len(done|{(a['ticker'],a['signal_date']) for a in attempts if a['status']=='SUCCESS'}),
         'remaining_eligible_queries':len(queue)-len(chosen),'all_stored_events':len(final),
         'title_event_types':dict(collections.Counter(x['event_type'] for x in final)),
         'fresh_new_title_events':sum(x['freshness']=='FRESH_0_10_SESSIONS' and x['is_amendment']=='False' for x in final),
         'api_pages':pages,'warnings':errors}


def parse_document_event_evidence(xml,event):
 """Return transparent source-cell candidates, not trusted estimates or confirmed surprises.
 Only a uniquely unit-tagged table + unique exact label is eligible for a numeric candidate.
 """
 ev=event['event_type'];want=METRIC_LABELS.get(ev,{})
 if not want:return [],'NO_SUPPORTED_NUMERIC_FIELD'
 soup=BeautifulSoup(xml.decode('utf-8-sig','replace'),'html.parser')
 results=[]
 for metric,aliases in want.items():
  hits=[];ambig=0
  for table in soup.find_all('table'):
   # Unit must occur locally in the same table, never inherited from unrelated section.
   t=table.get_text(' ',strip=True)
   units={re.sub(r'\s+','',m) for m in RAW_UNIT_RE.findall(t[:1000])}
   if len(units)!=1:continue
   unit=next(iter(units));factor={'원':1,'천원':1000,'백만원':1000000,'억원':100000000}.get(unit)
   if factor is None:continue
   for tr in table.find_all('tr'):
    cells=tr.find_all(['td','th'],recursive=False)
    if len(cells)!=2:continue
    lab=old.textnorm(cells[0].get_text(' ',strip=True))
    if lab not in {old.textnorm(z) for z in aliases}:continue
    raw=cells[1].get_text(' ',strip=True)
    # Not percentage, ranged, amended mixed, decimal multiplier or descriptive estimate.
    integer=old.num_krw(raw)
    if integer is None:ambig+=1;continue
    hits.append((raw,integer*factor,unit))
  if len(hits)==1 and ambig==0:
   raw,value,unit=hits[0]
   status='RAW_UNVERIFIED_AMOUNT_CANDIDATE'
  else:
   raw=value=unit=''
   status='AMBIGUOUS_VALUES_OR_UNITS' if len(hits)>1 or ambig else 'NO_UNAMBIGUOUS_CELL'
  results.append({'ticker':event['ticker'],'signal_date':event['signal_date'],'receipt_no':event['receipt_no'],
          'event_type':ev,'report_name':event['report_name'],'metric':metric,'raw_value':raw,
          'value_krw':value,'unit':unit,'period':'',
          'evidence_status':status,'source_url':event['source_url'],
          'archive_sha256':'','note':'No filing vintage/period/counterparty confirmation; no revision score can be inferred'})
 return results,'EXTRACTED_CANDIDATES_ONLY'


def run_quantify(args,cal):
 out=Path(args.outdir);ev=old.read_csv(out/'v941_forward_event_leads.csv')
 if not ev:ev=[normalize_event(x,cal) for x in old.read_csv(out/'v94_forward_event_leads.csv')]
 # Don't treat the publication-day forecast as revised expectations; original text needed.
 existing=old.read_csv(out/'v941_event_numeric_candidates.csv')
 attempts=read_json(out/'v941_numeric_attempts.json',{'attempts':[]})['attempts']
 counts={a['receipt_no']:int(a.get('attempt_count',0)) for a in attempts}
 # quantifying a document cannot establish novelty if amended, or after signal
 src=[];seen=set()
 for x in sorted(ev,key=lambda x:(x.get('is_amendment')=='True',x.get('freshness')!='FRESH_0_10_SESSIONS',x['ticker'],x['receipt_no'])):
  if x['receipt_no'] in seen or x.get('asof_eligible')!='True':continue
  seen.add(x['receipt_no'])
  if x['event_type'] in METRIC_LABELS and counts.get(x['receipt_no'],0)<args.max_retries:
   src.append(x)
 src=src[:args.max_documents]
 key=os.getenv('OPENDART_API_KEY','').strip()
 if src and not old.KEY_RE.fullmatch(key):raise ValueError('OPENDART_API_KEY unavailable')
 details=[]
 for e in src:
  receipt=e['receipt_no']
  try:
   blob=old.get_archive(key,receipt);xml,st=old.read_original_archive(blob,receipt)
   if st!='OK':raise ValueError('Archive structure could not be verified')
   rows,st=parse_document_event_evidence(xml,e)
   for x in rows:x['archive_sha256']=hashlib.sha256(blob).hexdigest()
   existing=[x for x in existing if x['receipt_no']!=receipt]+rows
   outcome='RAW_CANDIDATE_ONLY' if any(x['evidence_status']=='RAW_UNVERIFIED_AMOUNT_CANDIDATE' for x in rows) else 'NO_UNIQUE_AMOUNT'
  except (ValueError,TimeoutError,urllib.error.URLError,zipfile.BadZipFile) as exc:
   outcome='FETCH_FAILED';st=type(exc).__name__
  attempts=[x for x in attempts if x['receipt_no']!=receipt]+[{'receipt_no':receipt,'status':outcome,'attempt_count':counts.get(receipt,0)+1}]
  details.append({'receipt_no':receipt,'status':outcome})
  time.sleep(args.delay_seconds)
 dump_csv(out/'v941_event_numeric_candidates.csv',existing,NUM_COLS)
 dump_json(out/'v941_numeric_attempts.json',{'attempts':attempts,'strict_pit_approved':False})
 return {'documents_queried':len(src),'candidate_amount_cells':sum(x['evidence_status']=='RAW_UNVERIFIED_AMOUNT_CANDIDATE' for x in existing),
         'verified_future_profit_revisions':0,'outcomes':dict(collections.Counter(x['status'] for x in details)),
         'warning':'Even a detected amount is raw unverified, not a future profit revision'}


def main(argv=None):
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--mode',choices=['plan','verify','events','quantify'],default='plan')
 ap.add_argument('--financial',default='reports/v93_financial_calendar_adjusted_provisional.csv')
 ap.add_argument('--candidate-file',default='config/v94_signal_candidates_reference.csv')
 ap.add_argument('--ticker',default='');ap.add_argument('--asof',default='')
 ap.add_argument('--outdir',default='reports')
 ap.add_argument('--archive-bundle',default=None)
 ap.add_argument('--max-documents',type=int,default=6);ap.add_argument('--max-companies',type=int,default=12)
 ap.add_argument('--max-pages',type=int,default=5);ap.add_argument('--lookback-days',type=int,default=180)
 ap.add_argument('--max-retries',type=int,default=2);ap.add_argument('--delay-seconds',type=float,default=0.3)
 args=ap.parse_args(argv)
 if args.ticker and not re.fullmatch(r'\d{6}',args.ticker):ap.error('Ticker must be 6 digits')
 if args.asof:
  try:day=date.fromisoformat(args.asof)
  except ValueError:ap.error('Use YYYY-MM-DD asof')
  if day>date.today():ap.error('Future asof is not supported')
 if not 1<=args.max_documents<=12 or not 1<=args.max_companies<=30 or not 1<=args.max_pages<=10 or not 30<=args.lookback_days<=365 or not 1<=args.max_retries<=3 or not 0<=args.delay_seconds<=5:
  ap.error('Invalid bounded batch arguments')
 out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
 cal=xcals.get_calendar('XKRX')
 fin=old.read_csv(Path(args.financial))
 cand=old.read_csv(Path(args.candidate_file))
 if not fin or not cand:raise SystemExit('Required financial and chart signals are missing; no synthetic defaults')
 prioritized=old.recent_candidates(cand,fin,limit=2000)
 summary={'version':'9.4.1-conservative-evidence','mode':args.mode,
          'strict_pit_approved':False,'provisional_only':True,'historical_universe_complete':False,
          'financial_rows':len(fin),'candidates':len(cand),'candidate_receipts':len(prioritized),
          'known_limitations':['No historical analyst consensus dataset','Current API may include restatement',
             'PIT sector membership not verified','Raw document numbers do not prove future earnings revisions']}
 if args.mode=='plan':
  ev=old.read_csv(out/'v94_forward_event_leads.csv')
  prior=old.read_csv(out/'v941_forward_event_leads.csv')
  rows=[normalize_event(x,cal) for x in ev+prior]
  dump_csv(out/'v941_forward_event_leads.csv',unique_events(rows),EV_COLS)
  summary['preview']={'legacy_event_leads_reclassified':len(ev),
    'total_distinct_leads_after_merge':len(unique_events(rows)),
    'types':dict(collections.Counter(r['event_type'] for r in unique_events(rows))),
    'eligible_candidates':len(prioritized),'max_companies_per_run':args.max_companies}
 elif args.mode=='verify':summary['verify']=run_verify(args,fin,prioritized,cal)
 elif args.mode=='events':summary['events']=run_events(args,fin,prioritized,cal)
 else:summary['quantify']=run_quantify(args,cal)
 dump_json(out/'v941_research_summary.json',summary)
 print(json.dumps(summary,ensure_ascii=False))
 return summary

if __name__=='__main__':main()
