#!/usr/bin/env python3
"""Reproduce the predeclared C3 v6.37 mechanical experiment. Never orders.

Run on old, repeatedly studied data. Rankings are frozen v6.33 D-day features.
No issuer/biotech/PIT/session/2R/score80 eligibility is inferred from profits.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import itertools
import json
import math
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

from c3_event_replay_v637 import (BASE_COST, STRESS_COST, Policy, ENTRIES, EXITS,
                                 REGIMES, replay, resistance_clusters, net_rr)

RANKS = ('V632_BASE', 'BALANCED_LEADER')
MODEL = 'NEAR60_RISK8'
LAST = '2026-10-23'
FIRST = '2026-01-02'
FULL_ARCHIVE_SHA = '7eef1174032105d1790c41144e580d44380bdb9a4500b12afc69865fe6d6fd30'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, obj):
    def scalar(v):
        if hasattr(v, 'item'):
            return v.item()
        raise TypeError(type(v).__name__)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=scalar,
                                    allow_nan=False)+'\n', encoding='utf-8')


def csv(path, records):
    pd.DataFrame(records).to_csv(path, index=False, encoding='utf-8-sig')


def enrich(df):
    x = df.copy()
    x['Date'] = x['Date'].astype(str)
    if x.Date.duplicated().any() or not x.Date.is_monotonic_increasing:
        raise ValueError('DUPLICATE_OR_UNSORTED_PRICE_DATE')
    for col in ('Open', 'High', 'Low', 'Close'):
        x[col] = pd.to_numeric(x[col], errors='raise')
    if not np.isfinite(x[['Open','High','Low','Close']].to_numpy()).all():
        raise ValueError('NONFINITE_RAW_PRICE')
    c=x.Close
    x['ma5']=c.rolling(5).mean()
    x['ma20']=c.rolling(20).mean()
    x['ma20slope']=x.ma20/x.ma20.shift(5)-1
    tr=pd.concat([x.High-x.Low,(x.High-c.shift(1)).abs(),
                  (x.Low-c.shift(1)).abs()],axis=1).max(axis=1)
    x['atr14']=tr.rolling(14).mean()
    return x


def _bars(df):
    rows=[]
    for r in df.to_dict('records'):
        rows.append(dict(date=r['Date'], **{k.lower():float(r[k]) for k in ('Open','High','Low','Close')},
                         atr14=float(r['atr14']) if pd.notna(r['atr14']) else None,
                         ma5=float(r['ma5']) if pd.notna(r['ma5']) else None))
    return rows


def load_data(source, candidates, eligibility=None):
    x=pd.read_csv(candidates,dtype={'ticker':str,'asof':str})
    x['ticker']=x.ticker.str.zfill(6)
    if x.duplicated(['model','asof','ticker']).any():
        raise ValueError('DUPLICATE_FROZEN_CANDIDATE')
    x=x[x.model==MODEL].copy()
    if eligibility:
        e=pd.read_csv(eligibility,dtype=str).fillna('')
        if e.ticker.duplicated().any() or not e.snapshot_research_allowed.isin(['True','False']).all():
            raise ValueError('INVALID_ELIGIBILITY_AUDIT')
        allowed=set(e.loc[e.snapshot_research_allowed=='True','ticker'])
        x=x[x.ticker.isin(allowed)].copy()
    if x.empty or x['asof'].max()>LAST:
        raise ValueError('WRONG_HISTORICAL_COHORT')
    numeric=['signal_close','stopD','V632_BASE','BALANCED_LEADER']
    if not np.isfinite(x[numeric].to_numpy(float)).all():
        raise ValueError('INVALID_D_FEATURES')
    prices={};hist={};hashes={}
    with zipfile.ZipFile(source) as z:
        # A compact research subset carries the exact original member bytes.
        compact=json.loads(z.read('subset_manifest.json')) if 'subset_manifest.json' in z.namelist() else None
        if compact is None and sha(source)!=FULL_ARCHIVE_SHA:
            raise ValueError('UNEXPECTED_SOURCE_ARCHIVE_SHA')
        if compact and compact['parent_archive_sha256']!=FULL_ARCHIVE_SHA:
            raise ValueError('WRONG_SUBSET_PARENT')
        def read_member(n):
            b=z.read(n);h=hashlib.sha256(b).hexdigest();hashes[n]=h
            if compact and compact['member_sha256'].get(n)!=h:
                raise ValueError('SUBSET_MEMBER_HASH_MISMATCH')
            return pd.read_csv(io.BytesIO(b),dtype={'Date':str,'date':str})
        sessions=read_member('market/sessions.csv').date.tolist()
        bench=enrich(read_member('market/etf_prices/069500.csv')).set_index('Date',drop=False)
        for ticker in sorted(x.ticker.unique()):
            h=enrich(read_member(f'market/prices/{ticker}.csv'))
            rows=_bars(h);hist[ticker]=rows;prices[ticker]={r['date']:r for r in rows}
    market={d:bool(r.Close>r.ma20 and r.ma20slope>0)
            for d,r in bench.iterrows() if pd.notna(r.ma20slope)}
    extra=[]
    for r in x.to_dict('records'):
        t,d=r['ticker'],r['asof'];b=prices[t].get(d)
        if b is None or abs(b['close']-r['signal_close'])>.01:
            raise ValueError('D_FEATURE_PRICE_MISMATCH')
        if not 0<r['stopD']<r['signal_close'] or b['atr14'] is None:
            raise ValueError('INVALID_D_STOP_OR_ATR')
        h=[z for z in hist[t] if z['date']<=d][-60:]
        res=resistance_clusters(h,float(r['signal_close']),b['atr14'])
        r.update(atr14=b['atr14'],market_trend=market.get(d,False),
                 resistance=res['price'] if res else None,
                 resistance_evidence=res)
        extra.append(r)
    sessions=[d for d in sessions if FIRST<=d<=LAST]
    return extra,prices,hist,sessions,bench,hashes


def select_D(rows,rank):
    if rank not in RANKS:
        raise ValueError('UNDECLARED_RANK')
    groups={}
    for r in rows:groups.setdefault(r['asof'],[]).append(r)
    return [dict(sorted(g,key=lambda r:(-float(r[rank]),r['ticker']))[0]) for d,g in sorted(groups.items())]


def selected_random(rows,seed):
    rng=np.random.default_rng(seed);groups={}
    for r in rows:groups.setdefault(r['asof'],[]).append(r)
    return [dict(sorted(g,key=lambda r:r['ticker'])[int(rng.integers(len(g)))])
            for d,g in sorted(groups.items())]


def metrics(run):
    s=dict(run['summary']);t=run['trades'];p=np.array([r['pnl_krw'] for r in t])
    wins=p[p>0];loss=p[p<0]
    s.update(win_rate_pct=float((p>0).mean()*100) if len(p) else None,
             profit_factor=float(wins.sum()/-loss.sum()) if len(loss) else None,
             median_trade_net_pct=float(np.median([r['net_pct'] for r in t])) if t else None,
             average_closed_pnl_krw=float(p.mean()) if len(p) else None,
             closed_pnl_ex_top2_contribution_krw=float(p.sum()-np.sort(p)[-2:].sum()) if len(p)>2 else None,
             top2_share_of_positive_total_pct=float(np.sort(p)[-2:].sum()/p.sum()*100) if p.sum()>0 else None,
             exposure_days=sum(bool(d.get('position_ticker')) for d in run['daily']),
             total_sessions=len(run['daily']))
    s['avg_planned_r_multiple']=float(np.mean([r['pnl_krw']/r['planned_risk_krw'] for r in t])) if t else None
    return s


def monthly(run):
    grouped={}
    for row in run['daily']:
        if row['equity_krw'] is None:continue
        grouped[row['date'][:7]]=row
    prev=run['summary']['initial_cash'];out=[]
    for month,row in sorted(grouped.items()):
        e=row['equity_krw'];out.append(dict(month=month,equity_krw=e,
            pnl_krw=e-prev,return_pct=100*(e/prev-1),
            month_end_session=row['date'],open_ticker=row.get('position_ticker')))
        prev=e
    return out


def policy_id(rank,p):
    return '|'.join((rank,p.entry,p.exit,p.regime))


def run_grid(rows,prices,sessions,out):
    """Exactly 36 designs x two costs, declared before calculating outcomes."""
    registry=[]
    for rank,entry,exit_,regime in itertools.product(RANKS,ENTRIES,EXITS,REGIMES):
        p=Policy(entry=entry,exit=exit_,regime=regime)
        registry.append(dict(id=policy_id(rank,p),rank=rank,policy=p.__dict__,hash=p.digest()))
    dump(out/'experiment_registry.json',dict(primary_designs=registry,
         primary_design_count=len(registry),cost_scenarios=[BASE_COST.__dict__,STRESS_COST.__dict__],
         random_seed_range=[637000,637199],random_policy_exits=['LEGACY_TRAIL7_D12','STRUCT_ATR_D12'],
         random_policy_entries=['OPEN_CAPPED','RETEST_2D'],
         scope='PREDECLARED_THIS_ITERATION_REPEATEDLY_SEEN_HISTORY_NOT_OOS',
         retrospective_missing_top2_replays=True,chronological_segments=['H1','H2'],
         rr2_diagnostic_fixed_policy='V632_BASE|OPEN_CAPPED|STRUCT_ATR_D12|ALL',
         limit_penetration_stress_ticks=2,independent_new_trades=0))
    results={};stats=[];ledgers=[];days=[];mons=[];events=[]
    for reg in registry:
        chosen=select_D(rows,reg['rank']);p=Policy(**reg['policy'])
        for costs in (BASE_COST,STRESS_COST):
            run=replay(sessions,prices,chosen,p,costs);key=(reg['id'],costs.label)
            results[key]=run;tags=dict(experiment=reg['id'],cost_pct=costs.label)
            stats.append(dict(experiment=reg['id'],rank=reg['rank'],**metrics(run)))
            ledgers.extend(dict(**r,**tags) for r in run['trades'])
            days.extend(dict(**r,**tags) for r in run['daily'])
            mons.extend(dict(**r,**tags) for r in monthly(run))
            events.extend(dict(**r,**tags) for r in run['events'])
    for name,rr in [('scenario_comparison',stats),('closed_trade_ledger',ledgers),('daily_equity',days),
                    ('monthly_marked_equity',mons),('order_event_ledger',events)]:
        csv(out/f'{name}.csv',rr)
    return results,stats


def run_placebos(rows,prices,sessions,out):
    records=[]
    for seed in range(637000,637200):
        chosen=selected_random(rows,seed)
        for en,ex in itertools.product(('OPEN_CAPPED','RETEST_2D'),('LEGACY_TRAIL7_D12','STRUCT_ATR_D12')):
            r=replay(sessions,prices,chosen,Policy(entry=en,exit=ex))
            records.append(dict(seed=seed,**metrics(r)))
    csv(out/'same_date_random_selection_800.csv',records)
    return records


def run_diagnostics(rows,prices,sessions,results,out):
    stats=[];segment=[];match=[]
    for rank in RANKS:
        selected=select_D(rows,rank)
        for entry,ex in [('OPEN_CAPPED','LEGACY_TRAIL7_D12'),('OPEN_CAPPED','STRUCT_ATR_D12'),
                         ('RETEST_2D','LEGACY_TRAIL7_D12'),('RETEST_2D','STRUCT_ATR_D12')]:
            p=Policy(entry=entry,exit=ex);pid=policy_id(rank,p)
            run=results[(pid,BASE_COST.label)]
            best=sorted(run['trades'],key=lambda r:r['pnl_krw'],reverse=True)[:2]
            missing={r['asof'] for r in best}
            for costs in (BASE_COST,STRESS_COST):
                counter=replay(sessions,prices,[s for s in selected if s['asof'] not in missing],p,costs)
                stats.append(dict(diagnostic='RETROSPECTIVE_MISS_BEST_TWO_FULL_REPLAY',rank=rank,
                                  original=pid,removed_asof_dates=','.join(sorted(missing)),**metrics(counter)))
            for label,start,end in [('H1',FIRST,'2026-06-30'),('H2','2026-07-01',LAST)]:
                dates=[d for d in sessions if start<=d<=end]
                rr=replay(dates,prices,[s for s in selected if s['asof'] in dates],p)
                segment.append(dict(segment=label,rank=rank,original=pid,**metrics(rr)))
            if entry=='RETEST_2D':
                pp=Policy(entry=entry,exit=ex,limit_penetration_ticks=2)
                stats.append(dict(diagnostic='LIMIT_TWO_TICKS_PENETRATION',rank=rank,original=pid,
                                  **metrics(replay(sessions,prices,selected,pp))))
    for costs in (BASE_COST,STRESS_COST):
        p=Policy(require_rr2=True)
        r=replay(sessions,prices,select_D(rows,'V632_BASE'),p,costs)
        stats.append(dict(diagnostic='UNVERIFIED_D_RESISTANCE_GEOMETRY_RR2',rank='V632_BASE',**metrics(r)))
    for rank in RANKS:
        for s in select_D(rows,rank):
            for entry in ENTRIES:
                cap=s['signal_close']*1.025 if entry!='RETEST_2D' else s['signal_close']-.25*s['atr14']
                rr=net_rr(cap,s['stopD'],s['resistance'])
                match.append(dict(rank=rank,asof=s['asof'],ticker=s['ticker'],entry=entry,
                                  dated_cluster_resistance=s['resistance'],cap_before_tick=cap,
                                  net_rr_at_cap=rr,rr2_geometric_pass=rr is not None and rr>=2,
                                  final_score80_verified=False,PIT_issuer_verified=False,
                                  human_trade_review_ready=False))
    csv(out/'falsification_full_replays.csv',stats)
    csv(out/'chronological_segments_not_independent.csv',segment)
    csv(out/'dated_resistance_geometry.csv',match)
    return stats,segment


def same_exposure_benchmark(run,bench):
    """Benchmark on each actual paper trade's entry/exit dates, same notional.

    Assumes fractional benchmark units for comparison only. It is not an
    integer-share buy-and-hold portfolio and omits the open remainder.
    """
    records=[]
    for t in run['trades']:
        b=bench.loc[t['entry_date']];e=bench.loc[t['exit_date']]
        exit_px=float(e.Open if t['reason']=='WEAK_D5_EXIT_D6_OPEN' else e.Close)
        # A stop time within a daily stock candle is unknown; matched close is
        # explicitly an approximate comparison, not synchronous execution.
        ret=exit_px*(1-BASE_COST.sell)/(float(b.Open)*(1+BASE_COST.buy))-1
        bench_pnl=t['qty']*t['entry']*(1+BASE_COST.buy)*ret
        records.append(dict(asof=t['asof'],ticker=t['ticker'],entry_date=t['entry_date'],
                            exit_date=t['exit_date'],stock_pnl=t['pnl_krw'],
                            benchmark_same_notional_pnl=bench_pnl,
                            stock_minus_benchmark_pnl=t['pnl_krw']-bench_pnl,
                            benchmark_fractional_notional_and_exit_time_proxy=True))
    return records


def multiplicity_diagnostic(results,out):
    """Centered calendar-month block max-t, SAME 36 designs jointly resampled.

    Only a descriptive family-specific sensitivity. Ten already-studied months
    and unknown trials in previous versions prevent a global significance claim.
    """
    cols=[];ids=[]
    for (pid,cost),r in results.items():
        if cost!=BASE_COST.label or r['summary']['halted']:continue
        cols.append([m['return_pct'] for m in monthly(r)]);ids.append(pid)
    mat=np.asarray(cols,dtype=float).T
    n=mat.shape[0];mean=mat.mean(axis=0);std=mat.std(axis=0,ddof=1)
    observed=np.divide(np.sqrt(n)*mean,std,out=np.zeros_like(mean),where=std>0)
    rng=np.random.default_rng(637);idx=rng.integers(0,n,size=(5000,n))
    samples=(mat-mean)[idx];smean=samples.mean(axis=1);sstd=samples.std(axis=1,ddof=1)
    ts=np.divide(np.sqrt(n)*smean,sstd,out=np.zeros_like(smean),where=sstd>0)
    maxima=ts.max(axis=1)
    rows=[dict(experiment=pid,observed_monthly_t=float(t),
               within_36_centered_month_max_t_p=float((1+(maxima>=t).sum())/5001),
               calendar_months=n,already_studied=True,global_trial_count_unknown=True,
               is_future_profit_probability=False) for pid,t in zip(ids,observed)]
    csv(out/'within_family_multiplicity_diagnostic.csv',rows)
    return rows


def save_price_subset(source,hashes,out):
    target=out/'source_prices_subset.zip'
    with zipfile.ZipFile(source) as src,zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as dst:
        for name in sorted(hashes):dst.writestr(name,src.read(name))
        dst.writestr('subset_manifest.json',json.dumps(dict(parent_archive_sha256=FULL_ARCHIVE_SHA,
                    member_sha256=hashes,original_github_artifact_id=12502033196,
                    regular_only_attested=False,economic_total_return_verified=False),indent=2))
    return target


def run_all(source,candidates,out,random_runs=True,eligibility=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    rows,prices,hist,sessions,bench,hashes=load_data(source,candidates,eligibility)
    if eligibility:
        (out/'eligibility_snapshot_used.csv').write_bytes(Path(eligibility).read_bytes())
    dump(out/'adaptive_research_disclosure.json',dict(
         initial_raw_experiment_code_commit='6cde5d8',initial_raw_replays=494,
         followup_reason='Initial results exposed unverified common-share/pharma eligibility and winner sensitivity.',
         changes='Explicit KRX common equity / known nonpharma sector snapshot cleanup; added retest placebo and full miss-two replays at both costs.',
         historical_snapshot_applied_with_future_classification_bias=bool(eligibility),
         previous_494_results_retained_separately=True,not_independent_confirmation=True))
    # Registry is persisted BEFORE any new outcomes are replayed.
    results,stats=run_grid(rows,prices,sessions,out)
    diagnostics,segments=run_diagnostics(rows,prices,sessions,results,out)
    placebos=run_placebos(rows,prices,sessions,out) if random_runs else []
    multip=multiplicity_diagnostic(results,out)
    paired=[]
    for rank in RANKS:
        for en,ex in itertools.product(('OPEN_CAPPED','RETEST_2D'),('LEGACY_TRAIL7_D12','STRUCT_ATR_D12')):
            pid=policy_id(rank,Policy(entry=en,exit=ex))
            paired.extend(dict(experiment=pid,**r) for r in same_exposure_benchmark(results[(pid,BASE_COST.label)],bench))
    csv(out/'matched_exposure_benchmark_approximation.csv',paired)
    csv(out/'frozen_D_candidates.csv',rows)
    subset=save_price_subset(source,hashes,out)
    chosen=select_D(rows,'V632_BASE')
    hypotheses=[]
    for en,ex in itertools.product(('OPEN_CAPPED','RETEST_2D'),('LEGACY_TRAIL7_D12','STRUCT_ATR_D12')):
        a=[r['account_roi_pct'] for r in placebos if r['exit']==ex and r['entry']==en and not r['halted']]
        for rank in RANKS:
            pid=policy_id(rank,Policy(entry=en,exit=ex));s=results[(pid,BASE_COST.label)]['summary']
            v=s['account_roi_pct']
            hypotheses.append(dict(experiment=pid,roi_pct=v,
                same_date_random_portfolio_n=len(a),random_median_roi_pct=float(np.median(a)) if a else None,
                random_p05_roi_pct=float(np.quantile(a,.05)) if a else None,
                random_p95_roi_pct=float(np.quantile(a,.95)) if a else None,
                percentile_vs_random_pct=float(100*np.mean(np.asarray(a)<=v)) if a and v is not None else None))
    dump(out/'rank_random_comparison.json',hypotheses)
    meta=dict(schema='C3_V637_COMPLETED_RESEARCH',last_completed_source=LAST,
              source_github_run=39948306433,source_github_artifact=12502033196,
              original_archive_sha256=FULL_ARCHIVE_SHA,source_archive_used_sha256=sha(source),
              frozen_candidate_input_sha256=sha(candidates),subset_sha256=sha(subset),
              eligibility_audit_sha256=sha(eligibility) if eligibility else None,
              snapshot_common_nonpharma_cleanup_applied=bool(eligibility),
              snapshot_cleanup_is_not_historical_PIT_validation=True,
              model=MODEL,candidate_rows=len(rows),candidate_tickers=len(prices),signal_dates=len(chosen),
              sessions=len(sessions),primary_designs=36,cost_scenarios=72,
              random_portfolio_replays=len(placebos),diagnostic_replays=len(diagnostics),
              separate_segment_replays=len(segments),historical_total_replays=72+len(placebos)+len(diagnostics)+len(segments),
              all_scenario_daily_marks_complete=all(not s['halted'] for s in stats),
              all_outputs_are_repeated_retrospective_exploration=True,
              independent_future_completed_trades=0,issuer_common_stock_and_non_biotech_PIT_verified=False,
              regular_session_only_verified=False,dividends_and_corporate_actions_verified=False,
              final_score80_verified=False,broker_cash_or_fills_verified=False,
              mechanical_paper_returns_are_not_executable_strategy_returns=True,
              production_decision='CASH',trade_approved=False,orders_enabled=False,K100_changed=False)
    dump(out/'research_status.json',meta)
    dump(out/'output_sha256.json',{p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='output_sha256.json'})
    print(json.dumps(meta,ensure_ascii=False),flush=True)
    a=pd.DataFrame(stats)
    print(a[(a.cost_pct==BASE_COST.label)&(a.regime=='ALL')][
        ['rank','entry','exit','closed_trades','open_position_count','account_roi_pct',
         'daily_liquidation_mdd_pct','median_trade_net_pct','closed_pnl_ex_top2_contribution_krw']].to_string(index=False))
    print('RANDOM',json.dumps(hypotheses,ensure_ascii=False))
    return meta


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-zip',required=True)
    p.add_argument('--candidates',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--skip-placebos',action='store_true')
    p.add_argument('--eligibility-csv')
    args=p.parse_args()
    run_all(args.source_zip,args.candidates,args.out,not args.skip_placebos,args.eligibility_csv)
