#!/usr/bin/env python3
"""Replay frozen C3 stage observations into price-only stop/entry/resistance research.

No live trade approval. Does NOT certify the pykrx/aggregator's regular-only
session scope or actual turnover. As-of uses only completed, dated input bars.
The 36 registered names are used for continuity, not as a hindsight cohort.
"""
import argparse, csv, gzip, hashlib, io, json, math
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
import pandas as pd
from c3_entry_corridor_v1 import build_corridors
from practical_entry_quotes_v619 import krx_round

SCHEMA='C3_CORRIDOR_FROZEN_REPLAY_V1_RESEARCH_ONLY'
INPUTS=['status.json','c3_premove_observation_status_v1.json',
        'c3_premove_observations_v1.csv','c3_premove_history_v1.csv.gz',
        'c3_registered_followup_status_v1.json','c3_registered_reclaim_registry_v1.json']
FIELDS=['ticker','name','asof','source_run_id','track','registered_cohort',
        'observed_close','floor_date','support_confirmed_at','support','atr14',
        'model_stop','nearest_pivot_high','resistance_pivot_date','resistance_confirmed_at',
        'research_stage','research_reason','research_score_not_final80',
        'near_close_price_lane','first_resistance_upside_at_entry_pct',
        'primary_retest_low','primary_retest_high','flex_retest_low','flex_retest_high',
        'continuation_low','continuation_high','buy_approved','orders_enabled',
        'regular_only_scope_certified','actual_turnover_certified','security_type_certified']

def read_bundle(path):
    p=Path(path)
    if p.is_dir():
        return {name:(p/name).read_bytes() for name in INPUTS}
    with ZipFile(p) as z:
        if not set(INPUTS)<=set(z.namelist()):raise ValueError('BUNDLE_FILES_MISSING')
        return {name:z.read(name) for name in INPUTS}

def sha(raw):return hashlib.sha256(raw).hexdigest()

def load_and_audit(raw):
    d={n:json.loads(raw[n]) for n in INPUTS if n.endswith('json')}
    scan=d['status.json'];stage=d['c3_premove_observation_status_v1.json']
    registered=d['c3_registered_followup_status_v1.json']
    registry=d['c3_registered_reclaim_registry_v1.json']
    asof=stage['asof']
    if not (scan['market_data_date']==registered['asof']==stage['asof']
            ==scan['reference_market_date'] and registered.get('capture_completed')
            and stage.get('observation_audit_completed')):raise ValueError('ASOF_OR_CAPTURE_MISMATCH')
    if str(stage['run_context']['run_id'])!=str(registered['run_context']['run_id']):
        raise ValueError('MIXED_SOURCE_RUNS')
    if registered['registry_id']!=registry['registry_id'] or registered['registered_count']!=len(registry['setups']):
        raise ValueError('REGISTRY_ID_OR_COUNT_MISMATCH')
    canonical=lambda x:sha(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
    registry_copy=dict(registry);registry_copy.pop('registry_id')
    if canonical(registry_copy)!=registry['registry_id']:raise ValueError('REGISTRY_CONTENT_TAMPERED')
    for item in registry['setups']:
        setup=dict(item);identity=setup.pop('record_id')
        if canonical(setup)!=identity:raise ValueError('SETUP_CONTENT_TAMPERED')
    for filename in ['c3_premove_observations_v1.csv','c3_premove_history_v1.csv.gz']:
        if sha(raw[filename])!=stage['output_sha256'][filename]:
            raise ValueError('STAGE_SHA256_MISMATCH_'+filename)
    observations=pd.read_csv(io.BytesIO(raw['c3_premove_observations_v1.csv']),dtype={'ticker':str})
    history=pd.read_csv(io.BytesIO(gzip.decompress(raw['c3_premove_history_v1.csv.gz'])),dtype={'ticker':str})
    if len(observations)!=stage['evaluated_ticker_count'] or int(observations.price_stage_pass.sum())!=stage['price_stage_case_count']:
        raise ValueError('SOURCE_STAGE_COUNTS_MISMATCH')
    if history.date.max()!=asof or history.date.gt(asof).any() or len(history)!=stage['history_rows']:
        raise ValueError('HISTORY_ASOF_OR_SIZE_MISMATCH')
    if observations.ticker.duplicated().any():raise ValueError('DUPLICATE_TICKER')
    frozen={x['ticker']:x['name'] for x in registry['setups']}
    if len(frozen)!=registered['registered_count']:raise ValueError('DUPLICATE_REGISTRY_TICKERS')
    return asof,stage,registered,observations,history,frozen

def observed_unbroken_pivot_high(b,close,asof,lookback=120):
    """Five-bar highs must have two following completed sessions; no future data."""
    if len(b)<5 or str(b.date.iloc[-1])!=asof:raise ValueError('UNVERIFIED_TAIL_DATE')
    choices=[]
    for i in range(max(2,len(b)-lookback-2),len(b)-2):
        high=float(b.high.iloc[i]);window=b.high.iloc[i-2:i+3]
        if high<=close or high!=float(window.max()) or not (window<high).any():continue
        if float(b.high.iloc[i+1:].max())>high:continue
        choices.append((high,str(b.date.iloc[i]),str(b.date.iloc[i+2])))
    return min(choices) if choices else (None,None,None)

def atr_14(b):
    prev=b.close.shift(1)
    tr=pd.concat([b.high-b.low,(b.high-prev).abs(),(b.low-prev).abs()],axis=1).max(axis=1)
    return float(tr.tail(14).mean())

def research_score(track,ret20,rsi,plan,close,atr):
    """Technical research ranking; deliberately NOT the user-facing final 80pt score."""
    retest=[x for x in plan.get('corridors',[]) if x['mode']=='SUPPORT_RETEST']
    continuation=[x for x in plan.get('corridors',[]) if x['mode']=='STRENGTH_CONFIRMATION']
    if not retest:return 0,False,0
    ref=max(x['high_krw'] for x in retest)
    distance=(close-ref)/close
    proximity=distance<=.04 and (close-ref)<=atr*1.25
    potential=100*(plan['overhead_krw']/ref-1)
    base=30 if track=='EARLY_LAUNCH' else 20
    momentum=10 if ret20>0 else max(-10,ret20/2)
    rsi_adj=6 if 40<=rsi<=65 else -4 if rsi<40 or rsi>75 else 0
    future_option=6 if continuation else 0
    rr_adj=min(12,3*max(x['first_resistance_net_r_at_high'] for x in retest))
    return round(base+momentum+rsi_adj+(15 if proximity else 0)+future_option+rr_adj,2),bool(proximity),round(potential,2)

def analyze(asof,stage,registered,obs,history,names):
    if stage['source_session_scope_certified'] or registered['regular_only_scope_verified']:
        raise ValueError('UNEXPECTED_SCOPE_CERTIFICATION_NEEDS_NEW_AUDIT')
    grouped={ticker:g.sort_values('date').reset_index(drop=True)
             for ticker,g in history.groupby('ticker',sort=False)}
    results=[];counts=Counter();run_id=str(stage['run_context']['run_id'])
    for r in obs.loc[obs.price_stage_pass].itertuples(index=False):
        row=dict.fromkeys(FIELDS,None)
        row.update(ticker=r.ticker,name=names.get(r.ticker,''),asof=asof,
                   source_run_id=run_id,track=r.track,registered_cohort=r.ticker in names,
                   observed_close=float(r.close),floor_date=r.floor_date,
                   support_confirmed_at=r.floor_confirmed_at,support=float(r.floor_low),
                   buy_approved=False,orders_enabled=False,regular_only_scope_certified=False,
                   actual_turnover_certified=False,security_type_certified=False,
                   research_score_not_final80=0,near_close_price_lane=False)
        try:
            b=grouped[r.ticker]
            if b.date.iloc[-1]!=asof or b.date.gt(asof).any() or b.date.duplicated().any():
                raise ValueError('INVALID_HISTORY_DATES')
            if len(b)<120 or r.floor_confirmed_at>asof or r.floor_date>=r.floor_confirmed_at:
                raise ValueError('UNCONFIRMED_FLOOR_OR_HISTORY')
            close=float(b.close.iloc[-1]);support=float(r.floor_low)
            if close!=float(r.close) or not support<=close:raise ValueError('CLOSE_OR_SUPPORT_MISMATCH')
            if b.loc[b.date>r.floor_date,'low'].min()<support:raise ValueError('FLOOR_ALREADY_BROKEN')
            atr=atr_14(b)
            if not math.isfinite(atr) or atr<=0:raise ValueError('INVALID_ATR')
            ceiling,high_date,high_confirmed=observed_unbroken_pivot_high(b,close,asof)
            row['atr14']=round(atr,4);row['nearest_pivot_high']=ceiling
            row['resistance_pivot_date']=high_date;row['resistance_confirmed_at']=high_confirmed
            if ceiling is None:raise ValueError('NO_CONFIRMED_UNBROKEN_OVERHEAD')
            # Modelled stop = 0.15 ATR below confirmed floor; not a broker stop order.
            stop=krx_round(support-.15*atr,'down')
            if stop<=0:raise ValueError('MODELED_STOP_NONPOSITIVE')
            plan=build_corridors(asof=asof,close=close,atr14=atr,
                confirmed_support=support,structural_stop=stop,
                verified_first_resistance=ceiling,
                support_confirmed_at=str(r.floor_confirmed_at),
                resistance_source='UNBROKEN_CONFIRMED_5BAR_PIVOT_HIGH',
                regular_only_certified=False)
            row['model_stop']=stop
            if plan['status']!='WATCH_CORRIDORS_RESEARCH_ONLY':raise ValueError(plan['reason'])
            for quote in plan['corridors']:
                if quote['mode']=='SUPPORT_RETEST' and quote['tier']=='PRIMARY_UP_TO_5PCT':prefix='primary_retest'
                elif quote['mode']=='SUPPORT_RETEST' and quote['tier']=='FLEX_UP_TO_8PCT':prefix='flex_retest'
                elif quote['mode']=='STRENGTH_CONFIRMATION' and quote['tier']=='PRIMARY_UP_TO_5PCT':prefix='continuation'
                else:continue
                row[prefix+'_low']=quote['low_krw'];row[prefix+'_high']=quote['high_krw']
            score,practical,potential=research_score(r.track,float(r.ret20),float(r.rsi14),plan,close,atr)
            row['research_score_not_final80']=score
            row['near_close_price_lane']=practical
            row['first_resistance_upside_at_entry_pct']=potential
            row['research_stage']=('GEOMETRY_NEAR_CLOSE_WATCH' if practical and potential>=5
                                   else 'GEOMETRY_ONLY_ENTRY_TOO_DISTANT_OR_REWARD_TOO_SMALL')
            row['research_reason']=('SOURCE_UNCERTIFIED_NO_BUY' if practical and potential>=5
                                    else 'PRICE_TOUCH_OR_MIN5PCT_UPSIDE_GATE_FAILED')
        except (ValueError,KeyError,IndexError,TypeError) as exc:
            row['research_stage']='NO_RESEARCH_CORRIDOR'
            row['research_reason']=str(exc)
        counts[row['research_stage']]+=1
        results.append(row)
    return results,counts

def run(input_path,output):
    raw=read_bundle(input_path)
    asof,stage,registered,obs,history,names=load_and_audit(raw)
    records,counts=analyze(asof,stage,registered,obs,history,names)
    if len(records)!=stage['price_stage_case_count']:
        raise ValueError('FROZEN_STAGE_COHORT_COUNT_CHANGED_REQUIRES_REVIEW')
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    tab=out/'c3_corridor_replay_v1.csv'
    with tab.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerows(records)
    cohort=[r for r in records if r['registered_cohort']]
    ranked=sorted([r for r in cohort if r['research_stage']=='GEOMETRY_NEAR_CLOSE_WATCH'],
                  key=lambda r:(r['research_score_not_final80'],r['first_resistance_upside_at_entry_pct'],r['ticker']),reverse=True)
    status=dict(schema=SCHEMA,asof=asof,source_run_id=str(stage['run_context']['run_id']),
         source_history_sha256=stage['output_sha256']['c3_premove_history_v1.csv.gz'],
         source_observation_sha256=stage['output_sha256']['c3_premove_observations_v1.csv'],
         evaluated_price_stage_count=len(records),price_lane_counts=dict(counts),
         frozen_registered_count=registered['registered_count'],
         frozen_stage_pass_count=len(cohort),
         registered_near_close_watch_count=len(ranked),
         research_top2=[{k:v for k,v in item.items() if k in FIELDS} for item in ranked[:2]],
         chart_and_sector_flow_awaiting_certification=True,trade_approved=False,
         orders_enabled=False,profitability_proven=False,regular_only_source_certified=False,
         actual_turnover_verified=False,observed_broker_fills=0,
         simulated_levels_not_live_trade_orders=True,csv_sha256=sha(tab.read_bytes()))
    (out/'c3_corridor_replay_v1_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    summary=['# C3 entry-corridor research — '+asof,'','**No confirmed BUY. Not regular-session-certified.**','',
             f"- Price-stage cases: {len(records)}; near-close research: {counts['GEOMETRY_NEAR_CLOSE_WATCH']}",
             f"- Registered 36 original cases: stage pass {len(cohort)}; practical research: {len(ranked)}",'',
             '| Research rank | Stock | Close | Model stop | First observed pivot high | Retest primary | Conditional continuation |',
             '|---|---|---:|---:|---:|---|---|']
    for i,r in enumerate(ranked[:2],1):
        p=f"{r['primary_retest_low']:,}–{r['primary_retest_high']:,}" if r['primary_retest_low'] else '—'
        c=f"{r['continuation_low']:,}–{r['continuation_high']:,}" if r['continuation_low'] else '—'
        summary.append(f"| {i} | {r['name']} ({r['ticker']}) | {r['observed_close']:,.0f} | {r['model_stop']:,} | {r['nearest_pivot_high']:,.0f} | {p} | {c} |")
    (out/'c3_corridor_replay_v1_mobile.md').write_text('\n'.join(summary)+'\n',encoding='utf-8')
    return status

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--input',required=True);a.add_argument('--output',required=True)
    args=a.parse_args();status=run(args.input,args.output)
    print(json.dumps({k:v for k,v in status.items() if k not in ('research_top2',)},ensure_ascii=False,indent=2))
    print('RESEARCH_TOP2',[(x['ticker'],x['name'],x['research_score_not_final80']) for x in status['research_top2']])
