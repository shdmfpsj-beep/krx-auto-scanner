#!/usr/bin/env python3
"""Disclosed adaptive followup after the v6.38 primary screen. Never OOS proof."""
import argparse,ast,hashlib,io,itertools,json
from pathlib import Path
import zipfile
import numpy as np
import pandas as pd
import c3_event_replay_v637 as book
import c3_execution_v638 as engine
from c3_research_v637 import csv,dump,metrics,monthly,sha

PATTERN='TREND_FIRST_PULLBACK'
RANKS=('LEGACY_D_SCORE','STRUCTURE_D_SCORE','RS20_THEN_MONEY')


def load_cached(primary_dir,source):
    root=Path(primary_dir);candidate_path=root/'D_only_full_market_candidates.csv'
    checks=json.loads((root/'output_sha256.json').read_text())
    if checks.get(candidate_path.name)!=sha(candidate_path):raise ValueError('CACHED_D_FEATURES_SHA_CHANGED')
    status=json.loads((root/'research_status.json').read_text())
    if status['source_archive_sha256']!=sha(source):raise ValueError('FOLLOWUP_SOURCE_DIFFERS_FROM_PRIMARY')
    d=pd.read_csv(candidate_path,dtype={'ticker':str})
    pool=d[d.pattern==PATTERN].to_dict('records');prices={}
    with zipfile.ZipFile(source) as z:
        sessions=pd.read_csv(io.BytesIO(z.read('market/sessions.csv')),dtype=str).date.tolist()
        from c3_research_v638 import features
        from c3_research_v637 import _bars
        for ticker in sorted({r['ticker'] for r in pool}):
            x=features(pd.read_csv(io.BytesIO(z.read(f'market/prices/{ticker}.csv')),dtype={'Date':str}))
            prices[ticker]={r['date']:r for r in _bars(x)}
    for r in pool:
        if isinstance(r.get('confirmed_pivot_evidence'),str):
            r['confirmed_pivot_evidence']=ast.literal_eval(r['confirmed_pivot_evidence'])
        r['requires_confirmed_pivot']=True
        v=r['market_trend']
        if type(v) is bool:r['market_trend']=v
        elif isinstance(v,str) and v in ('True','False'):r['market_trend']=v=='True'
        else:raise ValueError('INVALID_BOOLEAN_IN_CACHED_D_FEATURES')
        r['signal_low']=prices[r['ticker']][r['asof']]['low']
    return pool,prices,[s for s in sessions if '2026-01-02'<=s<='2026-10-23']


def D_choices(pool,rank,rs_gate=False,alternatives=False,random_seed=None):
    groups={};rng=np.random.default_rng(random_seed) if random_seed is not None else None
    for r in pool:
        if not rs_gate or r['rs20']>0:groups.setdefault(r['asof'],[]).append(r)
    out=[]
    for day,group in sorted(groups.items()):
        if rank=='RS20_THEN_MONEY':
            group=sorted(group,key=lambda r:(-r['rs20'],-r['turnover_accel'],-r['rs5'],r['ticker']))
        elif rank in RANKS:group=sorted(group,key=lambda r:(-r[rank],r['ticker']))
        else:raise ValueError('UNDECLARED_FOLLOWUP_RANK')
        if rng is not None:
            group=sorted(group,key=lambda r:r['ticker']);group=[group[i] for i in rng.permutation(len(group))]
        s=dict(group[0])
        if alternatives:s['D_ranked_candidates']=[dict(r) for r in group]
        out.append(s)
    return out


def run(primary_dir,source,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    dump(out/'adaptive_registry.json',dict(adapted_after_primary_1194_replays=True,
        scope='TREND_FIRST_PULLBACK_ONLY_BENCH_TREND',ranks=RANKS,positive_RS20_gate=[False,True],
        D0_known_cash_alternative=[False,True],exits=['D5','D5_FAILED_REBOUND','TARGET10_D12'],
        primary_cost_scenarios=72,
        additional_shortlist_sensitivity=dict(capital=[269230,1000000,3000000],risk=[.005,.01,.02],
            known_D_affordability_alternative=[False,True],holding_sessions=[3,4,5,6],
            entry_depth_atr=[.15,.25,.5],leave_entry_month_out=True,costs=[.65,.95],scenario_count=80),
        note='No after-D gap substitution; no future return is consulted for affordability.',
        independent_holdout_claimed=False,trade_approved=False,orders_enabled=False))
    pool,prices,sessions=load_cached(primary_dir,source)
    stats=[];ledger=[];equity=[];events=[];runs={}
    for rank,gate,alternative,ex,costs in itertools.product(RANKS,(False,True),(False,True),
                                ('D5','D5_FAILED_REBOUND','TARGET10_D12'),(book.BASE_COST,book.STRESS_COST)):
        # 3*2*2*3*2 = 72 predeclared adaptive scenarios.
        p=engine.Policy(entry='REST_1D',regime='BENCH_TREND',
            exit='TARGET10_D12' if ex=='TARGET10_D12' else 'STRUCT_D5',
            failure_close_exit=ex=='D5_FAILED_REBOUND',D0_affordability_alternative=alternative)
        chosen=D_choices(pool,rank,gate,alternative)
        run=engine.replay(sessions,prices,chosen,p,costs)
        key=f'{rank}|RS20POS={gate}|D0ALT={alternative}|{ex}'
        tags=dict(experiment=key,cost_pct=costs.label)
        stats.append(dict(experiment=key,rank=rank,RS20_positive_gate=gate,
                          alternative_D0=alternative,exit_style=ex,**metrics(run)))
        ledger.extend(dict(**t,**tags) for t in run['trades'])
        equity.extend(dict(**t,**tags) for t in run['daily'])
        events.extend(dict(**t,**tags) for t in run['events'])
        runs[(key,costs.label)]=run
    for name,rr in [('adaptive_comparison',stats),('adaptive_trade_ledger',ledger),
                    ('adaptive_daily_equity',equity),('adaptive_order_events',events)]:csv(out/(name+'.csv'),rr)
    # Stress the primary winner and two predeclared alternatives; never pick
    # the followup winner retrospectively and describe this as confirmation.
    designs=[('PRIMARY_EXPLORATORY_LEADER','LEGACY_D_SCORE',False,False,False,'STRUCT_D5'),
             ('D0_CAPITAL_AND_FAILURE','LEGACY_D_SCORE',False,True,True,'STRUCT_D5'),
             ('RELATIVE_STRENGTH_FAILURE','RS20_THEN_MONEY',True,True,True,'STRUCT_D5')]
    stress=[];random_rows=[];months=[]
    for label,rank,gate,alt,failed,ex in designs:
        selected=D_choices(pool,rank,gate,alt)
        p=engine.Policy(entry='REST_1D',exit=ex,regime='BENCH_TREND',
                         D0_affordability_alternative=alt,failure_close_exit=failed)
        ref=engine.replay(sessions,prices,selected,p)
        best={t['asof'] for t in sorted(ref['trades'],key=lambda t:t['pnl_krw'],reverse=True)[:2]}
        for costs in (book.BASE_COST,book.STRESS_COST,book.Costs(.004,.0085)):
            r=engine.replay(sessions,prices,selected,p,costs)
            stress.append(dict(design=label,stress='COST_ONLY',**metrics(r)))
            removed=engine.replay(sessions,prices,[s for s in selected if s['asof'] not in best],p,costs)
            stress.append(dict(design=label,stress='MISS_TOP2_FULL_REPLAY',**metrics(removed)))
            for tickdepth in (2,3):
                pp=engine.Policy(**dict(p.__dict__,limit_penetration_ticks=tickdepth))
                stress.append(dict(design=label,stress=f'LIMIT_{tickdepth}_TICKS',
                                  **metrics(engine.replay(sessions,prices,selected,pp,costs))))
            pp=engine.Policy(**dict(p.__dict__,extra_stop_slippage=.003))
            stress.append(dict(design=label,stress='EXTRA_STOP_SLIPPAGE_30BP',
                              **metrics(engine.replay(sessions,prices,selected,pp,costs))))
        for probability,seed in itertools.product((.2,.4),range(638500,638520)):
            rng=np.random.default_rng(seed);choices=[]
            for s in selected:
                can_fill=bool(rng.random()>=probability)
                c=dict(s,simulated_fill_allowed=can_fill)
                if alt:c['D_ranked_candidates']=[dict(a,simulated_fill_allowed=can_fill) for a in s['D_ranked_candidates']]
                choices.append(c)
            stress.append(dict(design=label,stress=f'MISSED_FILL_{probability}',seed=seed,
                              **metrics(engine.replay(sessions,prices,choices,p))))
        for label_half,start,end in [('H1','2026-01-02','2026-06-30'),('H2','2026-07-01','2026-10-23')]:
            ss=[d for d in sessions if start<=d<=end]
            run=engine.replay(ss,prices,[s for s in selected if s['asof'] in ss],p)
            stress.append(dict(design=label,stress=label_half,**metrics(run)))
        for m in monthly(ref):months.append(dict(design=label,**m))
        for seed in range(638500,638700):
            random_D=D_choices(pool,rank,gate,alt,random_seed=seed)
            random_rows.append(dict(design=label,seed=seed,
                **metrics(engine.replay(sessions,prices,random_D,p))))
    csv(out/'focused_stress.csv',stress);csv(out/'focused_random_controls.csv',random_rows)
    csv(out/'focused_monthly_equity.csv',months)
    # Neighbors for the research shortlist; the default remains five sessions.
    shortlist=[];selected=D_choices(pool,'LEGACY_D_SCORE',False,False)
    for cash,risk,alternative,costs in itertools.product((269230.,1e6,3e6),(.005,.01,.02),
                                                       (False,True),(book.BASE_COST,book.STRESS_COST)):
        chosen=D_choices(pool,'LEGACY_D_SCORE',False,alternative)
        p=engine.Policy(entry='REST_1D',exit='STRUCT_D5',regime='BENCH_TREND',
                         initial_cash=cash,risk_fraction=risk,D0_affordability_alternative=alternative)
        shortlist.append(dict(diagnostic='CAPITAL_RISK_SENSITIVITY',
                              **metrics(engine.replay(sessions,prices,chosen,p,costs))))
    for days,depth,costs in itertools.product((3,4,5,6),(.15,.25,.5),(book.BASE_COST,book.STRESS_COST)):
        p=engine.Policy(entry='REST_1D',exit='STRUCT_D5',regime='BENCH_TREND',
                         fixed_exit_sessions=days,retest_atr=depth)
        shortlist.append(dict(diagnostic='HOLDING_DEPTH_NEIGHBOR',
                              **metrics(engine.replay(sessions,prices,selected,p,costs))))
    for month,costs in itertools.product(sorted({d[:7] for d in sessions}),(book.BASE_COST,book.STRESS_COST)):
        p=engine.Policy(entry='REST_1D',exit='STRUCT_D5',regime='BENCH_TREND')
        shortlist.append(dict(diagnostic='LEAVE_ENTRY_MONTH_OUT_FULL_REPLAY',omitted_month=month,
            **metrics(engine.replay(sessions,prices,[s for s in selected if not s['asof'].startswith(month)],p,costs))))
    csv(out/'shortlist_additional_sensitivity.csv',shortlist)
    stat=dict(adaptive_replays=len(stats),focused_stress_replays=len(stress),shortlist_sensitivity_replays=len(shortlist),
              random_control_replays=len(random_rows),total_replays=len(stats)+len(stress)+len(random_rows)+len(shortlist),
              baseline_winner_was_selected_on_seen_primary_data=True,
              snapshot_historical_PIT_and_actual_fills_unverified=True,
              new_independent_completed_trades=0,production_decision='CASH',
              trade_approved=False,orders_enabled=False)
    dump(out/'followup_status.json',stat)
    print(json.dumps(stat),flush=True)
    s=pd.DataFrame(stats);print(s[s.cost_pct==.65][['experiment','closed_trades','account_roi_pct',
        'daily_liquidation_mdd_pct','median_trade_net_pct']].sort_values('account_roi_pct',ascending=False).head(12).to_string(index=False))
    return stat


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('primary-dir','source-zip','out'):p.add_argument('--'+name,required=True)
    a=p.parse_args();run(a.primary_dir,a.source_zip,a.out)
