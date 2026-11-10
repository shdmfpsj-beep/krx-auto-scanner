"""Read-only multi-gate evaluation of the preserved real C3 preliminary TOP20.

Never reconstruct support/resistance from a single close or approve trading on
estimated turnover, unknown share type, or unverified financial statements.
"""
import json
from pathlib import Path
from c3_entry_geometry_gate import assess

def evaluate(snapshot, evidence=None):
    if snapshot.get('schema')!='C3_REAL_SCAN_PRELIMINARY_TOP20_V1':raise ValueError('INVALID_TOP20_SCHEMA')
    rows=snapshot.get('candidates')
    if not isinstance(rows,list) or len(rows)!=snapshot.get('top_n'):raise ValueError('TOP20_COUNT_MISMATCH')
    if snapshot.get('orders_enabled') is not False or snapshot.get('trade_approved') is not False:raise ValueError('UNSAFE_INPUT')
    if snapshot.get('entry_eligible_top2')!=[]:raise ValueError('PREAPPROVED_TOP2_FORBIDDEN')
    if not isinstance(evidence,dict):evidence={}
    seen=set();audits=[];watch=[]
    for expected_rank,row in enumerate(rows,1):
        ticker=row.get('ticker')
        if ticker in seen or row.get('rank')!=expected_rank:raise ValueError('DUPLICATE_OR_REORDERED')
        seen.add(ticker)
        reasons=[]
        if row.get('price_asof')!=snapshot['asof']:reasons.append('ASOF_MISMATCH')
        if row.get('instrument_type')!='COMMON_STOCK' or row.get('eligibility')!='REVIEW':
            reasons.append('COMMON_SHARE_NOT_CERTIFIED')
        if row.get('turnover_source')!='KRX_OFFICIAL_REGULAR_SESSION':
            reasons.append('REGULAR_TURNOVER_NOT_VERIFIED')
        item=evidence.get(ticker)
        if not isinstance(item,dict):
            reasons.extend(['DATED_OHLCV_NOT_AVAILABLE','ENTRY_PLAN_NOT_AVAILABLE','FINANCIALS_NOT_VERIFIED'])
            geometry=None
        else:
            if item.get('source_price_asof')!=snapshot['asof'] or item.get('source_regular_only_certified') is not True:
                reasons.append('DATED_REGULAR_PRICE_NOT_VERIFIED')
            if item.get('financials_asof_verified') is not True or item.get('financial_stability_pass') is not True:
                reasons.append('FINANCIALS_NOT_VERIFIED')
            geometry=assess(item,item.get('chart_bars'))
            reasons.extend(geometry['reasons'])
        entry={'rank':expected_rank,'ticker':ticker,'name':row.get('name'),
               'eligible_for_research_watch':not reasons,'blocking_reasons':list(dict.fromkeys(reasons)),
               'geometry':geometry}
        audits.append(entry)
        if not reasons:watch.append(entry)
    # Research watch candidates are not registered signals or buy approvals.
    selected=watch[:2]
    return {'schema':'C3_TOP20_MULTIGATE_REVIEW_V1','asof':snapshot['asof'],
            'source_sha256':snapshot['source_sha256'],'audited_count':len(audits),
            'audits':audits,'research_watch_top2':selected,'vacancies':2-len(selected),
            'current_action':'CASH','trade_approved':False,'orders_enabled':False,
            'registered_signals_created':0,'source_mutated':False,
            'thresholds_status':'RESEARCH_PROVISIONAL_NOT_BACKTESTED'}

def run(source,out,evidence_path=None):
    snapshot=json.loads(Path(source).read_text(encoding='utf-8'))
    evidence=json.loads(Path(evidence_path).read_text(encoding='utf-8')) if evidence_path else None
    result=evaluate(snapshot,evidence)
    target=Path(out);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('C3_TOP20_MULTIGATE '+json.dumps({'asof':result['asof'],'audited':result['audited_count'],
        'research_watch':len(result['research_watch_top2']),'vacancies':result['vacancies'],
        'action':result['current_action']},ensure_ascii=False))
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True);p.add_argument('--evidence')
    a=p.parse_args();run(a.source,a.out,a.evidence)
