"""Frozen whole-market replay and purged chronological dynamic-entry study.

No live provider queries, registration, ledger writes, signals, or notification.
The old CLI must reproduce the original scope before this study may run.
"""
import argparse,csv,gzip,hashlib,json,statistics,time
from collections import Counter,defaultdict
from pathlib import Path
from c3_dynamic_entry_v2 import DEFAULT,METHODS,MODELS,indicators,indicator_at,plans,best_plan,evaluate_trade,company_gate,pick_unique
from c3_forward_ledger_v8 import read_record,hash_value
from c3_daily_research_v8 import histories
from c3_selection_scope_v5 import classify,unique_index,read_csv,selection_features,digest
from c3_selection_factors_v6 import causal_factors,regime
from c3_entry_practical_v7 import features,entry_plan

DAY='2026-11-11'
CASES=('028050','180640','089860','034230','134380','012620','053060','136540')


def write(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n')


def load_dataset(engine,state,old,asof=None):
    asof=asof or DAY
    inputs=old/'private_inputs';panel=inputs/'panel/official_panel.csv.gz';audit=inputs/'panel/quality_audit.json'
    original=json.loads((state/'reports/c3_forward_v8/latest.json').read_text())
    if original.get('source_price_asof')!=asof:raise ValueError('REGISTERED_LATEST_SOURCE_DAY_MISMATCH')
    lane=state/'reports/c3_forward_v8/lanes/krx_unadjusted_v12'
    market=read_record(lane/'markets'/(asof+'.json.gz'));decision=read_record(lane/'decisions'/(asof+'.json'))
    if market['asof']!=asof or decision['source_snapshot_hash']!=hash_value(market):raise ValueError('FROZEN_ORIGINAL_DATE_OR_HASH_MISMATCH')
    meta=json.loads(audit.read_text())
    if digest(panel)!=original['source_hashes']['panel'] or digest(audit)!=original['source_hashes']['audit']:raise ValueError('FROZEN_HISTORY_HASH_MISMATCH')
    prices={t:dict(r,ticker=t,asof=asof) for t,r in market['rows'].items()}
    snapshots={r['asof']:r for r in (read_record(p) for p in sorted((lane/'markets').glob('*.json.gz'))) if r['asof']<=asof}
    from c3_current_candidates_v7 import fresh_snapshot
    oldprices,om=fresh_snapshot(inputs/'latest/requested-date-probe/2026-11-04')
    snapshots['2026-11-04']=dict(rows={t:dict(r,date='2026-11-04') for t,r in oldprices.items()})
    sessions=market['sessions'];grid={d:i for i,d in enumerate(sessions)}
    oldpast,_=histories(panel,audit,prices,snapshots,sessions,asof)
    raw=defaultdict(dict);count=0
    with gzip.open(panel,'rt') as f:
        for r in csv.DictReader(f):
            count+=1
            if r['ticker'] in prices and r['date']<=asof:raw[r['ticker']][r['date']]=r
    for d,s in snapshots.items():
        for t,r in s['rows'].items():
            if t in prices:raw[t][d]=dict(r,date=d)
    events={(r['ticker'],r['date']) for r in meta['reference_rebase_candidates']}
    allbars={};current={};coverage=Counter()
    for t,by in raw.items():
        bars=[];previous=None;segment=0
        for day,r in sorted(by.items()):
            if day not in grid:raise ValueError('HISTORY_DAY_OUTSIDE_FROZEN_BOARD_GRID')
            vals={k:float(r[k]) for k in ('open','high','low','close','volume','turnover_krw')}
            valid=0<vals['low']<=min(vals['open'],vals['close'])<=max(vals['open'],vals['close'])<=vals['high'] and vals['volume']>0 and vals['turnover_krw']>0
            boundary=(t,day) in events or bool(r.get('action_boundary',False))
            if previous:boundary=boundary or grid[day]!=grid[previous['date']]+1 or r['name']!=previous['name'] or (previous['close']>0 and abs(vals['close']/previous['close']-1)>.35)
            if boundary or not valid:segment+=1;coverage['boundary_or_invalid_bars']+=1
            b=dict(vals,date=day,name=r['name'],segment=segment,tradable=valid,invalid_data=not valid,action_boundary=boundary)
            bars.append(b)
            if not valid:segment+=1
            previous=b
        allbars[t]=bars
        tail=[b for b in bars if b['segment']==bars[-1]['segment'] and b['tradable']]
        if len(tail)>=65 and tail[-1]['date']==asof:current[t]=tail
    # Independent reconstruction may extend warm-up, but must preserve every
    # one of the original model's last90 observed prices exactly.
    if set(current)!=set(oldpast):raise ValueError('EXTENDED_HISTORY_UNIVERSE_CHANGED')
    fields=('date','open','high','low','close','volume','turnover_krw','name')
    for t,past in oldpast.items():
        a=[{k:b[k] for k in fields} for b in current[t][-90:]];b=[{k:b[k] for k in fields} for b in past]
        if a!=b:raise ValueError('EXTENDED_HISTORY_CHANGED_APPROVED_90_BAR_SUFFIX')
    basic=inputs/'issuer/basic';scope=engine/'reports/c3_work5_20261105/sources'
    basics=unique_index(read_csv(basic/'KOSPI_basic_v610.csv')+read_csv(basic/'KOSDAQ_basic_v610.csv'));kind=unique_index(read_csv(scope/'kind_companies.csv'))
    secondary=defaultdict(list)
    for r in read_csv(scope/'secondary_industries.csv'):secondary[r['ticker']].append(r)
    eligible={t for t in current if classify(prices[t],basics.get(t),kind.get(t),secondary[t])=='VERIFIED_NONBIO_COMMON_AS_REPORTED'}
    oldsummary=json.loads((old/'reselection_summary.json').read_text())
    expected=original['current_scope']
    if (len(prices),len(current),len(eligible),oldsummary['stock_preselector_count'],oldsummary['original_b_filter_count'])!=(expected['price_rows'],expected['continuous_history'],expected['analysis_eligible'],expected['a_candidates'],expected['b_candidates']):raise ValueError('REGISTERED_CURRENT_SCOPE_NOT_REPRODUCED')
    if asof=='2026-11-11' and (len(prices),len(current),len(eligible),oldsummary['stock_preselector_count'],oldsummary['original_b_filter_count'],oldsummary['eligible_entry_feasible_tickers'])!=(2769,2416,1988,149,50,4):raise ValueError('REQUIRED_NOV11_BASELINE_NOT_REPRODUCED')
    metadata={t:dict(ticker=t,name=prices[t]['name'],market=prices[t]['market'],sector=secondary[t][0]['sector']) for t in eligible}
    available=sorted({b['date'] for rows in allbars.values() for b in rows})
    provenance=dict(asof=asof,original_source_run_id=original['source_run_id'],original_decision_payload_sha256=hash_value(decision),original_market_payload_sha256=hash_value(market),
        full_market=len(prices),continuous_history=len(current),analysis_eligible=len(eligible),original_technical=oldsummary['stock_preselector_count'],original_b=oldsummary['original_b_filter_count'],old_geometry_pass=oldsummary['eligible_entry_feasible_tickers'],
        original_strength_and_geometry_pass=oldsummary.get('b_pool_research_pass_count',0),panel_sha256=digest(panel),panel_rows=count,panel_first=available[0],panel_last=available[-1],
        panel_sessions=len(available),current_source_rows={t:len(current[t]) for t in CASES if t in current},
        original_last90_suffix_unchanged=True,regular_only_certified=False,corporate_action_boundaries_respected=True,
        sector_membership_pit_verified=False,survivorship_bias_removed=False,historical_scope='REGISTERED_NONBIO_UNIVERSE_CONDITIONED_PRICE_ONLY',
        historical_financial_ranking_used=False,original_ledgers_modified=False,orders_enabled=False,telegram_requests=0,
        exclusions=dict(coverage),old_source_sha256=original['source_validation_sha256'])
    return allbars,current,eligible,metadata,market,oldsummary,provenance


def precompute(allbars):
    cache={}
    for t,bars in allbars.items():
        groups=defaultdict(list)
        for b in bars:
            if b['tradable']:groups[b['segment']].append(b)
        per={}
        for group in groups.values():
            if len(group)<DEFAULT['min_history']:continue
            x=indicators(group)
            for i,b in enumerate(group):
                if i+1>=DEFAULT['min_history']:
                    per[b['date']]=(group[:i+1],{k:v[:i+1] for k,v in x.items()})
        cache[t]=per
    return cache


def summarize(events,horizon,validity,fold):
    selected=[e for e in events if e['fold']==fold]
    outcomes=[(e,e['outcomes'][str(validity)][str(horizon)]) for e in selected]
    complete=[(e,o) for e,o in outcomes if o.get('return_pct') is not None]
    filled=[(e,o) for e,o in complete if o.get('filled')]
    avg=lambda vals:statistics.mean(vals) if vals else None
    n=len(complete);f=len(filled)
    return dict(selected_events=len(selected),complete_opportunities=n,censored=len(selected)-n,fills=f,
        fill_rate_pct=100*f/n if n else None,expectancy_per_opportunity_net_pct=avg([o['return_pct'] for _,o in complete]),
        mean_filled_net_pct=avg([o['return_pct'] for _,o in filled]),win_rate_pct=100*sum(o['return_pct']>0 for _,o in filled)/f if f else None,
        stop_rate_pct=100*sum(o['status'].startswith('STOP') for _,o in filled)/f if f else None,
        r1_hit_rate_pct=100*sum(o.get('r1_hit_before_stop',False) for _,o in filled)/f if f else None,
        r2_path_hit_rate_pct=100*sum(o.get('r2_path_hit',False) for _,o in filled)/f if f else None,
        mfe_pct=avg([o['mfe_pct'] for _,o in filled]),mae_pct=avg([o['mae_pct'] for _,o in filled]),
        missed_rally_over_10pct=sum(o.get('missed_rally_mfe_pct',0)>=10 for _,o in complete if not o.get('filled')),
        crash_after_fill_over_10pct=sum(o['mae_pct']<=-10 for _,o in filled),status_counts=dict(Counter(o['status'] for _,o in outcomes)),
        regime={r:dict(fills=sum(e['regime']==r for e,_ in filled),mean_net_pct=avg([o['return_pct'] for e,o in filled if e['regime']==r])) for r in ('UP','DOWN','SIDEWAYS')})


def study(engine,state,old,out):
    started=time.monotonic();allbars,current,eligible,meta,market,oldsummary,provenance=load_dataset(engine,state,old)
    cache=precompute({t:allbars[t] for t in eligible});sessions=market['sessions'];idx=market['indices']
    available=sorted({d for per in cache.values() for d in per})
    source_days=sorted({b['date'] for rows in allbars.values() for b in rows});hold_start=source_days[-DEFAULT['holdout_last_sessions']]
    hold_i=sessions.index(hold_start);dev_end=sessions[hold_i-DEFAULT['purge_sessions']-1]
    active=sorted(d for d in available if d<=dev_end or d>=hold_start)
    current_diag=[];daily={};method_counts=Counter();setup_counts=Counter();quality_reasons=Counter();historical_setups=defaultdict(Counter);funnels=defaultdict(lambda:defaultdict(Counter))
    for number,day in enumerate(active):
        pool=[];regimes={m:regime([v for d,v in sorted(idx[m].items()) if d<=day]) for m in ('KOSPI','KOSDAQ')}
        for t in sorted(eligible):
            item=cache[t].get(day)
            if item is None:continue
            past,pre=item;m=meta[t]['market'];mr=100*(idx[m][day]/idx[m][past[-21]['date']]-1)
            f=selection_features(past,mr)
            if f is None:continue
            cf=causal_factors(past,idx[m]);new,watch,error=plans(past,pre,t);best=best_plan(new);fi=indicator_at(past,pre)
            strong=cf['own_rs20']>0 and cf['rs_accel5']>0;liquid=f['turnover20']>=DEFAULT['min_turnover20_krw']
            r=dict(meta[t],date=day,close=past[-1]['close'],own_rs20=cf['own_rs20'],rs_accel5=cf['rs_accel5'],turnover20=f['turnover20'],
                regime=regimes[m],momentum_pass=strong,liquidity_pass=liquid,indicators=fi,plans=new,best_plan=best,structural_watch=watch,
                dynamic_geometry_pass=best is not None,financial_quality='UNKNOWN_PIT_NOT_RANKED',buy_approved=False)
            pool.append(r)
            fold='DEVELOPMENT' if day<=dev_end else 'HOLDOUT'
            for p in new:
                historical_setups[fold][p['method']]+=1;funnel=funnels[fold][p['method']];funnel['generated']+=1
                funnel['setup_confirmed']+=int(p['setup_confirmed']);funnel['geometry_pass']+=int(p['geometry_pass']);funnel['geometry_and_momentum_liquidity']+=int(p['geometry_pass'] and strong and liquid)
                for reason in p['reasons']:funnel[reason]+=1
            if day==DAY:
                current_diag.append(r)
                for p in new:setup_counts[p['method']]+=1;method_counts[p['method']]+=int(p['geometry_pass'])
                if not strong:quality_reasons['RS_NOT_POSITIVE_AND_IMPROVING']+=1
                if not liquid:quality_reasons['TURNOVER20_BELOW_1BN_RESEARCH_FLOOR']+=1
        pool.sort(key=lambda r:(-r['turnover20'],-r['own_rs20'],r['ticker']))
        bpool=[r for r in pool if r['momentum_pass']]
        if day==DAY:
            # Original count includes65-bar starts; expose the extra80-bar limit.
            original=json.loads((old/'technical_candidates.json').read_text())['rows']
            missing=sorted(set(r['ticker'] for r in original)-{r['ticker'] for r in pool})
            provenance['dynamic_warmup_excluded_from149']=missing;provenance['dynamic_reviewed_technical']=len(pool)
        arms={}
        original=[]
        for r in bpool[:2]:
            past,_=cache[r['ticker']][day];mr=100*(idx[r['market']][day]/idx[r['market']][past[-21]['date']]-1)
            oldf,why=features(past[-90:],mr);p,reason=entry_plan(r['ticker'],past[-90:],oldf,'A_SUPPORT_LIMIT',r['regime']) if oldf else (None,why)
            original.append(dict(r,chosen_plan=p))
        arms['C3_ORIGINAL']=original
        for model in MODELS[1:]:
            arms[model]=[dict(r,chosen_plan=r['best_plan']) for r in pool if r['momentum_pass'] and r['liquidity_pass'] and r['best_plan'] is not None
                         and ('BB' not in model or r['indicators']['bb_filter']) and ('ADX' not in model or r['indicators']['adx_filter'])]
        for method in METHODS:
            arms[method]=[dict(r,chosen_plan=p) for r in pool if r['momentum_pass'] and r['liquidity_pass'] for p in r['plans'] if p['method']==method and p['geometry_pass']]
        daily[day]=arms
        if number%15==0:print('DYNAMIC_SCREEN_PROGRESS',day,len(pool),flush=True)
    if len(current_diag)+len(provenance['dynamic_warmup_excluded_from149'])!=149:raise ValueError('CURRENT_TECHNICAL_SCOPE_MISMATCH')
    all_models=MODELS+METHODS
    events={m:[] for m in all_models};suppressed=Counter();last={m:{} for m in all_models}
    for day,arms in sorted(daily.items()):
        di=sessions.index(day);fold='DEVELOPMENT' if day<=dev_end else 'HOLDOUT'
        for model,rows in arms.items():
            chosen_rows,skipped=pick_unique(rows,last[model],di);suppressed[model]+=skipped
            for r in chosen_rows:
                t=r['ticker'];bars=allbars[t];bi=next(i for i,b in enumerate(bars) if b['date']==day)
                e=dict(ticker=t,name=r['name'],date=day,fold=fold,model=model,regime=r['regime'],method=(r['chosen_plan'] or {}).get('method','NO_ORIGINAL_SUPPORT_PLAN'),plan=r['chosen_plan'],outcomes={})
                for v in (1,2,3):
                    e['outcomes'][str(v)]={str(h):(evaluate_trade(r['chosen_plan'],bars,bi,sessions,v,h,sessions[hold_i-1] if fold=='DEVELOPMENT' else DAY) if r['chosen_plan'] else
                        dict(status='NO_ORIGINAL_SUPPORT_PLAN' if di+3+h<len(sessions) and sessions[di+3+h]<=(sessions[hold_i-1] if fold=='DEVELOPMENT' else DAY) else 'CENSORED_COMMON_CLOCK',return_pct=0. if di+3+h<len(sessions) and sessions[di+3+h]<=(sessions[hold_i-1] if fold=='DEVELOPMENT' else DAY) else None,filled=False)) for h in (5,10,20)}
                events[model].append(e)
    performance={m:{fold:{str(v):{str(h):summarize(rows,h,v,fold) for h in (5,10,20)} for v in (1,2,3)} for fold in ('DEVELOPMENT','HOLDOUT')} for m,rows in events.items()}
    for model in all_models:
        for fold in ('DEVELOPMENT','HOLDOUT'):
            limit=sessions[hold_i-1] if fold=='DEVELOPMENT' else DAY
            for validity in (1,2,3):
                for horizon in (5,10,20):
                    metrics=performance[model][fold][str(validity)][str(horizon)]
                    common_days=[d for d in active if (d<=dev_end if fold=='DEVELOPMENT' else d>=hold_start) and sessions.index(d)+3+horizon<len(sessions) and sessions[sessions.index(d)+3+horizon]<=limit]
                    metrics['common_mature_decision_days']=len(common_days)
                    vals=[e['outcomes'][str(validity)][str(horizon)]['return_pct'] for e in events[model] if e['fold']==fold and e['date'] in common_days and e['outcomes'][str(validity)][str(horizon)].get('return_pct') is not None]
                    metrics['half_slot_cash_inclusive_opportunity_net_pct']=sum(vals)*.5/len(common_days) if common_days else None
                    metrics['portfolio_simulated']=False
    usable=[m for m in MODELS[1:] if performance[m]['DEVELOPMENT']['1']['20']['complete_opportunities']>=DEFAULT['selector_development_min_complete_events']]
    chosen=max(usable,key=lambda m:performance[m]['DEVELOPMENT']['1']['20']['half_slot_cash_inclusive_opportunity_net_pct']) if usable else 'DYNAMIC'
    selector='DEVELOPMENT_ONLY_CHOICE' if usable else 'INSUFFICIENT_DEVELOPMENT_SAMPLE_FIXED_DYNAMIC_FALLBACK'
    technical=[dict(r,rank=i+1) for i,r in enumerate(daily.get(DAY,{}).get(chosen,[])[:2])]
    # Financial originals are NOT authenticated in the stored snapshots. They
    # cannot affect the rank or be retroactively claimed as selection reasons.
    company_file=Path('evidence/company/company_quality.json')
    company=json.loads(company_file.read_text()) if company_file.exists() else {};facts={r['ticker']:r for r in company.get('companies',[])}
    for r in current_diag:
        q=facts.get(r['ticker']) or {};r['company_quality_gate']=company_gate(q,DAY);r['selected_model_pass']=any(x['ticker']==r['ticker'] for x in daily[DAY][chosen]);r['company_context_only']=dict(status=q.get('status','MISSING'),latest_statement=q.get('latest_statement'),
            original_document_pit_verified=q.get('original_document_pit_verified',False),not_used_for_ranking=True)
    by_ticker={r['ticker']:r for r in current_diag}
    for r in technical:
        r.update({k:by_ticker[r['ticker']][k] for k in ('company_context_only','company_quality_gate','selected_model_pass')})
    base_watch=[dict(by_ticker[r['ticker']],chosen_plan=r['chosen_plan'],not_final_selected_model=True) for r in daily[DAY]['DYNAMIC'] if not by_ticker[r['ticker']]['selected_model_pass']][:2]
    integrated=[dict(r) for r in daily[DAY][chosen] if company_gate(facts.get(r['ticker']),DAY)=='CONFIRMED_FACTS_ONLY'][:2]
    cases=[];old_diag=json.loads((old/'all_technical_entry_diagnostics.json').read_text())['rows']
    for t in CASES:
        row=next((r for r in current_diag if r['ticker']==t),None)
        if row is None and t in cache and DAY in cache[t]:
            past,pre=cache[t][DAY];new,watch,error=plans(past,pre,t);row=dict(meta[t],date=DAY,close=past[-1]['close'],plans=new,best_plan=best_plan(new),structural_watch=watch,excluded_from_original149=True)
        cases.append(dict(ticker=t,original=next((r for r in old_diag if r['ticker']==t),None),dynamic=row))
    counts=dict(new_setups=dict(setup_counts),geometric_pass_by_method=dict(method_counts),technical_reviewed=len(current_diag),
        generated_plans=sum(len(r['plans']) for r in current_diag),geometry_pass_tickers=sum(r['best_plan'] is not None for r in current_diag),
        geometry_momentum_liquidity=sum(r['best_plan'] is not None and r['momentum_pass'] and r['liquidity_pass'] for r in current_diag),
        strict_pit_company_confirmed=sum(r['company_quality_gate']=='CONFIRMED_FACTS_ONLY' for r in current_diag),technical_research_top2=len(technical),quality_rejections=dict(quality_reasons))
    report=dict(schema='C3_DYNAMIC_ENTRY_STUDY_V2',asof=DAY,provenance=provenance,counts=counts,protocol=DEFAULT,
        protocol_sha256=digest(ROOT_PROTOCOL()),split=dict(first_signal_day=active[0] if active else None,development_signal_end=dev_end,
        development_outcome_end=sessions[hold_i-1],holdout_start=hold_start,last=DAY,purge_sessions=23,independent_unseen_validation=False),
        performance=performance,independent_strategy_setups={k:dict(v) for k,v in historical_setups.items()},independent_strategy_funnels={k:{m:dict(v) for m,v in methods.items()} for k,methods in funnels.items()},dedup_suppressed=dict(suppressed),development_chosen_model=chosen,selector_status=selector,
        technical_research_top2=technical,ablation_base_watch_candidates=base_watch,strict_integrated_top2=integrated,final_candidate_count=None,status='RESEARCH_MAINTAIN_SOURCE_AND_FINANCE_UNCERTIFIED',
        company_evidence={k:company.get(k) for k in ('asof','collected_at','requested','status_counts','original_document_pit_verified','selection_use')},
        decision='CASH',buy_approved=False,orders_enabled=False,telegram_requests=0,original_registered_signals_modified=False,
        elapsed_seconds=time.monotonic()-started,
        limitations=['REGULAR_SESSION_SCOPE_UNCERTIFIED','FINANCIAL_ORIGINAL_PIT_UNVERIFIED_NO_HISTORICAL_FINANCE_FILTER',
        'NOV11_CURRENT_UNIVERSE_CONDITIONING_SURVIVORSHIP_AND_SECTOR_PIT_BIAS','PREVIOUSLY_REUSED_HISTORY_NOT_INDEPENDENT_UNSEEN_HOLDOUT',
        'DAILY_BAR_SEQUENCE_CONSERVATIVE_NOT_BROKER_FILLS','THRESHOLDS_FIXED_BEFORE_FIRST_RUN_NOT_PROFITABILITY_VALIDATED','NO_STATISTICAL_SUPERIORITY_CLAIM'])
    write(out/'study_summary.json',report);write(out/'nov11_all_technical_plans.json',dict(asof=DAY,rows=current_diag));write(out/'case_comparison.json',cases)
    write(out/'historical_events.json',events)
    from c3_dynamic_visual_v2 import create_images
    images=create_images(report,cases,current,out/'charts')
    write(out/'chart_manifest.json',images)
    print('DYNAMIC_STUDY_SUMMARY',json.dumps(dict(counts=counts,chosen_model=chosen,selector_status=selector,technical_top2=[r['ticker'] for r in technical],elapsed=report['elapsed_seconds']),ensure_ascii=False),flush=True)


def ROOT_PROTOCOL():return Path(__file__).resolve().parent.parent/'config/c3_dynamic_entry_v2_protocol.json'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--engine',type=Path,required=True);p.add_argument('--state',type=Path,required=True);p.add_argument('--old',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();study(a.engine,a.state,a.old,a.out)
