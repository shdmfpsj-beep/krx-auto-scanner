"""Unapproved policy comparison on immutable sources. No network or delivery.

This module is not imported by the daily workflow or production selector.
Financial criteria, technical geometry and ranking are the existing functions.
"""
import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from c3_top5_financial_selection import select, attach_support_evidence, classify
from c3_watch5_delivery import choose


def compare(geometry, pool, financial, report, blocked, clock=None):
    asof=geometry.get('asof')
    if any(v.get('asof')!=asof for v in (pool,financial,report)):raise ValueError('COMPARISON_DATE_MISMATCH')
    if not isinstance(blocked,set):raise ValueError('HISTORY_EVIDENCE_REQUIRED')
    original=copy.deepcopy((geometry,pool,financial,report))
    observed=select(attach_support_evidence(copy.deepcopy(geometry),pool),financial)
    rows=financial.get('researched',[])+financial.get('excluded',[])
    approved={r['ticker'] for r in rows if classify(r,asof)=='QUALIFIED_BASIC_FINANCIAL_RISK'}
    if blocked & {r['code'] for r in observed['selected']}:raise ValueError('HISTORY_NOT_APPLIED')
    forbidden={r['ticker']:r.get('financial_decision',r.get('financial_verdict')) for r in rows if r['ticker'] not in approved}
    system_block=(observed.get('shared_system_error') or bool(financial.get('error')) or observed['operational_status']=='HOLD_DATA_INCOMPLETE'
        or bool(observed.get('technical_scope_unverified_codes')))
    if system_block:
        independent=copy.deepcopy(observed)
    else:
        subset={**copy.deepcopy(geometry),'candidates':[r for r in geometry['candidates'] if r['code'] in approved and r['code'] not in blocked]}
        codes={r['code'] for r in subset['candidates']}
        evidence={**copy.deepcopy(financial),'researched':[r for r in financial.get('researched',[]) if r['ticker'] in codes],
            'excluded':[r for r in financial.get('excluded',[]) if r['ticker'] in codes]}
        independent=select(attach_support_evidence(subset,pool),evidence)
    watches=choose(report,independent,blocked) if not system_block else []
    # The report is a comparison, never a new official execution_outcome.
    prices={r['code']:r for r in pool['candidates']}
    def details(row):
        code=row['code'];source=prices[code]
        result={k:source.get(k) for k in ('code','name','close','entry_low','entry_high','stop_ref','risk_pct','r1_ref','r2_ref','entry_status')}
        result.update(financial_verdict='PASS',entry_valid_until=pool.get('entry_valid_until'),
            exact_risk_pct=(source['entry_high']-source['stop_ref'])/source['entry_high']*100,
            distance_pct=(source['close']-source['entry_high'])/source['close']*100)
        return result
    for row in independent['selected']+watches:
        if row['code'] not in approved or row['code'] in blocked:raise ValueError('COMPARISON_UNVERIFIED_SELECTION')
    assert original==(geometry,pool,financial,report),'SOURCE_MUTATION'
    clock=clock or datetime.now(timezone.utc)
    deadline=datetime.fromisoformat(pool['entry_valid_until'])
    if deadline.utcoffset() is None:raise ValueError('COMPARISON_VALIDITY_TIMEZONE_REQUIRED')
    return dict(schema='C3_UNAPPROVED_POLICY_COMPARISON_V1',asof=asof,main_policy_changed=False,
        policy_change_requires_explicit_user_approval=True,delivery_authorized=False,telegram_photos_sent=0,
        operating_receipts_created=False,signal_expired=deadline<=clock,
        policy_a=dict(operational_status=observed['operational_status'],top5=observed['selected_count'],watch5=len(choose(report,observed,blocked)),
            approval_required_codes=observed['approval_required_codes'],approval_financial_complete=observed['approval_financial_complete']),
        policy_b=dict(hypothetical_selection_status=independent['operational_status'],top5=len(independent['selected']),watch5=len(watches),
            subset_financial_complete=independent.get('approval_financial_complete',False),
            selected=[details(r) for r in independent['selected']],watch=[details(r) for r in watches],
            excluded_financial_verdicts=forbidden,system_wide_block=bool(system_block)),
        all_interest_financial_complete=observed.get('all_interest_financial_complete'),original_financial_criteria_preserved=True)


def run(source,out):
    source,out=source.resolve(),out.resolve()
    if source==out or source in out.parents or out in source.parents or 'receipts' in out.parts:
        raise ValueError('COMPARISON_OUTPUT_MUST_BE_SEPARATE')
    def read(name):return json.loads((source/name).read_text())
    receipt=read('receipt.json');asof=receipt['asof'];integrity=receipt['source_integrity']
    outcome=read('execution_outcome.json')
    if outcome.get('program_status')!='COMPLETED' or outcome.get('operational_status') in ('ERROR','HOLD_DATA_INCOMPLETE'):
        raise ValueError('COMPARISON_BASELINE_SYSTEM_FAILURE')
    if integrity.get('session_count')!=60 or integrity.get('last_session')!=asof:
        raise ValueError('COMPARISON_PRICE_SOURCE_INCOMPLETE')
    raw=list((source/'krx_source').glob('*.meta.json'))
    if not raw:raise ValueError('COMPARISON_RAW_SOURCE_REQUIRED')
    for path in raw:
        meta=json.loads(path.read_text())
        if Path(meta['file']).name!=meta['file']:raise ValueError('COMPARISON_RAW_SOURCE_PATH')
        blob=(source/'krx_source'/meta['file']).read_bytes()
        if hashlib.sha256(blob).hexdigest()!=meta['sha256'] or meta['asof']>asof:
            raise ValueError('COMPARISON_RAW_SOURCE_INTEGRITY')
    paths=['entry_geometry_audit.json','qualified_chart_pool.json','financial_pool_gate.json','all_candidate_report/manifest.json']
    original={name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in paths+['receipt.json','execution_outcome.json','delivery_result.json','watch_delivery_result.json','duplicate_signal_audit.json']}
    result=compare(*[read(name) for name in paths],set(read('duplicate_signal_audit.json')['blocked_codes']))
    result.update(source_json_sha256=original,source_mode='VERIFIED_REAL_ARTIFACT_REPLAY_NO_NEW_MARKET_FETCH',
        source_certifications={k:integrity.get(k) for k in ('regular_session_price_certified','corporate_actions_certified')})
    out.mkdir(parents=True,exist_ok=True)
    (out/'policy_comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    if any(hashlib.sha256((source/name).read_bytes()).hexdigest()!=sha for name,sha in original.items()):raise ValueError('SOURCE_MUTATION')
    print('C3_POLICY_COMPARISON',json.dumps(result,ensure_ascii=False))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();run(args.source,args.out)
