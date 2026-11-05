"""Whole-dataset official -> validated KRX mirror recovery. No strategy changes.

The dated official control, exchange publication date, immutable cache commit,
full OHLCV/actual turnover and original provider are required. NAVER adjusted
prices never supply missing fields. Raw market files stay outside public output.
"""
import argparse,json,os,shutil,time
from pathlib import Path
from c3_eod_source_v9 import collect_day
from c3_current_candidates_v7 import fresh_snapshot
from c3_market_supply_v11 import mirror,validated_manifest
from c3_runtime_v10 import quality
from c3_supply_v11 import completed_day,now,write,digest,seal

LANE='lanes/krx_unadjusted_v12'


def collect_session(day,control,outdir,previous_session,official=collect_day,alternative=mirror,pause=time.sleep):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True);attempts=[];selected=None
    if day>completed_day():raise ValueError('FUTURE_OR_UNFINISHED_EOD')
    if not previous_session or previous_session>=day:raise ValueError('PREVIOUS_OBSERVED_SESSION_REQUIRED')
    baseline,_=fresh_snapshot(control)
    if not baseline:raise ValueError('VERIFIED_OFFICIAL_CONTROL_REQUIRED')
    control_copy=root/'_official_control';control_copy.mkdir(exist_ok=True)
    for p in Path(control).glob('*'):
        if p.name in ('krx_v65_collect_status.json','KOSPI_official.csv','KOSDAQ_official.csv'):shutil.copyfile(p,control_copy/p.name)
    for n in (1,2):
        folder=root/'_attempts'/('official_'+str(n))
        m=official(day,folder,os.environ.get('KRX_AUTH_KEY'))
        prices,_=fresh_snapshot(folder);q=quality(prices,baseline,day) if prices else None
        attempts.append(dict(provider='KRX_OFFICIAL_EOD',attempt=n,status=m['status'],rows=m['official_market_rows'],quality=q,response_diagnostics=m.get('response_diagnostics',[])))
        if prices and not q['errors']:
            selected=folder;break
        diagnostics=m.get('response_diagnostics',[])
        transient=any(x.get('status') in ('NETWORK_UNAVAILABLE','RATE_LIMITED','OUTBLOCK_EMPTY') or (x.get('http_status') or 0)>=500 for x in diagnostics)
        if not transient or n==2:break
        pause(1)
    primary_status=attempts[-1]['status']
    if selected is not None:
        state='OFFICIAL_VERIFIED';m.update(data_quality_state=state,source_provider='KRX_OFFICIAL_EOD')
    else:
        folder=root/'_attempts'/'mirror'
        try:
            m=alternative(day,control,folder,root/'_attempts'/'mirror_wire',previous_day=previous_session)
            if not validated_manifest(m):raise ValueError('MIRROR_VALIDATION_PROOF_REJECTED')
            # Re-read actual hashes/rows; a label alone cannot qualify a dataset.
            prices,_=fresh_snapshot(folder);q=quality(prices,baseline,day)
            if q['errors']:raise ValueError('MIRROR_QUALITY_REJECTED')
            selected=folder;state='RESEARCH_VALIDATED'
            attempts.append(dict(provider='FINANCEDATA_KRX_CACHE',status=state,rows=len(prices),quality=q,transport=m.get('transport',[])))
        except (ValueError,KeyError,TypeError,OSError) as exc:
            status_path=folder/'supply_validation.json'
            details=json.loads(status_path.read_text()) if status_path.exists() else {}
            wire=root/'_attempts'/'mirror_wire'/'transport.json'
            if wire.exists():details['transport']=json.loads(wire.read_text())
            state='CONFLICT' if details.get('status')=='CONFLICT' else 'UNAVAILABLE'
            attempts.append(dict(provider='FINANCEDATA_KRX_CACHE',status=state,error_type=type(exc).__name__,error_code=str(exc) if isinstance(exc,ValueError) and str(exc).replace('_','').isalnum() else 'TRANSPORT_OR_SCHEMA_FAILURE',details=details))
            m=dict(schema='C3_SUPPLY_UNAVAILABLE_V12',asof=day,retrieval_utc=now(),status=state,data_quality_state=state,krx_eod_authenticated=False,official_dataset_usable=False,official_market_rows=0,market_file_sha256={},price_files={},orders_enabled=False)
    if selected is not None:
        files=m.get('price_files') or {market:market+'_official.csv' for market in ('KOSPI','KOSDAQ')}
        for name in files.values():shutil.copyfile(selected/name,root/name)
    else:
        for pattern in ('*_official.csv','*_research.csv'):
            for p in root.glob(pattern):p.unlink()
    m.update(primary_collection_status=primary_status,supply_attempts=attempts,live_action='CASH',trade_approved=False,orders_enabled=False)
    write(root/'krx_v65_collect_status.json',m)
    return m


def preserve(root,folder,run_id):
    """Encrypted owner-only originals in git survive artifact expiry."""
    folder=Path(folder);m=json.loads((folder/'krx_v65_collect_status.json').read_text())
    identity=digest(json.dumps(dict(day=m['asof'],state=m['data_quality_state'],provider=m.get('source_provider'),hashes=m['market_file_sha256']),sort_keys=True).encode())
    dest=Path(root)/LANE/'supply_archives'/m['asof']/(identity+'.aesgcm');dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():seal(folder,dest,os.environ.get('KRX_AUTH_KEY'))
    audit=dict(asof=m['asof'],retrieval_utc=m['retrieval_utc'],run_id=str(run_id),state=m['data_quality_state'],provider=m.get('source_provider'),rows=m['official_market_rows'],
        primary_collection_status=m['primary_collection_status'],market_file_sha256=m['market_file_sha256'],validation_sha256=m.get('validation_sha256'),
        supply_attempts=m['supply_attempts'],encrypted_archive=str(dest.relative_to(Path(root))),encrypted_archive_sha256=digest(dest.read_bytes()),
        new_forward_signal=False,regular_only_certified=False,orders_enabled=False)
    receipt=Path(root)/LANE/'supply_receipts'/m['asof']/(str(run_id)+'-'+digest(json.dumps(audit,sort_keys=True).encode())[:12]+'.json')
    from c3_forward_ledger_v8 import immutable
    immutable(receipt,audit)
    return audit


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--asof',required=True);p.add_argument('--previous-session',required=True);p.add_argument('--control',required=True);p.add_argument('--outdir',required=True);p.add_argument('--ledger',required=True);p.add_argument('--audit',required=True);a=p.parse_args()
    m=collect_session(a.asof,a.control,a.outdir,a.previous_session)
    write(a.audit,preserve(a.ledger,a.outdir,os.environ.get('GITHUB_RUN_ID','LOCAL_READ_ONLY')))
    print(json.dumps({k:m.get(k) for k in ('asof','data_quality_state','source_provider','official_market_rows','primary_collection_status')}))
