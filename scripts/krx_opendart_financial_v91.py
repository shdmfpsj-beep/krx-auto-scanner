#!/usr/bin/env python3
"""OpenDART 9.1: incremental historical financial filing collection, research ONLY.

Important: OpenDART financial APIs may expose the latest normalized/restated values.
This program explicitly writes PROVISIONAL, never v90's verified/PIT input file.
No trading decisions or simulated performance are authorized by its output.
"""
from __future__ import annotations
import argparse
import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta
from pathlib import Path

ROOT = 'https://opendart.fss.or.kr/api/'
SCHEMA = ['ticker','corp_code','filing_date','available_date','report_year','report_code',
          'receipt_no','fs_div','revenue_yoy_pct','op_profit_yoy_pct','op_margin_pct',
          'debt_ratio_pct','revenue_amount_krw','op_profit_amount_krw','liabilities_amount_krw',
          'equity_amount_krw','source_url','validation_status']
AUDIT_COLS = ['ticker','year','report_code','filing_date','receipt_no','status','details']
REPORT_CODES = {'분기보고서': '11013', '반기보고서': '11012', '사업보고서': '11011'}

# These are *only* public, non-sensitive status descriptions. Never print API URLs or the key.
SAFE_DART_STATUS = {
    '010': '미등록 인증키: OpenDART 인증키를 다시 확인하세요.',
    '011': '사용 불가 인증키: 승인/활성화 상태를 확인하세요.',
    '012': '접근 불가 IP: OpenDART 사용 환경/IP 제한을 확인하세요.',
    '013': '조회 자료 없음',
    '014': '자료 파일 없음',
    '020': '요청 제한 초과: 나중에 재실행하세요.',
    '021': '조회 기업 수 제한 초과',
    '100': 'API 입력값 오류',
    '101': '접근 권한 오류',
    '800': 'OpenDART 점검 중: 이후 재실행하세요.',
    '900': 'OpenDART 서버 오류',
    '901': '인증키 만료: OpenDART 계정 상태를 확인하세요.',
}


def safe_dart_status(raw):
    """Extract only a 3-digit DART status from non-ZIP API error bodies."""
    try:
        root=ET.fromstring(raw)
        status=(root.findtext('.//status') or '').strip()
    except (ET.ParseError, TypeError):
        try:
            status=str(json.loads(raw).get('status','')).strip()
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError, TypeError):
            status=''
    return status if re.fullmatch(r'\d{3}', status) else None



def atomic_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    with temp.open('w', encoding='utf-8-sig', newline='') as file:
        writer=csv.DictWriter(file, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)
    temp.replace(path)


def atomic_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


def read_csv(path):
    if not path.exists():return []
    with path.open(encoding='utf-8-sig', newline='') as f:return list(csv.DictReader(f))


def cash(s):
    if s is None:return None
    val=str(s).replace(',','').replace(' ','').strip()
    if val in ('','-','N/A','null'):return None
    try:return int(val.strip('()')) * (-1 if val.startswith('(') and val.endswith(')') else 1)
    except ValueError:return None


def next_calendar_day(d):
    # Conservative; prevents using a disclosure on the filing day's closing signal.
    return (date.fromisoformat(d)+timedelta(days=1)).isoformat()


def get_json(key, name, params, fetch=None):
    params={'crtfc_key':key,**params}
    url=ROOT+name+'?'+urllib.parse.urlencode(params)
    if fetch is None:
        req=urllib.request.Request(url,headers={'User-Agent':'KRX-Financial-PIT-Research/9.1'})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req,timeout=30) as f: body=f.read()
                break
            except (urllib.error.URLError, TimeoutError):
                if attempt==2: raise
                time.sleep(1.5*(attempt+1))
    else:
        body=fetch(name,params)
    if isinstance(body,dict):res=body
    else:res=json.loads(body)
    status=str(res.get('status',''))
    if status not in ('000','013'):
        # Never put the URL, which contains the secret key, into logs/errors.
        safe=status if re.fullmatch(r'\d{3}',status) else 'UNKNOWN'
        description=SAFE_DART_STATUS.get(safe,'API 오류')
        raise RuntimeError(f'OpenDART {name}: status={safe} ({description})')
    return res


def get_corp_codes(key, fetch=None):
    if fetch is None:
        req=urllib.request.Request(ROOT+'corpCode.xml?'+urllib.parse.urlencode({'crtfc_key':key}),
                                  headers={'User-Agent':'KRX-Financial-PIT-Research/9.1'})
        with urllib.request.urlopen(req,timeout=60) as res:data=res.read()
    else:data=fetch('corpCode.xml',{'crtfc_key':key})
    if not zipfile.is_zipfile(io.BytesIO(data)):
        status=safe_dart_status(data[:16384])
        if status:
            raise RuntimeError(f'corpCode.xml: status={status} ({SAFE_DART_STATUS.get(status,"API 오류")})')
        raise RuntimeError('corpCode.xml: ZIP이 아닌 응답입니다. OpenDART 인증 및 서비스 상태를 확인하세요.')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml_file=next((s for s in z.namelist() if s.lower().endswith('.xml')),None)
        if not xml_file:raise RuntimeError('Missing CORPCODE.xml inside ZIP')
        root=ET.fromstring(z.read(xml_file))
    out={}
    for item in root.findall('.//list'):
        t=(item.findtext('stock_code') or '').strip(); corp=(item.findtext('corp_code') or '').strip()
        if re.fullmatch(r'\d{6}',t) and re.fullmatch(r'\d{8}',corp):out[t]=corp
    return out


def parse_original_filings(items,year):
    """Only original report submissions. Amendments never replace original vintage."""
    out={}
    for r in items:
        nm=(r.get('report_nm') or '').strip()
        if not nm or nm.startswith('['):continue
        rep=next((v for k,v in REPORT_CODES.items() if nm.startswith(k+' (') or nm.startswith(k+'(')),None)
        if not rep:continue
        m=re.search(r'\((\d{4})\.(\d{2})\)',nm)
        if not m or int(m.group(1))!=year:continue
        mon=int(m.group(2))
        if rep=='11013':
            if mon not in (3,9):continue
            if mon==9:rep='11014'
        elif rep=='11012' and mon!=6:continue
        elif rep=='11011' and mon!=12:continue
        receipt=str(r.get('rcept_no','')); day=str(r.get('rcept_dt',''))
        if not re.fullmatch(r'\d{14}',receipt) or not re.fullmatch(r'\d{8}',day):continue
        iso=f'{day[:4]}-{day[4:6]}-{day[6:]}'
        try: date.fromisoformat(iso)
        except ValueError:continue
        key=(year,rep)
        if key not in out or receipt<out[key]['receipt_no']:
            out[key]={'receipt_no':receipt,'filing_date':iso,'report_code':rep,'year':year}
    return sorted(out.values(),key=lambda x:(x['filing_date'],x['receipt_no']))


def pick_account(rows,names,ids,fs_type,kind):
    rows=[x for x in rows if x.get('sj_div') in (('BS',) if kind=='bs' else ('IS','CIS')) and
          (not x.get('fs_div') or x['fs_div']==fs_type) and
          (not x.get('account_detail') or x.get('account_detail')=='-')]
    idrows=[]
    for x in rows:
        ai=(x.get('account_id') or '').strip().lower()
        if ai in ids:idrows.append(x)
    if len(idrows)==1:return idrows[0]
    if len(idrows)>1:
        for x in idrows:
            if x.get('sj_div')=='IS':return x
        return None
    exact=[x for x in rows if (x.get('account_nm') or '').replace(' ','') in names]
    if len(exact)==1:return exact[0]
    return None


def ratio(cur,prev):
    # yoy % is not meaningful if prior revenue/profit <= 0.
    if cur is None or prev is None or prev<=0:return None
    return 100*(cur/prev-1)


def build_metrics(rows, year, report_code, fs_div, filing):
    rev=pick_account(rows,{'매출액','매출','수익(매출액)','영업수익'},
                     {'ifrs-full_revenue','ifrs_revenue','ifrs-full_revenuefromcontractswithcustomers'},fs_div,'is')
    op=pick_account(rows,{'영업이익','영업이익(손실)','영업손실'},
                    {'dart_operatingincomeloss','ifrs-full_profitlossfromoperatingactivities'},fs_div,'is')
    liabilities=pick_account(rows,{'부채총계'}, {'ifrs-full_liabilities','ifrs_liabilities'},fs_div,'bs')
    equity=pick_account(rows,{'자본총계'}, {'ifrs-full_equity','ifrs_equity'},fs_div,'bs')
    if any(x is None for x in (rev,op,liabilities,equity)):return None,'MISSING_ACCOUNT'
    annual=report_code=='11011'
    def amounts(x):
        # For interim reports: 3-month thstrm_amount vs YTD thstrm_add_amount.
        # Use *matching YTD periods* for both current/prior-year, not mixed 3-month/YTD.
        if annual: return cash(x.get('thstrm_amount')),cash(x.get('frmtrm_amount'))
        cur=cash(x.get('thstrm_add_amount')); prev=cash(x.get('frmtrm_add_amount'))
        if report_code=='11013':
            # Q1 YTD is identical to the quarter; add_amount can legitimately be blank.
            if cur is None:cur=cash(x.get('thstrm_amount'))
            if prev is None:prev=cash(x.get('frmtrm_q_amount'))
        return cur,prev
    cr,pr=amounts(rev); co,po=amounts(op)
    li=cash(liabilities.get('thstrm_amount')); eq=cash(equity.get('thstrm_amount'))
    if None in (cr,pr,co,po,li,eq) or cr<=0 or eq<=0:
        return None,'MISSING_OR_INVALID_FINANCIAL_AMOUNT'
    # No mixed currencies, never assume amounts in USD/other currency are KRW.
    records=[rev,op,liabilities,equity]
    if any((r.get('currency') or 'KRW').upper() not in ('KRW','원') for r in records):return None,'NON_KRW'
    ry=ratio(cr,pr); oy=ratio(co,po)
    if ry is None or oy is None:return None,'NONCOMPARABLE_PREVIOUS_YEAR'
    return {'revenue_yoy_pct':round(ry,4),'op_profit_yoy_pct':round(oy,4),
            'op_margin_pct':round(100*co/cr,4),'debt_ratio_pct':round(100*li/eq,4),
            'revenue_amount_krw':cr,'op_profit_amount_krw':co,
            'liabilities_amount_krw':li,'equity_amount_krw':eq},'OK'


def tickers_from_cache(folder):
    path=Path(folder)
    if not path.exists():raise FileNotFoundError(f'Missing price cache dir: {folder}')
    return sorted({p.stem for p in path.glob('*.csv') if re.fullmatch(r'\d{6}',p.stem)})


def collect(args, getj=get_json, getcodes=get_corp_codes, fetch=None):
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    provisional=out/'v91_financial_pit_provisional.csv'
    auditfile=out/'v91_financial_collection_audit.csv'
    progressfile=out/'v91_financial_collection_state.json'
    existing=read_csv(provisional); audit=read_csv(auditfile)
    completed=set(); last_checked={}
    if progressfile.exists():
        prior_state=json.loads(progressfile.read_text(encoding='utf-8'))
        completed=set(prior_state.get('completed_tickers',[]))
        last_checked=prior_state.get('last_checked_dates',{})
    targets=tickers_from_cache(args.cache_dir)
    if args.tickers:targets=[t for t in targets if t in set(args.tickers)]
    # Refresh older companies after 28 days so new quarterly reports are not missed.
    cutoff=date.today()-timedelta(days=args.refresh_days)
    todo=[t for t in targets if t not in completed]
    refresh=[t for t in targets if t in completed and (not last_checked.get(t) or date.fromisoformat(last_checked[t])<=cutoff)]
    selected=(todo+refresh)[:args.max_tickers]
    base={'version':'9.1','research_only':True,'strict_pit_approved':False,
          'source_status':'API_SNAPSHOT_NOT_ARCHIVED_ORIGINAL','mode':'dry-run' if args.dry_run else 'collect',
          'target_universe_size':len(targets),'selected_tickers':selected,
          'prior_completed_tickers':len(completed),'warnings':[
              'OpenDART API latest historical financial snapshots may include later corrections.',
              'Provisional data MUST NOT be substituted for config/v90_financial_pit.csv.',
              'Sector PIT file is not populated by this collector.',
              'No point-in-time survivorship-free universe or real trading approval.']}
    if args.dry_run:
        atomic_json(out/'v91_financial_collection_status.json',base)
        return base
    key=os.environ.get('OPENDART_API_KEY','').strip()
    if len(key)!=40:
        raise RuntimeError(f'OPENDART_API_KEY 형식 오류: 40자가 필요하지만 {len(key)}자입니다. '
                           '인증키 문자열만 복사하고 따옴표·설명문·공백은 제외하세요.')
    corp_map=getcodes(key,fetch=fetch)
    index={(x.get('ticker'),x.get('receipt_no'),x.get('fs_div')):x for x in existing}
    hard_errors=[]
    for ticker in selected:
        cc=corp_map.get(ticker)
        if not cc:
            audit.append({'ticker':ticker,'status':'NO_CORP_MAPPING','details':'Not in current OpenDART listed-company map'})
            completed.add(ticker);continue
        failed=False
        for year in args.years:
            try:
                found=getj(key,'list.json',{'corp_code':cc,'bgn_de':f'{year}0101',
                           'end_de':f'{min(year+1,date.today().year)}0630' if year<date.today().year else date.today().strftime('%Y%m%d'),
                           'pblntf_ty':'A','last_reprt_at':'N','page_count':'100'},fetch=fetch)
                if str(found.get('status'))=='013':reports=[]
                else:
                    # Simple users (max 6 tickers) do not want silent truncation.
                    if int(found.get('total_page',1))>1:raise RuntimeError('Listing has more than one page; do not silently truncate')
                    reports=parse_original_filings(found.get('list',[]),year)
                for fil in reports:
                    info=fil.copy(); info['ticker']=ticker
                    for fs in ('CFS','OFS'):
                        data=getj(key,'fnlttSinglAcntAll.json',{'corp_code':cc,'bsns_year':str(year),
                              'reprt_code':fil['report_code'],'fs_div':fs},fetch=fetch)
                        if str(data.get('status'))=='013':continue
                        rows=data.get('list',[])
                        receipts=set(str(r.get('rcept_no','')) for r in rows if r.get('rcept_no'))
                        if receipts!={fil['receipt_no']}:
                            audit.append({**info,'status':'RECEIPT_MISMATCH','details':f'fs={fs}: latest API figures not original receipt'})
                            continue
                        metric,why=build_metrics(rows,year,fil['report_code'],fs,fil)
                        if metric is None:
                            audit.append({**info,'status':why,'details':f'fs={fs}'})
                            continue
                        rec={'ticker':ticker,'corp_code':cc,'filing_date':fil['filing_date'],
                             'available_date':next_calendar_day(fil['filing_date']),
                             'report_year':year,'report_code':fil['report_code'],
                             'receipt_no':fil['receipt_no'],'fs_div':fs,
                             'source_url':'https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+fil['receipt_no'],
                             'validation_status':'PROVISIONAL_API_SNAPSHOT_NOT_PIT_VERIFIED',**metric}
                        index[(ticker,fil['receipt_no'],fs)]=rec
                        audit.append({**info,'status':'PROVISIONAL_SAVED','details':f'fs={fs}; original numbers NOT archived/verified'})
                        break
                    else:
                        audit.append({**info,'status':'NO_VERIFIABLE_ACCOUNTS','details':'CFS/OFS missing or mismatched; no invented values'})
            except (RuntimeError,urllib.error.URLError,TimeoutError,ValueError) as e:
                # Explicit allowlist only: never leak URLs, secrets or API response bodies.
                message=str(e) if isinstance(e,RuntimeError) else ''
                if not message.startswith(('OpenDART ', 'corpCode.xml:', 'OPENDART_API_KEY 형식 오류:')):
                    message=type(e).__name__
                audit.append({'ticker':ticker,'year':year,'status':'REQUEST_FAILED','details':message})
                hard_errors.append({'ticker':ticker,'year':year,'error_type':type(e).__name__,'safe_detail':message})
                print(f'Financial API request failed: ticker={ticker}, year={year}, reason={message}',file=sys.stderr)
                failed=True;break
        if not failed:
            completed.add(ticker)
            last_checked[ticker]=date.today().isoformat()
        # Incremental persistence: even partial successful tickers aren't lost.
        atomic_csv(provisional,sorted(index.values(),key=lambda x:(x['ticker'],x['filing_date'],x['receipt_no'])),SCHEMA)
        atomic_csv(auditfile,audit,AUDIT_COLS)
        atomic_json(progressfile,{'completed_tickers':sorted(completed),'last_checked_dates':last_checked,'last_run_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()})
    base.update({'total_provisional_rows':len(index),'newly_completed_tickers':len(completed)-base['prior_completed_tickers'],
                 'incomplete_tickers':len(targets)-len(completed),'errors':hard_errors,
                 'financial_file':str(provisional),'sector_pit_status':'NOT_POPULATED',
                 'strict_pit_approved':False})
    atomic_json(out/'v91_financial_collection_status.json',base)
    return base


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cache-dir',default='reports/v36_ohlcv_cache')
    ap.add_argument('--outdir',default='reports')
    ap.add_argument('--years',type=int,nargs='+',default=[2023,2024,2025,2026])
    ap.add_argument('--max-tickers',type=int,default=12)
    ap.add_argument('--refresh-days',type=int,default=28)
    ap.add_argument('--tickers',nargs='*')
    ap.add_argument('--dry-run',action='store_true')
    a=ap.parse_args()
    if not (1<=a.max_tickers<=50):ap.error('max-tickers must be between 1 and 50')
    if not (7<=a.refresh_days<=365):ap.error('refresh-days must be 7-365')
    if any(y<2015 or y>date.today().year for y in a.years):ap.error('invalid year')
    if a.tickers and any(not re.fullmatch(r'\d{6}',t) for t in a.tickers):ap.error('bad ticker')
    try:
        status=collect(a)
    except Exception as e:
        # Never print str(HTTPError/URLError): their URL may contain the secret.
        if isinstance(e, RuntimeError):
            msg=str(e)
            if msg.startswith(('OPENDART_API_KEY 형식 오류:', 'corpCode.xml:', 'OpenDART ')):
                print('Collection failed:',msg,file=sys.stderr)
            else:
                print('Collection failed: RuntimeError (세부 원인 별도 확인 필요)',file=sys.stderr)
        elif isinstance(e, urllib.error.HTTPError):
            print('Collection failed: OpenDART HTTP 상태',e.code,'(주소와 키는 숨김)',file=sys.stderr)
        elif isinstance(e, (urllib.error.URLError,TimeoutError)):
            print('Collection failed: OpenDART 네트워크 연결/시간 초과 (키 숨김)',file=sys.stderr)
        else:
            print('Collection failed:',type(e).__name__,'(키 숨김)',file=sys.stderr)
        sys.exit(1)
    print(json.dumps(status,ensure_ascii=False))

if __name__=='__main__':main()
