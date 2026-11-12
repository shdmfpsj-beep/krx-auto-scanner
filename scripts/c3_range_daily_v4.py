"""Registered-source V4 daily observations, isolated from production ledgers.

No order/Telegram client. Replays cannot create forward records. A prospective
caller must supply the exact approved registration commit/run and source proof.
"""
import argparse,json,os,re,subprocess
from datetime import datetime,timezone
from pathlib import Path
from c3_range_forward_v1 import hash_value,immutable,register,update_existing


def isolated_outputs(engine,state,old,out,records):
    protected=[Path(p).resolve() for p in (engine,state,old)]
    for p in (Path(out).resolve(),Path(records).resolve()):
        if any(p==q or p.is_relative_to(q) or q.is_relative_to(p) for q in protected):
            raise ValueError('RESEARCH_OUTPUT_OVERLAPS_PROTECTED_INPUT')
        if any(part in {'c3_forward_v8','.git','.github'} for part in p.parts):
            raise ValueError('RESEARCH_OUTPUT_USES_PROTECTED_LEDGER_PATH')


def lineage(latest,market,decision,source,proof,state_sha,caller,clock,mode):
    from c3_morning_source_v1 import normalized_hash,prior_session
    from c3_morning_registration_v1 import check_review
    day=market['asof'];run=str(latest.get('source_run_id',''))
    if (latest.get('source_price_asof')!=day or decision.get('price_asof')!=day or
        latest.get('research_top2_registered_for_source_session') is not True or
        decision.get('source_snapshot_hash')!=hash_value(market) or
        str(market.get('source',{}).get('source_run_id'))!=run):
        raise ValueError('REGISTERED_DAILY_SOURCE_MISMATCH')
    rows=[dict(r,ticker=t,asof=day) for t,r in market['rows'].items()]
    if set(r['market'] for r in rows)!={'KOSPI','KOSDAQ'} or len(rows)!=latest['current_scope']['price_rows']:
        raise ValueError('DAILY_FULL_MARKET_SCOPE_MISMATCH')
    if (source.get('schema')!='C3_MORNING_OFFICIAL_SOURCE_V1' or source.get('ready') is not True or
        source.get('status')!='OFFICIAL_CACHE_MATCHED' or source.get('requested_day')!=day or
        source.get('normalized_rows_sha256')!=normalized_hash(rows)):
        raise ValueError('DAILY_OFFICIAL_PROOF_MISMATCH')
    if mode=='replay':return dict(status='READ_ONLY_REPLAY',forward_allowed=False,registered_state_sha=state_sha,source_run_id=run,market_payload_sha256=hash_value(market))
    if mode!='forward':raise ValueError('INVALID_DAILY_MODE')
    check_review(proof,state_sha,day,caller)
    if (proof['source_run_id']!=run or proof['market_payload_sha256']!=hash_value(market) or
        proof['decision_payload_sha256']!=hash_value(decision)):
        raise ValueError('DAILY_REGISTRATION_PAYLOAD_MISMATCH')
    target=prior_session(clock)
    if day!=target['requested_day']:raise ValueError('STALE_DAILY_SOURCE_NO_SUBSTITUTION')
    import exchange_calendars as xc
    opening=xc.get_calendar('XKRX').session_open(target['expected_entry_session']).to_pydatetime()
    if clock>=opening:raise ValueError('FORWARD_RESEARCH_AFTER_ENTRY_OPEN_FORBIDDEN')
    received=datetime.fromisoformat(source['final_collection_at'].replace('Z','+00:00'))
    if received.tzinfo is None or not datetime.fromisoformat(day+'T15:30:00+09:00')<=received<=clock:
        raise ValueError('INVALID_DAILY_SOURCE_RECEIPT_TIME')
    return dict(status='REGISTERED_PROSPECTIVE_SOURCE',forward_allowed=True,registered_state_sha=state_sha,registration_run_id=str(caller),source_run_id=run,market_payload_sha256=hash_value(market),decision_payload_sha256=hash_value(decision),registration_proof_sha256=hash_value(proof))


def decision_identity(report):
    # A retry may have a new wall clock/run. It cannot change the model input,
    # selected tickers, structural stops or financial/market facts for this day.
    return {k:report[k] for k in ('model_version','model_code_sha256','source_date','source_run_id','source_hash',
        'original_decision_hash','analysis_identity_sha256','watch_top2','final_research_top2','funnel','regime')}


def freeze(root,report,clock,mode):
    if mode=='replay':return dict(status='REPLAY_NOT_REGISTERED_AS_FORWARD',writes=0,records=[])
    if mode!='forward':raise ValueError('INVALID_DAILY_MODE')
    if report.get('mode')!='PROSPECTIVE_RESEARCH_OBSERVATION' or report.get('buy_approved') is not False:
        raise ValueError('PROSPECTIVE_RESEARCH_NOT_TRADE_REQUIRED')
    model=report['model_version'];day=report['source_date']
    if not re.fullmatch('[A-Z0-9_]+',model) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):
        raise ValueError('INVALID_DAILY_SNAPSHOT_ID')
    from c3_morning_source_v1 import prior_session
    import exchange_calendars as xc
    from datetime import date
    date.fromisoformat(day)
    timing=prior_session(clock)
    if day!=timing['requested_day'] or clock>=xc.get_calendar('XKRX').session_open(timing['expected_entry_session']).to_pydatetime():
        raise ValueError('STALE_OR_AFTER_OPEN_DAILY_SNAPSHOT_FORBIDDEN')
    path=Path(root)/'decisions'/model/(day+'.json');identity=hash_value(decision_identity(report))
    if path.exists():
        saved=json.loads(path.read_text())
        if saved.get('sha256')!=hash_value(saved['record']):raise ValueError('DAILY_DECISION_HASH_MISMATCH')
        if saved['record']['identity_sha256']!=identity:raise ValueError('IMMUTABLE_DAILY_DECISION_CONFLICT')
        frozen=saved['record']['report'];status='ALREADY_RECORDED'
    else:
        frozen=report;record=dict(identity_sha256=identity,report=frozen)
        status=immutable(path,dict(record=record,sha256=hash_value(record)))
    picks=frozen['final_research_top2'] or frozen['watch_top2'];records=[]
    for row in picks:
        plan=row.get('display_plan')
        record=dict(source_date=day,ticker=row['ticker'],source_run_id=frozen['source_run_id'],source_hash=frozen['source_hash'],
            model_version=model,created_at=frozen['generated_at'],source_received_at=frozen['source_received_at'],
            reasons=row.get('reason_text',''),market_regime=frozen['regime'],range=plan['range'] if plan else None,plan=plan,
            stop=plan['stop'] if plan else None,r1=plan['r1'] if plan else None,r2=plan['r2'] if plan else None,
            selection_role='ENTRY_FIT' if frozen['final_research_top2'] else 'WATCH_ONLY',buy_approved=False,registration_lineage=frozen.get('registration_lineage',{}),model_code_sha256=frozen['model_code_sha256'],
            execution_policy='USER_DISCRETION_NO_PRESCRIBED_COUNT',automated_order_enabled=False)
        records.append(register(root,record,clock))
    return dict(status=status,identity_sha256=identity,records=records,entry_fit=len(frozen['final_research_top2']),
        watch_only=len(frozen['watch_top2']) if not frozen['final_research_top2'] else 0,actual_telegram_requests=0)


def build(engine,state,old,source_path,company_path,out,records,mode='replay',registration=None,caller=None,clock=None,macro=None):
    from c3_dynamic_study_v2 import load_dataset,write
    from c3_forward_ledger_v8 import read_record
    from c3_market_range_study_v1 import financial_review,choose_watch,choose_practical_top2
    from c3_market_context_v1 import domestic_context,combine,fetch_indices,load_prior_macro
    from c3_single_entry_range_v1 import generate_ranges,PROTOCOL
    from c3_entry_structure_v4 import review_v4
    from c3_range_card_v1 import render,hold_card
    from c3_range_delivery_v1 import envelope,safe_claim
    isolated_outputs(engine,state,old,out,records)
    clock=clock or datetime.now(timezone.utc);out.mkdir(parents=True,exist_ok=True)
    latest=json.loads((state/'reports/c3_forward_v8/latest.json').read_text());day=latest['source_price_asof']
    lane=state/'reports/c3_forward_v8/lanes/krx_unadjusted_v12'
    market=read_record(lane/'markets'/(day+'.json.gz'));decision=read_record(lane/'decisions'/(day+'.json'))
    source=json.loads(source_path.read_text());proof=json.loads(registration.read_text()) if registration else {}
    sha=subprocess.check_output(['git','-C',str(state),'rev-parse','HEAD'],text=True).strip()
    checked=lineage(latest,market,decision,source,proof,sha,caller,clock,mode)
    allbars,current,eligible,metadata,market,baseline,provenance=load_dataset(engine,state,old,asof=day)
    technical=json.loads((old/'technical_candidates.json').read_text())
    if technical['asof']!=day or len(technical['rows'])!=latest['current_scope']['a_candidates']:
        raise ValueError('DAILY_TECHNICAL_SCOPE_MISMATCH')
    company=json.loads(company_path.read_text())
    if company['asof']!=day:raise ValueError('DAILY_FINANCIAL_DATE_MISMATCH')
    collected=datetime.fromisoformat(company['collected_at'].replace('Z','+00:00'))
    if collected.tzinfo is None or collected>clock:raise ValueError('DAILY_FINANCIAL_FUTURE_COLLECTION')
    finance={r['ticker']:financial_review(r,day) for r in company['companies']}
    domestic=domestic_context({t:current[t] for t in eligible},metadata,market['indices'],day)
    global_context=load_prior_macro(json.loads(macro.read_text()),clock) if macro else dict(status='UNAVAILABLE_NO_DATED_MACRO_BUNDLE',legacy_risk_classification={'regime':'GLOBAL_INCOMPLETE'})
    global_context['indices_and_megacaps']=fetch_indices(clock,out/'global_raw') if mode=='forward' else {}
    regime=combine(global_context,domestic)
    rows=[]
    for original in technical['rows']:
        r=dict(original);t=r['ticker'];legacy=generate_ranges(current[t]);review=review_v4(current[t],legacy)
        r.update(momentum_pass=r['own_rs20']>0 and r['rs_accel5']>0,liquidity_pass=r['turnover20']>=PROTOCOL['min_turnover20_krw'],
            range_review=review,financial=finance.get(t,financial_review({},day)))
        rows.append(r)
    by={r['ticker']:r for r in rows};pool=choose_watch(rows,finance,domestic['sectors']);fit=choose_practical_top2([r for r in pool if len(current[r['ticker']])>=119],by)
    watch=[]
    for r in pool[:2]:
        w=dict(by[r['ticker']]);w.update(display_plan=w['range_review']['best'],status='WATCH',buy_approved=False,
            reason_text='현재 재무 API 관측·RS·유동성 연구 후보. 원문 PIT 및 정규장 인증 미완료.');watch.append(w)
    scripts=Path(__file__).parent
    code_identity={p.name:__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in [scripts/'c3_entry_structure_v4.py',scripts/'c3_single_entry_range_v1.py',Path(__file__)]}
    report=dict(schema='C3_AI_MARKET_ENTRY_RANGE_REPORT_V2',model_version=PROTOCOL['model_version'],model_code_sha256=hash_value(code_identity),
        mode='PROSPECTIVE_RESEARCH_OBSERVATION' if mode=='forward' else 'ARCHIVED_PRICE_CURRENT_CONTEXT_REVIEW',
        source_date=day,source_received_at=source['final_collection_at'],source_run_id=latest['source_run_id'],source_hash=hash_value(market),
        original_decision_hash=hash_value(decision),analysis_identity_sha256=hash_value(dict(rows=rows,domestic=domestic)),
        generated_at=clock.isoformat(),research_run_id=os.environ.get('GITHUB_RUN_ID'),registration_lineage=checked,
        research_commit=subprocess.check_output(['git','-C',str(scripts.parent),'rev-parse','HEAD'],text=True).strip(),upstream_caller_sha=os.environ.get('GITHUB_SHA'),
        watch_top2=watch,entry_fit_top2=fit,final_research_top2=fit,regime=regime,current_action='CASH',
        buy_approved=False,regular_only_certified=False,financial_original_pit_verified=False,telegram_requests=0,
        automated_order_enabled=False,original_ledgers_modified=False,entry_execution_policy='USER_DISCRETION_NO_PRESCRIBED_COUNT',
        financial_context_collected_at=company['collected_at'],funnel=dict(full_market=len(market['rows']),analysis_eligible=len(eligible),technical=len(rows),
            original_b=baseline['original_b_filter_count'],observed_positive_financial=sum(r['financial']['observed_positive'] for r in rows),
            practical_entry_pass=sum(r['range_review']['best'] is not None for r in rows),entry_fit_top2=len(fit)),provenance=provenance)
    write(out/'market_environment.json',dict(global_context=global_context,domestic=domestic,regime=regime,price_asof=day,context_asof=clock.isoformat()))
    report['report_payload_sha256']=hash_value(report);write(out/'report.json',report)
    write(out/'all_technical_diagnostics.json',dict(asof=day,rows=rows));write(out/'lineage_check.json',checked)
    paths=[];manifests=[]
    for rank,row in enumerate(fit,1):
        bars=current[row['ticker']][-119:];chart=dict(ticker=row['ticker'],source_date=day,source_hash=hash_value(market),bars=bars)
        write(out/'chart_sources'/(row['ticker']+'.json'),chart);path=out/'cards'/('C3_RANGE_'+day.replace('-','')+'_'+row['ticker']+'.png')
        manifests.append(render(dict(row,research_rank=rank,chart_source_sha256=hash_value(chart)),bars,report,path));paths.append(path)
    if not paths:
        path=out/'cards'/('C3_CASH_'+day.replace('-','')+'.png');manifests.append(hold_card(report,path));paths.append(path)
    write(out/'card_manifest.json',dict(cards=manifests,report_hash=report['report_payload_sha256']))
    packet=envelope(paths,manifests,report);claims={};safe_claim(claims,packet['key'],packet)
    write(out/'delivery_dry_run.json',dict(packet=packet,repeat=safe_claim(claims,packet['key'],packet),actual_telegram_requests=0))
    registered=freeze(records,report,clock,mode)
    index_by_ticker={t:market['indices'][metadata[t]['market']] for t in metadata}
    updates=update_existing(records,allbars,index_by_ticker,market['sessions'],day) if mode=='forward' else dict(status='REPLAY_NO_FORWARD_WRITES',observations=0)
    write(out/'forward_tracking.json',dict(registration=registered,updates=updates,production_modified=False))
    write(out/'execution_summary.json',dict(source_day=day,source_run_id=latest['source_run_id'],mode=mode,funnel=report['funnel'],
        final_candidates=[r['ticker'] for r in fit],png_count=len(paths),actual_telegram_requests=0,original_ledger_writes=0,forward=registered))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('engine','state','old','source','company','out','records'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--macro',type=Path);p.add_argument('--mode',choices=('replay','forward'),default='replay');p.add_argument('--registration',type=Path);p.add_argument('--caller-run-id')
    a=p.parse_args();result=build(a.engine,a.state,a.old,a.source,a.company,a.out,a.records,a.mode,a.registration,a.caller_run_id,macro=a.macro)
    print(json.dumps(dict(source_date=result['source_date'],funnel=result['funnel'],buy_approved=False),ensure_ascii=False))
