"""Reconcile supported original-note layouts; no issuer exceptions or risk changes."""
from decimal import Decimal
import re
from c3_dart_normalization import amount, compact, close_to, current_column, BORROWING_LABELS, NONBORROWING_LABELS


def column_financing_debt(table):
    """An exhaustive IAS7 roll-forward can omit a separate grand-total column.

    Every disclosed financing-liability column must be classified and reconcile
    beginning + all disjoint movements = closing. Missing cells stay unknown.
    """
    meta=compact(table['metadata']);context=compact(table['context'])
    if not ('당기' in meta and '전기' not in meta and '재무활동' in context and '부채' in context
            and any(s in context for s in ('조정','변동'))):return None
    rows=table['rows']
    begin=next((r for r in rows if len(r)>2 and '기초부채' in compact(r[0]) and compact(r[0])==compact(r[1])),None)
    end=next((r for r in rows if len(r)>2 and '기말부채' in compact(r[0]) and compact(r[0])==compact(r[1])),None)
    if begin is None or end is None:return None
    header=next((r for r in rows[:3] if len(r)==len(end) and not any(compact(c) for c in r[:2])
                 and all(compact(c) in BORROWING_LABELS|NONBORROWING_LABELS for c in r[2:])),None)
    if header is None:return None
    labels=[compact(c) for c in header[2:]]
    if len(labels)!=len(set(labels)) or not labels or '총차입금' in labels:return None
    if '차입금' in labels and any(l in BORROWING_LABELS-{'차입금','사채','전환사채','유동전환사채','비유동전환사채','유동사채','유동성사채','비유동사채'} for l in labels):return None
    start,stop=rows.index(begin),rows.index(end)
    if start>=stop:return None
    movements=[];parents=set();children=set()
    for row in rows[start+1:stop]:
        if len(row)!=len(end):return None
        values=[amount(x,dash=True) for x in row[2:]]
        if all(not compact(x) for x in row[2:]):continue  # explicit abstract/group heading
        if any(v is None for v in values):return None
        a,b=compact(row[0]),compact(row[1])
        if not a or not b:return None
        (parents if a==b else children).add(a)
        movements.append(values)
    if not movements or parents & children:return None  # never sum parent and child movements twice
    closing=[amount(v,dash=True) for v in end[2:]]
    opening=[amount(v,dash=True) for v in begin[2:]]
    if any(v is None or v<0 for v in opening+closing):return None
    for i in range(len(labels)):
        if abs(opening[i]+sum(v[i] for v in movements)-closing[i])>Decimal(len(movements)+2)/2+1:return None
    borrow=[l in BORROWING_LABELS for l in labels]
    count=sum(borrow)
    if not count:return None  # zero-debt recovery continues to require the existing explicit total
    value=sum(v for v,b in zip(closing,borrow) if b)*table['scale']
    return dict(value=value,precision_krw=count*table['scale'],label='완전한 재무활동 부채 변동표의 리스 제외 차입·사채 합계',
        method='RECONCILED_COMPLETE_COLUMN_FINANCING_LIABILITIES',reconciliation=dict(
            total_column_present=False,all_columns_classified=True,movements_reconciled=True,
            maximum_rounding_error_krw=count*table['scale']/2,
            classified_columns=[dict(label=l,value=float(v),value_krw=int(v*table['scale']),borrowing=b,
                group='bonds' if '사채' in l else 'loans' if b else 'nonborrowing') for l,v,b in zip(labels,closing,borrow)]))


def standard_interest_breakdown(table, finance_costs, facts):
    """Match explicit IS interest to same-context standard XBRL and a full note tree."""
    if finance_costs is None:return None
    col=current_column(table)
    if col is None:return None
    records={};category=None
    for row in table['rows']:
        if len(row)<=col:continue
        labels=[compact(x) for x in row[:col]]
        if not labels or labels[0] not in ('금융원가','금융비용'):continue
        path=[]
        for label in labels:
            if label and (not path or label!=path[-1]):path.append(label)
        value=amount(row[col],dash=True)
        if value is None:continue
        key=tuple(path)
        if key in records:return None
        records[key]=value;category=category or key[0]
        if key[0]!=category:return None
    if not category or (category,) not in records:return None
    total=records[(category,)];roots={k:v for k,v in records.items() if len(k)==2}
    if not roots or total==0 or not close_to(abs(total)*table['scale'],abs(finance_costs),table['scale']):return None
    if abs(sum(roots.values())-total)>Decimal(len(roots))/2+1:return None
    for path,value in records.items():
        children={k:v for k,v in records.items() if len(k)==len(path)+1 and k[:-1]==path}
        if children and abs(sum(children.values())-value)>Decimal(len(children))/2+1:return None
    interests=[v for k,v in roots.items() if re.sub(r'\((?:금융원가|금융비용)\)$','',k[-1]) in ('이자비용','이자비용-기타','기타이자비용')]
    if not interests or any(v*total<0 for v in interests):return None
    quoted=abs(sum(interests))*table['scale'];matches=[]
    for interest in facts:
        if interest['account'] not in ('InterestExpenseFinanceExpense','InterestExpense') or interest['value']<0:continue
        cost=[f for f in facts if f['account']=='FinanceCosts' and f['context']==interest['context']]
        if not cost or any(not close_to(f['value'],finance_costs,max(table['scale'],f['precision_krw'])) for f in cost):continue
        if close_to(quoted,interest['value'],max(len(interests)*table['scale'],interest['precision_krw'])):
            matches.append(interest)
    if not matches:return None
    first=min(matches,key=lambda x:x['precision_krw'])
    if any(abs(x['value']-first['value'])>(x['precision_krw']+first['precision_krw'])/2+1 for x in matches):return None
    return dict(value=first['value'],precision_krw=first['precision_krw'],
        label='표준 손익 이자비용 및 주석 계층 합계 대조',method='STANDARD_IS_INTEREST_AND_NOTE_HIERARCHY_RECONCILED',
        reconciliation=dict(finance_costs_krw=finance_costs,quoted_cost_total_krw=float(abs(total)*table['scale']),
            quoted_interest_krw=float(quoted),standard_interest_fact=first,component_count=len(roots),
            maximum_rounding_error_krw=first['precision_krw']/2,
            parent_child_double_counted=False,other_costs_not_used_as_interest=True))


def primary_debt_covered(metrics, fact):
    """Resolve only a recognized standard roll-up, matched to complete note groups."""
    if fact['provenance']['method']!='RECONCILED_COMPLETE_COLUMN_FINANCING_LIABILITIES':return False
    unresolved=metrics.get('unresolved_debt_accounts',[])
    allowed={'ifrs-full_CurrentLoansReceivedAndCurrentPortionOfNoncurrentLoansReceived':'loans'}
    if not unresolved or any(r['account_id'] not in allowed or r.get('value') is None or r['value']<0 for r in unresolved):return False
    groups={'loans':0,'bonds':0};seen=set()
    for name,item in metrics.get('direct_account_evidence',{}).items():
        if name=='interest_expense':continue
        if item.get('state') not in ('VALID','UNAVAILABLE'):return False
        for source in item.get('sources',[]):
            identity=(source['account_id'],source.get('account_name'))
            if identity in seen:return False
            seen.add(identity);groups['bonds' if 'bonds' in name else 'loans']+=source['value']
    # A reported total current-loan roll-up cannot be added to its short/current children.
    if any(metrics.get('direct_account_evidence',{}).get(n,{}).get('value') is not None for n in ('short_term_borrowings','current_portion_long_term_borrowings')):return False
    for row in unresolved:groups[allowed[row['account_id']]]+=row['value']
    columns=fact['provenance']['reconciliation']['classified_columns'];unit=fact['provenance']['source_table_scale']
    for group in groups:
        selected=[r for r in columns if r.get('group')==group]
        if not selected and groups[group]:return False
        if abs(sum(r['value_krw'] for r in selected)-groups[group])>len(selected)*unit/2+1:return False
    return True
