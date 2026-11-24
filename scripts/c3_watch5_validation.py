"""Replay a verified market artifact through WATCH5 without API calls or writes to its source."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from c3_watch5_delivery import run, image_bytes, write


def validate(source, output, asof=None, source_kind='verified-artifact'):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or source in output.parents or output == Path(__file__).resolve().parents[1]/'output/c3_top5':
        raise ValueError('WATCH_VALIDATION_REQUIRES_SEPARATE_OUTPUT')
    names = ('receipt.json','qualified_chart_pool.json','entry_geometry_audit.json',
             'financial_pool_gate.json','financial_selection_research.json','candidate_decisions.json',
             'duplicate_signal_audit.json','execution_outcome.json','delivery_result.json')
    outcome = json.loads((source/'execution_outcome.json').read_text())
    completed = outcome.get('operational_status') in ('TOP5_READY','CASH_NO_ELIGIBLE')
    names = names if completed else tuple(name for name in names if (source/name).is_file())
    before = {name: hashlib.sha256((source/name).read_bytes()).hexdigest() for name in names}
    source_day = json.loads((source/'receipt.json').read_text()).get('asof') if (source/'receipt.json').is_file() else None
    if asof and source_day and source_day != asof:
        raise ValueError('WATCH_REPLAY_ASOF_MISMATCH')
    output.mkdir(parents=True, exist_ok=True)
    for name in names: shutil.copy2(source/name, output/name)
    if (source/'all_candidate_report').is_dir():
        shutil.copytree(source/'all_candidate_report', output/'all_candidate_report', dirs_exist_ok=True)
    env = {k:v for k,v in os.environ.items() if k not in ('TELEGRAM_BOT_TOKEN','TELEGRAM_CHAT_ID','GH_TOKEN')}
    env.update(C3_FINANCIAL_MODEL='balanced', GITHUB_EVENT_NAME='workflow_dispatch',
               GITHUB_REF_NAME='watch5-artifact-dry-run')
    def forbidden(*a, **k): raise AssertionError('WATCH_VALIDATION_NETWORK_FORBIDDEN')
    result = run(output, env, opener=forbidden)
    after = {name: hashlib.sha256((source/name).read_bytes()).hexdigest() for name in names}
    assert before == after, 'WATCH_VALIDATION_SOURCE_MODIFIED'
    for item in result['selected']: image_bytes(output, item)
    proof = dict(schema='C3_WATCH5_EXECUTION_PROOF_V1', asof=result.get('asof',source_day), requested_asof=asof,
        input_kind=('INCOMPLETE_SOURCE_NO_MARKET_VERIFICATION' if not completed else
                    'ACTUAL_MAIN_KRX_OPENDART_DRY_RUN' if source_kind=='live-output' else
                    'EXISTING_VERIFIED_KRX_OPENDART_ARTIFACT'), status=result['status'],
        official_operational_status=result.get('official_operational_status'),
        official_top5=len(json.loads((source/'financial_selection_research.json').read_text())['selected'])
            if (source/'financial_selection_research.json').is_file() else None,
        watch5=result['selected_count'], final_watch_png_count=len(result['selected']),
        telegram_photos_sent=result['telegram_photos_sent'], actual_telegram_sent=False,
        selected=[{k:r.get(k) for k in ('code','name','asof_close','entry_low','entry_high','stop_ref',
                    'r1_ref','r2_ref','risk_pct','distance_pct','financial_verdict','image','image_sha256')}
                  for r in result['selected']], source_json_sha256=before,
        source_preserved=True, top5_decision_preserved=True,
        operating_receipts_created=False, network_calls=0)
    write(output/'watch5_validation_proof.json',proof)
    print('C3_WATCH5_EXECUTION_PROOF',json.dumps(proof,ensure_ascii=False))
    if result['status'] in ('ERROR','PARTIAL_ERROR'):raise ValueError('WATCH_REPLAY_FAILED_'+str(result.get('reason')))
    return proof


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--asof')
    parser.add_argument('--source-kind',choices=['verified-artifact','live-output'],default='verified-artifact')
    args=parser.parse_args();validate(args.source,args.out,args.asof,args.source_kind)


if __name__=='__main__':main()
