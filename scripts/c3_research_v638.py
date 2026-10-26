#!/usr/bin/env python3
"""Stop-first marketwide snapshot research. Repeated historical data, no orders.

The whole source is screened on D-only features. Current issuer/industry
snapshots are not historical PIT eligibility, and OHLC fills are not verified.
"""
from __future__ import annotations
import argparse,hashlib,io,itertools,json,math
from pathlib import Path
import zipfile
from datetime import datetime,time
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import c3_event_replay_v637 as book
import c3_execution_v638 as execution
from c3_research_v637 import enrich,_bars,metrics,monthly,csv,dump,sha,FULL_ARCHIVE_SHA

PATTERNS=('NEAR60_STOP_FIRST','TREND_FIRST_PULLBACK')
RANKS=('LEGACY_D_SCORE','STRUCTURE_D_SCORE')
FIRST='2026-01-02'
LAST='2026-10-23'


def features(frame):
    x=enrich(frame)
    for col in ('Volume','TurnoverKRW'):x[col]=pd.to_numeric(x[col],errors='coerce')
    c=x.Close
    for n in (5,10,20,60):x[f'ma{n}']=c.rolling(n).mean()
    x['ma60slope']=x.ma60/x.ma60.shift(5)-1
    x['ret5']=100*(c/c.shift(5)-1);x['ret20']=100*(c/c.shift(20)-1)
    x['prior20high']=x.High.shift(1).rolling(20).max()
    x['rv20']=x.Volume/x.Volume.shift(1).rolling(20).mean()
    x['turnover_accel']=x.TurnoverKRW/x.TurnoverKRW.shift(1).rolling(20).mean()
    x['close_position']=(c-x.Low)/(x.High-x.Low).replace(0,np.nan)
    x['rolling3_stop']=x.Low.rolling(3).min()-.15*x.atr14
    x['breakout_pct']=100*(c/x.prior20high-1)
    x['valid_ohlc']=((x.Low>0)&(x.High>=x[['Open','Close']].max(axis=1))&
                    (x.Low<=x[['Open','Close']].min(axis=1)))
    x['valid65']=x.valid_ohlc.rolling(65).sum()==65
    return x


def candidate_from_index(x,bars,i,ticker,pattern,bench):
    row=x.iloc[i];history=bars[:i+1]
    pivot=execution.unbroken_daily_stop(history)
    if pivot is None:return None,'NO_UNBROKEN_DAILY_PIVOT'
    risk=100*(float(row.Close)-pivot['stop'])/float(row.Close)
    if not 0<risk<=12:return None,'CONFIRMED_STRUCTURE_RISK_GT12'
    d=str(row.Date);b=bench.loc[d]
    rs5=float(row.ret5-b.ret5);rs20=float(row.ret20-b.ret20)
    if not all(math.isfinite(v) for v in [rs5,rs20,float(row.rv20),float(row.turnover_accel)]):
        return None,'NONFINITE_D_FEATURE'
    rv=float(row.rv20);breakout=float(row.breakout_pct)
    legacy_risk=100*(float(row.Close)-float(row.rolling3_stop))/float(row.Close)
    base=.4*float(row.ret5)+2*min(rv,3)-.45*legacy_risk+.3*min(breakout,5)
    consistent=.4*float(row.ret5)+2*min(rv,3)-.45*risk+.3*min(breakout,5)
    resistance=book.resistance_clusters(history[-60:],float(row.Close),float(row.atr14))
    return dict(pattern=pattern,model=pattern,ticker=ticker,asof=d,signal_close=float(row.Close),
        stopD=pivot['stop'],atr14=float(row.atr14),riskD_pct=risk,ret5=float(row.ret5),
        ret20=float(row.ret20),rv20=rv,turnover_accel=float(row.turnover_accel),
        actual_turnover_krw=float(row.TurnoverKRW),rs5=rs5,rs20=rs20,
        turnover_session_scope='SOURCE_REPORTED_NOT_REGULAR_ONLY_ATTESTED',
        ohlc_session_scope='SOURCE_REPORTED_PENDING_FILE_LEVEL_ATTESTATION',
        LEGACY_D_SCORE=base,STRUCTURE_D_SCORE=consistent,
        requires_confirmed_pivot=True,confirmed_pivot_evidence=pivot,
        resistance=resistance['price'] if resistance else None,
        market_trend=bool(b.Close>b.ma20 and b.ma20slope>0)),None


def load_pool(source,eligibility,first=FIRST,last=LAST,expected_source_sha=None):
    book.iso_day(first);book.iso_day(last)
    if first>last:raise ValueError('REVERSED_SOURCE_DATE_RANGE')
    now=datetime.now(ZoneInfo('Asia/Seoul'))
    if last>now.date().isoformat() or last==now.date().isoformat() and now.time()<time(15,30):
        raise ValueError('REQUESTED_SESSION_NOT_COMPLETED')
    e=pd.read_csv(eligibility,dtype=str).fillna('')
    if e.ticker.duplicated().any() or not e.snapshot_research_allowed.isin(['True','False']).all():
        raise ValueError('INVALID_ISSUER_SNAPSHOT')
    allowed=set(e.loc[e.snapshot_research_allowed=='True','ticker'])
    records=[];prices={};hist={};reasons={};scanned=0;source_count=0
    with zipfile.ZipFile(source) as z:
        compact=json.loads(z.read('subset_manifest.json')) if 'subset_manifest.json' in z.namelist() else None
        expected=expected_source_sha or FULL_ARCHIVE_SHA
        if compact is None and sha(source)!=expected:raise ValueError('SOURCE_SHA_MISMATCH')
        if compact and compact['parent_archive_sha256']!=expected:raise ValueError('SUBSET_PARENT_MISMATCH')
        def read(n):
            raw=z.read(n)
            if compact and hashlib.sha256(raw).hexdigest()!=compact['member_sha256'].get(n):
                raise ValueError('SUBSET_MEMBER_SHA_CHANGED')
            return pd.read_csv(io.BytesIO(raw),dtype={'Date':str,'date':str})
        all_sessions=read('market/sessions.csv').date.tolist()
        if all_sessions!=sorted(set(all_sessions)) or last not in all_sessions:
            raise ValueError('INVALID_EXCHANGE_SESSIONS_OR_MISSING_REQUESTED_ASOF')
        index={d:i for i,d in enumerate(all_sessions)}
        bench=features(read('market/etf_prices/069500.csv')).set_index('Date',drop=False)
        for name in sorted(z.namelist()):
            if not(name.startswith('market/prices/') and name.endswith('.csv')):continue
            source_count+=1;ticker=Path(name).stem
            if ticker not in allowed:continue
            scanned+=1;x=features(read(name));bars=None;emitted=[]
            session_ix=x.Date.map(index)
            contiguous=(session_ix-session_ix.shift(64)==64)
            common=(x.Date.between(first,last)&x.valid65&contiguous&(x.Close>=2000)&
                    (x.TurnoverKRW>=5e9)&(x.atr14>0)&(x.atr14/x.Close<=.12))
            near=(common&(x.ma5>x.ma10)&(x.ma10>x.ma20)&x.ret5.between(3,17)&
                  x.ret20.between(-5,32)&(x.close_position>=.65)&(x.rv20>=.75)&
                  (x.ma20slope>0)&(x.Close>x.prior20high)&(x.ma20/x.ma60).between(.92,1.02))
            trend=(common&(x.Close>x.ma20)&(x.ma20>x.ma60)&(x.ma20slope>0)&
                   (x.ma60slope>=0)&(x.Low<=x.ma10+.25*x.atr14)&
                   (x.Close>x.High.shift(1))&(x.Close>=x.Open)&(x.close_position>=.65)&
                   x.rv20.between(.5,1.8)&x.ret20.between(0,40))
            breakouts=((x.Close>x.prior20high)&(x.rv20>=1.2)&x.valid65).fillna(False).to_numpy()
            near_array=near.fillna(False).to_numpy();trend_array=trend.fillna(False).to_numpy()
            last_break=-100;last_emitted={p:-100 for p in PATTERNS};consumed_break=-100
            for i in range(len(x)):
                possibilities=[]
                if near_array[i] and i-last_emitted[PATTERNS[0]]>=12:possibilities.append(PATTERNS[0])
                if trend_array[i] and 1<=i-last_break<=8 and consumed_break!=last_break:
                    possibilities.append(PATTERNS[1])
                for pattern in possibilities:
                    if bars is None:bars=_bars(x)
                    r,why=candidate_from_index(x,bars,i,ticker,pattern,bench)
                    if r:
                        records.append(r);emitted.append(i);last_emitted[pattern]=i
                        if pattern==PATTERNS[1]:consumed_break=last_break
                    else:reasons[why]=reasons.get(why,0)+1
                if breakouts[i]:last_break=i
            if emitted:
                prices[ticker]={b['date']:b for b in bars};hist[ticker]=bars
            if scanned%500==0:print('SCREENED',scanned,'candidates',len(records),flush=True)
    sessions=[d for d in all_sessions if first<=d<=last]
    audit=dict(source_price_codes=source_count,snapshot_eligible_codes_scanned=scanned,
               candidate_rows=len(records),candidate_codes=len(prices),D_stop_rejections=reasons,
               first=first,last=last,source_archive_sha256=sha(source),eligibility_sha256=sha(eligibility),
               corporate_actions_regular_session_and_historical_PIT_verified=False)
    return records,prices,hist,sessions,bench,audit


def choose_D(pool,pattern,rank,random_seed=None):
    if rank not in RANKS:raise ValueError('UNDECLARED_D_RANK')
    groups={}
    for r in pool:
        if r['pattern']==pattern:groups.setdefault(r['asof'],[]).append(r)
    rng=np.random.default_rng(random_seed) if random_seed is not None else None
    selected=[]
    for d,group in sorted(groups.items()):
        if rng is None:choice=sorted(group,key=lambda r:(-r[rank],r['ticker']))[0]
        else:
            group=sorted(group,key=lambda r:r['ticker']);choice=group[int(rng.integers(len(group)))]
        selected.append(dict(choice))
    return selected


def identifier(pattern,rank,p):return '|'.join([pattern,rank,p.entry,p.exit,p.regime])


def dump_run_outputs(out,runs):
    stats=[];trades=[];days=[];months=[];events=[]
    for (pid,cost),run in runs.items():
        tag=dict(experiment=pid,cost_pct=cost)
        stats.append(dict(experiment=pid,**metrics(run)))
        trades.extend(dict(**t,**tag) for t in run['trades'])
        days.extend(dict(**t,**tag) for t in run['daily'])
        months.extend(dict(**t,**tag) for t in monthly(run))
        events.extend(dict(**t,**tag) for t in run['events'])
    for name,data in [('scenario_comparison',stats),('trade_ledger',trades),('daily_equity',days),
                      ('monthly_equity',months),('order_events',events)]:csv(out/(name+'.csv'),data)
    return stats


def primary(pool,prices,sessions,out):
    runs={}
    for pattern,rank,en,ex,regime in itertools.product(PATTERNS,RANKS,execution.ENTRIES,execution.EXITS,execution.REGIMES):
        p=execution.Policy(entry=en,exit=ex,regime=regime);pid=identifier(pattern,rank,p)
        selected=choose_D(pool,pattern,rank)
        for costs in (book.BASE_COST,book.STRESS_COST):
            runs[(pid,costs.label)]=execution.replay(sessions,prices,selected,p,costs)
    return runs,dump_run_outputs(out,runs)


def diagnostics(pool,prices,sessions,runs,out):
    rows=[];neighbors=[];missed=[];capital=[];segments=[]
    for pattern in PATTERNS:
        selected=choose_D(pool,pattern,'STRUCTURE_D_SCORE')
        for ex in ('STRUCT_ATR_D12','TARGET10_D12'):
            p=execution.Policy(exit=ex);pid=identifier(pattern,'STRUCTURE_D_SCORE',p)
            base=runs[(pid,book.BASE_COST.label)]
            top=sorted(base['trades'],key=lambda r:r['pnl_krw'],reverse=True)[:2]
            dates={t['asof'] for t in top}
            for costs in (book.BASE_COST,book.STRESS_COST):
                r=execution.replay(sessions,prices,[s for s in selected if s['asof'] not in dates],p,costs)
                rows.append(dict(diagnostic='RETROSPECTIVE_MISS_TOP_TWO_FULL_REPLAY',pattern=pattern,
                                 original=pid,removed_dates=','.join(sorted(dates)),**metrics(r)))
        for costs in (book.BASE_COST,book.STRESS_COST,book.Costs(.004,.0085)):
            for kind,p in [('RR2_GEOMETRY',execution.Policy(require_rr2=True)),
                           ('EXTRA_STOP_SLIPPAGE_30BP',execution.Policy(extra_stop_slippage=.003)),
                           ('TWO_TICK_LIMIT_PENETRATION',execution.Policy(limit_penetration_ticks=2))]:
                rows.append(dict(diagnostic=kind,pattern=pattern,**metrics(execution.replay(sessions,prices,selected,p,costs))))
        for depth,trail,costs in itertools.product((.15,.25,.50),(1.5,2.,2.5),(book.BASE_COST,book.STRESS_COST)):
            p=execution.Policy(retest_atr=depth,trail_atr=trail)
            neighbors.append(dict(pattern=pattern,**metrics(execution.replay(sessions,prices,selected,p,costs))))
        for probability,seed,costs in itertools.product((.2,.4),range(638000,638020),(book.BASE_COST,book.STRESS_COST)):
            rng=np.random.default_rng(seed)
            preknown=[dict(s,simulated_fill_allowed=bool(rng.random()>=probability)) for s in selected]
            r=execution.replay(sessions,prices,preknown,execution.Policy(),costs)
            missed.append(dict(pattern=pattern,miss_probability_sensitivity=probability,seed=seed,**metrics(r)))
        for cash,risk,costs in itertools.product((269230.,1e6,3e6),(.005,.01),(book.BASE_COST,book.STRESS_COST)):
            p=execution.Policy(initial_cash=cash,risk_fraction=risk)
            capital.append(dict(pattern=pattern,**metrics(execution.replay(sessions,prices,selected,p,costs))))
        for label,start,end in [('H1',FIRST,'2026-06-30'),('H2','2026-07-01',LAST)]:
            ss=[d for d in sessions if start<=d<=end]
            r=execution.replay(ss,prices,[s for s in selected if s['asof'] in ss],execution.Policy())
            segments.append(dict(pattern=pattern,segment=label,**metrics(r)))
    for n,data in [('falsification',rows),('parameter_neighbors',neighbors),('missed_fills_sensitivity',missed),
                   ('capital_integer_shares',capital),('chronological_segments',segments)]:csv(out/(n+'.csv'),data)
    return dict(falsification=len(rows),parameter_neighbors=len(neighbors),missed_fills=len(missed),
                capital_scenarios=len(capital),segments=len(segments))


def random_controls(pool,prices,sessions,out,count=200):
    rows=[]
    for pattern,ex,seed in itertools.product(PATTERNS,('STRUCT_ATR_D12','TARGET10_D12'),range(638000,638000+count)):
        selected=choose_D(pool,pattern,'STRUCTURE_D_SCORE',random_seed=seed)
        r=execution.replay(sessions,prices,selected,execution.Policy(exit=ex))
        rows.append(dict(pattern=pattern,seed=seed,**metrics(r)))
    csv(out/'same_date_random_controls.csv',rows)
    return rows


def frozen_legacy_stop_audit(old_candidates,source_prices,out):
    old=pd.read_csv(old_candidates,dtype={'ticker':str});old=old[old.model=='NEAR60_RISK8']
    evidence=[]
    with zipfile.ZipFile(source_prices) as z:
        for ticker,group in old.groupby('ticker'):
            path=f'market/prices/{ticker}.csv'
            if path not in z.namelist():continue
            frame=features(pd.read_csv(io.BytesIO(z.read(path)),dtype={'Date':str}));bars=_bars(frame)
            for s in group.to_dict('records'):
                h=[b for b in bars if b['date']<=s['asof']]
                previous=book.confirmed_daily_stop(h,h[-1]['atr14'])
                new=execution.unbroken_daily_stop(h)
                broken=False
                if previous:
                    later=[b for b in h if b['date']>previous['confirmation_date']]
                    broken=any(b['low']<=previous['stop'] for b in later)
                evidence.append(dict(asof=s['asof'],ticker=ticker,
                    v637_confirmed_stop=previous['stop'] if previous else None,
                    v637_pivot_already_breached=broken,v638_unbroken_stop=new['stop'] if new else None,
                    v638_pivot_date=new['pivot_date'] if new else None))
    csv(out/'legacy_confirmed_stop_validity_audit.csv',evidence)
    return evidence


def run(source,eligibility,out,legacy_candidates=None,random_count=200):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    registry=dict(schema='C3_V638_EXPERIMENT_REGISTRY',patterns=PATTERNS,ranks=RANKS,
        entries=execution.ENTRIES,exits=execution.EXITS,regimes=execution.REGIMES,costs=[.65,.95],
        primary_design_count=72,primary_cost_scenarios=144,default_cash=1e6,default_account_risk=.01,
        actual_turnover_min_krw=5e9,stop_max_D_price_risk_pct=12,
        parameter_neighbors=dict(retest_atr=[.15,.25,.50],trail_atr=[1.5,2.,2.5]),
        missed_fill_sensitivities=[.2,.4],random_seed_range=[638000,638000+random_count-1],
        adapted_after_v637_results=True,untouched_historical_holdout_claimed=False,
        new_independent_completed_trades=0,orders_enabled=False,trade_approved=False)
    dump(out/'experiment_registry.json',registry)
    pool,prices,hist,sessions,bench,audit=load_pool(source,eligibility)
    csv(out/'D_only_full_market_candidates.csv',pool);dump(out/'source_and_coverage_audit.json',audit)
    if not pool:raise ValueError('NO_DECLARED_PATTERN_CANDIDATES')
    runs,stats=primary(pool,prices,sessions,out)
    extra=diagnostics(pool,prices,sessions,runs,out)
    controls=random_controls(pool,prices,sessions,out,random_count)
    comparisons=[]
    for pattern,rank,ex in itertools.product(PATTERNS,RANKS,('STRUCT_ATR_D12','TARGET10_D12')):
        p=execution.Policy(exit=ex);pid=identifier(pattern,rank,p);s=runs[(pid,.65)]['summary']
        randoms=[r['account_roi_pct'] for r in controls if r['pattern']==pattern and r['exit']==ex and not r['halted']]
        v=s['account_roi_pct']
        comparisons.append(dict(experiment=pid,roi_pct=v,random_count=len(randoms),
            random_median_roi_pct=float(np.median(randoms)) if randoms else None,
            random_p05_roi_pct=float(np.quantile(randoms,.05)) if randoms else None,
            random_p95_roi_pct=float(np.quantile(randoms,.95)) if randoms else None,
            percentile_not_future_win_probability=float(np.mean(np.array(randoms)<=v)*100) if randoms and v is not None else None))
    dump(out/'rank_vs_random.json',comparisons)
    if legacy_candidates:frozen_legacy_stop_audit(legacy_candidates,source,out)
    # Within-family descriptive max-t; ten already-seen months do not establish
    # a global search-adjusted significance result.
    matrix=[];ids=[]
    for (pid,cost),r in runs.items():
        if cost==.65 and not r['summary']['halted']:
            matrix.append([v['return_pct'] for v in monthly(r)]);ids.append(pid)
    a=np.asarray(matrix).T;n=a.shape[0];means=a.mean(axis=0);sd=a.std(axis=0,ddof=1)
    ts=np.divide(np.sqrt(n)*means,sd,out=np.zeros_like(means),where=sd>0)
    rng=np.random.default_rng(638);blocks=(a-means)[rng.integers(0,n,size=(5000,n))]
    bs=blocks.std(axis=1,ddof=1);bt=np.divide(np.sqrt(n)*blocks.mean(axis=1),bs,out=np.zeros_like(bs),where=bs>0)
    maxima=bt.max(axis=1)
    csv(out/'within_family_multiplicity.csv',[dict(experiment=pid,monthly_t=float(t),
        family_max_t_p_descriptive=float((1+(maxima>=t).sum())/5001),months=n,
        historical_global_trial_count_unknown=True) for pid,t in zip(ids,ts)])
    qty=math.floor(1e6/(float(bench.loc[sessions[0]].Open)*(1+book.BASE_COST.buy)))
    cash=1e6-qty*float(bench.loc[sessions[0]].Open)*(1+book.BASE_COST.buy)
    bvalue=cash+qty*float(bench.loc[sessions[-1]].Close)*(1-book.BASE_COST.sell)
    status=dict(schema='C3_V638_COMPLETED_REPEATED_HISTORY_RESEARCH',**audit,
        primary_cost_scenarios=len(runs),random_control_replays=len(controls),**extra,
        total_replays=len(runs)+len(controls)+sum(extra.values()),
        halted_primary_scenarios=sum(r['halted'] for r in stats),
        hypothetical_benchmark_full_investment_roi_pct=100*(bvalue/1e6-1),
        full_investment_benchmark_is_not_same_risk_or_exposure=True,
        source_was_already_studied=True,actual_current_broker_cash_not_updated=True,
        new_independent_completed_trades=0,final80_certified_regular_only_PIT_and_2R_not_verified=True,
        production_decision='CASH',trade_approved=False,orders_enabled=False,K100_changed=False)
    dump(out/'research_status.json',status)
    dump(out/'output_sha256.json',{p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='output_sha256.json'})
    print('STATUS',json.dumps(status,ensure_ascii=False),flush=True)
    s=pd.DataFrame(stats)
    print(s[(s.cost_pct==.65)&(s.regime=='ALL')][['experiment','closed_trades','account_roi_pct',
        'daily_liquidation_mdd_pct','profit_factor','median_trade_net_pct']].to_string(index=False))
    return status


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source-zip','eligibility-csv','out'):p.add_argument('--'+name,required=True)
    p.add_argument('--legacy-candidates');p.add_argument('--random-count',type=int,default=200)
    p.add_argument('--snapshot-only',action='store_true')
    p.add_argument('--asof');p.add_argument('--expected-source-sha');p.add_argument('--protocol')
    a=p.parse_args()
    if a.snapshot_only:
        if not(a.asof and a.expected_source_sha and a.protocol):
            raise ValueError('NEW_SNAPSHOT_NEEDS_ASOF_KNOWN_ARTIFACT_SHA_AND_FROZEN_PROTOCOL')
        out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
        rows,_,_,_,_,audit=load_pool(a.source_zip,a.eligibility_csv,last=a.asof,expected_source_sha=a.expected_source_sha)
        if rows:csv(out/'D_only_full_market_candidates.csv',rows)
        else:pd.DataFrame(columns=['asof','ticker','pattern','market_trend','LEGACY_D_SCORE','STRUCTURE_D_SCORE']).to_csv(
            out/'D_only_full_market_candidates.csv',index=False,encoding='utf-8-sig')
        dump(out/'research_status.json',dict(audit,first=FIRST,last=a.asof))
        dump(out/'output_sha256.json',{'D_only_full_market_candidates.csv':sha(out/'D_only_full_market_candidates.csv')})
        from c3_protocol_v638 import capture
        print(json.dumps(capture(out,a.protocol,a.asof,out/'D_close_freeze.json'),ensure_ascii=False))
    else:run(a.source_zip,a.eligibility_csv,a.out,a.legacy_candidates,a.random_count)
