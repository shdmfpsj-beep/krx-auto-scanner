#!/usr/bin/env python3
"""Audit the gap between price hypotheses and the user's net2R gate.

This is a disclosed post-shortlist diagnostic. Automatic D-high clusters
are an unverified resistance proxy, never a final80/company/sector approval.
The registered A/B protocol is not modified by this audit.
"""
import argparse,json
from dataclasses import replace
from pathlib import Path
import pandas as pd
import c3_event_replay_v637 as book
from c3_execution_v638 import Policy,replay
from c3_followup_v638 import load_cached,D_choices
from c3_protocol_v638 import implementation_hashes
from c3_research_v637 import csv,dump,metrics,sha


def run(primary_dir,source,protocol_path,out):
    root=Path(primary_dir);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    protocol=json.loads(Path(protocol_path).read_text())
    if protocol['frozen_implementation_sha256']!=implementation_hashes():
        raise ValueError('FROZEN_SHORTLIST_IMPLEMENTATION_CHANGED')
    pool,prices,sessions=load_cached(root,source)
    baseline=pd.read_csv(root/'trade_ledger.csv',dtype={'ticker':str})
    lookup={(r['asof'],r['ticker']):r for r in pool}
    original_geometry=[];stats=[];ledger=[];events=[]
    for h in protocol['hypotheses']:
        policy=Policy(**h['full_policy'])
        key='|'.join((h['pattern'],h['rank'],h['entry'],h['exit'],h['regime']))
        for costs in (book.BASE_COST,book.STRESS_COST):
            old=baseline[(baseline.experiment==key)&(baseline.cost_pct==costs.label)]
            for _,trade in old.iterrows():
                signal=lookup[(trade['asof'],trade.ticker)]
                resistance=signal.get('resistance')
                rr=book.net_rr(trade.submitted_cap,trade.stop,resistance,costs)
                original_geometry.append(dict(hypothesis=h['id'],cost_pct=costs.label,
                    asof=trade['asof'],ticker=trade.ticker,submitted_cap=trade.submitted_cap,
                    structural_stop=trade.stop,resistance_proxy=resistance,
                    proxy_net_R=rr,proxy_net2R_present=rr is not None and rr>=2,
                    dated_resistance_independently_verified=False,trade_approved=False))
            chosen=D_choices(pool,h['rank'])
            result=replay(sessions,prices,chosen,replace(policy,require_rr2=True),costs)
            tags=dict(hypothesis=h['id'],cost_pct=costs.label)
            stats.append(dict({**result['summary'],**metrics(result),**tags},
                resistance_scope='AUTOMATIC_D_HIGH_CLUSTER_NOT_INDEPENDENTLY_VERIFIED',
                final80_company_sector_cash_gates_applied=False))
            ledger.extend(dict(t,**tags) for t in result['trades'])
            events.extend(dict(t,**tags) for t in result['events'])
    csv(out/'original_closed_trade_RR_geometry.csv',original_geometry)
    csv(out/'net2R_proxy_scenarios.csv',stats)
    csv(out/'net2R_proxy_trade_ledger.csv',ledger)
    csv(out/'net2R_proxy_order_events.csv',events)
    status=dict(schema='C3_V638_POST_SHORTLIST_NET2R_GEOMETRY_AUDIT',
        protocol_sha256=sha(protocol_path),source_archive_sha256=sha(source),
        additional_repeated_history_replays=4,
        automatic_resistance_is_not_verified_real_overhead=True,
        A_B_frozen_protocol_changed=False,new_independent_completed_trades=0,
        production_decision='CASH',trade_approved=False,orders_enabled=False)
    dump(out/'net2R_audit_status.json',status)
    print(json.dumps(status,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('primary-dir','source-zip','protocol','out'):p.add_argument('--'+name,required=True)
    a=p.parse_args();run(a.primary_dir,a.source_zip,a.protocol,a.out)
