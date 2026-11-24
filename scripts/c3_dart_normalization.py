"""Narrow, reconciled annual note facts; never infer missing accounts as zero.

Only original annual documents with verified entity/period and matching XBRL
balance anchors can provide automatic financial inputs. Every accepted amount
retains source, scale, rounding precision, scope, period and reconciliation.
"""
import hashlib
import io
import math
import re
import zipfile
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET
from c3_dart_document_evidence import ReviewDocumentParser, tag, normalized, inspect_archive


def compact(value):
    return re.sub(r'\s+','',str(value or ''))


def amount(value, dash=False):
    text=compact(value).replace(',','').replace('−','-')
    if text in ('-','—','–'):return 0 if dash else None
    if not text:return None
    if text.startswith('(') and text.endswith(')'):text='-'+text[1:-1]
    if not re.fullmatch(r'-?\d+(?:\.\d+)?',text):return None
    try:return Decimal(text)
    except InvalidOperation:return None


def grid(table):
    """Expand actual rowspan/colspan, including inherited audit-period cells."""
    result=[];pending={}
    for tr in table.iter():
        if tag(tr)!='TR':continue
        row={i:text for i,(remaining,text) in pending.items()}
        pending={i:(remaining-1,text) for i,(remaining,text) in pending.items() if remaining>1}
        col=0
        for cell in list(tr):
            if tag(cell) not in ('TD','TH','TE','TU'):continue
            attrs={k.upper():v for k,v in cell.attrib.items()}
            across=min(int(attrs.get('COLSPAN','1')),50);down=min(int(attrs.get('ROWSPAN','1')),100)
            while col in row:col+=1
            text=normalized(cell)
            for i in range(across):
                row[col+i]=text
                if down>1:pending[col+i]=(down-1,text)
            col+=across
        if row:result.append([row.get(i,'') for i in range(max(row)+1)])
    return result


def original_document(binary, identity):
    if len(binary)>32*1024*1024:raise ValueError('DOCUMENT_TOO_LARGE')
    with zipfile.ZipFile(io.BytesIO(binary)) as archive:
        name=identity['receipt_no']+'.xml'
        if name not in archive.namelist():raise ValueError('ORIGINAL_MAIN_DOCUMENT_UNAVAILABLE')
        if archive.getinfo(name).file_size>32*1024*1024:raise ValueError('DOCUMENT_TOO_LARGE')
        raw=archive.read(name)
    if b'<!ENTITY' in raw.upper():raise ValueError('DOCUMENT_ENTITY_FORBIDDEN')
    raw=re.sub(rb'<!DOCTYPE[^\[>]*>',b'',raw,flags=re.I)
    if b'<!DOCTYPE' in raw.upper():raise ValueError('DOCUMENT_DTD_FORBIDDEN')
    try:root=ET.fromstring(raw)
    except (ET.ParseError,ValueError):
        try:text=raw.decode('utf-8')
        except UnicodeError:text=raw.decode('euc-kr')
        parser=ReviewDocumentParser();parser.feed(text);root=parser.root
    names=[n for n in root.iter() if tag(n)=='COMPANY-NAME']
    identifiers={str({k.upper():v for k,v in n.attrib.items()}.get('AREGCIK','')) for n in names}
    if identifiers!={identity['corp_code']}:raise ValueError('DOCUMENT_COMPANY_MISMATCH')
    covers=[n for n in root.iter() if tag(n)=='COVER']
    if len(covers)!=1:raise ValueError('DOCUMENT_COVER_AMBIGUOUS')
    periods={}
    for n in covers[0].iter():
        attrs={k.upper():v for k,v in n.attrib.items()}
        if attrs.get('AUNIT') in ('PERIODFROM','PERIODTO'):
            periods.setdefault(attrs['AUNIT'],set()).add(attrs.get('AUNITVALUE'))
    year=identity['fiscal_year']
    if periods!={'PERIODFROM':{f'{year}0101'},'PERIODTO':{f'{year}1231'}}:
        raise ValueError('DOCUMENT_PERIOD_MISMATCH')
    doc_names=[n for n in root.iter() if tag(n)=='DOCUMENT-NAME']
    if not any('사업보고서' in normalized(n) for n in doc_names):
        raise ValueError('DOCUMENT_NOT_ANNUAL_REPORT')
    wanted='연결재무제표주석' if identity['division']=='CFS' else '재무제표주석'
    sections=[n for n in root.iter() if tag(n).startswith('SECTION') and any(
        re.sub(r'[\s\d.()\-]','',normalized(c))==wanted for c in list(n) if tag(c)=='TITLE')]
    if len(sections)!=1:raise ValueError('DOCUMENT_FINANCIAL_SCOPE_AMBIGUOUS')
    return root,sections[0],name


def tables_with_context(section):
    nodes=list(section.iter());parents={c:n for n in section.iter() for c in n}
    preceding={};paragraphs=[]
    for node in nodes:
        kind=tag(node)
        if kind in ('P','TITLE'):
            paragraphs.append(normalized(node))
            paragraphs=paragraphs[-3:]
        elif kind=='TABLE':preceding[id(node)]=list(paragraphs)
    for index,table in enumerate(n for n in nodes if tag(n)=='TABLE'):
        rows=grid(table)
        if not rows:continue
        parent=parents.get(table);siblings=list(parent) if parent is not None else []
        position=siblings.index(table) if table in siblings else 0
        local=[normalized(n) for n in siblings[max(0,position-3):position]
               if tag(n)!='TABLE' or len(normalized(n))<=500]
        # For XBRL-rendered note groups the preceding unit/period header is a
        # separate sibling table. Ordinary notes often put the unit in row one.
        metadata=' '.join(local[-2:])+ ' '+' '.join(' '.join(r) for r in rows[:2])
        unit_matches=re.findall(r'(?:단위\s*[:：]\s*)(백만원|천원|원)\s*\)',metadata)
        scales={'원':1,'천원':1000,'백만원':1000000}
        unit=unit_matches[-1] if unit_matches and len(set(unit_matches))==1 else None
        if any(word in metadata for word in ('USD','US$','외화단위','달러')):unit=None
        context=' '.join(preceding[id(table)]+local[-2:])
        yield dict(index=index,rows=rows,unit=unit,scale=scales.get(unit),metadata=metadata,
                   context=context)


def current_column(table):
    for row in table['rows'][:3]:
        columns=[i for i,text in enumerate(row) if i and re.search(r'당기|\(당\)',compact(text))]
        if len(columns)==1:return columns[0]
    # A one-period XBRL note table carries its period in a separate header.
    meta=compact(table['metadata'])
    if '당기' in meta and '전기' not in meta:
        widths={len(r) for r in table['rows']}
        return max(widths)-1 if max(widths)<=3 else None
    return None


def close_to(quoted,reference,scale):
    return reference is not None and abs(Decimal(str(quoted))-Decimal(str(reference)))<=Decimal(scale)/2+1


BORROWING_LABELS={'차입금','총차입금','단기차입금','장기차입금','유동성장기차입금',
    '사채','유동사채','유동성사채','비유동사채','유동전환사채','비유동전환사채','전환사채'}
NONBORROWING_LABELS={'리스부채','유동리스부채','비유동리스부채','미지급배당금',
    '임대보증금','임대보증금-유동','임대보증금-비유동','유동임대보증금','비유동임대보증금',
    '예수보증금','유동예수보증금','비유동예수보증금'}


def transposed_financing_debt(table):
    context=compact(table['context']+' '+table['metadata'])
    if not ('재무활동' in context and '부채' in context and '당기' in compact(table['metadata'])):return None
    rows=table['rows']
    closing=next((r for r in rows if r and '기말부채' in compact(r[0])),None)
    if not closing:return None
    total_col=len(closing)-1
    header=next((r for r in rows[:4] if len(r)==len(closing) and
                 '합계' in compact(r[-1]) and any('차입금' in compact(c) for c in r)),None)
    if not header:return None
    # Use the lowest detailed header, not its current/non-current group labels.
    headers=[r for r in rows[:4] if len(r)==len(closing) and '합계' in compact(r[-1])]
    header=headers[-1]
    numeric=[i for i in range(total_col) if amount(closing[i],dash=True) is not None]
    labels=[compact(header[i]) for i in numeric]
    allowed=BORROWING_LABELS|NONBORROWING_LABELS|{'유동성장기부채','유동성리스부채'}
    if not labels or len(set(labels))!=len(labels) or any(x not in allowed for x in labels):return None
    if len(labels)>1 and set(labels)&{'차입금','총차입금'}:return None
    beginning=next((r for r in rows if r and '기초부채' in compact(r[0])),None)
    cash=next((r for r in rows if len(r)>1 and compact(r[0])==compact(r[1]) and '재무현금흐름' in compact(r[0])),None)
    noncash=next((r for r in rows if len(r)>1 and compact(r[0])==compact(r[1]) and '비현금흐름변동' in compact(r[0])),None)
    if any(r is None for r in (beginning,cash,noncash)):return None
    for col in numeric+[total_col]:
        vals=[amount(r[col],dash=True) if len(r)>col else None for r in (beginning,cash,noncash,closing)]
        if any(v is None for v in vals) or abs(sum(vals[:3])-vals[3])>2:return None
    values=[amount(closing[i],dash=True) for i in numeric]
    total=amount(closing[total_col],dash=True)
    if any(v<0 for v in values) or abs(sum(values)-total)>Decimal(len(values))/2+1:return None
    borrow=[label in BORROWING_LABELS or label=='유동성장기부채' for label in labels]
    debt=sum(v for v,b in zip(values,borrow) if b)
    return dict(value=debt*table['scale'],label='재무활동 부채 변동표의 차입금·사채 합계',
        method='RECONCILED_TRANSPOSED_FINANCING_LIABILITIES',reconciliation=dict(total=float(total),
            classified_columns=[dict(label=l,value=float(v),borrowing=b) for l,v,b in zip(labels,values,borrow)]))


def financing_debt(table):
    """Closed classification of a reconciled ALL-financing-liabilities note.

    Zero borrowing is supported only by an exhaustive, current, fully classified
    table with its explicit total and verified movements; API omission is unused.
    """
    context=compact(table['context'])
    if not (('재무활동' in context and '부채' in context) and any(w in context for w in ('변동','조정'))):return None
    header=next((r for r in table['rows'][:3] if any(re.search('기말|당기말',compact(c)) for c in r)),None)
    if not header:return None
    col=next(i for i,c in enumerate(header) if re.search('기말|당기말',compact(c)))
    if '전기말' in compact(header[col]):return None
    if '당기말' not in compact(header[col]) and not re.search(r'\(당\)|당기',compact(table['metadata']+' '+table['context'])):return None
    entries=[];total=None
    for row in table['rows'][table['rows'].index(header)+1:]:
        if len(row)<=col:continue
        label=compact(row[0]);value=amount(row[col],dash=True)
        if not label or label in ('구분','구분(단위:천원)'):continue
        if label in ('합계','합계(*)','계'):
            if total is not None:return None
            total=value;continue
        if label not in BORROWING_LABELS|NONBORROWING_LABELS or value is None or value<0:return None
        movements=[amount(v,dash=True) for v in row[1:col+1]]
        if not all(v is not None for v in movements):return None
        if abs(sum(movements[:-1])-movements[-1])>Decimal(len(movements))/2+1:return None
        entries.append(dict(label=label,value=value,borrowing=label in BORROWING_LABELS))
    if not entries or total is None or abs(sum(r['value'] for r in entries)-total)>Decimal(len(entries))/2+1:return None
    labels={r['label'] for r in entries if r['borrowing']}
    if len(labels)!=sum(r['borrowing'] for r in entries):return None
    if len(labels)>1 and labels & {'차입금','총차입금'}:return None
    value=sum(r['value'] for r in entries if r['borrowing'])
    return dict(value=value*table['scale'],label='리스 제외 차입금·사채 합계',method='RECONCILED_ALL_FINANCING_LIABILITIES',
                reconciliation=dict(total=float(total),classified_rows=[dict(r,value=float(r['value'])) for r in entries],
                    zero_basis='EXHAUSTIVE_CURRENT_TABLE_RECONCILED_ALL_ROWS_CLASSIFIED' if value==0 else None))


def capital_debt(table, references):
    context=compact(table['context']+' '+table['metadata'])
    if not any(word in context for word in ('자본관리','자본위험','자본구조')):return None
    col=current_column(table)
    if col is None:return None
    data={compact(r[0]):amount(r[col],dash=True) for r in table['rows'] if len(r)>col}
    debt=data.get('총차입금',data.get('차입금'))
    if debt is None or debt<0:return None
    if data.get('부채') is None or data.get('자본') is None:return None
    if not (close_to(data.get('부채',-1)*table['scale'],references.get('Liabilities'),table['scale']) and
            close_to(data.get('자본',-1)*table['scale'],references.get('Equity'),table['scale'])):return None
    return dict(value=debt*table['scale'],label='공시 자본관리 차입금 총액',method='CAPITAL_STRUCTURE_TOTAL_WITH_BALANCE_ANCHORS',
                reconciliation=dict(liabilities=float(data['부채']),equity=float(data['자본'])))


def note_interest(table, finance_costs):
    context=compact(table['context'])
    has_section=any(word in context for word in ('금융손익','금융수익및금융','금융원가','금융비용','금융수익(원가)'))
    if not has_section or finance_costs is None:return None
    col=current_column(table)
    if col is None:return None
    rows=table['rows'];in_costs=False;components=[];interests=[];subtotal=None
    for row in rows:
        label='|'.join(compact(x) for x in row[:col])
        value=amount(row[col],dash=True) if len(row)>col else None
        labels={compact(x) for x in row[:col]}
        interest_labels={label for label in labels if re.sub(r'\((?:금융원가|금융비용)\)$','',label)
                         in ('이자비용','이자비용-기타','기타이자비용')}
        if labels & {'금융원가','금융비용'}:
            if value is not None and labels.issubset({'금융원가','금융비용',''}):subtotal=value
            in_costs=True
        if interest_labels and value is not None:
            interests.append(value)
        if value is not None and any(x in {'기타금융비용','기타금융원가'} for x in labels):
            # A generic residual can contain more interest. Its contents must
            # be disclosed before the explicit interest rows are exhaustive.
            return None
        if in_costs and labels & {'소계','합계','계'} and value is not None:
            subtotal=value;break
        if in_costs and value is not None and not labels.issubset({'금융원가','금융비용',''}):
            components.append(value)
    # Some issuers publish a standalone financial-expense table with one line.
    if not in_costs and '금융비용' in context and interests:
        values=[amount(r[col],dash=True) for r in rows if len(r)>col]
        values=[v for v in values if v is not None]
        if len(values)==1:subtotal=interests[0]
    if not interests or subtotal is None or subtotal==0:return None
    scale=table['scale']
    if not close_to(abs(subtotal)*scale,abs(finance_costs),scale):return None
    if any(interest*subtotal<0 for interest in interests):return None
    # Validate the explicit expense subsection total where individual components
    # are in separate rows. Row-spanned category labels are not summed twice.
    if components and abs(sum(components)-subtotal)>Decimal(len(components))/2+1:return None
    return dict(value=abs(sum(interests))*scale,label='손익 금융비용 주석 이자비용',method='FINANCE_COST_SUBTOTAL_RECONCILED',
                reconciliation=dict(finance_costs_krw=finance_costs,quoted_subtotal=float(subtotal),
                    raw_interest_components=[float(x) for x in interests],
                    maximum_rounding_error_krw=len(interests)*scale/2,expense_sign='MATCHED_COST_SUBTOTAL'))


def audit_note(root, division):
    results=[]
    for table in (n for n in root.iter() if tag(n)=='TABLE'):
        rows=grid(table)
        if not rows:continue
        header=next((r for r in rows[:2] if '감사의견' in [compact(c) for c in r] and
                     any('계속기업' in compact(c) for c in r)),None)
        if not header:continue
        opinion=next(i for i,c in enumerate(header) if compact(c)=='감사의견')
        concern=next(i for i,c in enumerate(header) if '계속기업' in compact(c))
        emphasis=next((i for i,c in enumerate(header) if compact(c)=='강조사항'),None)
        kind=next((i for i,c in enumerate(header) if compact(c)=='구분'),None)
        if emphasis is None or kind is None:continue
        target='연결감사보고서' if division=='CFS' else '감사보고서'
        for row in rows:
            if len(row)<=max(opinion,concern,emphasis,kind):continue
            if not re.search(r'당기|\(당\)',compact(row[0])) or compact(row[kind])!=target:continue
            empty={'-','해당사항없음','해당없음','없음'}
            clean=compact(row[opinion]) in ('적정','적정의견')
            no_concern=compact(row[concern]) in empty and compact(row[emphasis]) in empty
            modified=compact(row[opinion]) in ('한정','한정의견','부적정','부적정의견','의견거절')
            results.append(dict(state='FAIL' if modified else 'PASS' if clean and no_concern else 'REVIEW_REQUIRED',
                opinion=row[opinion],going_concern=row[concern],emphasis=row[emphasis],scope=target))
    return results[0] if len(results)==1 else dict(state='REVIEW_REQUIRED',reason='AUDIT_NOTE_SCOPE_AMBIGUOUS')


def normalize_notes(document, xbrl, identity, references, finance_costs=None, known_debt_floor=0):
    result=dict(identity=identity,metrics={},findings=[],errors=[])
    try:
        root,section,name=original_document(document,identity)
        verified=inspect_archive(xbrl,identity['division'],identity['fiscal_year'],identity['corp_code'],references)
        if not verified.get('xbrl_evidence',{}).get('reference_balance_matches'):
            raise ValueError('NOTE_XBRL_BALANCE_ANCHOR_UNVERIFIED')
        source_sha=hashlib.sha256(document).hexdigest()
        xbrl_total=verified.get('xbrl_evidence',{}).get('disclosed_totals',{}).get('loans_plus_bonds')
        candidates={name:[] for name in ('interest_expense','interest_bearing_debt_excluding_leases')}
        for table in tables_with_context(section):
            if table['scale'] is None:continue
            debt=capital_debt(table,references) or financing_debt(table) or transposed_financing_debt(table)
            interest=note_interest(table,finance_costs)
            for metric,fact in (('interest_bearing_debt_excluding_leases',debt),('interest_expense',interest)):
                if not fact:continue
                if metric.startswith('interest_bearing') and float(fact['value'])+table['scale']/2<known_debt_floor:
                    result['errors'].append('NOTE_DEBT_BELOW_VERIFIED_COMPONENTS');continue
                if metric.startswith('interest_bearing') and xbrl_total is not None and not close_to(fact['value'],xbrl_total,table['scale']):
                    result['errors'].append('NOTE_DEBT_XBRL_TOTAL_MISMATCH');continue
                provenance=dict(**identity,account_name=fact['label'],unit=table['unit'],precision_krw=table['scale'],
                    receipt_source_file=name,document_sha256=source_sha,xbrl_sha256=hashlib.sha256(xbrl).hexdigest(),
                    table_index=table['index'],context=table['context'][-500:],method=fact['method'],
                    reconciliation=fact['reconciliation'],verification_state='VALIDATED_ENTITY_PERIOD_SCOPE_UNIT_AND_TOTAL',
                    source_url='https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+identity['receipt_no'])
                candidates[metric].append(dict(value=float(fact['value']),provenance=provenance))
        for metric,facts in candidates.items():
            if not facts:continue
            # Separate redundant note occurrences from conflicting evidence.
            first=facts[0]
            if any(abs(f['value']-first['value'])>
                   (f['provenance']['precision_krw']+first['provenance']['precision_krw'])/2+1 for f in facts):
                result['errors'].append('CONFLICTING_NOTE_'+metric.upper());continue
            result['metrics'][metric]=min(facts,key=lambda f:f['provenance']['precision_krw'])
        result['audit']=audit_note(root,identity['division'])
        result['state']='VALIDATED_ORIGINAL_NOTE_EVIDENCE'
    except (ValueError,KeyError,zipfile.BadZipFile,UnicodeError) as exc:
        result.update(state='REVIEW_REQUIRED',reason=str(exc) if isinstance(exc,ValueError) else type(exc).__name__)
    return result


def enrich_financial_notes(cache, key, identity, references, metrics, audit, document_fetch=None):
    from c3_balanced_source_probe import DocumentCache
    from c3_dart_document_evidence import download_document
    docs=DocumentCache(cache.root/'documents')
    try:
        payloads=[]
        for endpoint in ('document.xml','fnlttXbrl.xml'):
            binary=docs.get(endpoint,identity['receipt_no'],'11011',key,document_fetch or download_document)
            if not zipfile.is_zipfile(io.BytesIO(binary)):
                observed=inspect_archive(binary,identity['division'])
                status=observed.get('api_status')
                docs.events[-1]['api_status']=status
                if status not in ('013','014'):raise ValueError('NOTE_DOCUMENT_API_ERROR_'+str(status))
                return dict(state='REVIEW_REQUIRED',reason='ORIGINAL_NOTE_FILE_UNAVAILABLE',api_status=status)
            payloads.append(binary)
        floor=sum(v for v in metrics.get('debt_components',[]) if isinstance(v,(int,float)) and v>=0)
        result=normalize_notes(*payloads,identity,references,metrics.get('finance_costs'),floor)
        if result.get('errors'):raise ValueError('NOTE_FINANCIAL_COMPONENT_MISMATCH')
        if result.get('reason') in ('DOCUMENT_COMPANY_MISMATCH','DOCUMENT_PERIOD_MISMATCH'):
            raise ValueError(result['reason'])
        for name,fact in result['metrics'].items():
            existing=metrics.get(name)
            if existing is not None and not close_to(fact['value'],existing,fact['provenance']['precision_krw']):
                raise ValueError('DIRECT_AND_NOTE_FINANCIAL_MISMATCH')
            if name=='interest_bearing_debt_excluding_leases' and metrics.get('unresolved_debt_accounts'):
                fact['qualification_use']='BLOCKED_UNCLASSIFIED_PRIMARY_DEBT';continue
            if existing is None:
                metrics[name]=fact['value']
                metrics.setdefault('metric_sources',{})[name]=fact['provenance']
                fact['qualification_use']='MISSING_DIRECT_VALUE_FILLED_AFTER_VALIDATION'
                if name=='interest_bearing_debt_excluding_leases':metrics['debt_scope_state']='RECONCILED_ORIGINAL_NOTE_TOTAL'
        source_audit=result.get('audit',{})
        if audit.get('state')=='PASS' and source_audit.get('state')=='FAIL':
            raise ValueError('AUDIT_SOURCE_MISMATCH')
        if audit.get('state')=='REVIEW_REQUIRED' and source_audit.get('state') in ('PASS','FAIL'):
            audit.update(state=source_audit['state'],opinions=[source_audit['opinion']],
                going_concern_basis='CURRENT_ORIGINAL_AUDIT_TABLE_EXPLICIT_OPINION_AND_NO_UNCERTAINTY',
                original_document_evidence={**identity,**source_audit,
                    'sha256':hashlib.sha256(payloads[0]).hexdigest()})
        return result
    finally:
        cache.events.extend(docs.events)


def insurance_capital_disclosure(binary, identity):
    """Expose latest official K-ICS availability without a manufacturing pass.

    An unpublished quarter is not replaced with a previous annual ratio.
    Solvency tables may cover different regulatory scopes: keep each table.
    """
    receipt=identity['receipt_no'];year=identity['fiscal_year']
    report=identity.get('report_code','11014')
    if not zipfile.is_zipfile(io.BytesIO(binary)):
        checked=inspect_archive(binary,'OFS');status=checked.get('api_status')
        if status not in ('013','014'):raise ValueError('INSURANCE_DOCUMENT_API_ERROR_'+str(status))
        return dict(state='REVIEW_REQUIRED',reason='INSURANCE_CAPITAL_DISCLOSURE_UNAVAILABLE',api_status=status)
    with zipfile.ZipFile(io.BytesIO(binary)) as z:
        name=receipt+'.xml'
        if name not in z.namelist():return dict(state='REVIEW_REQUIRED',reason='INSURANCE_ORIGINAL_UNAVAILABLE')
        raw=z.read(name)
    if b'<!ENTITY' in raw.upper():raise ValueError('DOCUMENT_ENTITY_FORBIDDEN')
    parser=ReviewDocumentParser();parser.feed(raw.decode('utf-8'));root=parser.root
    corp={str({k.upper():v for k,v in n.attrib.items()}.get('AREGCIK','')) for n in root.iter() if tag(n)=='COMPANY-NAME'}
    if corp!={identity['corp_code']}:raise ValueError('DOCUMENT_COMPANY_MISMATCH')
    covers=[n for n in root.iter() if tag(n)=='COVER'];ends=set()
    for cover in covers:
        for n in cover.iter():
            attrs={k.upper():v for k,v in n.attrib.items()}
            if attrs.get('AUNIT')=='PERIODTO':ends.add(attrs.get('AUNITVALUE'))
    end={'11013':f'{year}0331','11012':f'{year}0630','11014':f'{year}0930','11011':f'{year}1231'}[report]
    if ends!={end}:raise ValueError('DOCUMENT_PERIOD_MISMATCH')
    found=[]
    for index,table in enumerate(n for n in root.iter() if tag(n)=='TABLE'):
        rows=grid(table)
        if not rows or len(rows)>20:continue
        # Take the explicitly published current-quarter column (first fiscal
        # column), preserving the header and all previous-period cells as text.
        header=next((r for r in rows[:2] if len(r)>1 and ('분기' in r[1] or str(year) in r[1])),None)
        if not header:continue
        ratios=[r for r in rows if len(r)>1 and '지급여력비율' in compact(r[0])]
        for row in ratios:
            found.append(dict(table_index=index,header=header,account_name=row[0],current_raw=row[1],
                current_value= float(amount(row[1])) if amount(row[1]) is not None else None,
                prior_raw=row[2:],unit='PERCENT',verification_state='VERIFIED_ORIGINAL_CURRENT_PERIOD_COLUMN',
                **identity,document_sha256=hashlib.sha256(binary).hexdigest()))
    unpublished=bool(found) and all('산출중' in compact(r['current_raw']) for r in found)
    return dict(state='REVIEW_REQUIRED',reason='CURRENT_KICS_NOT_PUBLISHED' if unpublished else 'INSURANCE_SPECIAL_MODEL_REQUIRED',
                current_period_end=end,disclosures=found,manufacturing_model_applied=False,
                prior_period_not_substituted=True)
