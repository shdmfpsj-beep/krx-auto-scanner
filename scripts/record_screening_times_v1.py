#!/usr/bin/env python3
"""Immutable technical-screen snapshot times. No ranking or order changes.

recorded_at is when a completed candidate/rank snapshot is registered; it is
not the market-data date, a per-ticker quote timestamp, or an older unknown
discovery time. Repeated attempts are separately identified.
"""
import argparse,csv,hashlib,json,os,re
from datetime import date,datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo

KST=ZoneInfo('Asia/Seoul')

def aware(value):
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.tzinfo is None or d.utcoffset() is None:raise ValueError('timezone required')
    return d

def atom(path,text):
    temp=path.with_name(path.name+'.tmp');temp.write_text(text,encoding='utf-8');temp.replace(path)

def record(out,run_id,attempt,commit,now=None):
    out=Path(out);clock=now or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:raise ValueError('aware clock required')
    status_path=out/'status.json';status=json.loads(status_path.read_text(encoding='utf-8'))
    if status.get('scan_complete') is not True or status.get('data_date_verified') is not True:
        raise ValueError('completed, date-verified collection required')
    asof=status.get('market_data_date');date.fromisoformat(asof)
    started=aware(status['run_kst']) if status.get('run_kst') else None
    if started and started>clock:raise ValueError('scan cannot start after registration')
    if not str(run_id).isdigit() or not str(attempt).isdigit():raise ValueError('run identity required')
    sources={};rows={}
    for name in ['candidates.csv','c3_preliminary.csv']:
        p=out/name;sources[name]=hashlib.sha256(p.read_bytes()).hexdigest()
        with p.open(encoding='utf-8-sig',newline='') as f:
            for rank,r in enumerate(csv.DictReader(f),1):
                t=str(r.get('ticker','')).strip()
                if not re.fullmatch(r'\d{6}',t):raise ValueError('invalid ticker')
                if r.get('latest_date')!=asof:raise ValueError('mixed or stale candidate date')
                v=rows.setdefault(t,dict(ticker=t,name=r.get('name',''),data_asof=asof,
                    data_source=r.get('data_source'),technical_preliminary_rank=None))
                if name=='c3_preliminary.csv':
                    v.update(name=r.get('name') or v['name'],technical_preliminary_rank=rank,
                        eligibility=r.get('eligibility'),preliminary_score=r.get('c3_preliminary_score'))
    digest=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()
    ledger=out/'screening_observations_v1.jsonl';history=[]
    if ledger.exists():
        for line in ledger.read_text(encoding='utf-8').splitlines():
            if line.strip():history.append(json.loads(line))
    old={r['observation_id']:r for r in history}
    events=[]
    for t,r in sorted(rows.items()):
        key=f'{run_id}|{attempt}|{asof}|{t}|TECHNICAL_PRELIMINARY'
        if key in old:
            if old[key]['source_snapshot_sha256']!=digest:raise ValueError('immutable observation conflict')
            continue
        events.append(dict(**r,observation_id=key,run_id=str(run_id),run_attempt=int(attempt),commit=commit,
            recorded_at_utc=clock.astimezone(timezone.utc).isoformat(),recorded_at_kst=clock.astimezone(KST).isoformat(),
            collection_started_at_kst=started.astimezone(KST).isoformat() if started else None,
            source_snapshot_sha256=digest,input_sha256=sources,
            source_session_scope_certified=status.get('source_session_scope_certified') is True,
            earlier_discovery_time_unverified=True,scope='TECHNICAL_PRELIMINARY_SNAPSHOT_REGISTRATION',
            timestamp_is_per_ticker_quote_time=False,trade_approved=False,orders_enabled=False))
    history+=events;registry={}
    for e in sorted(history,key=lambda r:(aware(r['recorded_at_utc']),r['observation_id'])):
        t=e['ticker'];v=registry.setdefault(t,dict(ticker=t,first_recorded_at_utc=e['recorded_at_utc'],
            first_recorded_at_kst=e['recorded_at_kst'],first_observation_id=e['observation_id'],
            earlier_discovery_time_unverified=True))
        v.update(latest_recorded_at_utc=e['recorded_at_utc'],latest_recorded_at_kst=e['recorded_at_kst'],
            latest_observation_id=e['observation_id'],latest_data_asof=e['data_asof'],name=e['name'],
            source_session_scope_certified=e['source_session_scope_certified'])
    atom(ledger,''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in history))
    result=dict(schema='C3_SCREENING_TIMES_V1',timestamp_definition='completed technical candidate snapshot registration; no older unknown discovery inferred',
        run_id=str(run_id),run_attempt=int(attempt),data_asof=asof,new_observations=len(events),
        total_observations=len(history),issuers=registry,trade_approved=False,orders_enabled=False)
    atom(out/'screening_registry_v1.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--outdir',default='reports');a=p.parse_args()
    result=record(a.outdir,os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT'],os.environ.get('GITHUB_SHA',''))
    print(json.dumps({k:v for k,v in result.items() if k!='issuers'},ensure_ascii=False))

if __name__=='__main__':main()
