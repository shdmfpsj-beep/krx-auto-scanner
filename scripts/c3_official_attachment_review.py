"""Read-only official attachment capture; never qualifies a financial decision."""
import argparse
import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from c3_balanced_financials import retry_network
from c3_dart_document_evidence import ReviewDocumentParser, normalized


def sections(html, receipt):
    if not re.fullmatch(r'\d{14}',receipt):raise ValueError('INVALID_RECEIPT')
    result=[];seen=set()
    for block in re.findall(r'var (node\d+)\s*=\s*\{\};([\s\S]*?)treeData\.push\(\1\);',html):
        node,body=block
        values=dict(re.findall(re.escape(node)+r"\['(text|rcpNo|dcmNo|eleId|offset|length|dtd)'\]\s*=\s*\"([^\"]*)\"",body))
        if set(values)!={'text','rcpNo','dcmNo','eleId','offset','length','dtd'}:raise ValueError('VIEWER_NODE_INCOMPLETE')
        if values['rcpNo']!=receipt:raise ValueError('VIEWER_RECEIPT_MISMATCH')
        if not all(re.fullmatch(r'\d{1,12}',values[k]) for k in ('dcmNo','eleId','offset','length')):
            raise ValueError('VIEWER_NODE_NUMBER_INVALID')
        if not re.fullmatch(r'dart\d+\.xsd',values['dtd']) or not 0<int(values['length'])<=2*1024*1024:
            raise ValueError('VIEWER_NODE_SCOPE_UNSUPPORTED')
        identity=(values['dcmNo'],values['eleId'],values['offset'],values['length'])
        if identity in seen:raise ValueError('VIEWER_NODE_DUPLICATE')
        seen.add(identity);result.append(values)
    if not result or len(result)>8:raise ValueError('VIEWER_NODE_BUDGET_OR_EMPTY')
    return result


def fetch_public(url):
    request=urllib.request.Request(url,headers={'User-Agent':'C3-readonly-filing-evidence/1.0'})
    with urllib.request.urlopen(request,timeout=15) as response:
        if response.status!=200:raise ValueError('PUBLIC_FILING_HTTP_FAILED')
        binary=response.read(2*1024*1024+1)
    if len(binary)>2*1024*1024:raise ValueError('PUBLIC_FILING_TOO_LARGE')
    return binary


def capture(viewer, expected_sha, receipt, asof, out, fetch=fetch_public):
    if not re.fullmatch(r'\d{8}',asof) or receipt[:8]>asof:raise ValueError('DOCUMENT_AFTER_ASOF')
    original=viewer.read_bytes()
    if hashlib.sha256(original).hexdigest()!=expected_sha:raise ValueError('VIEWER_SOURCE_HASH_MISMATCH')
    nodes=sections(original.decode('utf-8'),receipt)
    out.mkdir(parents=True,exist_ok=True);records=[]
    for node in nodes:
        params={k:node[k] for k in ('rcpNo','dcmNo','eleId','offset','length','dtd')}
        url='https://dart.fss.or.kr/report/viewer.do?'+urllib.parse.urlencode(params)
        record=dict(title=node['text'],parameters=params,source_url=url,qualification_use=False)
        records.append(record)
        try:
            binary=retry_network(lambda:fetch(url))
            if len(binary)>2*1024*1024:raise ValueError('PUBLIC_FILING_TOO_LARGE')
            try:text=binary.decode('utf-8')
            except UnicodeError:text=binary.decode('euc-kr')
            parser=ReviewDocumentParser();parser.feed(text);plain=normalized(parser.root)
            if len(plain)<20:raise ValueError('PUBLIC_FILING_CONTENT_EMPTY')
            stem=receipt+'_'+node['eleId'];(out/(stem+'.html')).write_bytes(binary)
            (out/(stem+'.txt')).write_text(plain+'\n')
            record.update(state='OFFICIAL_SECTION_CAPTURED_CONTENT_REVIEW_REQUIRED',file=stem+'.html',
                text_file=stem+'.txt',sha256=hashlib.sha256(binary).hexdigest(),bytes=len(binary))
        except Exception as error:record.update(state='ERROR',error_class=type(error).__name__)
    result=dict(receipt_no=receipt,asof=asof,observed_at=datetime.now(timezone.utc).isoformat(),
        viewer_sha256=expected_sha,sections=records,qualification_use=False,trade_approved=False,
        scope='OFFICIAL_ATTACHMENT_CONTENT_CAPTURE_NOT_AUTOMATIC_FINANCIAL_APPROVAL')
    (out/'attachment_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--viewer',type=Path,required=True)
    p.add_argument('--sha256',required=True);p.add_argument('--receipt',required=True)
    p.add_argument('--asof',required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=capture(a.viewer,a.sha256,a.receipt,a.asof,a.out)
    print('C3_ATTACHMENT_REVIEW',json.dumps(r,ensure_ascii=False))
