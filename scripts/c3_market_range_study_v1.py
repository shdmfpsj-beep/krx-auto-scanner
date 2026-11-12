"""Read-only archived market review + dated current global context.

Stock WATCH selection is frozen before range calculation. Financial API
snapshots fetched later are current review context, never causal past input.
No production registration, schedule change, original mutation, or live send.
"""
import argparse,csv,hashlib,io,json,os,statistics,subprocess,time,zipfile
from collections import Counter
from datetime import datetime,timezone,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from c3_dynamic_study_v2 import load_dataset,write
from c3_dynamic_entry_v2 import evaluate_trade
from c3_selection_scope_v5 import selection_features
from c3_selection_factors_v6 import causal_factors
from c3_single_entry_range_v1 import generate_ranges,single_scenario,PROTOCOL
from c3_market_context_v1 import load_prior_macro,fetch_indices,domestic_context,combine
from c3_range_forward_v1 import hash_value,register,observe,append_outcome
from c3_range_card_v1 import render,hold_card
from c3_range_delivery_v1 import envelope,transport_test,safe_claim
from c3_range_structure_v3 import reassess,audit_no_anchor_change
from c3_entry_structure_v4 import review_v4
from c3_filter_audit_v4 import exclusion_audit,rejection_cohorts

DAY='2026-11-11'
MACRO_ARTIFACT=13914336548
MACRO_ZIP_SHA='40200b039eaeab03a4a30f3b86e83ff310d20813e03e05490aaf2a4f1884b14c'

def restore_pr106_baseline(out):
    raw=subprocess.check_output(['gh','api','repos/shdmfpsj-beep/krx-auto-scanner/actions/artifacts/13930503168/zip'],timeout=60)
    if hashlib.sha256(raw).hexdigest()!='4347b7fc1483b63953a8a07f314f13e8ba5231ab0ac2e825c5ae1a398712e522':raise ValueError('PR106_BASELINE_ARCHIVE_HASH_MISMATCH')
    result={}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in ('report.json','all149_range_diagnostics.json','historical_single_entry_summary.json'):
            info=z.getinfo('evidence/market-range/'+name)
            if info.file_size>12*1024*1024:raise ValueError('PR106_BASELINE_FILE_OVERSIZED')
            body=z.read(info);target=out/'baseline_pr106'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
            result[name]=json.loads(body)
    return result

def restore_v3_baseline(out):
    raw=subprocess.check_output(['gh','api','repos/shdmfpsj-beep/krx-auto-scanner/actions/artifacts/13937200195/zip'],timeout=60)
    if hashlib.sha256(raw).hexdigest()!='747b868adfec90e096ff0d0a3337a21a988349d0d8db04fb21fbf0c54e63e160':raise ValueError('V3_BASELINE_ARCHIVE_HASH_MISMATCH')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        name='evidence/market-range/all149_range_diagnostics.json';info=z.getinfo(name)
        if info.file_size>20*1024*1024:raise ValueError('V3_BASELINE_OVERSIZED')
        body=z.read(info)
    write(out/'baseline_v3_all149.json',json.loads(body))
    return {r['ticker']:r for r in json.loads(body)['rows']}


def restore_macro(path):
    raw=subprocess.check_output(['gh','api','repos/shdmfpsj-beep/krx-auto-scanner/actions/artifacts/'+str(MACRO_ARTIFACT)+'/zip'],timeout=60)
    if hashlib.sha256(raw).hexdigest()!=MACRO_ZIP_SHA:raise ValueError('MACRO_SOURCE_ARCHIVE_HASH_MISMATCH')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        item=z.getinfo('v618_global_macro_status.json')
        if item.file_size>100000:raise ValueError('MACRO_SOURCE_OVERSIZED')
        body=z.read(item)
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
    return json.loads(body)

def latest_probe(out,clock):
    """Exactly one official KRX request per board; never uses false tomorrow."""
    from c3_eod_source_v9 import collect_day
    from c3_morning_source_v1 import cache_rows,compare
    from c3_telegram_inputs import GitHub
    import exchange_calendars as xc
    today=clock.astimezone(ZoneInfo('Asia/Seoul')).date();cal=xc.get_calendar('XKRX')
    session=cal.date_to_session(today,direction='previous')
    if cal.session_close(session).to_pydatetime()>clock:session=cal.previous_session(session)
    day=session.strftime('%Y-%m-%d');root=out/'latest-probe';m=collect_day(day,root,os.environ.get('KRX_AUTH_KEY'),now=clock)
    result=dict(requested_completed_day=day,official=m,attempts_per_board=1,used_for_new_selection=False,regular_only_certified=False)
    if m['official_dataset_usable']:
        try:
            gh=GitHub(os.environ['GH_TOKEN'],'FinanceData/fdr_krx_data_cache');ref=gh.head('master')
            raw=gh.file('data/listing/krx/'+day+'.csv',ref);cached,excluded=cache_rows(raw,day)
            official=[]
            for board in ('KOSPI','KOSDAQ'):
                with (root/(board+'_official.csv')).open() as f:official.extend(dict(r,asof=r.get('asof',r.get('date'))) for r in csv.DictReader(f))
            result.update(cache_ref=ref,cache_sha256=hashlib.sha256(raw).hexdigest(),comparison=compare(official,cached,day),excluded=excluded)
        except Exception as e:result['cache_comparison_error']=dict(type=type(e).__name__,message=str(e)[:180])
    result['selection_policy']='NEW_DATE_REQUIRES_NEW_REGISTERED_SAME_RUN_ORIGINAL_AND_HISTORY;NO_RETROACTIVE_SUBSTITUTION'
    write(out/'latest_source_probe.json',result);return result

def financial_review(row,cutoff):
    s=(row or {}).get('latest_statement') or {}
    if not s or s.get('published_on','9999')>cutoff:return dict(status='UNAVAILABLE_OR_FUTURE_REPORT',observed_positive=False,confirmed=False)
    fields=('revenue_krw','operating_profit_krw','operating_cashflow_ytd_krw','equity_krw')
    positive=all(isinstance(s.get(k),(int,float)) and s[k]>0 for k in fields)
    balanced=isinstance(s.get('balance_identity_gap_fraction'),(int,float)) and abs(s['balance_identity_gap_fraction'])<=.01
    liability=s.get('liabilities_krw');assets=s.get('assets_krw')
    stable_balance=bool(assets and liability is not None and 0<=liability<assets and balanced)
    observed=positive and stable_balance
    growth=s.get('revenue_increased') is True and s.get('operating_profit_increased') is True
    confirmed=observed and row.get('financial_pit_verified') is True and row.get('original_document_pit_verified') is True
    return dict(status='CONFIRMED_ORIGINAL_PIT' if confirmed else 'LATER_API_CONTEXT_NOT_ORIGINAL_PIT',observed_positive=observed,
        growth_observed=growth,confirmed=confirmed,statement=s,business_competitiveness_verified=False,
        operational_ranking_approved=False,not_available_as_original_nov11_selection_reason=True)

def choose_watch(rows,financial,sector):
    # Logical gates and deterministic lexicographic ordering, no invented
    # weighted score. This is a NOV12 review of NOV11 prices, not a past signal.
    pool=[]
    for row in rows:
        q=financial.get(row['ticker'],{})
        if not q.get('observed_positive') or not row['momentum_pass'] or not row['liquidity_pass']:continue
        s=sector.get(row['sector'],{});leader=s.get('median_own_board_rs20_pct',float('-inf'))>0
        pool.append(dict(row,financial=q,sector_proxy_positive=leader))
    pool.sort(key=lambda r:(not r['financial']['confirmed'],not r['financial']['growth_observed'],not r['sector_proxy_positive'],-r['turnover20'],-r['own_rs20'],r['ticker']))
    return pool

def choose_practical_top2(stock_pool,all_candidates,limit=2):
    """Reselect across the full screened pool; never lock the final TOP2 before entry checks.

    The pre-entry WATCH ranks are retained for diagnostics, while the final
    research cards include only candidates with a structurally validated
    observation range. Preserve the existing qualitative order among
    entry-qualified names; do not tune thresholds to a desired ticker.
    """
    selected=[]
    for stock in stock_pool:
        row=dict(all_candidates[stock['ticker']])
        plan=row['range_review']['best']
        if not plan:continue
        row.update(display_plan=plan,status='ENTRY RANGE',data_status='UNVERIFIED',
            buy_approved=False,selection_scope='FULL_STOCK_POOL_ENTRY_FIT_RESELECTION',
            reason_text='매출·영업이익·현금흐름 양수 API 관찰 · RS '+f"{row['own_rs20']:.1f}%p"+
            ' / 최근 개선 '+f"{row['rs_accel5']:.1f}%p"+' · 재무 원문 PIT 미확인')
        selected.append(row)
        if len(selected)>=limit:break
    return selected

def history_comparison(allbars,eligible,meta,market,out):
    """Limited price-only rerun; already reused history is NOT a holdout."""
    sessions=market['sessions'];idx=market['indices'];source_days=sorted({b['date'] for bs in allbars.values() for b in bs})[-85:]
    cursors={t:0 for t in eligible};last={};events=[];days=0
    for day in source_days:
        pool=[]
        for t in eligible:
            bs=allbars[t];i=cursors[t]
            while i<len(bs) and bs[i]['date']<=day:i+=1
            cursors[t]=i
            if not i or bs[i-1]['date']!=day:continue
            segment=bs[i-1]['segment'];past=[]
            for b in reversed(bs[:i]):
                if b['segment']!=segment or not b['tradable']:break
                past.append(b)
            past.reverse()
            if len(past)<80:continue
            ix=idx[meta[t]['market']]
            if day not in ix or past[-21]['date'] not in ix:continue
            mr=100*(ix[day]/ix[past[-21]['date']]-1);f=selection_features(past,mr)
            if not f:continue
            cf=causal_factors(past,ix)
            if cf['own_rs20']<=0 or cf['rs_accel5']<=0 or f['turnover20']<PROTOCOL['min_turnover20_krw']:continue
            pool.append(dict(ticker=t,turnover20=f['turnover20'],rs=cf['own_rs20'],past=past,bi=i-1))
        pool.sort(key=lambda r:(-r['turnover20'],-r['rs'],r['ticker']));days+=1
        picked=[]
        for r in pool:
            if sessions.index(day)-last.get(r['ticker'],-10000)<=20:continue
            picked.append(r)
            if len(picked)==2:break
        for r in picked:
            t=r['ticker'];last[t]=sessions.index(day);p=generate_ranges(r['past'])['best']
            scenarios={choice:{str(v):{str(h):evaluate_trade(single_scenario(p,choice),allbars[t],r['bi'],sessions,v,h,DAY)
                if p else dict(status='NO_RANGE_CASH' if sessions.index(day)+3+h<len(sessions) and sessions[sessions.index(day)+3+h]<=DAY else 'PENDING_FUTURE_SESSIONS',
                    return_pct=0. if sessions.index(day)+3+h<len(sessions) and sessions[sessions.index(day)+3+h]<=DAY else None,filled=False)
                for h in (5,10,20)} for v in (1,2,3)} for choice in ('upper','middle','lower')}
            record=dict(source_date=day,ticker=t,model_version=PROTOCOL['model_version'],plan=p,
                price_prefix_hash=hash_value(r['past']),scope='PRICE_ONLY_REUSED_HISTORY_REPLAY_NOT_FORWARD')
            selection=observe(record,allbars[t],idx[meta[t]['market']],sessions,DAY)
            events.append(dict(ticker=t,name=meta[t]['name'],date=day,plan=p,scenarios=scenarios,selection_outcomes=selection))
    result={}
    for choice in ('upper','middle','lower'):
        result[choice]={}
        for validity in (1,2,3):
            result[choice][str(validity)]={}
            for horizon in (5,10,20):
                rows=[e['scenarios'][choice][str(validity)][str(horizon)] for e in events]
                complete=[r for r in rows if r.get('return_pct') is not None];filled=[r for r in complete if r.get('filled')]
                avg=lambda a:statistics.mean(a) if a else None
                result[choice][str(validity)][str(horizon)]=dict(range_opportunities=len(rows),mature=len(complete),filled=len(filled),
                    reach_rate_pct=100*len(filled)/len(complete) if complete else None,
                    cash_inclusive_net_expectancy_pct=avg([r['return_pct'] for r in complete]),
                    stop_rate_pct=100*sum(r['status'].startswith('STOP') for r in filled)/len(filled) if filled else None,
                    mfe_pct=avg([r['mfe_pct'] for r in filled]),mae_pct=avg([r['mae_pct'] for r in filled]),
                    r1_rate_pct=100*sum(r.get('r1_hit_before_stop',False) for r in filled)/len(filled) if filled else None,
                    r2_rate_pct=100*sum(r.get('r2_path_hit',False) for r in filled)/len(filled) if filled else None,
                    missed_rally_ge10pct=sum(r.get('missed_rally_mfe_pct',0)>=10 for r in complete if not r.get('filled')),
                    daily_fills_confirmed=False)
    selection_metrics={}
    for horizon in (5,10,20):
        matured=[e['selection_outcomes']['horizons'][str(horizon)] for e in events if e['selection_outcomes']['horizons'][str(horizon)].get('selection_return_pct') is not None]
        selection_metrics[str(horizon)]=dict(mature=len(matured),positive_rate_pct=100*sum(r['selection_return_pct']>0 for r in matured)/len(matured) if matured else None,
            average_selection_close_return_pct=statistics.mean(r['selection_return_pct'] for r in matured) if matured else None,
            average_excess_pct=statistics.mean(r['excess_pct'] for r in matured if r['excess_pct'] is not None) if any(r['excess_pct'] is not None for r in matured) else None)
    replay_tracking=[]
    for event in events[:3]:
        r=dict(source_date=event['date'],ticker=event['ticker'],model_version=PROTOCOL['model_version'],plan=event['plan'],scope='REPLAY_NOT_NEW_FORWARD')
        o=observe(r,allbars[r['ticker']],idx[meta[r['ticker']]['market']],sessions,DAY)
        first=append_outcome(out/'replay_tracking_only',r,o);again=append_outcome(out/'replay_tracking_only',r,o)
        replay_tracking.append(dict(source_date=r['source_date'],ticker=r['ticker'],first=first,repeat=again,actual_forward_signal=False))
    summary=dict(price_only_days=days,selected_opportunities=len(events),range_events=sum(e['plan'] is not None for e in events),
        no_range_is_cash_and_included_in_expectancy=True,selection_metrics=selection_metrics,replay_tracking=replay_tracking,
        scope='NOV11_SURVIVOR_UNIVERSE_PRICE_ONLY_REUSED_HISTORY_NOT_INDEPENDENT',portfolio_return_not_simulated=True,
        financial_or_current_global_context_used=False,parameters_optimized=False,profitability_proven=False,results=result)
    write(out/'historical_single_entry_events.json',events);write(out/'historical_single_entry_summary.json',summary)
    return summary

def run(engine,state,old,out,fetch=True,reuse_history=False):
    started=time.monotonic();out.mkdir(parents=True,exist_ok=True);clock=datetime.now(timezone.utc)
    allbars,current,eligible,meta,market,baseline,provenance=load_dataset(engine,state,old)
    source=json.loads(Path('evidence/source-original/morning_source.json').read_text());company=json.loads(Path('evidence/company/company_quality.json').read_text())
    technical=json.loads((old/'technical_candidates.json').read_text())['rows']
    if len(technical)!=149:raise ValueError('BASELINE_TECHNICAL_149_NOT_REPRODUCED')
    previous=restore_pr106_baseline(out) if fetch else {name:json.loads((out/'baseline_pr106'/name).read_text()) for name in ('report.json','all149_range_diagnostics.json','historical_single_entry_summary.json')}
    if previous['report.json']['source_hash']!=provenance['original_market_payload_sha256']:raise ValueError('PR106_SOURCE_MARKET_CHANGED')
    previous_by={r['ticker']:r for r in previous['all149_range_diagnostics.json']['rows']}
    v3_baseline=restore_v3_baseline(out)
    probe=latest_probe(out,clock) if fetch else dict(status='OFFLINE_NO_NEW_PROVIDER_REQUEST')
    macro=restore_macro(out/'source_global_snapshot.json') if fetch else json.loads(Path('evidence/source-global/v618_global_macro_status.json').read_text())
    global_c=load_prior_macro(macro,clock)
    global_c['indices_and_megacaps']=fetch_indices(clock,out/'global_raw') if fetch else {}
    domestic=domestic_context({t:current[t] for t in eligible},meta,market['indices'],DAY);regime=combine(global_c,domestic)
    write(out/'market_environment.json',dict(global_context=global_c,domestic=domestic,regime=regime,
        context_asof=clock.isoformat(),price_asof=DAY,historical_causal_context=False))
    company_by={r['ticker']:r for r in company['companies']};finance={t:financial_review(r,DAY) for t,r in company_by.items()}
    rows=[]
    for original in technical:
        t=original['ticker'];r=dict(original)
        r['momentum_pass']=r['own_rs20']>0 and r['rs_accel5']>0
        r['liquidity_pass']=r['turnover20']>=PROTOCOL['min_turnover20_krw'];rows.append(r)
    stock_pool=choose_watch(rows,finance,domestic['sectors'])
    selected_ids=[r['ticker'] for r in stock_pool[:2]] # frozen BEFORE any range
    by={r['ticker']:r for r in rows};range_counts=Counter();diags=[]
    for r in rows:
        legacy=generate_ranges(current[r['ticker']]);prior=previous_by[r['ticker']]['range_review']
        if legacy!=prior:raise ValueError('PR106_RANGE_MODEL_NOT_EXACTLY_REPRODUCED:'+r['ticker'])
        v3=reassess(current[r['ticker']],legacy);audit_no_anchor_change(legacy,v3)
        if v3!=v3_baseline[r['ticker']]['range_review']:raise ValueError('V3_FULL_REVIEW_NOT_REPRODUCED:'+r['ticker'])
        d=review_v4(current[r['ticker']],legacy)
        range_counts['range_generated']+=bool(legacy['plans']);range_counts['range_risk_pass']+=bool(legacy['best'])
        range_counts['practical_entry_pass']+=bool(d['best'])
        range_counts['any_confirmed_stop']+=any(p['stop_reliability']['research_eligible'] for p in d['plans'])
        range_counts['v3_practical_pass']+=bool(v3['best'])
        range_counts['v4_generated']+=bool(d['plans'])
        range_counts['v4_risk_pass']+=any(p['range_valid'] for p in d['plans'])
        r.update(range_review=d,financial=finance.get(r['ticker'],{}));diags.append(r)
    if range_counts['range_generated']!=102 or range_counts['range_risk_pass']!=30 or range_counts['v3_practical_pass']!=9:raise ValueError('PR106_102_RANGES_30_RISK_PASS_NOT_REPRODUCED')
    sensitivity={str(t):dict(risk_and_width=sum(any(p['range_valid'] and p['range']['width_atr']>=t for p in r['range_review']['plans']) for r in rows),
        risk_width_and_confirmed_stop=sum(any(p['range_valid'] and p['range']['width_atr']>=t and p['stop_reliability']['research_eligible'] for p in r['range_review']['plans']) for r in rows)) for t in (0,.1,.2,.3,.4)}
    write(out/'practicality_sensitivity.json',dict(asof=DAY,thresholds_not_optimized=True,live_minimum_adopted=False,by_width_atr=sensitivity))
    write(out/'filter_exclusion_audit.json',exclusion_audit(rows))
    write(out/'range_cut_audit.json',[dict(ticker=r['ticker'],name=r['name'],old_clipped=[dict(method=p['method'],structural=p['range'].get('structural_range'),low=p['range']['low'],high=p['range']['high'],width_atr=p['range']['width_atr'],too_narrow=p['practicality']['status']=='RANGE_TOO_NARROW') for p in r['range_review']['v3_review']['plans'] if p['range_valid']],new=[dict(method=p['method'],range=p['range']) for p in r['range_review']['plans']]) for r in rows])
    watch=[]
    for t in selected_ids:
        r=dict(by[t]);p=r['range_review']['best']
        diagnostic=min(r['range_review']['plans'],key=lambda a:(r['close']-a['structural_high'])/a['atr14']) if r['range_review']['plans'] else None
        r.update(display_plan=p,diagnostic_plan=diagnostic,status='ENTRY RANGE' if p else 'WATCH',data_status='UNVERIFIED',buy_approved=False,
            reason_text='매출·영업이익·현금흐름 양수 API 관찰 · RS '+f"{r['own_rs20']:.1f}%p"+' / 최근 개선 '+f"{r['rs_accel5']:.1f}%p"+' · 재무 원문 PIT 미확인')
        if not p:r['entry_hold_reason']='CURRENT_SUPPORT_TOO_DEEP_OR_ACTIVE_RESISTANCE_UNCONFIRMED'
        watch.append(r)
    fit=choose_practical_top2(stock_pool,by)
    for i,r in enumerate(fit,1):r['research_rank']=i
    report=dict(schema='C3_AI_MARKET_ENTRY_RANGE_REPORT_V2',model_version=PROTOCOL['model_version'],mode='ARCHIVED_PRICE_CURRENT_CONTEXT_REVIEW',
        source_date=DAY,source_received_at=source['final_collection_at'],source_run_id=provenance['original_source_run_id'],source_hash=provenance['original_market_payload_sha256'],
        generated_at=datetime.now(timezone.utc).isoformat(),research_run_id=os.environ.get('GITHUB_RUN_ID'),research_commit=os.environ.get('GITHUB_SHA'),
        regime=regime,watch_top2=watch,entry_fit_top2=fit,final_research_top2=fit,
        final_research_ranking_policy='CORPORATE_OBSERVATIONS_MOMENTUM_THEN_TYPED_STRUCTURE_STOP_AND_WHOLE_RANGE',confirmed_company_quality_top2=[],
        selection_rank_frozen_before_range=True,financial_context_collected_at=company['collected_at'],
        financial_original_pit_verified=False,regular_only_certified=False,current_action='CASH',buy_approved=False,
        entry_execution_policy='USER_DISCRETION_NO_PRESCRIBED_COUNT',automated_order_enabled=False,telegram_requests=0,original_ledgers_modified=False,
        funnel=dict(full_market=2769,continuous_history=2416,analysis_eligible=1988,technical=149,original_b=50,
            positive_improving_rs=sum(r['momentum_pass'] for r in rows),observed_positive_financial=sum(v['observed_positive'] for v in finance.values()),
            original_pit_confirmed=sum(v['confirmed'] for v in finance.values()),current_review_watch_eligible=len(stock_pool),
            provisional_watch_top2=len(watch),entry_fit_top2=len(fit),**dict(range_counts)),
        certification_state='UNVERIFIED_NOT_CONFIRMED_ZERO_CANDIDATES',latest_source_probe=probe,provenance=provenance)
    report['report_payload_sha256']=hash_value(report)
    write(out/'report.json',report);write(out/'all149_range_diagnostics.json',dict(asof=DAY,rows=diags))
    write(out/'frozen_selection_ids.json',dict(selected_before_range=selected_ids,selected_after_range=[r['ticker'] for r in watch],same=True,
        final_research_top2=[r['ticker'] for r in fit],watch_only=[r['ticker'] for r in watch if r['ticker'] not in {v['ticker'] for v in fit}],
        final_rescreen_scope='FULL_149_TECHNICAL_CANDIDATES_NOT_FIXED_WATCH_TOP2'))
    paths=[];manifests=[];case_paths=[];case_manifests=[]
    for r in fit:
        p=out/'cards'/('C3_WATCH_'+DAY.replace('-','')+'_'+r['ticker']+'.png')
        bars=current[r['ticker']][-119:]
        source_doc=dict(ticker=r['ticker'],source_date=DAY,original_source_run_id=report['source_run_id'],
            original_market_payload_sha256=report['source_hash'],panel_sha256=provenance['panel_sha256'],bars=bars)
        write(out/'chart_sources'/(r['ticker']+'.json'),source_doc)
        manifest=render(dict(r,chart_source_sha256=hash_value(source_doc)),bars,report,p)
        manifests.append(manifest);paths.append(p)
    for t in ('028050','051160'):
        row=dict(by[t]);legacy=row['range_review']['legacy_best']
        if not legacy:continue
        plan=row['range_review']['best'] or next(p for p in row['range_review']['v3_review']['plans'] if p['method']==legacy['method'] and p['support']==legacy['support'] and p['stop']==legacy['stop'])
        row.update(display_plan=plan,is_diagnostic=True,case_selected=row['range_review']['best'] is not None,reason_text='기존 V3와 구조 유형별 판단 비교')
        path=out/'case_reviews'/('C3_CASE_'+DAY.replace('-','')+'_'+t+'.png')
        case_bars=current[t][-119:]
        chart_source=dict(ticker=t,source_date=DAY,original_source_run_id=report['source_run_id'],
            original_market_payload_sha256=report['source_hash'],panel_sha256=provenance['panel_sha256'],bars=case_bars)
        write(out/'chart_sources'/(t+'.json'),chart_source)
        case_manifests.append(render(dict(row,chart_source_sha256=hash_value(chart_source)),case_bars,report,path));case_paths.append(path)
        write(out/'case_reviews'/(t+'_structure.json'),dict(ticker=t,name=row['name'],asof=DAY,plan=plan,
            latest20=current[t][-20:],all_plans=row['range_review']['plans'],original_plan_numbers_unchanged=True,not_a_final_top2=True))
    write(out/'case_review_manifest.json',dict(cards=case_manifests,final_top2=False))
    if not paths:
        p=out/'cards'/('C3_UNVERIFIED_'+DAY.replace('-','')+'.png');manifests.append(hold_card(report,p));paths.append(p)
    write(out/'card_manifest.json',dict(source_run_id=report['source_run_id'],report_hash=report['report_payload_sha256'],cards=manifests))
    packet=envelope(paths,manifests,report)
    zero_card=out/'safe_test_inputs/C3_UNVERIFIED_ZERO_CANDIDATE_TEST.png';zero_manifest=hold_card(report,zero_card)
    test_paths=paths if len(paths)>=2 else case_paths
    tests={str(n):transport_test(test_paths[:n] if n else [zero_card]) for n in (0,1,2) if n<2 or len(test_paths)>=2}
    claims={};claim=safe_claim(claims,packet['key'],packet);duplicate=safe_claim(claims,packet['key'],packet)
    write(out/'telegram_safe_test.json',dict(envelope=packet,zero_candidates_mean_one_hold_card=True,
        scenarios=tests,zero_scenario_card=zero_manifest,first_claim=claim,repeat=duplicate,actual_telegram_requests=0,status='LIVE_SEND_HELD_RESEARCH_NOT_APPROVED',
        legacy_messages_40_41_42_untouched=True))
    forward=[]
    for r in fit:
        p=r['range_review']['best'];record=dict(source_date=DAY,ticker=r['ticker'],source_run_id=report['source_run_id'],source_hash=report['source_hash'],
            model_version=PROTOCOL['model_version'],created_at=report['generated_at'],source_received_at=report['source_received_at'],
            reasons=r['reason_text'],market_regime=regime,range=p['range'] if p else None,plan=p,
            stop=p['stop'] if p else None,r1=p['r1'] if p else None,r2=p['r2'] if p else None,
            execution_policy='USER_DISCRETION_NO_PRESCRIBED_COUNT',automated_order_enabled=False)
        reg=register(out/'research_only_forward',record,clock,replay=True)
        forward.append(dict(registration=reg,observation=observe(record,allbars[r['ticker']],market['indices'][r['market']],market['sessions'],DAY)))
    write(out/'forward_tracking.json',dict(records=forward,backdated_forward_registrations=0,live_daily_deployment=False,
        code_supports_immutable_records_and_5_10_20_updates=True,reason='FROZEN_NOV11_REPLAY_NOT_NEW_FORWARD_SIGNAL'))
    cohorts,cohort_events=rejection_cohorts(allbars,eligible,meta,market,DAY)
    write(out/'three_rejection_cohorts.json',cohorts);write(out/'three_rejection_cohort_events.json',cohort_events)
    history=previous['historical_single_entry_summary.json'] if reuse_history else history_comparison(allbars,eligible,meta,market,out)
    if reuse_history:write(out/'historical_reference_pr106.json',dict(status='REUSED_PRIOR_RESULT_NOT_A_V3_BACKTEST',source_run_id='43191464464',
        archive_sha256='4347b7fc1483b63953a8a07f314f13e8ba5231ab0ac2e825c5ae1a398712e522',reference=history,
        new_practicality_stop_policy_profitability_claimed=False))
    write(out/'execution_summary.json',dict(funnel=report['funnel'],watch=[dict(ticker=r['ticker'],name=r['name'],close=r['close'],status=r['status']) for r in watch],
        research_entry_fit=len(fit),final_research_top2=[dict(ticker=r['ticker'],name=r['name'],range=[r['display_plan']['range']['low'],r['display_plan']['range']['high']]) for r in fit],
         buy_approved=False,action='CASH',regime=regime,historical_range_events=history['range_events'],
        png_count=len(paths),diagnostic_case_pngs=len(case_paths),all149_original_numeric_plans_unchanged=True,new_typed_plans_are_separate_version=True,
        historical_metrics_scope='REUSED_PR106_REFERENCE_NOT_V3_BACKTEST' if reuse_history else 'V3_EXPLORATORY_NOT_INDEPENDENT',
        telegram_actual_requests=0,elapsed_seconds=round(time.monotonic()-started,2)))
    print(json.dumps(dict(funnel=report['funnel'],watch=selected_ids,final_research_top2=[r['ticker'] for r in fit],png_count=len(paths),buy_approved=False),ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--engine',type=Path,required=True);p.add_argument('--state',type=Path,required=True)
    p.add_argument('--old',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--offline',action='store_true');p.add_argument('--reuse-pr106-history',action='store_true');a=p.parse_args()
    run(a.engine,a.state,a.old,a.out,not a.offline,a.reuse_pr106_history)
