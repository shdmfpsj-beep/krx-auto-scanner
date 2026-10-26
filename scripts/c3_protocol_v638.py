#!/usr/bin/env python3
"""Freeze the two research shortlist hypotheses. No brokerage or BUY approval."""
import argparse,ast,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
from c3_event_replay_v637 import BASE_COST
from c3_execution_v638 import Policy,Handlers
from c3_forward_freeze_v637 import canonical_digest,freeze_once
from c3_research_v637 import sha


def implementation_hashes():
    root=Path(__file__).parent
    names=['c3_execution_v638.py','c3_event_replay_v637.py','c3_research_v638.py','c3_protocol_v638.py']
    return {name:sha(root/name) for name in names}


def create_protocol(path):
    p=Path(path)
    if p.exists():return json.loads(p.read_text())
    obj=dict(schema='C3_V638_1_FULL_RESEARCH_PROTOCOL',registered_at_utc=datetime.now(timezone.utc).isoformat(),
        earliest_fresh_D_signal='2026-10-26',paper_cash=1000000,account_risk_fraction=.01,
        evidence_layers=['REPEATED_HISTORICAL','NEW_UNVERIFIED_PRICE_PROXY',
                         'NEW_VERIFIED_PRICE_PAPER','BROKER_EXECUTION_VERIFIED'],
        hypotheses=[dict(id='A_TREND_PULLBACK_D5',pattern='TREND_FIRST_PULLBACK',rank='LEGACY_D_SCORE',
                         entry='REST_1D',exit='STRUCT_D5',regime='BENCH_TREND',
                         full_policy=Policy(entry='REST_1D',exit='STRUCT_D5',regime='BENCH_TREND').__dict__),
                    dict(id='B_TREND_PULLBACK_TARGET10',pattern='TREND_FIRST_PULLBACK',rank='STRUCTURE_D_SCORE',
                         entry='REST_1D',exit='TARGET10_D12',regime='BENCH_TREND',
                         full_policy=Policy(entry='REST_1D',exit='TARGET10_D12',regime='BENCH_TREND').__dict__)],
        frozen_implementation_sha256=implementation_hashes(),
        candidate_eligibility='Unbroken confirmed daily pivot; D structural risk <=12%; turnover >= KRW5bn.',
        A_priority_feature='Setup momentum/volume/3-day compactness score; actual stop uses the confirmed unbroken pivot.',
        B_priority_feature='The same fixed formula with actual confirmed structural risk.',
        rejected_as_default=['profit-activated ATR on the NEAR60 cohort','after-open price-filtered opening fills',
                             'D0 affordability alternatives','relative-strength positive gate','extra failed-rebound exit'],
        parameter_change_requires_new_protocol_version=True,
        research_review_can_use_verified_new_paper_prices_without_actual_money_at_risk=True,
        real_trade_approval_still_requires_final80_net2R_current_cash_regular_source_and_company_checks=True,
        independent_verified_forward_samples=0,trade_approved=False,orders_enabled=False)
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as w:w.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    return obj


def capture(primary_dir,protocol_path,asof,out):
    root=Path(primary_dir);p=root/'D_only_full_market_candidates.csv'
    checks=json.loads((root/'output_sha256.json').read_text())
    if sha(p)!=checks.get(p.name):raise ValueError('CANDIDATE_POOL_SHA_MISMATCH')
    status=json.loads((root/'research_status.json').read_text())
    if status['last']!=asof:raise ValueError('SNAPSHOT_DATE_DOES_NOT_MATCH_LAST_COMPLETED_SOURCE')
    protocol=json.loads(Path(protocol_path).read_text());version=canonical_digest(protocol)
    if protocol.get('schema')!='C3_V638_1_FULL_RESEARCH_PROTOCOL':
        raise ValueError('LEGACY_PROTOCOL_LACKS_FULL_PARAMETER_AND_CODE_FREEZE')
    if protocol['frozen_implementation_sha256']!=implementation_hashes():
        raise ValueError('FROZEN_PROTOCOL_IMPLEMENTATION_CHANGED')
    data=pd.read_csv(p,dtype={'ticker':str})
    rows=data[data['asof']==asof].to_dict('records')
    registered=datetime.fromisoformat(protocol['registered_at_utc']).astimezone(ZoneInfo('Asia/Seoul')).date().isoformat()
    retrospective=(asof<max(protocol['earliest_fresh_D_signal'],registered))
    choices=[]
    for h in protocol['hypotheses']:
        candidates=[r for r in rows if r['pattern']==h['pattern']]
        candidates.sort(key=lambda r:(-r[h['rank']],r['ticker']))
        choice=dict(hypothesis=h['id'],pattern_candidate_count=len(candidates),paper_order=None)
        if candidates:
            s=dict(candidates[0]);v=s['market_trend']
            if not (type(v) is bool or isinstance(v,str) and v in ('True','False')):
                raise ValueError('INVALID_MARKET_BOOLEAN')
            trend=(v is True or v=='True')
            if isinstance(s.get('confirmed_pivot_evidence'),str):
                s['confirmed_pivot_evidence']=ast.literal_eval(s['confirmed_pivot_evidence'])
            s['requires_confirmed_pivot']=True
            policy=Policy(**h['full_policy'])
            if trend:
                pending,why=Handlers.make_pending(s,policy,BASE_COST,1e6,1e6,0)
                if pending:choice['paper_order']=dict(ticker=s['ticker'],limit=pending['cap'],
                    stop=pending['stop'],qty=pending['qty'],hypothetical_target=pending['target'] if h['exit']=='TARGET10_D12' else None,
                    policy_hash=policy.digest(),confirmed_pivot=s['confirmed_pivot_evidence'])
                choice['blocker']=why
            else:choice['blocker']='BENCH_TREND_FILTER'
        else:choice['blocker']='NO_FIXED_PATTERN_SIGNAL'
        choices.append(choice)
    path=Path(out)
    captured=json.loads(path.read_text())['record']['captured_at_utc'] if path.exists() else datetime.now(timezone.utc).isoformat()
    record=dict(schema='C3_V638_IMMUTABLE_D_CLOSE_RESEARCH_FREEZE',asof=asof,
        captured_at_utc=captured,protocol_hash=version,protocol_registered_at_utc=protocol['registered_at_utc'],
        source_sha256=status['source_archive_sha256'],D_pool_sha256=sha(p),hypotheses=choices,
        evidence_layer='REPEATED_HISTORICAL' if retrospective else 'NEW_UNVERIFIED_PRICE_PROXY',
        independent_verified_future_sample=False,actual_current_broker_cash_verified=False,
        final_score80_and_independent_resistance2R_verified=False,
        production_decision='CASH',trade_approved=False,orders_enabled=False)
    return freeze_once(path,record)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--protocol',required=True);p.add_argument('--primary-dir')
    p.add_argument('--asof');p.add_argument('--out')
    a=p.parse_args();create_protocol(a.protocol)
    if a.primary_dir:
        if not(a.asof and a.out):raise ValueError('CAPTURE_NEEDS_ASOF_AND_OUT')
        r=capture(a.primary_dir,a.protocol,a.asof,a.out)
        print(json.dumps(r,ensure_ascii=False))
