"""Registered source handoff only; no selection, ledger mutation or transport."""
import argparse,hashlib,json,os,re,subprocess
from pathlib import Path


def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()


def seal(latest,decision,market,day,caller_run_id=None):
    if latest.get('source_price_asof')!=day or decision.get('price_asof')!=day or market.get('asof')!=day:
        raise ValueError('REGISTRATION_SOURCE_DAY_MISMATCH')
    if latest.get('research_top2_registered_for_source_session') is not True or latest.get('errors'):
        raise ValueError('REGISTERED_SOURCE_REQUIRED')
    run=str(latest.get('source_run_id',''))
    if not re.fullmatch(r'[0-9]+',run):raise ValueError('ORIGINAL_SOURCE_RUN_ID_REQUIRED')
    if market.get('source',{}).get('source_run_id')!=run:
        raise ValueError('REGISTERED_MARKET_RUN_ID_MISMATCH')
    if set(decision.get('models',{}))!={'A','B'} or any(
        str(r.get('source_run_id',''))!=run or r.get('source_price_asof',day)!=day
        for rows in decision['models'].values() for r in rows):
        raise ValueError('REGISTERED_SIGNAL_RUN_ID_MISMATCH')
    if decision.get('source_snapshot_hash')!=digest(market):raise ValueError('REGISTERED_DECISION_MARKET_HASH_MISMATCH')
    if caller_run_id is not None:
        if not re.fullmatch(r'[0-9]+',str(caller_run_id)):raise ValueError('REGISTRATION_CALLER_ID_REQUIRED')
        if latest.get('new_decision_registered') is True and run!=str(caller_run_id):
            raise ValueError('NEW_REGISTRATION_CALLER_MISMATCH')
    return dict(schema='C3_MORNING_REGISTERED_SOURCE_V1',source_day=day,source_run_id=run,
        registration_run_id=str(caller_run_id) if caller_run_id else None,
        mode='APPROVED_PIPELINE' if caller_run_id else 'READ_ONLY_REPLAY',
        decision_payload_sha256=digest(decision),market_payload_sha256=digest(market),
        source_validation_sha256=latest.get('source_validation_sha256'),
        original_registration_reused=latest.get('new_decision_registered') is not True,
        orders_enabled=False,original_signals_modified=False)


def completed_handoff(proof,state_sha):
    if proof.get('mode')!='APPROVED_PIPELINE' or not re.fullmatch(r'[a-f0-9]{40}',state_sha):
        raise ValueError('REGISTERED_COMMIT_OR_APPROVED_PIPELINE_REQUIRED')
    return dict(proof,registered_state_sha=state_sha)


def check_review(proof,state_sha,day,caller_run_id):
    if (proof.get('schema')!='C3_MORNING_REGISTERED_SOURCE_V1' or proof.get('mode')!='APPROVED_PIPELINE' or
        proof.get('source_day')!=day or proof.get('registration_run_id')!=str(caller_run_id) or
        not re.fullmatch(r'[a-f0-9]{40}',str(state_sha)) or proof.get('registered_state_sha')!=state_sha or
        not re.fullmatch(r'[0-9]+',str(proof.get('source_run_id',''))) or
        not re.fullmatch(r'[a-f0-9]{64}',str(proof.get('decision_payload_sha256',''))) or
        not re.fullmatch(r'[a-f0-9]{64}',str(proof.get('market_payload_sha256','')))):
        raise ValueError('REGISTERED_SOURCE_HANDOFF_MISMATCH')
    return proof


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--latest');p.add_argument('--ledger');p.add_argument('--day');p.add_argument('--caller-run-id');p.add_argument('--complete',action='store_true');p.add_argument('--proof',required=True);a=p.parse_args()
    path=Path(a.proof)
    if a.complete:
        proof=json.loads(path.read_text());head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
        proof=completed_handoff(proof,head);check_review(proof,head,proof['source_day'],a.caller_run_id)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as f:
                for k in ('registered_state_sha','source_run_id','source_day'):f.write(k+'='+proof[k]+'\n')
                f.write('registration_proof='+canonical(proof)+'\n')
    else:
        from c3_forward_ledger_v8 import read_record
        root=Path(a.ledger)/'lanes/krx_unadjusted_v12'
        proof=seal(json.loads(Path(a.latest).read_text()),read_record(root/'decisions'/(a.day+'.json')),read_record(root/'markets'/(a.day+'.json.gz')),a.day,a.caller_run_id)
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(canonical(proof)+'\n')
    print(canonical({k:proof.get(k) for k in ('mode','source_day','source_run_id','registration_run_id','registered_state_sha')}))
