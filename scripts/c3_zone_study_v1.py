"""Same ticker/date/funds paired Zone Entry comparison, no live side effects."""
import argparse,csv,gzip,hashlib,json,math,statistics,time
from collections import Counter,defaultdict
from pathlib import Path
from c3_dynamic_study_v2 import load_dataset,write,DAY
from c3_zone_entry_v1 import P,MODELS,PROTOCOL_PATH,zone_plan,allocation
from c3_zone_execution_v1 import simulate
from c3_selection_scope_v5 import selection_features,digest
from c3_selection_factors_v6 import causal_factors,regime
from c3_entry_practical_v7 import features,entry_plan
from c3_forward_ledger_v8 import read_record,hash_value
from c3_competition_v2 import cluster_ci

SPLITS={'A_SINGLE_UPPER':(1.,0.),'B_ORIGINAL_ZONE_50_50':(.5,.5),'C_ZONE_V1_50_50':(.5,.5),'H_HALF_UPPER_REST_CASH':(.5,0.)}


def prefixes(allbars):
    out={}
    for t,bars in allbars.items():
        groups=defaultdict(list)
        for b in bars:
            if b['tradable']:groups[b['segment']].append(b)
        out[t]={b['date']:g[:i+1] for g in groups.values() for i,b in enumerate(g) if i>=64}
    return out


def metric(group,model,v,h):
    # Primary ABC comparison uses the SAME evaluable opportunities in all arms.
    common=[e for e in group if all(e['outcomes'][m][v][h].get('conservative_plan_return_pct') is not None for m in MODELS)]
    pairs=[(e,e['outcomes'][model][v][h]) for e in common];xs=[(e,o) for e,o in pairs if 'worst' in o];n=len(pairs)
    mean=lambda seq:statistics.mean(seq) if seq else None
    first=[(e,o) for e,o in xs if o['first_filled']];second=[(e,o) for e,o in first if o['second_filled']];only=[(e,o) for e,o in first if not o['second_filled']]
    return dict(opportunities=n,excluded_common_data_or_maturity=len(group)-n,first_fills=len(first),second_fills=len(second),first_only=len(only),unfilled=n-len(first),
        first_certain_count=sum(o.get('first_fill_certain_across_simulated_paths',False) for _,o in pairs),first_possible_count=sum(o.get('first_fill_possible',False) for _,o in pairs),second_certain_count=sum(o.get('second_fill_certain_across_simulated_paths',False) for _,o in pairs),second_possible_count=sum(o.get('second_fill_possible',False) for _,o in pairs),
        first_fill_rate_pct=100*len(first)/n if n else None,second_fill_rate_pct=100*len(second)/n if n else None,first_only_rate_pct=100*len(only)/n if n else None,unfilled_rate_pct=100*(n-len(first))/n if n else None,
        expectancy_plan_capital_net_pct=mean([o['conservative_plan_return_pct'] for _,o in pairs]),optimistic_bound_mean_pct=mean([o['optimistic_plan_return_pct'] for _,o in pairs]),
        mean_filled_plan_net_pct=mean([o['conservative_plan_return_pct'] for _,o in first]),mean_first_only_plan_net_pct=mean([o['conservative_plan_return_pct'] for _,o in only]),mean_both_plan_net_pct=mean([o['conservative_plan_return_pct'] for _,o in second]),
        stop_count=sum(o['worst']['stop_occurred'] for _,o in first),stop_rate_among_filled_pct=100*sum(o['worst']['stop_occurred'] for _,o in first)/len(first) if first else None,
        r1_rate_among_filled_pct=100*sum(o['worst']['r1_reached'] for _,o in first)/len(first) if first else None,r2_rate_among_filled_pct=100*sum(o['worst']['r2_reached'] for _,o in first)/len(first) if first else None,
        plan_nav_mfe_pct=mean([o['worst']['plan_nav_mfe_pct'] for _,o in first]),plan_nav_mae_pct=mean([o['worst']['plan_nav_mae_pct'] for _,o in first]),
        mean_plan_close_mdd_pct=mean([o['worst']['max_drawdown_close_pct'] for _,o in first]),worst_plan_close_mdd_pct=min([o['worst']['max_drawdown_close_pct'] for _,o in first],default=None),
        worst_intraday_path_stress_dd_pct=min([o['worst']['intraday_path_stress_drawdown_pct'] for _,o in first],default=None),
        ambiguous_count=sum(o.get('ambiguous',False) for _,o in pairs),gap_below_stop_uncertain=sum('AUCTION_BUYS_BELOW_STOP_EXECUTION_UNCERTAIN' in o['worst']['flags'] for _,o in xs),
        second_and_stop_same_bar=sum('SAME_DAY_TWO_LIMITS_AND_STOP' in o['worst']['flags'] for _,o in xs),
        missed_unfilled_10pct_rally=sum((o.get('missed_rally_mfe_pct') or 0)>=10 for _,o in pairs),
        descriptive_month_cluster_ci=cluster_ci([(e['date'][:7],o['conservative_plan_return_pct']) for e,o in pairs]),
        market_regime={r:dict(n=len(z:=[(e,o) for e,o in pairs if e['regime']==r]),expectancy_plan_pct=mean([o['conservative_plan_return_pct'] for _,o in z])) for r in ('UP','SIDEWAYS','DOWN')},
        cash_is_in_denominator=True,capital_constrained_portfolio_simulated=False)


def paired_delta(group,left,right,v='1',h='20'):
    pairs=[(e,e['outcomes'][left][v][h],e['outcomes'][right][v][h]) for e in group if all(e['outcomes'][m][v][h].get('conservative_plan_return_pct') is not None for m in MODELS)]
    values=[a['conservative_plan_return_pct']-b['conservative_plan_return_pct'] for _,a,b in pairs];sd=statistics.stdev(values) if len(values)>1 else None
    required=math.ceil(((1.9599639845+.8416212336)*sd/P['power_planning_effect_plan_pct'])**2) if sd and sd>0 else None
    return dict(n=len(values),mean_plan_pct=statistics.mean(values) if values else None,median_plan_pct=statistics.median(values) if values else None,
        positive_differences=sum(v>0 for v in values),negative_differences=sum(v<0 for v in values),zero_differences=sum(v==0 for v in values),
        descriptive_month_cluster_ci=cluster_ci([(e['date'][:7],a['conservative_plan_return_pct']-b['conservative_plan_return_pct']) for e,a,b in pairs]),
        planning_effect_pct=P['power_planning_effect_plan_pct'],paired_sd_pct=sd,iid_power_sample_lower_bound=required,independently_unseen_complete_samples=0,
        note='Approximate 80% power / 5% alpha planning only; month/issuer correlation, reuse and multiple hypotheses require more evidence')


def case_replays(allbars,cache,market,state,out):
    doc=json.loads(Path('evidence/case_source/render_diagnostics.json').read_text());source={r['ticker']:r for r in doc['cards']};cases=[]
    lane=state/'reports/c3_forward_v8/lanes/krx_unadjusted_v12'
    for day in ('2026-11-05','2026-11-06'):
        frozen=lane/'decisions'/(day+'.json');record=read_record(frozen) if frozen.exists() else None
        for t in ('028050','030530'):
            past=cache[t][day];raw=source[t];row=next((x for x in (record or {}).get('models',{}).get('B',[]) if x['ticker']==t),None)
            p=((row or {}).get('entry_plans',{}).get('A_SUPPORT_LIMIT') or {}).get('plan') if row else raw['original_support_plan'] if day=='2026-11-05' else None
            source_status='FROZEN_REGISTERED_DECISION' if row else 'ARCHIVED_UNREGISTERED_PREVIEW' if p else 'NO_ORIGINAL_PLAN_FOR_THIS_DAY'
            new,reasons=zone_plan(past,t);by={x['date']:i for i,x in enumerate(allbars[t])};i=by[day];observed=[]
            for b in allbars[t]:
                if day<b['date']<=DAY:observed.append({k:b[k] for k in ('date','open','high','low','close','volume')})
            comparisons={}
            for m,split in SPLITS.items():
                use=new if m.startswith('C_') and new and new['geometry_pass'] else None if m.startswith('C_') else p
                comparisons[m]=simulate(use,allbars[t],i,market['sessions'],split=split,cutoff=DAY,allow_partial=True)
            hold={m:simulate(p,allbars[t],i,market['sessions'],split=SPLITS[m],cutoff=DAY,allow_partial=True,exit_policy='CASE_CLOSE_STOP_NO_R1_EXIT') for m in ('A_SINGLE_UPPER','B_ORIGINAL_ZONE_50_50','H_HALF_UPPER_REST_CASH')}
            reported=dict(source='USER_REPORTED_NOT_BROKER_RECEIPT',reported_orders=[dict(limit=63500,budget_krw=2500000),dict(limit=60700,budget_krw=2500000)] if t=='028050' else [dict(limit=23500,budget_krw=2500000)],
                reported_fill_state='BOTH_REPORTED_FILLED' if t=='028050' else 'UPPER_REPORTED_FILLED; LOWER_NOT_REPORTED',actual_quantities=None,exact_execution_timestamps=None,broker_execution_verified=False)
            if day=='2026-11-05' and p:
                expected=(60700,63500,57700) if t=='028050' else (22100,23500,20600)
                if (p['low'],p['high'],p['stop'])!=expected:raise ValueError('ARCHIVED_USER_CASE_PLAN_CHANGED')
                if past[-1]['close']!=raw['close']:raise ValueError('ARCHIVED_CASE_CLOSE_CHANGED')
            c=dict(ticker=t,name=past[-1]['name'],asof=day,original_plan=p,new_zone_plan=new,new_zone_reasons=reasons,source_status=source_status,
                original_decision_payload_sha256=hash_value(record) if record else None,source_run_id=(row or {}).get('source_run_id') or raw.get('source_run_id'),
                original_source_received_at=(row or {}).get('source_received_at') or raw['source_labels']['source_received_at'],original_registered_at=(row or {}).get('registered_at'),
                original_selection_reasons=(row or {}).get('selection_reasons'),user_report=reported,comparisons=comparisons,hold_no_r1_case_diagnostic=hold,observed_after_signal=observed,
                limited_forward_sessions=len(observed),not_twenty_day_performance=True,preopen_availability_authenticated=False,chart_bars=past[-119:])
            cases.append(c)
    write(out/'case_replays.json',cases);return cases


def run(engine,state,old,out):
    start=time.monotonic();allbars,current,eligible,meta,market,control,provenance=load_dataset(engine,state,old)
    cache=prefixes({t:allbars[t] for t in eligible});sessions=market['sessions'];indices=market['indices'];grid={d:i for i,d in enumerate(sessions)}
    source_days=sorted({b['date'] for bs in allbars.values() for b in bs});hold_start=source_days[-P['holdout_last_sessions']];hold_i=grid[hold_start];dev_end=sessions[hold_i-P['purge_sessions']-1]
    days=sorted({d for t in cache for d in cache[t] if d<=dev_end or d>=hold_start});events=[];last={};daily_diag=[];suppressed=0;daily_original={}
    for di,day in enumerate(days):
        pool=[];reg={m:regime([v for d,v in sorted(indices[m].items()) if d<=day]) for m in ('KOSPI','KOSDAQ')}
        for t in sorted(eligible):
            past=cache[t].get(day)
            if past is None:continue
            market_name=meta[t]['market'];idx=indices[market_name];mr=100*(idx[day]/idx[past[-21]['date']]-1);f=selection_features(past,mr)
            if f is None:continue
            cf=causal_factors(past,idx);r=dict(meta[t],date=day,close=past[-1]['close'],own_rs20=cf['own_rs20'],rs_accel5=cf['rs_accel5'],turnover20=f['turnover20'],regime=reg[market_name],market_return20=mr)
            r['momentum_pass']=r['own_rs20']>0 and r['rs_accel5']>0;r['liquidity_pass']=r['turnover20']>=P['min_turnover20_krw'];pool.append(r)
        pool.sort(key=lambda r:(-r['turnover20'],-r['own_rs20'],r['ticker']));bpool=[r for r in pool if r['momentum_pass']];selected=bpool[:2];daily_original[day]=[r['ticker'] for r in selected]
        if day==DAY:
            if (len(pool),len(bpool),daily_original[day])!=(149,50,['028050','180640']):raise ValueError('ZONE_BASELINE_SELECTOR_NOT_REPRODUCED')
            for r in pool:
                new,why=zone_plan(cache[r['ticker']][day],r['ticker']);daily_diag.append(dict(r,zone=new,zone_reasons=why,financial_quality='UNKNOWN_ORIGINAL_PIT',buy_approved=False))
        for r in selected:
            t=r['ticker'];g=grid[day]
            if g-last.get(t,-10000)<=P['same_ticker_lockout_sessions']:suppressed+=1;continue
            last[t]=g;past=cache[t][day];f,why=features(past[-90:],r['market_return20']);original,reason=entry_plan(t,past[-90:],f,'A_SUPPORT_LIMIT',r['regime']) if f else (None,why)
            new,newwhy=zone_plan(past,t);approved_new=new if new and new['geometry_pass'] and r['liquidity_pass'] else None
            plans={m:(approved_new if m.startswith('C_') else original) for m in MODELS};e=dict(r,fold='DEVELOPMENT' if day<=dev_end else 'REUSED_CHRONOLOGICAL_HOLDOUT',original_plan=original,new_zone=new,new_zone_rejections=newwhy,
                plans=plans,all_three_valid=original is not None and approved_new is not None,outcomes={})
            bi=next(i for i,b in enumerate(allbars[t]) if b['date']==day);cutoff=sessions[hold_i-1] if e['fold']=='DEVELOPMENT' else DAY
            for m in MODELS:
                e['outcomes'][m]={str(v):{str(h):simulate(plans[m],allbars[t],bi,sessions,SPLITS[m],v,h,cutoff=cutoff) for h in (5,10,20)} for v in (1,2,3)}
            events.append(e)
        if di%40==0:print('ZONE_SCREEN_PROGRESS',day,len(pool),len(events),flush=True)
    folds=('DEVELOPMENT','REUSED_CHRONOLOGICAL_HOLDOUT');performance={}
    company=json.loads(Path('evidence/company/company_quality.json').read_text());company_rows={r['ticker']:r for r in company['companies']}
    for r in daily_diag:
        c=company_rows.get(r['ticker'],{});r['later_financial_context_not_used_for_ranking']=dict(status=c.get('status','MISSING'),latest_statement=c.get('latest_statement'),original_pit_verified=False)
    for fold in folds:
        group=[e for e in events if e['fold']==fold];performance[fold]={m:{str(v):{str(h):metric(group,m,str(v),str(h)) for h in (5,10,20)} for v in (1,2,3)} for m in MODELS}
    comparisons={fold:{name:paired_delta([e for e in events if e['fold']==fold],a,b) for name,a,b in [('B_MINUS_A',MODELS[1],MODELS[0]),('C_MINUS_B',MODELS[2],MODELS[1]),('B_MINUS_HALF_UPPER',MODELS[1],MODELS[3])]} for fold in folds}
    common_plan_metrics={fold:{m:metric([e for e in events if e['fold']==fold and e['all_three_valid']],m,'1','20') for m in MODELS[:3]} for fold in folds}
    zone_rows=[r for r in daily_diag if r['zone']];price_ok=[r for r in zone_rows if r['zone']['geometry_pass']];quality=[r for r in price_ok if r['momentum_pass'] and r['liquidity_pass']]
    cases=case_replays(allbars,cache,market,state,out)
    width={}
    for label,key,edges in [('WIDTH','width_pct',P['descriptive_bins']['width_pct']),('DISTANCE','upper_gap_pct',P['descriptive_bins']['upper_gap_pct'])]:
        bins=defaultdict(list)
        for e in events:
            p=e['original_plan']
            if not p:continue
            value=100*((p['high']-p['low']) if key=='width_pct' else (e['close']-p['high']))/e['close']
            bucket=next((f'LE_{x}' for x in edges if value<=x),'ABOVE_'+str(edges[-1]));bins[bucket].append(e)
        width[label]={b:{m:metric(xs,m,'1','20') for m in (MODELS[0],MODELS[1],MODELS[3])} for b,xs in bins.items()}
    failures=[]
    for e in events:
        o=e['outcomes'][MODELS[1]]['1']['20']
        if o.get('worst') and o['worst']['stop_occurred'] and e['ticker'] not in ('028050','030530'):failures.append(dict(ticker=e['ticker'],name=e['name'],date=e['date'],fold=e['fold'],original_plan=e['original_plan'],execution=o))
    failures.sort(key=lambda x:x['execution']['conservative_plan_return_pct'])
    summary=dict(schema='C3_ZONE_ENTRY_V1_STUDY',asof=DAY,protocol=P,protocol_sha256=digest(PROTOCOL_PATH),provenance=provenance,
        split=dict(first_signal=days[0],development_signal_end=dev_end,development_outcome_end=sessions[hold_i-1],holdout_start=hold_start,last=DAY,purge_sessions=P['purge_sessions'],independently_unseen=False),
        counts=dict(full_market=2769,analysis_eligible=1988,technical_candidates=len(daily_diag),original_b=50,zone_generated=len(zone_rows),ordered_and_distinct_limits=len(zone_rows),
            accessible=sum(r['zone']['entry_distance_pct']<=P['max_entry_distance_pct'] and r['zone']['entry_distance_atr']<=P['max_entry_distance_atr'] for r in zone_rows),
            total_risk_pass=sum(r['zone']['allocation']['full_plan_risk_pct']<=P['max_total_plan_risk_pct'] for r in zone_rows),
            integrated_rr_pass=sum((r['zone']['allocation']['full_fill_net_r1_rr'] or -999)>=P['min_full_fill_net_r1_rr'] for r in zone_rows),all_price_geometry_pass=len(price_ok),momentum_liquidity_and_zone_pass=len(quality),
            chronological_events=len(events),duplicate_signals_suppressed=suppressed),
        company_evidence_context_only={k:company.get(k) for k in ('asof','collected_at','requested','status_counts','original_document_pit_verified','selection_use')},
        technical_research_top2=quality[:2],financial_pit_confirmed_top2=[],final_candidate_count=None,decision='CASH',status='SELECTION_HELD_SOURCE_AND_FINANCE_UNCERTIFIED',
        performance=performance,paired_comparisons=comparisons,all_three_valid_plan_subset=common_plan_metrics,width_distance_diagnostics=width,
        original_b_selected_by_day=daily_original,failures=failures[:8],verdict='RESEARCH_MAINTAIN_NOT_PROMOTED',orders_enabled=False,telegram_requests=0,ledger_writes=0,
        limitations=['PRESERVED_HISTORY_REUSED_NOT_INDEPENDENT_UNSEEN','CURRENT_NOV11_UNIVERSE_AND_SECTOR_SURVIVORSHIP_BIAS','FINANCIAL_ORIGINAL_PIT_AND_BUSINESS_QUALITY_UNKNOWN',
        'REGULAR_ONLY_OHLCV_AND_TURNOVER_UNCERTIFIED','OHLC_BOUNDS_NOT_BROKER_FILLS_OR_QUEUE_PROOF','DAILY_EXTREMA_SEQUENCE_ASSUMPTIONS_AND_GAP_LOW_STRESS_NOT_GUARANTEED_TRUE_BOUNDS',
        'PER_PLAN_EXPECTANCY_AND_DRAWDOWN_NOT_CAPITAL_CONSTRAINED_PORTFOLIO','PRIMARY_COMMON_INTRADAY_STOP_R1_EXIT_IS_NOT_FROZEN_C3_CLOSE_STOP_EXECUTION','FULL_ZONE_RR_CONDITIONAL_ON_BOTH_LIMITS_FILLING'],
        elapsed_seconds=time.monotonic()-start)
    write(out/'zone_summary.json',summary);write(out/'nov11_zone_diagnostics.json',dict(rows=daily_diag));write(out/'failure_examples.json',failures[:8])
    with gzip.open(out/'paired_events.json.gz','wt') as f:json.dump(events,f,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
    from c3_zone_visual_v1 import create_images
    images=create_images(summary,cases,current,out/'charts');write(out/'chart_manifest.json',images)
    rows=[]
    for fold,models in performance.items():
        for model,vs in models.items():
            for v,hs in vs.items():
                for h,metrics in hs.items():rows.append(dict(fold=fold,model=model,validity=v,horizon=h,**{k:v for k,v in metrics.items() if not isinstance(v,(dict,list))}))
    with (out/'paired_metrics.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print('ZONE_STUDY_SUMMARY',json.dumps(dict(counts=summary['counts'],paired=comparisons,elapsed=summary['elapsed_seconds']),ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--engine',type=Path,required=True);p.add_argument('--state',type=Path,required=True);p.add_argument('--old',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);run(a.engine,a.state,a.old,a.out)
