"""Revalidate existing real candidate inputs; no operating writes or delivery.

Live mode refreshes routing and filing catalogues through existing OpenDART.
Offline mode is explicitly a hash-verified source replay, never a fresh fetch.
"""
import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from c3_balanced_financials import SnapshotCache, collect_balanced, digest
from c3_top5_financial_selection import attach_support_evidence, select


def validate(source, out, live=False):
    def read(name):return json.loads((source/name).read_text())
    out.mkdir(parents=True,exist_ok=True)
    inputs=read('financial_pool_input.json');before=read('financial_pool_gate.json')
    geometry=read('entry_geometry_audit.json');pool=read('qualified_chart_pool.json')
    if len({r['asof'] for r in (inputs,before,geometry,pool)})!=1:
        raise ValueError('SOURCE_ASOF_MISMATCH')
    asof=datetime.strptime(inputs['asof'],'%Y%m%d').date()
    target=out/'financial_cache'
    if target.exists():raise ValueError('VALIDATION_OUTPUT_ALREADY_EXISTS')
    shutil.copytree(source/'financial_cache',target)
    cache=SnapshotCache(target)
    stocks=[dict(ticker=r['code'],name=r.get('name','')) for r in inputs['candidates']]
    kwargs={}
    if not live:
        observations={}
        for path in (target/'observations').rglob('*.json'):
            r=json.loads(path.read_text())
            if digest(r['payload'])!=r['sha256']:raise ValueError('OBSERVATION_INTEGRITY_ERROR')
            identity=r['identity'];key=digest(dict(endpoint=identity['endpoint'],params=identity['params']))
            if key not in observations or observations[key]['observed_at']<r['observed_at']:observations[key]=r
        def request(endpoint,params,key):
            identity=digest(dict(endpoint=endpoint,params=params))
            if identity not in observations:raise ValueError('REPLAY_RESPONSE_UNAVAILABLE')
            return observations[identity]['payload']
        def forbidden(*args):raise ValueError('REPLAY_DOCUMENT_UNAVAILABLE')
        kwargs.update(request=request,document_fetch=forbidden)
    key=(os.environ.get('DART_API_KEY') or os.environ.get('OPENDART_API_KEY') or os.environ.get('OPEN_DART_API_KEY')) if live else 'a'*40
    result=collect_balanced(asof,stocks,key,datetime.now(timezone.utc).date(),cache,**kwargs)
    # These are the production bridge's policies, not collector defaults.
    for field in ('request_scope','aggregate_policy'):
        if field in before:result[field]=before[field]
    selected=select(attach_support_evidence(geometry,pool),result)
    rows=result['researched']+result['excluded'];old={r['ticker']:r for r in before['researched']+before['excluded']}
    summary=dict(asof=inputs['asof'],source_mode='LIVE_CATALOGUE_RECEIPT_KEYED_ORIGINALS' if live else 'VERIFIED_ARTIFACT_REPLAY',
        observed_at=datetime.now(timezone.utc).isoformat(),counts={},operational_status=selected['operational_status'],
        approval_required_codes=selected['approval_required_codes'],approval_financial_complete=selected['approval_financial_complete'],companies=[])
    for row in rows:
        verdict=row.get('financial_decision',row.get('financial_verdict','ERROR'))
        summary['counts'][verdict]=summary['counts'].get(verdict,0)+1
        summary['companies'].append(dict(ticker=row['ticker'],name=row.get('name'),before=old[row['ticker']].get('financial_decision'),
            after=verdict,annual_receipt=row.get('annual_receipt_no'),interim_receipt=row.get('interim_receipt_no'),
            missing=row.get('risk_assessment',{}).get('mandatory_missing'),error=row.get('error')))
    for name,payload in [('financial_pool_gate.json',result),('financial_selection_research.json',selected),('validation_summary.json',summary)]:
        (out/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    print('C3_REQUIRED_FINANCIAL_VALIDATION',json.dumps(summary,ensure_ascii=False))
    if live and not any(r.get('financial_decision')=='ERROR' for r in rows):
        # Investigate only unresolved candidates that can currently be approved.
        remaining=[r for r in rows if r['ticker'] in selected['approval_required_codes'] and r.get('financial_decision')=='REVIEW_REQUIRED']
        if remaining:
            from c3_balanced_source_probe import capture
            capture(dict(asof=inputs['asof'],researched=remaining,excluded=[]),cache,out/'required_source_probe',key)
    if any(r.get('financial_decision')=='ERROR' for r in rows) or result.get('error'):
        raise ValueError('LIVE_FINANCIAL_VALIDATION_ERROR')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--live',action='store_true')
    args=parser.parse_args();validate(args.source,args.out,args.live)
