"""Apply existing approved/V4 calculations to an actual new source, NO ORDERS.

No fabricated original registration: late or uncertified sources are dated
research reviews. Original A/B ledgers and trading stops are never written.
"""
import argparse,csv,gzip,hashlib,json,os,subprocess
from collections import defaultdict,Counter
from datetime import datetime,timezone
from pathlib import Path
from c3_telegram_inputs import canonical,GitHub,RESEARCH
from c3_source_recovery_v1 import write,validate


def sha(value):return hashlib.sha256(canonical(value)).hexdigest()


def load_prices(source):
    manifest=json.loads((source/'collection.json').read_text())
    if not manifest.get('research_ready'):raise ValueError('NEW_SOURCE_UNAVAILABLE_NO_PREVIOUS_DATE_FALLBACK')
    doc=json.loads((source/'normalized_market.json').read_text());day=manifest['asof'];rows=doc['rows'];validate(rows,day)
    from c3_morning_source_v1 import normalized_hash
    if doc['asof']!=day or normalized_hash(rows)!=manifest['normalized_rows_sha256']:raise ValueError('NEW_SOURCE_HASH_OR_DAY_MISMATCH')
    fields=('ticker','name','market','asof','open','high','low','close','volume','turnover_krw')
    prices={r['ticker']:{k:r[k] for k in fields} for r in rows}
    payload=dict(schema='C3_NEW_DATED_SOURCE_V1',asof=day,price_basis=manifest['price_basis'],
        regular_only_certified=False,rows=prices)
    return manifest,prices,payload


def dated_snapshot(rows,day):
    return dict(rows={t:dict(r,date=day) for t,r in rows.items()})


def prior_research_history(state,snapshots,day):
    """Read preserved past prices without registering past trading signals."""
    from c3_supply_v11 import open_sealed
    from c3_morning_source_v1 import normalized_hash
    root=state/'reports/c3_new_session_v1';proof=[]
    fields=('open','high','low','close','volume','turnover_krw')
    def comparable(rows):
        return {t:(r['name'],tuple(float(r[k]) for k in fields)) for t,r in rows.items()}
    for path in sorted((root/'sources').glob('*/*.aesgcm')):
        prior=path.parent.name
        if prior>=day:continue  # Neither the current source nor a future session.
        datetime.strptime(prior,'%Y-%m-%d')
        payload=json.loads(open_sealed(path,os.environ.get('KRX_AUTH_KEY')))
        if payload.get('schema')!='C3_NEW_DATED_SOURCE_V1' or payload.get('asof')!=prior or sha(payload)!=path.stem:
            raise ValueError('PRIOR_RESEARCH_SOURCE_HASH_OR_DATE_MISMATCH')
        rows=list(payload['rows'].values());validate(rows,prior);norm=normalized_hash(rows)
        receipts=[json.loads(p.read_text()) for p in (root/'receipts'/prior).glob('*.json')]
        if not any(r.get('source_sha256')==path.stem and r.get('normalized_rows_sha256')==norm for r in receipts):
            raise ValueError('PRIOR_RESEARCH_SOURCE_RECEIPT_REQUIRED')
        if prior in snapshots and comparable(snapshots[prior]['rows'])!=comparable(payload['rows']):
            raise ValueError('PRIOR_RESEARCH_OR_ORIGINAL_PRICE_CONFLICT')
        snapshots.setdefault(prior,dated_snapshot(payload['rows'],prior))
        proof.append(dict(asof=prior,source_sha256=path.stem,normalized_rows_sha256=norm,rows=len(rows),
            original_signal_registered=False,regular_only_certified=False))
    return proof


def extended_history(panel,audit,prices,snapshots,sessions,day):
    """Same segmentation as V4; approved 90-bar suffix is checked separately."""
    events={(e['ticker'],e['date']) for e in audit['reference_rebase_candidates']};grid={d:i for i,d in enumerate(sessions)}
    raw=defaultdict(dict)
    with gzip.open(panel,'rt') as f:
        for r in csv.DictReader(f):
            if r['ticker'] in prices and r['date']<=day:raw[r['ticker']][r['date']]=r
    for d,doc in snapshots.items():
        if d<=day:
            for t,r in doc['rows'].items():
                if t in prices:raw[t][d]=dict(r,date=d)
    for t,r in prices.items():raw[t][day]=dict(r,date=day)
    result={};allbars={}
    for t,by in raw.items():
        bars=[];previous=None;segment=0
        for d,r in sorted(by.items()):
            if d not in grid:raise ValueError('PRICE_DATE_NOT_IN_OBSERVED_BOARD_CALENDAR')
            values={k:float(r[k]) for k in ('open','high','low','close','volume','turnover_krw')}
            valid=0<values['low']<=min(values['open'],values['close'])<=max(values['open'],values['close'])<=values['high'] and values['volume']>0 and values['turnover_krw']>0
            boundary=(t,d) in events or bool(r.get('action_boundary',False))
            if previous:boundary=boundary or grid[d]!=grid[previous['date']]+1 or r['name']!=previous['name'] or (previous['close']>0 and abs(values['close']/previous['close']-1)>.35)
            if boundary or not valid:segment+=1
            bars.append(dict(values,date=d,name=r['name'],segment=segment,tradable=valid,action_boundary=boundary))
            if not valid:segment+=1
            previous=dict(date=d,name=r['name'],close=values['close'])
        allbars[t]=bars
        tail=[b for b in bars if b['segment']==bars[-1]['segment'] and b['tradable']]
        if len(tail)>=65 and tail[-1]['date']==day:result[t]=tail
    return result,allbars


def run(source,engine,state,out,private,macro=None,timing_cohort=None):
    from c3_bootstrap_cache_v13 import restore
    from c3_forward_ledger_v8 import read_record
    from c3_daily_research_v8 import histories,choose
    from c3_current_candidates_v7 import fresh_snapshot
    from c3_selection_scope_v5 import classify,read_csv,unique_index,selection_features,digest
    from c3_selection_factors_v6 import causal_factors,regime as board_regime
    from c3_market_range_study_v1 import financial_review,choose_watch,choose_practical_top2
    from c3_single_entry_range_v1 import generate_ranges,PROTOCOL
    from c3_entry_structure_v4 import review_v4
    from c3_market_context_v1 import domestic_context,combine,load_prior_macro
    from c3_company_quality_review_v1 import collect
    from c3_range_card_v1 import render,hold_card
    from c3_range_delivery_v1 import envelope,safe_claim
    from c3_watch_card_v1 import watch_rows,render_watch,annotate_entry_card
    manifest,prices,payload=load_prices(source);day=manifest['asof'];out.mkdir(parents=True,exist_ok=True)
    if manifest.get('indices_ready') is not True:raise ValueError('NEW_DAY_BENCHMARKS_REQUIRED')
    indices={}
    for market in ('KOSPI','KOSDAQ'):
        with (source/'indices'/(market+'_index.csv')).open() as f:indices[market]={r['date']:float(r['close']) for r in csv.DictReader(f) if r['date']<=day}
    if any(max(v)!=day for v in indices.values()) or set(indices['KOSPI'])!=set(indices['KOSDAQ']):raise ValueError('NEW_DAY_BOARD_INDEX_DATES_MISMATCH')
    sessions=sorted(indices['KOSPI']);lane=state/'reports/c3_forward_v8';oldlatest=json.loads((lane/'latest.json').read_text())
    restore(engine/'reports/c3_work8_20261105/inputs.json',private,lane,out/'bootstrap_audit.json')
    panel=private/'panel/official_panel.csv.gz';auditfile=private/'panel/quality_audit.json';audit=json.loads(auditfile.read_text())
    if digest(panel)!=oldlatest['source_hashes']['panel'] or digest(auditfile)!=oldlatest['source_hashes']['audit']:raise ValueError('REGISTERED_BOOTSTRAP_HISTORY_HASH_MISMATCH')
    snapshots={r['asof']:r for r in (read_record(p) for p in sorted((lane/'lanes/krx_unadjusted_v12/markets').glob('*.json.gz'))) if r['asof']<=day}
    prior_proof=prior_research_history(state,snapshots,day)
    baseline,bmeta=fresh_snapshot(private/'latest/requested-date-probe/2026-11-04')
    snapshots[bmeta['asof']]=dated_snapshot(baseline,bmeta['asof'])
    past,excluded=histories(panel,auditfile,prices,snapshots,sessions,day)
    current,allbars=extended_history(panel,audit,prices,snapshots,sessions,day)
    if set(current)!=set(past):raise ValueError('EXTENDED_HISTORY_UNIVERSE_MISMATCH')
    fields=('date','name','open','high','low','close','volume','turnover_krw')
    for t,bs in past.items():
        if [{k:b[k] for k in fields} for b in current[t][-90:]]!=[{k:b[k] for k in fields} for b in bs]:raise ValueError('APPROVED_90_BAR_SUFFIX_MISMATCH')
    basic=private/'issuer/basic';scope=engine/'reports/c3_work5_20261105/sources'
    basics=unique_index(read_csv(basic/'KOSPI_basic_v610.csv')+read_csv(basic/'KOSDAQ_basic_v610.csv'));kind=unique_index(read_csv(scope/'kind_companies.csv'));secondary=defaultdict(list)
    for r in read_csv(scope/'secondary_industries.csv'):secondary[r['ticker']].append(r)
    eligible={t for t in past if classify(prices[t],basics.get(t),kind.get(t),secondary[t])=='VERIFIED_NONBIO_COMMON_AS_REPORTED'}
    meta={t:dict(ticker=t,name=prices[t]['name'],market=prices[t]['market'],sector=secondary[t][0]['sector']) for t in eligible}
    known=datetime.now(timezone.utc).isoformat();models,counts=choose(prices,past,basics,kind,secondary,indices,sessions,known,
        dict(asof=day,received_at=manifest['data_received_at'],regular_only_certified=False,price_basis=manifest['price_basis']),
        os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_SHA'])
    technical=[]
    for t in sorted(eligible):
        p=prices[t];bs=past[t];ix=indices[p['market']];f=selection_features(bs,100*(ix[day]/ix[bs[-21]['date']]-1))
        if f is None:continue
        cf=causal_factors(bs,ix);technical.append(dict(ticker=t,name=p['name'],market=p['market'],sector=meta[t]['sector'],market_regime=board_regime([ix[d] for d in sessions]),**f,**cf))
    technical.sort(key=lambda r:(-r['turnover20'],-r['rs20'],r['ticker']))
    if len(technical)!=counts['a_candidates']:raise ValueError('NEW_DAY_TECHNICAL_SCOPE_NOT_REPRODUCED')
    if [r['ticker'] for r in technical[:2]]!=[r['ticker'] for r in models['A']]:raise ValueError('NEW_DAY_APPROVED_MODEL_REPRODUCTION_MISMATCH')
    write(out/'technical_candidates.json',dict(asof=day,rows=technical))
    company=collect(dict(asof=day,rows=technical));write(out/'company_quality.json',company)
    finances={r['ticker']:financial_review(r,day) for r in company['companies']}
    domestic=domestic_context({t:current[t] for t in eligible},meta,indices,day)
    global_context=load_prior_macro(json.loads(macro.read_text()),datetime.now(timezone.utc)) if macro and macro.exists() else {'legacy_risk_classification':{'regime':'GLOBAL_INCOMPLETE'}}
    market=combine(global_context,domestic)
    write(out/'market_environment.json',dict(domestic=domestic,global_context=global_context,regime=market,historical_causal_claimed=False))
    rows=[]
    for r in technical:
        t=r['ticker'];r.update(momentum_pass=r['own_rs20']>0 and r['rs_accel5']>0,liquidity_pass=r['turnover20']>=PROTOCOL['min_turnover20_krw'],
            financial=finances.get(t,financial_review({},day)),range_review=review_v4(current[t],generate_ranges(current[t])))
        rows.append(r)
    pool=choose_watch(rows,finances,domestic['sectors']);by={r['ticker']:r for r in rows}
    fit=choose_practical_top2([r for r in pool if len(current[r['ticker']])>=119],by)
    for i,r in enumerate(fit,1):r['research_rank']=i
    from c3_watch_quality_audit_v1 import audit as watch_audit,prior_reviews
    observation=watch_audit(rows,current,pool,fit,day,prior_reviews(state,day))
    write(out/'watch_quality_audit.json',observation)
    for group in (rows,pool,fit):
        for row in group:row['observation_audit']=observation['observations'][row['ticker']]
    if timing_cohort is not None:
        from c3_entry_timing_audit_v1 import run as timing_audit
        timing_audit(allbars,indices,sessions,day,timing_cohort,out/'entry_timing_audit')
    completed=datetime.now(timezone.utc).isoformat()
    report=dict(schema='C3_NEW_SESSION_RESEARCH_REPORT_V1',source_date=day,source_run_id=manifest['source_run_id'],source_hash=sha(payload),
        normalized_rows_sha256=manifest['normalized_rows_sha256'],source_received_at=manifest['data_received_at'],generated_at=completed,
        research_run_id=os.environ['GITHUB_RUN_ID'],research_commit=os.environ['GITHUB_SHA'],model_version=PROTOCOL['model_version'],
        v4_code_commit=subprocess.check_output(['git','-C','v4','rev-parse','HEAD'],text=True).strip(),mode='NEW_SOURCE_RETROSPECTIVE_RESEARCH_NOT_REGISTERED_TRADE',
        watch_quality_audit_sha256=observation['audit_payload_sha256'],
        source_status=manifest['status'],regular_only_certified=False,financial_original_pit_verified=False,
        selection_status='RESEARCH_ANALYSIS_COMPLETE' if any(r['financial'].get('required_metrics_complete') for r in rows) else 'RESEARCH_ANALYSIS_INCOMPLETE_FINANCIAL',analysis_completed=True,final_research_top2=fit,
        watch_top2=watch_rows(pool,fit),
        regime=market,current_action='CASH',buy_approved=False,orders_enabled=False,automated_order_enabled=False,telegram_requests=0,
        entry_execution_policy='USER_DISCRETION_NO_PRESCRIBED_COUNT',approved_original_registered=False,new_forward_records=0,
        original_history_source_date=oldlatest['source_price_asof'],funnel=dict(full_market=len(prices),analysis_eligible=len(eligible),continuous_history=len(past),technical=len(rows),
            original_b=counts['b_candidates'],observed_positive_financial=sum(r['financial']['observed_positive'] for r in rows),
            company_momentum_liquidity=len(pool),structural_stop_pass=sum(any(p['stop_reliability']['research_eligible'] for p in r['range_review']['plans']) for r in rows),
            practical_entry_pass=sum(r['range_review']['best'] is not None for r in rows),final_candidates=len(fit)),
        financial_context_collected_at=company['collected_at'],classification_pit_verified=False,model_profitability_promoted=False)
    report['report_payload_sha256']=sha(report);write(out/'report.json',report);write(out/'all_technical_diagnostics.json',dict(asof=day,rows=rows))
    approved={m:[{k:v for k,v in r.items() if k not in ('chart_bars','registered_at','signal_id')} for r in rs] for m,rs in models.items()}
    write(out/'approved_engine_calculation.json',dict(asof=day,models=approved,counts=counts,original_registration=False,research_only=True))
    write(out/'source_payload.json',payload);write(out/'history_provenance.json',dict(panel_sha256=digest(panel),audit_sha256=digest(auditfile),excluded=excluded,approved_90_suffix_equal=True,observed_sessions=len(sessions),prior_research_sources=prior_proof))
    paths=[];manifests=[]
    for row in fit:
        t=row['ticker'];chart=dict(ticker=t,source_date=day,source_hash=sha(payload),bars=current[t][-119:]);write(out/'chart_sources'/(t+'.json'),chart)
        path=out/'cards'/('C3_NEW_'+day.replace('-','')+'_'+t+'.png')
        card=render(dict(row,chart_source_sha256=sha(chart)),current[t][-119:],report,path)
        manifests.append(annotate_entry_card(path,card,row));paths.append(path)
    if not paths:
        p=out/'cards'/('C3_NEW_'+day.replace('-','')+'_CASH.png');manifests.append(hold_card(report,p));paths.append(p)
    write(out/'card_manifest.json',dict(cards=manifests,report_hash=report['report_payload_sha256']))
    watch_manifests=[]
    for rank,row in enumerate(pool[:2],1):
        t=row['ticker'];chart=dict(ticker=t,source_date=day,source_hash=sha(payload),bars=current[t][-119:])
        write(out/'watch_chart_sources'/(t+'.json'),chart)
        path=out/'watch_cards'/('C3_WATCH_'+day.replace('-','')+'_'+t+'.png')
        watch_manifests.append(render_watch(dict(row,chart_source_sha256=sha(chart)),current[t][-119:],report,path,rank))
    write(out/'watch_card_manifest.json',dict(cards=watch_manifests,report_hash=report['report_payload_sha256']))
    packet=envelope(paths,manifests,report);claims={};safe_claim(claims,packet['key'],packet)
    write(out/'delivery_status.json',dict(status='RESEARCH_NOT_SENT',actual_telegram_requests=0,repeat=safe_claim(claims,packet['key'],packet),packet=packet))
    print(json.dumps(dict(asof=day,funnel=report['funnel'],final_candidates=[r['ticker'] for r in fit],png_count=len(paths),buy_approved=False),ensure_ascii=False))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('source','engine','state','out','private'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--macro',type=Path);p.add_argument('--timing-cohort',type=Path);a=p.parse_args();run(a.source,a.engine,a.state,a.out,a.private,a.macro,a.timing_cohort)
