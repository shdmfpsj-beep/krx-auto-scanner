#!/usr/bin/env python3
"""Locate official filing-note evidence without inventing financial facts.

Document tables and XBRL facts are preserved for review. Table discovery never
authorizes a company, establishes absence of PF risk, or replaces direct IS/BS
accounts. CFS and OFS note sections are kept separate.
"""
import argparse
import hashlib
import io
import json
import os
import re
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET
from html.parser import HTMLParser
from dart_financial_screen import integer

API='https://opendart.fss.or.kr/api/'
TERMS=('차입금','사채','이자비용','유동성위험','만기','우발','지급보증','프로젝트파이낸싱','미청구공사','공사손실')
MAX_BYTES=32*1024*1024


class ReviewDocumentParser(HTMLParser):
    """Recover malformed issuer document markup for manual note discovery only.

    This parser cannot fetch external resources and is never used on XBRL.
    Recovered tables do not certify periods, units or financial eligibility.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root=ET.Element('RECOVERED_DOCUMENT')
        self.stack=[self.root]

    def handle_starttag(self,name,attrs):
        node=ET.SubElement(self.stack[-1],name,dict((k,v or '') for k,v in attrs))
        if name not in ('br','hr','img','meta','link','input'):
            self.stack.append(node)

    def handle_startendtag(self,name,attrs):
        self.handle_starttag(name,attrs)
        self.handle_endtag(name)

    def handle_endtag(self,name):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==name:
                del self.stack[i:]
                break

    def handle_data(self,data):
        node=self.stack[-1]
        if len(node):node[-1].tail=(node[-1].tail or '')+data
        else:node.text=(node.text or '')+data


def tag(node):
    return node.tag.split('}')[-1].upper() if isinstance(node.tag,str) else ''


def normalized(node):
    return re.sub(r'\s+',' ',''.join(node.itertext())).strip()


def xbrl_facts(root, division, year, corp_code, references):
    """Expose exact entity/period/currency/scope facts; no dimension summation."""
    ns='{http://www.xbrl.org/2003/instance}'
    expected='ifrs-full:ConsolidatedMember' if division=='CFS' else 'ifrs-full:SeparateMember'
    units={n.attrib.get('id') for n in root.findall(ns+'unit')
           if n.findtext(ns+'measure')=='iso4217:KRW'}
    contexts={}
    for context in root.findall(ns+'context'):
        identifier=context.findtext('.//'+ns+'identifier')
        members=[(n.attrib.get('dimension'),n.text) for n in context.iter() if tag(n)=='EXPLICITMEMBER']
        if identifier!=corp_code or members!=[('ifrs-full:ConsolidatedAndSeparateFinancialStatementsAxis',expected)]:continue
        if any(tag(n)=='TYPEDMEMBER' for n in context.iter()):continue
        period=context.find(ns+'period')
        if period is None:continue
        dates={tag(n):n.text for n in period}
        if dates not in ({'INSTANT':f'{year}-12-31'},
                          {'STARTDATE':f'{year}-01-01','ENDDATE':f'{year}-12-31'}):continue
        contexts[context.attrib['id']]=dates
    found={}
    for fact in root:
        context=fact.attrib.get('contextRef');name=fact.tag.split('}')[-1]
        if context not in contexts or fact.attrib.get('unitRef') not in units:continue
        value=integer(fact.text)
        if value is None:continue
        found.setdefault(name,[]).append({'value':value,'context':context,'period':contexts[context],
            'concept':fact.tag,'unit':'KRW','entity':corp_code,'division':division})
    def unique(name):
        rows=[row for row in found.get(name,[]) if row['period']=={'INSTANT':f'{year}-12-31'}]
        return rows[0]['value'] if rows and len({r['value'] for r in rows})==1 else None
    anchors=bool(references) and all(references.get(name) is not None and unique(name)==references[name]
                                   for name in ('Assets','Liabilities','Equity'))
    interesting={name:rows for name,rows in found.items() if any(word in name.lower() for word in
                 ('borrow','bondsissued','interestexpense','financecost','cashandcashequivalents'))}
    disclosed={}
    if anchors:
        loans,bonds,cash=(unique(name) for name in ('OtherBorrowings','BondsIssued','CashAndCashEquivalents'))
        if all(value is not None and value>=0 for value in (loans,bonds,cash)):
            disclosed={'loans':loans,'bonds_total':bonds,'cash':cash,'loans_plus_bonds':loans+bonds,
                       'loans_plus_bonds_less_cash':loans+bonds-cash,
                       'definition':'Exact disclosed OtherBorrowings plus BondsIssued less cash; lease liabilities excluded',
                       'qualification_use':'NOT_AUTOMATICALLY_PROMOTED; loan component classification and maturity review remain separate'}
    return {'entity':corp_code,'fiscal_year':year,'division':division,'currency':'KRW',
            'reference_balance_matches':anchors,'facts':interesting,'disclosed_totals':disclosed,
            'formal_is_interest_expense_verified':False,'automatic_financial_promotion':False}


def inspect_archive(binary, division, fiscal_year=None, corp_code=None, references=None):
    if len(binary)>MAX_BYTES:
        raise ValueError('DOCUMENT_TOO_LARGE')
    result={'state':'MANUAL_REVIEW_REQUIRED','division':division,'tables':[],
            'automatic_financial_promotion':False,'scope_verified':False}
    if not zipfile.is_zipfile(io.BytesIO(binary)):
        # OpenDART returns XML status codes instead of ZIP on API failure.
        root=ET.fromstring(binary)
        status=root.findtext('status','UNKNOWN')
        return {**result,'state':'API_UNAVAILABLE' if status in ('013','014') else 'ERROR','api_status':status}
    with zipfile.ZipFile(io.BytesIO(binary)) as archive:
        files=[f for f in archive.infolist() if f.filename.lower().endswith(('.xml','.xbrl'))]
        if len(files)>1000 or sum(f.file_size for f in files)>128*1024*1024:
            raise ValueError('DOCUMENT_ARCHIVE_BUDGET_EXCEEDED')
        result['xml_files']=[f.filename for f in files]
        for file in files:
            if file.file_size>MAX_BYTES:
                continue
            raw=archive.read(file)
            # No external entities, DTD processing or external document reads.
            if b'<!ENTITY' in raw.upper():
                continue
            raw=re.sub(rb'<!DOCTYPE[^\[>]*>',b'',raw,flags=re.IGNORECASE)
            if b'<!DOCTYPE' in raw.upper():continue
            try:root=ET.fromstring(raw)
            except (ValueError,ET.ParseError):
                # Primary XBRL facts retain strict XML/scope/period validation.
                if re.search(rb'<(?:\w+:)?xbrl\b',raw,re.I):continue
                try:text=raw.decode('utf-8')
                except UnicodeError:
                    try:text=raw.decode('euc-kr')
                    except UnicodeError:continue
                parser=ReviewDocumentParser();parser.feed(text);root=parser.root
                result.setdefault('recovered_document_files',[]).append(file.filename)
                result['recovery_use']='MANUAL_NOTES_ONLY_NO_AUTOMATIC_FINANCIAL_PROMOTION'
            if tag(root)=='XBRL' and fiscal_year and corp_code:
                evidence=xbrl_facts(root,division,fiscal_year,corp_code,references)
                if evidence['facts']:
                    result['xbrl_evidence']=evidence
                    result['scope_verified']=evidence['reference_balance_matches']
                continue
            wanted='연결재무제표주석' if division=='CFS' else '재무제표주석'
            sections=[]
            for node in root.iter():
                if not tag(node).startswith('SECTION'):continue
                titles=[normalized(child) for child in list(node) if tag(child)=='TITLE']
                if any(re.sub(r'[\s\d.()\-]','',title)==wanted for title in titles):
                    sections.append(node)
            # Multiple matching note scopes cannot safely be merged.
            if len(sections)!=1:continue
            result['scope_verified']=True
            for table in sections[0].iter():
                if tag(table)!='TABLE':continue
                text=normalized(table)
                found=[term for term in TERMS if term in text.replace(' ','')]
                if not found:continue
                rows=[]
                for row in table.iter():
                    if tag(row)!='TR':continue
                    cells=[normalized(cell)[:200] for cell in list(row) if tag(cell) in ('TD','TH','TE','TU')]
                    if cells:rows.append(cells[:20])
                    if len(rows)>=30:break
                result['tables'].append({'file':file.filename,'scope':division,'matched_terms':found,
                    'rows':rows,'unit_and_period_validated':False})
                if len(result['tables'])>=16:break
    if result['tables']:
        result['state']='SCOPED_NOTE_TABLES_LOCATED_REVIEW_REQUIRED'
    elif result.get('xbrl_evidence',{}).get('reference_balance_matches'):
        result['state']='SCOPED_PERIOD_CURRENCY_XBRL_FACTS_VALIDATED_SEMANTIC_REVIEW_REQUIRED'
    return result


def download_document(endpoint, receipt, report, key, fetch=None):
    if endpoint not in ('document.xml','fnlttXbrl.xml'):
        raise ValueError('UNSUPPORTED_DOCUMENT_ENDPOINT')
    params={'crtfc_key':key,'rcept_no':receipt}
    if endpoint=='fnlttXbrl.xml':params['reprt_code']=report
    req=urllib.request.Request(API+endpoint+'?'+urllib.parse.urlencode(params),
                              headers={'User-Agent':'C3-readonly-filing-evidence/1.0'})
    if fetch:return fetch(req)
    with urllib.request.urlopen(req,timeout=30) as response:
        binary=response.read(MAX_BYTES+1)
    if len(binary)>MAX_BYTES:raise ValueError('DOCUMENT_TOO_LARGE')
    return binary


def probe(receipt, report, division, asof, key, out, download=download_document,
          fiscal_year=None,corp_code=None,references=None):
    result={'receipt_no':receipt,'report_code':report,'division':division,'routes':[],
            'observed_at':datetime.now(timezone.utc).isoformat(),'automatic_financial_promotion':False}
    try:
        if not re.fullmatch(r'\d{14}',receipt) or division not in ('CFS','OFS') or report not in ('11011','11012','11013','11014'):
            raise ValueError('INVALID_DOCUMENT_IDENTITY')
        received=datetime.strptime(receipt[:8],'%Y%m%d').date()
        if received>asof:raise ValueError('DOCUMENT_AFTER_SIGNAL_DATE')
        if not key or not re.fullmatch(r'[A-Za-z0-9]{40}',key):raise ValueError('DART_KEY_UNAVAILABLE')
        out=Path(out);out.mkdir(parents=True,exist_ok=True)
        for endpoint in ('document.xml','fnlttXbrl.xml'):
            try:
                binary=download(endpoint,receipt,report,key)
                sha=hashlib.sha256(binary).hexdigest()
                suffix='.zip' if zipfile.is_zipfile(io.BytesIO(binary)) else '.xml'
                filename=receipt+'_'+endpoint.split('.')[0]+suffix
                (out/filename).write_bytes(binary)
                checked=inspect_archive(binary,division,fiscal_year,corp_code,references)
                result['routes'].append({'endpoint':endpoint,'file':filename,'sha256':sha,
                    'bytes':len(binary),'analysis':checked})
                if checked.get('tables'):break
            except Exception as exc:
                result['routes'].append({'endpoint':endpoint,'state':'ERROR','error':type(exc).__name__})
        result['state']='EVIDENCE_LOCATED_REVIEW_REQUIRED' if any(r.get('analysis',{}).get('tables') or
            r.get('analysis',{}).get('xbrl_evidence',{}).get('reference_balance_matches') for r in result['routes']) else 'AUTOMATIC_EXTRACTION_UNVERIFIED'
    except Exception as exc:
        result.update(state='ERROR',error=str(exc) if isinstance(exc,ValueError) and re.fullmatch(r'[A-Z_]+',str(exc)) else type(exc).__name__)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--financial',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--geometry',type=Path)
    args=parser.parse_args()
    financial=json.loads(args.financial.read_text())
    asof=datetime.strptime(financial['asof'],'%Y%m%d').date()
    key=os.environ.get('DART_API_KEY') or os.environ.get('OPENDART_API_KEY') or os.environ.get('OPEN_DART_API_KEY')
    rows=financial.get('researched',[])+financial.get('excluded',[])
    geometry=json.loads(args.geometry.read_text()) if args.geometry and args.geometry.is_file() else {}
    watch={r['code'] for r in geometry.get('candidates',[]) if r.get('geometry_validated')}
    # Spend the bounded note budget on unresolved evidence, not on auxiliary
    # details of companies already rejected by proven financial risk.
    rows=[r for r in rows if r.get('financial_verdict') in ('ERROR','REVIEW_REQUIRED')]
    rows.sort(key=lambda r:(0 if r.get('financial_verdict')=='ERROR' else 1 if r['ticker'] in watch else 2,r['ticker']))
    results=[]
    for row in rows[:3]:
        receipt=row.get('annual_receipt_no') or row.get('requested_annual_receipt_no')
        division=row.get('statement_division') or row.get('statement_division_attempted')
        if receipt and division:
            results.append({'ticker':row['ticker'],**probe(receipt,'11011',
                division,asof,key,args.out,fiscal_year=row.get('annual_fiscal_year'),
                corp_code=row.get('corp_code'),references={'Assets':row.get('decision_basis',{}).get('annual_assets_krw'),
                    'Liabilities':row.get('liabilities_krw'),'Equity':row.get('equity_krw')})})
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'document_evidence.json').write_text(json.dumps({'asof':financial['asof'],
        'scope':'SUPPLEMENTARY_SOURCE_DISCOVERY_NOT_A_QUALIFICATION_GATE','companies':results},
        ensure_ascii=False,indent=2)+'\n')
    print('DART_DOCUMENT_EVIDENCE',json.dumps([{'ticker':r['ticker'],'state':r['state'],
        'routes':len(r['routes'])} for r in results]))


if __name__=='__main__':main()
