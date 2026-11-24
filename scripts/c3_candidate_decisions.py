"""Explain every technical candidate, including finance review and non-buy states."""
import argparse
import csv
import json
from pathlib import Path
from c3_top5_financial_selection import valid_entry


def report(receipt, geometry, selection, financial):
    evidence = {x['ticker']: x for x in financial.get('researched', []) + financial.get('excluded', [])}
    verdicts = selection.get('financial_verdicts', {})
    rows = []
    for c in geometry.get('candidates', []):
        item = evidence.get(c['code'], {})
        verdict = verdicts.get(c['code'], 'REVIEW_REQUIRED')
        collection_error = financial.get('error') if not evidence else None
        if collection_error:
            verdict = 'ERROR'
        reasons = list(c.get('rejection_reasons', []))
        risk = item.get('risk_assessment', {})
        scope=selection.get('technical_approval_scope',{}).get(c['code'],{})
        reasons += item.get('exclusion_reasons', [])
        reasons += risk.get('mandatory_missing', [])
        if item.get('error'):
            reasons.append(item['error'])
        if collection_error:
            reasons.append(collection_error)
        if verdict == 'ERROR':
            state = 'ERROR'
        elif verdict == 'REJECTED_FINANCIAL_RISK' or not c.get('geometry_validated'):
            state = 'REJECTED'
        elif verdict != 'PASS':
            state = 'REVIEW_REQUIRED'
        elif valid_entry(c):
            state = c['entry_status']
        else:
            state = 'WATCH'
        if c.get('geometry_validated') and not valid_entry(c):
            reasons.append('OUTSIDE_EXISTING_2PCT_NEAR_ENTRY_GATE')
        if not item:
            reasons.append('FINANCIAL_REVIEW_NOT_COMPLETED')
        rows.append(dict(code=c['code'], name=c.get('name'), technical_score=c.get('score'),
            opportunity_score=c.get('opportunity_score'), financial_verdict=verdict,
            financial_quality_score=item.get('quality_100', {}).get('score'),
            financial_score_available_points=item.get('quality_100', {}).get('available_points'),
            statement_division=item.get('statement_division'),
            annual_filing_date=item.get('filing_date'), interim_filing_date=item.get('interim_filing_date'),
            annual_receipt_no=item.get('annual_receipt_no'), interim_receipt_no=item.get('interim_receipt_no'),
            entry_low=c.get('entry_low') if c.get('geometry_validated') else None,
            entry_high=c.get('entry_high') if c.get('geometry_validated') else None,
            stop_ref=c.get('stop_ref') if c.get('geometry_validated') else None,
            risk_pct=c.get('risk_pct'), attempted_entry_low=c.get('attempted_entry_low', c.get('entry_low')),
            attempted_entry_high=c.get('attempted_entry_high', c.get('entry_high')),
            structural_stop_diagnostic=c.get('structural_stop_diagnostic'),
            technical_status=c.get('entry_status'), status=state,
            approval_scope='REQUIRED' if scope.get('required') else 'NOT_REQUIRED' if scope.get('verified') else 'UNVERIFIED',
            financial_blocks_execution=c['code'] in selection.get('approval_required_codes',[]) and verdict in ('ERROR','REVIEW_REQUIRED'),
            approval_scope_reason=scope.get('reason'),
            top5=any(x['code']==c['code'] for x in selection.get('selected', [])),
            reasons=list(dict.fromkeys(reasons))))
    integrity = receipt.get('source_integrity', {})
    market = integrity.get('market_rows_latest', {})
    counts = {state: sum(r['financial_verdict']==state for r in rows) for state in
              ('PASS', 'REJECTED_FINANCIAL_RISK', 'REVIEW_REQUIRED', 'ERROR')}
    summary = dict(market_symbols=sum(market.get(k, 0) for k in ('kospi_rows', 'kosdaq_rows')),
        valid_60_session_symbols=receipt.get('valid_60_session_symbols'),
        technical_candidates=len(rows), financial_requested=selection.get('financial_requested_count', 0),
        financial_processed=len(evidence), financial_collection_error=financial.get('error'),
        financial_decisions=counts,
        invalid_entry_zone=sum('INVALID_ENTRY_ZONE' in r['reasons'] for r in rows),
        risk_above_5pct=sum('RISK_ABOVE_5PCT' in r['reasons'] for r in rows),
        **{state.lower():sum(r['status']==state for r in rows) for state in
           ('ENTRY_READY', 'NEAR_ENTRY', 'WATCH', 'REJECTED', 'REVIEW_REQUIRED', 'ERROR')},
        technical_watch=sum(c.get('geometry_validated') and c.get('entry_status')=='WATCH'
                            for c in geometry.get('candidates', [])),
        final_top5=selection.get('selected_count', 0))
    summary.update(approval_required=selection.get('approval_required_count'),
        approval_financial_complete=selection.get('approval_financial_complete'),
        nonblocking_financial_unverified=len(selection.get('nonblocking_financial_unverified_codes',[])),
        comparison_conservative_operational_status=selection.get('comparison_conservative_operational_status'))
    outcome = selection.get('operational_status', 'ERROR')
    reason = ('NO_FINANCIAL_AND_TECHNICAL_ENTRY_INTERSECTION' if outcome=='CASH_NO_ELIGIBLE'
              else 'MANDATORY_FINANCIAL_EVIDENCE_PENDING' if outcome=='HOLD_FINANCIAL_UNVERIFIED'
              else outcome)
    return dict(schema='C3_CANDIDATE_DECISIONS_V1', asof=geometry.get('asof'),
        operational_status=outcome, reason=reason, summary=summary, candidates=rows,
        trade_approved=False, user_executes_trades=True)


def save(root, result):
    root.mkdir(parents=True, exist_ok=True)
    (root/'candidate_decisions.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    fields = ['name','code','technical_score','financial_verdict','financial_quality_score',
              'entry_low','entry_high','stop_ref','risk_pct','status','top5','reasons',
              'annual_filing_date','interim_filing_date','approval_scope','financial_blocks_execution','approval_scope_reason']
    with (root/'candidate_decisions.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows({**r, 'reasons':' | '.join(r['reasons'])} for r in result['candidates'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    root = parser.parse_args().root
    data = [json.loads((root/(name+'.json')).read_text()) for name in
            ('receipt','entry_geometry_audit','financial_selection_research','financial_pool_gate')]
    result = report(*data)
    save(root, result)
    print('C3_CANDIDATE_DECISIONS', json.dumps(result['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
