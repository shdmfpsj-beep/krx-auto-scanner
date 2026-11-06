"""Reuse captured direct official prices; reconcile the newly available date.

No new official API call, no forty-stock replay and no prospective signal.
All full raw datasets are owner-encrypted in the resulting evidence archive.
"""
import csv,json,os,subprocess
from pathlib import Path
from c3_supply_v11 import digest,write,open_sealed,seal,now
from c3_supply_bridge_v11 import extract_zip
from c3_market_supply_v11 import mirror,control_check


def restore(artifact_id,expected,out):
    body=subprocess.check_output(['gh','api','repos/shdmfpsj-beep/krx-auto-scanner/actions/artifacts/'+str(artifact_id)+'/zip'],timeout=60)
    if digest(body)!=expected:raise ValueError('PINNED_EVIDENCE_HASH_MISMATCH')
    extract_zip(body,out)


def load(folder):
    m=json.loads((Path(folder)/'krx_v65_collect_status.json').read_text());rr=[]
    for market in ('KOSPI','KOSDAQ'):
        p=Path(folder)/(m.get('price_files') or {}).get(market,market+'_official.csv')
        if digest(p.read_bytes())!=m['market_file_sha256'][market]:raise ValueError('RECONCILIATION_SOURCE_HASH_MISMATCH')
        with p.open(encoding='utf-8-sig') as f:rr+=list(csv.DictReader(f))
    return rr,m


def run(out):
    root=Path(out);private=root/'private';pub=root/'public';private.mkdir(parents=True,exist_ok=True);key=os.environ['KRX_AUTH_KEY']
    restore(13464566128,'f784393e672e59765cd077051adcae845a981bf5db799843514634226b33a0f9',private/'direct_run')
    original=private/'direct_run/ledger/lanes/krx_unadjusted_v12/supply_archives/2026-11-05/a6cacfc4f25e618c4ec8a7a283c2fdad7c5adbea43c14ce7f4e4147bc5a79734.aesgcm'
    extract_zip(open_sealed(original,key),private/'official')
    restore(13452332422,'c236eb90bc1ff5239267178a0aea323abe46138b1c732facdbe7eff195a6b799',private/'prior_validation')
    extract_zip(open_sealed(private/'prior_validation/private_market_data.aesgcm',key),private/'prior_cache')
    official,om=load(private/'official');old,oldm=load(private/'prior_cache/validated/2026-11-05')
    current=private/'current_cache';m=mirror('2026-11-05',private/'official/_official_control',current,private/'wire',previous_day='2026-11-04');cached,_=load(current)
    original_check=control_check(official,old);current_check=control_check(official,cached)
    out=dict(run_id=os.environ.get('GITHUB_RUN_ID'),generated_at=now(),asof='2026-11-05',official_rows=len(official),original_cache_rows=len(old),current_cache_rows=len(cached),
        original_cache_comparison=original_check,current_cache_comparison=current_check,
        current_state='OFFICIAL_VERIFIED' if current_check['complete_match'] else 'CONFLICT',
        current_official_file_sha256=om['market_file_sha256'],prior_cache_file_sha256=oldm['market_file_sha256'],current_cache_file_sha256=m['market_file_sha256'],
        cache_validation=m['validation'],cache_transport=m['transport'],independent_price_vendors=1,regular_only_certified=False,
        official_collected_until=max(r['received_at'] for r in om['response_diagnostics']),
        source_control='CAPTURED_REAL_DIRECT_API_RESPONSE_NOT_SYNTHETIC',new_official_requests=0,new_signals=0,live_action='CASH')
    write(pub/'reconciliation.json',out)
    if not current_check['complete_match']:write(pub/'issue.json',dict(status='CONFLICT',price_source_mixing_allowed=False))
    write(pub/'archive_manifest.json',seal(private,root/'private_market_data.aesgcm',key))
    print(json.dumps({k:out[k] for k in ('asof','official_rows','original_cache_rows','current_cache_rows','current_state','new_signals')}))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);run(p.parse_args().outdir)
