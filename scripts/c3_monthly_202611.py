"""Single fixed November analysis. Production files, orders and sends are read-only."""
import argparse
import ast
import collections
import contextlib
import csv
import datetime
import gzip
import hashlib
import io
import json
import math
import os
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xc
import dart_financial_screen as finance
from c3_top5_dart_bridge import bridge
from c3_top5_financial_selection import requested_candidates, select
from c3_monthly_xbrl import parse_archive, payload_for

PIN = '5aa4a5f330a92a70b7f1a907f1e02b2198b6a952'
START, END = '20261102', '20261120'
KST = ZoneInfo('Asia/Seoul')
REPO = Path(__file__).resolve().parents[1]
PRODUCTION = ['.github/workflows/c3_top5_daily_telegram.yml',
    'scripts/c3_top5_financial_selection.py', 'scripts/c3_top5_dart_bridge.py',
    'scripts/dart_financial_screen.py', 'scripts/dart_interim_periods.py',
    'scripts/c3_top5_session_policy.py']

def sha(data):
    return hashlib.sha256(data).hexdigest()

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def code_nodes():
    lines = (REPO/PRODUCTION[0]).read_text().splitlines()
    step = next(i for i, v in enumerate(lines) if v.strip() ==
                '- name: Collect KRX sessions and render one classic image per stock')
    begin = next(i for i in range(step+1, len(lines)) if " - <<'PY'" in lines[i])+1
    end = next(i for i in range(begin, len(lines)) if lines[i].strip() == 'PY')
    tree = ast.parse('\n'.join(v[10:] for v in lines[begin:end]))
    fetch = next(v for v in ast.walk(tree) if isinstance(v, ast.FunctionDef) and v.name == 'fetch')
    number = next(v for v in ast.walk(tree) if isinstance(v, ast.FunctionDef) and v.name == 'num')
    ingest = next(v for v in ast.walk(tree) if isinstance(v, ast.For) and
        isinstance(v.target, ast.Name) and v.target.id == 'r' and
        isinstance(v.iter, ast.Name) and v.iter.id == 'rows')
    block = next(v for v in tree.body if isinstance(v, ast.Try)).body
    a = next(i for i,v in enumerate(block) if isinstance(v,ast.Assign) and
             any(isinstance(t,ast.Name) and t.id=='bench' for t in v.targets))
    b = next(i for i in range(a,len(block)) if isinstance(block[i],ast.Assign) and
             ast.unparse(block[i].targets[0])=="receipt['stage']" and
             isinstance(block[i].value,ast.Constant) and block[i].value.value=='IMAGE_GENERATION')
    compile_nodes = lambda values: compile(ast.Module(body=values, type_ignores=[]), '<PINNED_MAIN>', 'exec')
    return compile_nodes([fetch,number]), compile_nodes([ingest]), compile_nodes(block[a:b])

def base_namespace():
    return dict(os=os,json=json,urllib=urllib,time=time,math=math,csv=csv,io=io,
        datetime=datetime,collections=collections,statistics=statistics,
        hashlib=hashlib,Path=Path,ZoneInfo=ZoneInfo)

class Sources:
    def __init__(self, root, nodes):
        self.root=root;self.key=os.environ.get('DART_API_KEY','')
        self.manifest=[];self.filing_cache={};self.archive_cache={}
        self.namespace=base_namespace()
        exec(nodes[0],self.namespace)

    def http(self, endpoint, params, binary=False):
        url='https://opendart.fss.or.kr/api/'+endpoint+'?'+urllib.parse.urlencode(
            dict(params,crtfc_key=self.key))
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url,timeout=45) as response:
                    data=response.read(80_000_001)
                if len(data)>80_000_000:raise ValueError('DART_RESPONSE_LIMIT')
                return data if binary else json.loads(data)
            except (urllib.error.URLError,TimeoutError,json.JSONDecodeError):
                if attempt==2:raise ValueError('DART_REQUEST_FAILED') from None
                time.sleep(2*(attempt+1))

    def market(self, day, endpoint):
        path=self.root/'source/krx'/f'{day}_{endpoint}.json.gz'
        if path.exists():
            with gzip.open(path,'rt') as f:return json.load(f)
        rows=self.namespace['fetch'](day,endpoint)
        data=json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode()
        path.parent.mkdir(parents=True,exist_ok=True)
        with gzip.open(path,'wb') as f:f.write(data)
        self.manifest.append(dict(type='KRX',day=day,endpoint=endpoint,
            file=str(path.relative_to(self.root)),sha256=sha(data),rows=len(rows)))
        return rows

    def corporations(self):
        path=self.root/'source/dart/corporations.zip'
        if not path.exists():
            raw=self.http('corpCode.xml',{},True);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        return finance.parse_corps(path.read_bytes())

    def filings(self, corp):
        if corp in self.filing_cache:return self.filing_cache[corp]
        path=self.root/'source/dart'/f'{corp}_filings.json'
        if path.exists():payload=json.loads(path.read_text())
        else:
            values=[]
            for page in range(1,21):
                p=self.http('list.json',dict(corp_code=corp,bgn_de='20240101',
                    end_de=END,pblntf_ty='A',page_count=100,page_no=page,last_reprt_at='N'))
                if p.get('status')=='013':break
                if p.get('status')!='000':raise ValueError('DART_FILINGS_UNAVAILABLE')
                values.extend(p.get('list',[]))
                if page>=int(p.get('total_page',1)):break
            else:raise ValueError('DART_FILINGS_PAGE_LIMIT')
            payload=dict(status='000',list=values);write_json(path,payload)
        self.filing_cache[corp]=payload
        return payload

    def receipt(self, corpus, year, report, cutoff):
        payload=self.filings(corpus)
        filtered=dict(status='000',list=[r for r in payload['list'] if r.get('rcept_dt','')<=cutoff.strftime('%Y%m%d')])
        if report=='11011':
            result=finance.annual_receipt(filtered,year,cutoff)
            return result[1] if result else None
        found=[]
        for r in filtered['list']:
            when=finance.iso_day(r.get('rcept_dt'))
            f=finance.latest_interim_filing(dict(status='000',list=[r]),cutoff)
            if f and f['fiscal_year']==year and f['report_code']==report:
                found.append((when,r['rcept_no']))
        return max(found)[1] if found else None

    def original_payload(self, corp, year, report, scope, cutoff):
        receipt=self.receipt(corp,year,report,cutoff)
        if not receipt:return dict(status='013',list=[])
        assert receipt[:8]<=cutoff.strftime('%Y%m%d')
        cache_key=(receipt,report)
        if cache_key not in self.archive_cache:
            path=self.root/'source/dart/originals'/f'{receipt}_{report}.zip'
            if not path.exists():
                raw=self.http('fnlttXbrl.xml',dict(rcept_no=receipt,reprt_code=report),True)
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            raw=path.read_bytes()
            try:
                facts,diagnostics=parse_archive(raw)
                diagnostics.update(receipt=receipt,report_code=report,corp_code=corp,sha256=sha(raw))
                write_json(path.with_suffix('.diagnostics.json'),diagnostics)
                self.archive_cache[cache_key]=facts
            except (ValueError,ET_PARSE_ERROR) as error:
                write_json(path.with_suffix('.diagnostics.json'),dict(receipt=receipt,
                    status=type(error).__name__,reason=str(error)[:100],sha256=sha(raw)))
                self.archive_cache[cache_key]={}
        payload=payload_for(self.archive_cache[cache_key],year,report,scope,receipt)
        write_json(self.root/'source/dart/adapted'/f'{receipt}_{report}_{scope}.json',payload)
        return payload

    def financial_gate(self, day, requested, corps):
        cutoff=datetime.datetime.strptime(day,'%Y%m%d').date()
        def request(endpoint,params,key):
            if endpoint=='list.json':
                p=self.filings(params['corp_code'])
                return dict(status='000',list=[r for r in p['list'] if r.get('rcept_dt','')<=day])
            if endpoint!='fnlttSinglAcntAll.json':raise ValueError('UNEXPECTED_FINANCIAL_ENDPOINT')
            return self.original_payload(params['corp_code'],int(params['bsns_year']),
                                         params['reprt_code'],params['fs_div'],cutoff)
        def original_collector(observed,stocks,key,today):
            # Only the core's logical replay clock is simulated. Every number
            # comes from a fixed original receipt <= cutoff, never today's JSON.
            result=finance.collect(cutoff,stocks,key,today=cutoff,
                                   request_json=request,get_corps=lambda key:corps)
            write_json(self.root/'replay'/day/'original_financial_research.json',result)
            return result
        return bridge(dict(asof=day,candidates=[dict(code=c['code'],name=c.get('name','')) for c in requested]),
            self.key,today=datetime.datetime.now(KST).date(),collector=original_collector)

from xml.etree.ElementTree import ParseError as ET_PARSE_ERROR

def technical(day, window, source, nodes, calendar, root):
    target=root/'replay'/day;target.mkdir(parents=True,exist_ok=True)
    ns=base_namespace();exec(nodes[0],ns)
    ns.update(data=collections.defaultdict(dict),names={},rejected_rows=collections.Counter(),
              dated_rows_checked=0,days=window,root=target)
    coverage=[]
    for ds in reversed(window):
        counts={}
        for market,endpoint in [('KOSPI','stk_bydd_trd'),('KOSDAQ','ksq_bydd_trd')]:
            rows=source.market(ds,endpoint);counts[market]=len(rows)
            if len(rows)<(500 if market=='KOSPI' else 800):raise ValueError('KRX_MARKET_COVERAGE_'+ds)
            ns.update(ds=ds,market=market,rows=rows);exec(nodes[1],ns)
        coverage.append(dict(date=ds,**counts))
    ns['receipt']=dict(asof=day,source_integrity=dict(session_count=60,last_session=day,
        market_rows_min={m:min(c[m] for c in coverage) for m in ('KOSPI','KOSDAQ')},
        reported_date_rows_checked=ns['dated_rows_checked'],duplicate_valid_rows=0))
    next_session=calendar.next_session(day)
    ns['plan']=dict(entry_valid_until=calendar.session_close(next_session).tz_convert('Asia/Seoul').isoformat())
    with contextlib.redirect_stdout(io.StringIO()):exec(nodes[2],ns)
    write_json(target/'price_receipt.json',ns['receipt'])
    geometry=json.loads((target/'entry_geometry_audit.json').read_text())
    pool=json.loads((target/'qualified_chart_pool.json').read_text())
    return geometry,pool

def evaluate_trade(signal, sessions, quotes, cutoff=END):
    row=dict(signal);row.update(fill_status='PASS',fill_date='',fill_price=None,
        exit_date='',exit_price=None,highest_return_pct=None,current_return_pct=None,
        highest_day='',possible_highest_return_pct=None,possible_highest_day='',
        sequence_uncertain=False,peak_uncertain=False,adjustment_warning=False)
    following=[d for d in sessions if d>signal['signal_date']]
    if not following or following[0]>cutoff:
        row['fill_status']='PENDING_AFTER_EVALUATION';return row
    first=following[0];key=signal['code'];bar=quotes.get((first,key))
    if bar is None:row['fill_status']='PRICE_DATA_MISSING';return row
    lo,hi,stop=signal['entry_low'],signal['entry_high'],signal['stop_ref']
    opening,high,low,close=(bar[k] for k in ('open','high','low','close'))
    if opening<=stop:row['fill_status']='PASS_GAP_BELOW_STOP';return row
    if high<lo or low>hi:return row
    price=opening if lo<=opening<=hi else hi if opening>hi else lo
    row.update(fill_status='FILLED',fill_date=first,fill_price=price)
    row['sequence_uncertain']=bool(opening<lo and low<=stop)
    lower=upper=price;lower_day=upper_day=first
    previous=quotes.get((signal['signal_date'],key),{}).get('close')
    for day in following:
        if day>cutoff:break
        b=quotes.get((day,key))
        if b is None:row['fill_status']='PRICE_DATA_MISSING_AFTER_FILL';return row
        o,h,l,c=(b[k] for k in ('open','high','low','close'))
        if previous is not None and abs(c/previous-1)>.35:row['adjustment_warning']=True
        previous=c
        if day!=first and o<=stop:
            row.update(fill_status='STOPPED',exit_date=day,exit_price=o);break
        stopped=l<=stop
        if stopped:
            attainable=price if day==first else max(price,o)
            if attainable>lower:lower,lower_day=attainable,day
            if h>upper:upper,upper_day=h,day
            row.update(fill_status='STOPPED',exit_date=day,exit_price=stop)
            break
        certain_high=(day!=first or lo<=opening<=hi or opening<lo)
        attainable=h if certain_high else max(price,c)
        if attainable>lower:lower,lower_day=attainable,day
        if h>upper:upper,upper_day=h,day
    final=quotes.get((cutoff,key))
    if final is None:row['fill_status']='EVALUATION_CLOSE_MISSING';return row
    current=row['exit_price'] if row['exit_price'] is not None else final['close']
    row.update(highest_return_pct=round((lower/price-1)*100,4),highest_day=lower_day,
        possible_highest_return_pct=round((upper/price-1)*100,4),possible_highest_day=upper_day,
        peak_uncertain=(upper!=lower),current_return_pct=round((current/price-1)*100,4),
        evaluation_close=final['close'],reference_close_return_pct=round((final['close']/price-1)*100,4))
    return row

def csv_file(path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)

def actual_signals(root):
    token=os.environ.get('GH_TOKEN','');repo=os.environ.get('GITHUB_REPOSITORY','shdmfpsj-beep/krx-auto-scanner')
    def get(path,binary=False):
        req=urllib.request.Request('https://api.github.com/repos/'+repo+'/'+path,
            headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'})
        with urllib.request.urlopen(req,timeout=45) as r:data=r.read(30_000_001)
        return data if binary else json.loads(data)
    results=[]
    try:
        runs=get('actions/workflows/420918398/runs?event=schedule&per_page=100')['workflow_runs']
        runs=[r for r in runs if '2026-11-02'<=r['created_at'][:10]<='2026-11-21']
        for run in runs:
            meta=dict(run_id=run['id'],event=run['event'],commit=run['head_sha'],
                      workflow_conclusion=run['conclusion'],run_url=run['html_url'])
            arts=get(f"actions/runs/{run['id']}/artifacts")['artifacts']
            artifact=next((a for a in arts if a['name']=='c3-top5-daily-classic-per-stock' and not a['expired']),None)
            if not artifact:results.append(dict(meta,status='ARTIFACT_UNAVAILABLE'));continue
            raw=get(f"actions/artifacts/{artifact['id']}/zip",True)
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                def read(name):
                    match=next((n for n in z.namelist() if n==name or n.endswith('/'+name)),None)
                    return json.loads(z.read(match)) if match else {}
                receipt=read('receipt.json');delivery=read('delivery_result.json')
                selection=read('financial_selection_research.json');manifest=read('finance_first_delivery_manifest.json')
                day=receipt.get('asof','')
                if not START<=day<=END:continue
                write_json(root/'actual_issued'/f"{run['id']}.json",dict(meta,receipt=receipt,
                    delivery=delivery,selection=selection,manifest=manifest))
                confirmed=delivery.get('photos',[])
                if not confirmed:
                    jobs=get(f"actions/runs/{run['id']}/jobs")['jobs']
                    for job in jobs:
                        try:
                            text=get(f"actions/jobs/{job['id']}/logs",True).decode('utf-8-sig')
                            for line in text.splitlines():
                                if '\x1b' in line:continue
                                m=re.search(r'C3_FINANCE_FIRST_PHOTO_SENT\s+\d+\s+([0-9A-Z]{6})\s+telegram_message_id\s+(\d+).*mode\s+PRODUCTION',line)
                                if m:confirmed.append(dict(code=m[1],telegram_message_id=int(m[2])))
                        except Exception:pass
                if confirmed:
                    for photo in confirmed:results.append(dict(meta,signal_date=day,status='CONFIRMED_ISSUED',**photo))
                else:
                    status=('ACTUAL_CASH' if manifest.get('status')=='CASH_NO_FINANCIAL_CANDIDATES'
                            and run['conclusion']=='success' else 'NO_CONFIRMED_DELIVERY')
                    results.append(dict(meta,signal_date=day,status=status))
    except Exception as error:
        results.append(dict(status='ISSUANCE_AUDIT_INCOMPLETE',error=type(error).__name__))
    write_json(root/'actual_issued/index.json',results)
    return results

def reports(root,daily,trades,issued,manifest):
    fields=['signal_date','rank','code','name','technical_status','entry_low','entry_high','stop_ref','r1_ref','r2_ref',
        'risk_pct','entry_valid_until','fill_status','fill_date','fill_price','exit_date','exit_price',
        'highest_return_pct','highest_day','possible_highest_return_pct','possible_highest_day','peak_uncertain',
        'current_return_pct','evaluation_close','reference_close_return_pct','sequence_uncertain','adjustment_warning',
        'same_code_within_20_sessions','result_kind']
    csv_file(root/'monthly_top5_performance.csv',trades,fields)
    csv_file(root/'daily_summary.csv',daily,['date','status','technical_candidates','geometry_qualified',
        'requested_financial','selected_count','codes','reason'])
    csv_file(root/'actual_issued_signals.csv',issued,['signal_date','code','status','telegram_message_id',
        'run_id','event','commit','workflow_conclusion','run_url','error'])
    filled=[r for r in trades if r.get('fill_price') is not None]
    eligible=[r for r in filled if r.get('current_return_pct') is not None and
              not r.get('sequence_uncertain') and not r.get('adjustment_warning')]
    summary=dict(days=len(daily),verified_days=sum(r['status'] in ('CASH','TOP5') for r in daily),
        incomplete_days=[r['date'] for r in daily if r['status'] not in ('CASH','TOP5')],
        selected_signal_count=sum(r['selected_count'] for r in daily),filled=len(filled),
        included_return_observations=len(eligible),
        mean_current_return_pct=round(statistics.mean(r['current_return_pct'] for r in eligible),4) if eligible else None,
        mean_confirmed_peak_return_pct=round(statistics.mean(r['highest_return_pct'] for r in eligible),4) if eligible else None,
        stopped=sum(r.get('fill_status')=='STOPPED' for r in filled),
        pass_signals=sum(str(r.get('fill_status','')).startswith('PASS') for r in trades),
        pending=sum(r.get('fill_status')=='PENDING_AFTER_EVALUATION' for r in trades),
        sequence_uncertain=sum(bool(r.get('sequence_uncertain')) for r in filled),
        cash_dates=[r['date'] for r in daily if r['status']=='CASH'],
        best_confirmed_peak=max(eligible,key=lambda r:r['highest_return_pct']) if eligible else None,
        actual_confirmed_issued_records=sum(r.get('status')=='CONFIRMED_ISSUED' for r in issued))
    write_json(root/'summary.json',summary);write_json(root/'analysis_manifest.json',manifest)
    lines=['# 강현AI PRO · C3 TOP5 2026년 11월 단일 분석','',
        f'분석 기간: {START}–{END}, 평가 종가: {END}. 고정 운영 main: `{PIN}`.',
        '최신 알고리즘의 과거 재현이며 당시 실제 운영 발행 신호와 다르다. 운영 main·원장·Telegram은 수정하지 않았다.','',
        '## 집계 기준','',
        '- 선정에는 해당 일자까지의 60봉과 해당 일자 23:59 KST까지 제출된 고정 접수번호 XBRL만 사용했다. 현재 재무 JSON을 소급 사용하지 않았다.',
        '- 기존 점수·필터·최대 TOP5·가격 산식은 변경하지 않았다. 원본 숫자를 확인하지 못한 날은 UNVERIFIED_PIT이며 CASH가 아니다.',
        '- 진입은 기존 유효기간인 다음 KRX 거래일 하루만 관찰한다. 이후 미체결은 PASS, 11/20 신호의 다음 거래일은 평가일 이후이므로 PENDING이다.',
        '- 시가가 매수구간 안이면 시가, 위에서 구간에 진입하면 상단, 아래에서 진입하면 하단 체결 가정. 시가가 손절 이하이면 진입하지 않는다.',
        '- 손절만 적용하고 R1/R2에서 자동 익절하지 않는다. 갭 하락 손절은 시가, 그 외는 손절가로 청산 가정한다.',
        '- 일봉 내 순서 불확실성을 별도 표시한다. 매수·손절 순서가 불명확한 사례와 큰 가격불연속 사례는 평균에서 제외한다.',
        '- 최고수익률은 체결 후 확인 가능한 최고가의 보수적 하한이다. 진입/손절 당일 고가의 선후가 불명확하면 가능한 상한도 CSV에 별도 제공한다.',
        '- 손절된 거래의 현재수익률은 실현 손절수익률이다. 청산 후 11/20 종가 수익률은 참고 열이며 실제 보유수익으로 합산하지 않는다.',
        '- 20거래일 중복 제한: 현 main 선정함수에 없어 원본 TOP5 재현에서는 미적용. 반복 종목은 CSV에 표시하며 평균은 종목×선정일 단순평균이다. 포트폴리오 수익률이 아니다.',
        '- 수수료·거래세·배당·슬리피지는 미적용한 가격수익률이다. 매수범위 터치 체결은 가정이며 실제 계좌 체결이 아니다.','',
        '## 일자별 선정','',
        '| 일자 | 상태 | 기술 후보 | 재무 조회 | 선정 | 종목/사유 |','|---|---|---:|---:|---:|---|']
    for d in daily:lines.append(f"| {d['date']} | {d['status']} | {d['technical_candidates']} | {d['requested_financial']} | {d['selected_count']} | {d.get('codes') or d.get('reason','')} |")
    lines+=['','## 신호별 체결·성과','','| 선정일 | 종목 | 매수범위 | 손절 | 체결 상태/가격 | 확인 최고 % | 현재 % | 최고일 |','|---|---|---|---:|---|---:|---:|---|']
    for r in trades:
        if not r.get('code'):continue
        peak=str(r.get('highest_return_pct')) if r.get('highest_return_pct') is not None else '—'
        if r.get('peak_uncertain'):peak+=' (상한 '+str(r['possible_highest_return_pct'])+')'
        lines.append(f"| {r['signal_date']} | {r['name']} {r['code']} | {r['entry_low']}–{r['entry_high']} | {r['stop_ref']} | {r['fill_status']} / {r.get('fill_price') or '—'} | {peak} | {r.get('current_return_pct') if r.get('current_return_pct') is not None else '—'} | {r.get('highest_day') or '—'} |")
    lines+=['','## 요약','',f"- 검증된 날짜: {summary['verified_days']}/15. 미확인 날짜: {', '.join(summary['incomplete_days']) or '없음'}.",
        f"- 선정 신호 {summary['selected_signal_count']}건, 체결 {summary['filled']}건, 손절 {summary['stopped']}건, PASS {summary['pass_signals']}건, 평가일 이후 대기 {summary['pending']}건.",
        f"- 평균 현재수익률: {summary['mean_current_return_pct']}%, 평균 확인 최고수익률: {summary['mean_confirmed_peak_return_pct']}% (포함 관측 {summary['included_return_observations']}건).",
        '- CASH 날짜: '+(', '.join(summary['cash_dates']) or '없음'),
        f"- 실제 운영의 확인된 발송 기록: {summary['actual_confirmed_issued_records']}건. actual_issued_signals.csv와 원본 증거를 별도로 제공한다."]
    if summary['best_confirmed_peak']:
        best=summary['best_confirmed_peak'];lines.append(f"- 최고 상승: {best['name']} {best['code']}, {best['highest_return_pct']}%, 확인 최고일 {best['highest_day']}.")
    lines+=['','## 한계','',
        '당시 선택 가능했던 원본 공시를 확인한 범위만 재현했다. 회사별 원본 계정·연결/별도 문맥이 해석되지 않으면 미확인으로 남긴다. KRX 비수정 일봉의 기업행위·가격정정·실제 체결/봉 내부 순서는 독립 인증하지 않았다. 월중 중복을 포함한 단순평균을 실제 계좌 손익으로 해석하지 않는다.',
        f"실행: https://github.com/{os.environ.get('GITHUB_REPOSITORY','shdmfpsj-beep/krx-auto-scanner')}/actions/runs/{os.environ.get('GITHUB_RUN_ID','LOCAL')}" ]
    (root/'monthly_report.md').write_text('\n'.join(lines)+'\n')
    return summary

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    root=args.out;root.mkdir(parents=True,exist_ok=True)
    hashes={p:sha((REPO/p).read_bytes()) for p in PRODUCTION}
    expected=json.loads((REPO/'analysis/c3_monthly_202611_manifest.json').read_text())
    if hashes!=expected['production_sha256']:raise ValueError('PRODUCTION_ALGORITHM_CHANGED')
    calendar=xc.get_calendar('XKRX',start='2026-06-01',end='2026-12-10')
    sessions=[s.strftime('%Y%m%d') for s in calendar.sessions_in_range('2026-06-01','2026-11-30')]
    days=[d for d in sessions if START<=d<=END];assert len(days)==15
    needed=sessions[sessions.index(START)-59:sessions.index(END)+1]
    nodes=code_nodes();source=Sources(root,nodes)
    daily=[];trades=[];quotes={};pools={};geometries={};corps=None
    for day in reversed(needed):
        for market,endpoint in [('KOSPI','stk_bydd_trd'),('KOSDAQ','ksq_bydd_trd')]:
            rows=source.market(day,endpoint)
            if len(rows)<(500 if market=='KOSPI' else 800):raise ValueError('KRX_MISSING_EXPECTED_SESSION_'+day)
            for r in rows:
                code=str(r.get('ISU_CD','')).strip()
                if not re.fullmatch('[0-9A-Z]{6}',code):continue
                values=[source.namespace['num'](r.get(k)) for k in ('TDD_OPNPRC','TDD_HGPRC','TDD_LWPRC','TDD_CLSPRC')]
                if None not in values and min(values)>0:
                    quotes[(day,code)]=dict(zip(('open','high','low','close'),values))
        print('MONTHLY_KRX_COLLECTED',day,flush=True)
    for day in days:
        window=sessions[sessions.index(day)-59:sessions.index(day)+1]
        g,pool=technical(day,window,source,nodes,calendar,root)
        geometries[day]=g;pools[day]=pool
        print('MONTHLY_TECHNICAL',day,g['technical_candidate_count'],len(requested_candidates(g)),flush=True)
    if any(requested_candidates(g) for g in geometries.values()):corps=source.corporations()
    previous={}
    for day in days:
        g,pool=geometries[day],pools[day];requested=requested_candidates(g)
        f=source.financial_gate(day,requested,corps or {})
        chosen=select(g,f);target=root/'replay'/day
        write_json(target/'financial_pool_gate.json',f);write_json(target/'selection.json',chosen)
        status=('UNVERIFIED_PIT' if chosen['status']=='ERROR_FINANCIAL_EVIDENCE'
                else 'ERROR_GEOMETRY' if chosen['status']=='ERROR_ENTRY_GEOMETRY'
                else 'TOP5' if chosen['selected'] else 'CASH')
        daily.append(dict(date=day,status=status,technical_candidates=g['technical_candidate_count'],
            geometry_qualified=g['qualified_count'],requested_financial=len(requested),
            selected_count=len(chosen['selected']),codes=','.join(c['code'] for c in chosen['selected']),
            reason=f['status'] if status=='UNVERIFIED_PIT' else 'NO_QUALIFIED_CANDIDATES' if status=='CASH' else ''))
        lookup={c['code']:c for c in pool['candidates']}
        for rank,item in enumerate(chosen['selected'],1):
            c=lookup[item['code']]
            signal=dict(signal_date=day,rank=rank,code=c['code'],name=c['name'],
                technical_status=c['entry_status'],**{k:c.get(k) for k in ('entry_low','entry_high','stop_ref','r1_ref','r2_ref','risk_pct')},
                entry_valid_until=pool['entry_valid_until'],result_kind='CURRENT_MAIN_HISTORICAL_REPLAY')
            row=evaluate_trade(signal,sessions,quotes)
            row['same_code_within_20_sessions']=c['code'] in previous and sessions.index(day)-previous[c['code']]<20
            previous[c['code']]=sessions.index(day);trades.append(row)
        print('MONTHLY_SELECTION',day,status,len(chosen['selected']),flush=True)
        write_json(root/'source/source_manifest.json',source.manifest)
    issued=actual_signals(root)
    assert hashes=={p:sha((REPO/p).read_bytes()) for p in PRODUCTION}
    manifest=dict(pinned_main=PIN,production_sha256=hashes,start=START,end=END,
        observed_at=datetime.datetime.now(KST).isoformat(),financial_basis='RECEIPT_PINNED_ORIGINAL_XBRL',
        selection_cutoff='signal day 23:59:59 Asia/Seoul; next-session entry only',
        future_prices_in_selection=False,duplicate_20_session_limit_applied=False,
        fee_bps=0,tax_bps=0,production_files_changed=False,orders=0,telegram_sends=0)
    summary=reports(root,daily,trades,issued,manifest)
    print('MONTHLY_SUMMARY',json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as error:
        print('MONTHLY_ANALYSIS_FAILED',type(error).__name__,str(error)[:120] if isinstance(error,ValueError) else '',flush=True)
        raise SystemExit(1)
