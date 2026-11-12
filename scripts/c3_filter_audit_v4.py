"""Exclusion accounting and three frozen price-only rejection cohorts."""
import statistics
from collections import Counter
from itertools import combinations
from c3_entry_structure_v4 import reasons,review_v4
from c3_single_entry_range_v1 import generate_ranges,single_scenario,PROTOCOL
from first_pullback_v55 import up
from c3_dynamic_entry_v2 import evaluate_trade
from c3_selection_scope_v5 import selection_features
from c3_selection_factors_v6 import causal_factors


def exclusion_audit(rows):
    result={}
    for version in ('v3','v4'):
        counts=Counter();combos=Counter();pairs=Counter();single=Counter()
        for r in rows:
            why=reasons(r,version);counts.update(why);combos[' + '.join(why) or 'ALL_PASS']+=1
            pairs.update(' + '.join(p) for p in combinations(why,2))
            if len(why)==1:single[why[0]]+=1
        result[version]=dict(total=len(rows),inclusive_failure_counts=dict(counts),exclusive_reason_combinations=dict(combos),
            pairwise_overlap=dict(pairs),single_failure_only=dict(single),multiple_failures=sum(v for k,v in combos.items() if ' + ' in k),
            all_pass=combos['ALL_PASS'],inclusive_counts_not_additive=True)
    steps=[('company',lambda r:r.get('financial',{}).get('observed_positive',False)),('relative_strength',lambda r:r['momentum_pass']),
        ('turnover',lambda r:r['liquidity_pass']),('structural_stop',lambda r:any(p['stop_reliability']['research_eligible'] for p in r['range_review']['plans'])),
        ('risk_and_practical_range',lambda r:r['range_review']['best'] is not None)]
    pool=list(rows);sequence=[]
    for name,predicate in steps:
        after=[r for r in pool if predicate(r)];sequence.append(dict(stage=name,before=len(pool),passed=len(after),failed=len(pool)-len(after)));pool=after
    result['v4_sequential_funnel']=sequence
    result['cash_interpretation']=dict(price_structure_review_completed=True,eligible_research_candidates=len(pool),
        official_regular_session_certified=False,financial_original_pit_certified=False,
        absence_of_marketwide_profitable_stocks_proven=False,over_exclusion_ruled_out=False,
        research_no_candidate_distinct_from_live_authentication_hold=True)
    clipping=[]
    for row in rows:
        for p in row['range_review']['v3_review']['plans']:
            if not p['range_valid']:continue
            r=p['range'];floor=up(max(p['structural_low'],p['reference_close']-p['atr14']*PROTOCOL['max_distance_atr'],p['reference_close']*(1-PROTOCOL['max_distance_pct']/100)))
            if r['low']>p['structural_low'] and r['low']==floor and r['width_atr']<PROTOCOL['support_band_atr'] and (r['high']-p['structural_low'])/p['atr14']>=PROTOCOL['support_band_atr']:
                clipping.append(dict(ticker=row['ticker'],name=row['name'],method=p['method'],structural_low=p['structural_low'],
                    clipped_low=r['low'],high=r['high'],width_atr=r['width_atr'],original_width_atr=(r['high']-p['structural_low'])/p['atr14']))
    result['component_diagnostics']=dict(rs20_nonpositive=sum(r['own_rs20']<=0 for r in rows),
        rs_accel5_nonpositive=sum(r['rs_accel5']<=0 for r in rows),
        rs_both_nonpositive=sum(r['own_rs20']<=0 and r['rs_accel5']<=0 for r in rows),
        original_pit_confirmed=sum(r['financial'].get('confirmed',False) for r in rows),
        distance_caused_narrow_fragments=len({r['ticker'] for r in clipping}),distance_fragment_examples=clipping,
        current_growth_observation_is_ranking_context_not_historical_proof=True)
    return result


def rejection_cohorts(allbars,eligible,meta,market,out_asof):
    """Three source-session offsets frozen before any outcome is examined.

    Current financial API snapshots/global news are NEVER used in these past
    cohorts. Current-universe conditioning and prior sample reuse remain.
    """
    sessions=market['sessions'];idx=market['indices'];source_days=sorted({b['date'] for bs in allbars.values() for b in bs if b['date']<=out_asof})
    days=[source_days[-n] for n in (67,45,23)];events=[]
    for day in days:
        for t in sorted(eligible):
            bs=allbars[t];prefix=[b for b in bs if b['date']<=day]
            if not prefix or prefix[-1]['date']!=day:continue
            segment=prefix[-1]['segment'];past=[]
            for b in reversed(prefix):
                if b['segment']!=segment or not b['tradable']:break
                past.append(b)
            past.reverse()
            if len(past)<80:continue
            ix=idx[meta[t]['market']]
            if day not in ix or past[-21]['date'] not in ix:continue
            f=selection_features(past,100*(ix[day]/ix[past[-21]['date']]-1))
            if f is None:continue
            cf=causal_factors(past,ix);legacy=generate_ranges(past);review=review_v4(past,legacy)
            row=dict(ticker=t,date=day,name=meta[t]['name'],momentum_pass=cf['own_rs20']>0 and cf['rs_accel5']>0,
                liquidity_pass=f['turnover20']>=1e9,financial=dict(status='HISTORICAL_PIT_UNAVAILABLE',observed_positive=False),
                range_review=review)
            old=review['v3_review']['best'];new=review['best'];bi=len(prefix)-1;start=sessions.index(day)
            returns={}
            for h in (5,10,20):
                if start+h>=len(sessions) or sessions[start+h]>out_asof:returns[str(h)]=None;continue
                path={b['date']:b for b in bs};wanted=sessions[start:start+h+1]
                if any(d not in path or not path[d]['tradable'] or path[d]['action_boundary'] or path[d]['segment']!=segment for d in wanted):returns[str(h)]=None;continue
                returns[str(h)]=100*(path[wanted[-1]]['close']/past[-1]['close']-1)
            outcomes={};paired={}
            byday={b['date']:b for b in bs}
            for h in (5,10,20):
                end=start+3+h
                wanted=sessions[start:end+1]
                paired[str(h)]=bool(end<len(sessions) and sessions[end]<=out_asof and all(d in byday and byday[d]['tradable'] and not byday[d]['action_boundary'] and byday[d]['segment']==segment for d in wanted))
            for tag,plan in [('v3',old),('v4',new)]:
                outcomes[tag]={choice:{str(v):{str(h):evaluate_trade(single_scenario(plan,choice),bs,bi,sessions,v,h,out_asof)
                    for h in (5,10,20)} for v in (1,2,3)} for choice in ('upper','middle','lower')} if plan else {}
            events.append(dict(ticker=t,name=meta[t]['name'],date=day,rs20=cf['own_rs20'],rs_accel5=cf['rs_accel5'],
                turnover20=f['turnover20'],v3_price_pass=old is not None,v4_price_pass=new is not None,
                v3_method=old['method'] if old else None,v4_method=new['method'] if new else None,
                v4_plan_summary={k:new[k] for k in ('method','support_known_on','invalidation_low','stop','r1','r2','range')} if new else None,
                rs_pass=row['momentum_pass'],turnover_pass=row['liquidity_pass'],selection_close_returns=returns,
                outcomes=outcomes,paired_maturity=paired,v3_rejection_reasons=reasons(row,'v3'),v4_rejection_reasons=reasons(row,'v4'),
                history_financial_quality='UNAVAILABLE_NOT_BACKFILLED'))
    groups={}
    for name,predicate in [('V3_PRICE_REJECTED',lambda e:not e['v3_price_pass']),('V4_NEWLY_ADMITTED',lambda e:e['v4_price_pass'] and not e['v3_price_pass']),
        ('RS_ACCEL_REJECTED_WITH_V4_RANGE',lambda e:e['v4_price_pass'] and not e['rs_pass']),('V4_PRICE_REJECTED',lambda e:not e['v4_price_pass'])]:
        subset=[e for e in events if predicate(e)];groups[name]={}
        for h in (5,10,20):
            rs=[e['selection_close_returns'][str(h)] for e in subset if e['selection_close_returns'][str(h)] is not None]
            groups[name][str(h)]=dict(signals=len(subset),mature=len(rs),rose_after_selection=sum(v>0 for v in rs),
                mean_selection_close_return_pct=statistics.mean(rs) if rs else None,executable_profit_claimed=False)
    trade={}
    for tag in ('v3','v4'):
        trade[tag]={}
        for choice in ('upper','middle','lower'):
            trade[tag][choice]={}
            for h in (5,10,20):
                rs=[e['outcomes'][tag][choice]['1'][str(h)] for e in events if e['outcomes'][tag]];mature=[r for r in rs if r.get('return_pct') is not None];fills=[r for r in mature if r.get('filled')]
                trade[tag][choice][str(h)]=dict(range_opportunities=len(rs),mature=len(mature),fills=len(fills),
                    cash_inclusive_net_expectancy_pct=statistics.mean(r['return_pct'] for r in mature) if mature else None,
                    stops=sum(r['status'].startswith('STOP') for r in fills),r1_touched=sum(r.get('r1_hit_before_stop',False) for r in fills),
                    range_unreached=sum(r['status']=='PASS_UNFILLED' for r in mature),
                    mean_mae_pct=statistics.mean(r['mae_pct'] for r in fills) if fills else None,actual_fill_confirmed=False)
    paired_trade={}
    for cohort,predicate in [('ALL_TECHNICAL',lambda e:True),('RS_POSITIVE_IMPROVING_AND_LIQUID',lambda e:e['rs_pass'] and e['turnover_pass'])]:
        paired_trade[cohort]={}
        for tag in ('v3','v4'):
            paired_trade[cohort][tag]={}
            for choice in ('upper','middle','lower'):
                paired_trade[cohort][tag][choice]={}
                for h in (5,10,20):
                    selected=[e for e in events if predicate(e) and e['paired_maturity'][str(h)]]
                    rs=[e['outcomes'][tag][choice]['1'][str(h)] if e['outcomes'][tag] else dict(status='NO_RANGE_CASH',return_pct=0,filled=False) for e in selected]
                    if any(r.get('return_pct') is None for r in rs):raise ValueError('PAIRED_COMMON_CLOCK_HAS_CENSORED_MODEL_OUTCOME')
                    fills=[r for r in rs if r.get('filled')]
                    paired_trade[cohort][tag][choice][str(h)]=dict(common_opportunities=len(rs),fills=len(fills),
                        no_range_cash=sum(r['status']=='NO_RANGE_CASH' for r in rs),unfilled=sum(r['status']=='PASS_UNFILLED' for r in rs),
                        net_expectancy_per_selected_opportunity_pct=statistics.mean(r['return_pct'] for r in rs) if rs else None,
                        stops=sum(r['status'].startswith('STOP') for r in fills),paired_population_includes_no_range_cash=True,
                        actual_fills_confirmed=False)
    examples=sorted([e for e in events if not e['v3_price_pass'] and e['selection_close_returns']['10'] is not None and e['selection_close_returns']['10']>0],
        key=lambda e:(e['date'],e['ticker']))[:5]
    return dict(session_offsets=[67,45,23],cohort_dates=days,price_only_technical_events=len(events),groups=groups,trade=trade,
        paired_cash_inclusive_trade=paired_trade,unpaired_range_only_means_are_not_model_superiority_evidence=True,
        illustrative_missed_rises=[{k:e[k] for k in ('ticker','name','date','selection_close_returns','v3_rejection_reasons','v4_price_pass')} for e in examples],
        reused_and_current_universe_conditioned_not_independent_validation=True,parameters_optimized=False,financial_or_future_global_inputs_used=False,
        superiority_proven=False),events
