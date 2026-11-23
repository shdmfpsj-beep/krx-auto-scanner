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

API='https://opendart.fss.or.kr/api/'
TERMS=('차입금','사채','이자비용','유동성위험','만기','우발','지급보증','프로젝트파이낸싱','미청구공사','공사손실')
MAX_BYTES=32*1024*1024


def tag(node):
    return node.tag.split('}')[-1].upper() if isinstance(node.tag,str) else ''


def normalized(node):
    return re.sub(r'\s+',' ',''.join(node.itertext())).strip()


def inspect_archive(binary, division):
    if len(binary)>MAX_BYTES:
        raise ValueError('DOCUMENT_TOO_LARGE')
    result={'state':'MANUAL_REVIEW_REQUIRED','division':division,'tables':[],
            'automatic_financial_promotion':False,'scope_verified':False}
    if not zipfile.is_zipfile(io.BytesIO(binary)):
        # OpenDART returns XML status codes instead of ZIP on API failure.
        root=ET.fromstring(binary)
        return {**result,'state':'API_UNAVAILABLE','api_status':root.findtext('status','UNKNOWN')}
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
            except ValueError:
                try:root=ET.fromstring(raw.decode('euc-kr'))
                except (UnicodeError,ET.ParseError):continue
            except ET.ParseError:continue
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


def probe(receipt, report, division, asof, key, out, download=download_document):
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
                checked=inspect_archive(binary,division)
                result['routes'].append({'endpoint':endpoint,'file':filename,'sha256':sha,
                    'bytes':len(binary),'analysis':checked})
                if checked.get('tables'):break
            except Exception as exc:
                result['routes'].append({'endpoint':endpoint,'state':'ERROR','error':type(exc).__name__})
        result['state']='EVIDENCE_LOCATED_REVIEW_REQUIRED' if any(r.get('analysis',{}).get('tables') for r in result['routes']) else 'AUTOMATIC_EXTRACTION_UNVERIFIED'
    except Exception as exc:
        result.update(state='ERROR',error=str(exc) if isinstance(exc,ValueError) and re.fullmatch(r'[A-Z_]+',str(exc)) else type(exc).__name__)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--financial',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    financial=json.loads(args.financial.read_text())
    asof=datetime.strptime(financial['asof'],'%Y%m%d').date()
    key=os.environ.get('DART_API_KEY') or os.environ.get('OPENDART_API_KEY') or os.environ.get('OPEN_DART_API_KEY')
    rows=financial.get('researched',[])+financial.get('excluded',[])
    results=[]
    for row in rows[:3]:
        if row.get('annual_receipt_no') and row.get('statement_division'):
            results.append({'ticker':row['ticker'],**probe(row['annual_receipt_no'],'11011',
                row['statement_division'],asof,key,args.out)})
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'document_evidence.json').write_text(json.dumps({'asof':financial['asof'],
        'scope':'SUPPLEMENTARY_SOURCE_DISCOVERY_NOT_A_QUALIFICATION_GATE','companies':results},
        ensure_ascii=False,indent=2)+'\n')
    print('DART_DOCUMENT_EVIDENCE',json.dumps([{'ticker':r['ticker'],'state':r['state'],
        'routes':len(r['routes'])} for r in results]))


if __name__=='__main__':main()
