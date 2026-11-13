"""Matched entry comparison on an already frozen C3 cohort; never a live model.

Reuse the conservative daily execution engine. All methods share each original
structural stop, resistance, capital, fee, signal date and one-session validity.
The next-open price is a simulated execution price, never a signal-time quote.
Previously studied history is explicitly NOT a new independent holdout.
"""
import copy,hashlib,json,statistics
from collections import Counter,defaultdict
from pathlib import Path

MODELS=('ORIGINAL_LIMIT','CONDITIONAL_NEXT_OPEN','MA5_LIMIT','MA10_LIMIT','MA20_LIMIT')

def mean(xs):return statistics.mean(xs) if xs else None

def execute(model,base,bars,i,sessions,horizon,cutoff):
    from c3_dynamic_entry_v2 import evaluate_trade
    from first_pullback_v55 import down
    p=copy.deepcopy(base);day=bars[i]['date'];g=sessions.index(day)
    if g+3+horizon>=len(sessions) or sessions[g+3+horizon]>cutoff:return dict(status='CENSORED_COMMON_CLOCK',return_pct=None)
    if model=='CONDITIONAL_NEXT_OPEN':
        if i+1>=len(bars) or bars[i+1]['date']!=sessions[g+1]:return dict(status='CENSORED_MISSING_NEXT_SESSION',return_pct=None)
        opening=bars[i+1]['open']
        # evaluate_trade performs the same gap/support/R1 invalidation and
        # stop-first checks. This is the market-order execution adapter only.
        if opening<=p['stop']:return dict(status='CANCEL_GAP_BELOW_STOP',return_pct=0.,filled=False)
        p.update(low=p['stop'],high=opening)
    elif model.startswith('MA'):
        n=int(model[2:].split('_')[0]);level=down(statistics.mean(b['close'] for b in bars[i-n+1:i+1]))
        if not p['stop']<level<bars[i]['close'] or (p.get('resistance') is not None and level>=p['resistance']):
            return dict(status='NO_VALID_FROZEN_MA_PULLBACK_LEVEL_CASH',return_pct=0.,filled=False)
        p.update(low=level,high=level)
    elif model!='ORIGINAL_LIMIT':raise ValueError('UNKNOWN_MATCHED_ENTRY_MODEL')
    result=evaluate_trade(p,bars,i,sessions,validity=1,horizon=horizon,cutoff=cutoff)
    if result.get('filled') and result.get('return_pct') is not None and model=='CONDITIONAL_NEXT_OPEN' and result['entry_price']!=bars[i+1]['open']:
        raise ValueError('NEXT_OPEN_EXECUTION_ADAPTER_NOT_AT_OPEN')
    if result.get('filled') and result.get('return_pct') is not None:
        f=__import__('c3_dynamic_entry_v2').DEFAULT['fees'];e=result['entry_price'];b=(1+f['buy'])*(1+f['slippage_each_side']);s=(1-f['sell'])*(1-f['slippage_each_side'])
        risk=e*b-p['stop']*s
        result['initial_net_r1_rr']=(p['resistance']*s-e*b)/risk if p.get('resistance') is not None and risk>0 else None
    return result

def summarize(events,model,horizon):
    rows=[e['results'][model][str(horizon)] for e in events]
    done=[r for r in rows if r.get('return_pct') is not None];filled=[r for r in done if r.get('filled')]
    pct=lambda n,d:100*n/d if d else None
    return dict(opportunities=len(rows),complete=len(done),censored=len(rows)-len(done),fills=len(filled),
        fill_pct=pct(len(filled),len(done)),unfilled_pct=pct(sum(not r.get('filled') for r in done),len(done)),
        planned_capital_net_return_pct=mean([r['return_pct'] for r in done]),
        filled_only_net_return_pct=mean([r['return_pct'] for r in filled]),
        stop_pct_of_fills=pct(sum(r['status'].startswith('STOP') for r in filled),len(filled)),
        r1_pct_of_fills=pct(sum(bool(r.get('r1_hit_before_stop')) for r in filled),len(filled)),
        r2_pct_of_fills=pct(sum(bool(r.get('r2_path_hit')) for r in filled),len(filled)),
        mean_mfe_pct=mean([r['mfe_pct'] for r in filled]),mean_mae_pct=mean([r['mae_pct'] for r in filled]),
        mean_initial_net_r1_rr=mean([r['initial_net_r1_rr'] for r in filled if r.get('initial_net_r1_rr') is not None]),
        unfilled_missed_rally_mfe_pct=mean([r['missed_rally_mfe_pct'] for r in done if r.get('status')=='PASS_UNFILLED']),
        daily_sequence_ambiguous=sum(bool(r.get('entry_day_target_sequence_unknown')) for r in filled))

def run(allbars,indices,sessions,cutoff,cohort_path,out):
    from c3_watch_quality_audit_v1 import price_metrics
    from c3_selection_factors_v6 import regime
    from c3_dynamic_entry_v2 import DEFAULT
    raw=Path(cohort_path).read_bytes();source=json.loads(raw);cohort=source['C3_ORIGINAL'];grid={d:i for i,d in enumerate(sessions)}
    events=[];excluded=Counter();last={}
    for original in sorted(cohort,key=lambda e:(e['date'],e['ticker'])):
        t=original['ticker'];day=original['date'];bs=allbars.get(t,[]);by={b['date']:i for i,b in enumerate(bs)}
        if day not in by or day not in grid:excluded['FROZEN_SIGNAL_PRICE_UNAVAILABLE']+=1;continue
        i=by[day];p=original['plan'];b=bs[i]
        if grid[day]-last.get(t,-10000)<=20:excluded['SAME_TICKER_WITHIN_20_SESSIONS']+=1;continue
        if b['close']!=p['reference_close'] or b['segment']!=p['segment']:
            excluded['FROZEN_REFERENCE_PRICE_OR_SEGMENT_CHANGED']+=1;continue
        past=[]
        for x in reversed(bs[:i+1]):
            if x['segment']!=b['segment'] or not x.get('tradable',True):break
            past.append(x)
        past.reverse()
        if len(past)<65:excluded['CONTINUOUS_WARMUP_LT65']+=1;continue
        if p.get('known_on','9999')>day:raise ValueError('FROZEN_PLAN_USES_FUTURE_CONFIRMATION')
        last[t]=grid[day];metrics=price_metrics(past,day)
        results={m:{str(h):execute(m,p,bs,i,sessions,h,cutoff) for h in (5,10,20)} for m in MODELS}
        # Common complete-case comparison for every model; missing prices or
        # corporate-action boundaries cannot selectively improve one method.
        for h in ('5','10','20'):
            if any(results[m][h].get('return_pct') is None for m in MODELS):
                for m in MODELS:results[m][h]=dict(status='CENSORED_MATCHED_PATH',return_pct=None)
        market=next((ix for ix in indices.values() if day in ix),{})
        e=dict(ticker=t,name=original['name'],date=day,original_fold=original['fold'],
            period='REUSED_EARLIER_PERIOD' if original['fold']=='DEVELOPMENT' else 'REUSED_LATER_PERIOD',
            regime=original['regime'],price_metrics=metrics,original_plan=p,results=results)
        events.append(e)
    earlier=[e['price_metrics']['ma20_extension_pct'] for e in events if e['period']=='REUSED_EARLIER_PERIOD']
    q=statistics.quantiles(earlier,n=3,method='inclusive') if len(earlier)>=3 else None
    for e in events:
        x=e['price_metrics']['ma20_extension_pct'];e['extension_bucket']='LOW' if q and x<=q[0] else 'MIDDLE' if q and x<=q[1] else 'HIGH' if q else 'UNAVAILABLE'
    groups={'ALL':events}
    groups.update({s:[e for e in events if e['period']==s] for s in ('REUSED_EARLIER_PERIOD','REUSED_LATER_PERIOD')})
    groups.update({'EXTENSION_'+s:[e for e in events if e['extension_bucket']==s] for s in ('LOW','MIDDLE','HIGH')})
    groups.update({'REGIME_'+s:[e for e in events if e['regime']==s] for s in ('UP','SIDEWAYS','DOWN')})
    summary={k:{m:{str(h):summarize(es,m,h) for h in (5,10,20)} for m in MODELS} for k,es in groups.items()}
    result=dict(schema='C3_MATCHED_ENTRY_TIMING_AUDIT_V1',cutoff=cutoff,original_cohort_artifact_id='13920100040',
        original_cohort_sha256=hashlib.sha256(raw).hexdigest(),original_opportunities=len(cohort),reviewed=len(events),exclusions=dict(excluded),
        chronology_split_reused_from_pr104=True,independent_holdout=False,financial_original_pit_verified=False,
        survivorship_bias_removed=False,original_universe_scope='NOV11_NONBIO_SURVIVOR_CONDITIONED',
        extension_tertiles_from_earlier_period=q,extension_tertiles_are_descriptive_not_filters=True,
        costs=DEFAULT['fees'],capital_per_opportunity='100_PERCENT_PLANNED_CAPITAL_UNFILLED_CASH_ZERO',validity_sessions=1,
        next_open_scope='NEXT_OPEN_ONLY_IF_FROZEN_SUPPORT_AND_R1_GAP_GATES_REMAIN_VALID',
        summary=summary,profitable_model_promoted=False,selection_rules_changed=False,orders_enabled=False,telegram_requests=0,
        conclusion='EXPLORATORY_REUSED_COHORT_NOT_EVIDENCE_OF_CAUSAL_OR_INDEPENDENT_SUPERIORITY')
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n')
    (out/'events.json').write_text(json.dumps(events,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n')
    return result
