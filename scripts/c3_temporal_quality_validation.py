#!/usr/bin/env python3
"""Read-only PR87 shadow-cohort quality and date-purged temporal study.
No predictor promotion, operations, ledger, approvals, orders or live ranking.
"""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

FEATURES=("momentum_20d_pct","rvol_20d","ma20_extension_pct","ma20_vs_ma60_pct","stop_distance_pct")
MAX_UNEXPLAINED_DAILY_MOVE=.35
MIN_SPLIT_COUNT=20

def auc(y, x):
    pos=[v for label,v in zip(y,x) if label]
    neg=[v for label,v in zip(y,x) if not label]
    if not pos or not neg:return None
    return round(sum((a>b)+.5*(a==b) for a in pos for b in neg)/(len(pos)*len(neg)),4)

def feature_asof(bars,i):
    h=bars[:i+1]
    if len(h)<61:return None
    cl=[b['close'] for b in h]
    vol=[b['volume'] for b in h]
    if cl[-21]<=0 or sum(vol[-21:-1])<=0:return None
    ma20=sum(cl[-20:])/20
    ma60=sum(cl[-60:])/60
    return {
        'momentum_20d_pct':round((cl[-1]/cl[-21]-1)*100,3),
        'rvol_20d':round(vol[-1]/(sum(vol[-21:-1])/20),3),
        'ma20_extension_pct':round((cl[-1]/ma20-1)*100,4),
        'ma20_vs_ma60_pct':round((ma20/ma60-1)*100,4),
    }

def independently_reconstructed_stop_distance(bars,i):
    h=bars[:i+1]
    if len(h)<61:return None
    cl=[b['close'] for b in h]
    ma20=sum(cl[-20:])/20
    ma60=sum(cl[-60:])/60
    if not cl[-1]>ma20>ma60:return None
    tr=[max(b['high']-b['low'],abs(b['high']-h[j-1]['close']),abs(b['low']-h[j-1]['close'])) for j,b in enumerate(h) if j>0]
    atr=sum(tr[-14:])/14
    stop=min(b['low'] for b in h[-10:])
    resistance=max(b['high'] for b in h[-20:-1])
    candidates={'MA20_PULLBACK':ma20*.995,'CLOSE_MINUS_1ATR':cl[-1]-atr,'BREAKOUT_RETEST':resistance*1.005}
    entries=[]
    for model,price in candidates.items():
        if price<=stop or (price-stop)/price>.12:continue
        if model=='BREAKOUT_RETEST' and cl[-1]<=resistance*1.005:continue
        target=price+2*(price-stop) if model=='BREAKOUT_RETEST' else resistance
        if (target-price)/(price-stop)<2:continue
        entries.append(price)
    return round((max(entries)/stop-1)*100,4) if entries else None

def audit_segment(bars,start,end,market_index):
    flags=[]
    for j in range(max(1,start),end+1):
        if j>=len(bars):return ['NOT_ENOUGH_BARS']
        prev,cur=bars[j-1],bars[j]
        if prev['date'] not in market_index or cur['date'] not in market_index:
            flags.append('MARKET_DATE_NOT_FOUND')
            continue
        if market_index[cur['date']]!=market_index[prev['date']]+1:
            flags.append('TICKER_MARKET_SESSION_GAP')
        if prev['close']<=0 or cur['close']<=0 or abs(cur['close']/prev['close']-1)>MAX_UNEXPLAINED_DAILY_MOVE:
            flags.append('UNEXPLAINED_CLOSE_DISCONTINUITY')
    return sorted(set(flags))

def evaluate(source_rows,feature_cohort,min_market_sessions=120):
    by=defaultdict(list)
    days=set()
    seen=set()
    for r in source_rows:
        key=(str(r['ticker']),str(r['date']))
        if key in seen:raise ValueError('DUPLICATE_TICKER_DATE_SOURCE')
        seen.add(key)
        b={'ticker':key[0],'date':key[1]}
        for field in ('open','high','low','close','volume'):
            b[field]=float(r[field])
            if not math.isfinite(b[field]):raise ValueError('NONFINITE_SOURCE_BAR')
        if not (0<b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high'] and b['volume']>=0):
            raise ValueError('INVALID_SOURCE_BAR')
        by[key[0]].append(b)
        days.add(key[1])
    days=sorted(days)
    market_index={d:i for i,d in enumerate(days)}
    for ticker in by:by[ticker].sort(key=lambda b:b['date'])
    seen_events=set()
    last_event_index={}
    events=[]
    for e in feature_cohort.get('events',[]):
        ticker,date=str(e['ticker']),str(e['date'])
        key=(ticker,date)
        if key in seen_events:raise ValueError('DUPLICATE_EVENT')
        seen_events.add(key)
        bars=by.get(ticker,[])
        i=next((i for i,b in enumerate(bars) if b['date']==date),None)
        if i is not None:
            prev=last_event_index.get(ticker)
            if prev is not None and i-prev<=20:
                raise ValueError('OVERLAPPING_TICKER_20_SESSIONS')
            last_event_index[ticker]=i
        if i is None or i<60:
            events.append({'ticker':ticker,'date':date,'asof_quality':['INSUFFICIENT_ASOF_BARS'],'horizons':{}})
            continue
        f=e.get('features',{})
        expected=feature_asof(bars,i)
        reasons=audit_segment(bars,i-60,i,market_index)
        if expected is None or any(k not in f or abs(float(f[k])-v)>.001 for k,v in (expected or {}).items()):
            reasons.append('ASOF_FEATURE_MISMATCH')
        stop_distance=f.get('stop_distance_pct')
        if not isinstance(stop_distance,(int,float)) or not math.isfinite(stop_distance):
            reasons.append('STOP_DISTANCE_NONFINITE')
        else:
            reconstructed=independently_reconstructed_stop_distance(bars,i)
            if reconstructed is None:reasons.append('ASOF_ENTRY_MODEL_MISSING')
            elif abs(float(stop_distance)-reconstructed)>.001:reasons.append('ASOF_STOP_DISTANCE_MISMATCH')
        record={'ticker':ticker,'date':date,'features':f,'asof_quality':sorted(set(reasons)),'horizons':{}}
        for h in (5,10,20):
            k=str(h)
            if i+h>=len(bars):
                record['horizons'][k]={'quality':'CENSORED','maturity_date':None}
                continue
            maturity=bars[i+h]['date']
            outcome_flags=audit_segment(bars,i+1,i+h,market_index)
            ret=round((bars[i+h]['close']/bars[i]['close']-1)*100,4)
            old=e.get('outcomes',{}).get(k,{})
            if old.get('status')!='OBSERVED_EXPLORATORY' or old.get('close_return_pct') is None or abs(ret-float(old['close_return_pct']))>.001:
                outcome_flags.append('OUTCOME_MISMATCH')
            quality='QC_VALID_EXPLORATORY' if not (reasons or outcome_flags) else 'QC_EXCLUDED'
            record['horizons'][k]={'quality':quality,'maturity_date':maturity,
                'reasons':sorted(set(reasons+outcome_flags)),'positive_close':ret>0,'close_return_pct':ret}
        events.append(record)
    groups={}
    for h in (5,10,20):
        k=str(h)
        valid=[e for e in events if e['horizons'].get(k,{}).get('quality')=='QC_VALID_EXPLORATORY']
        original=sum(e['horizons'].get(k,{}).get('quality') not in ('CENSORED',None) for e in events)
        dates=sorted({e['date'] for e in events if e['horizons'].get(k,{}).get('quality')!='CENSORED'})
        cutoff=dates[len(dates)//2] if dates else None
        train=[e for e in valid if cutoff and e['date']<cutoff and e['horizons'][k]['maturity_date']<cutoff]
        test=[e for e in valid if cutoff and e['date']>=cutoff]
        stats={}
        for field in FEATURES:
            result={'status':'BLOCKED_INSUFFICIENT_MATURED_HOLDOUT','train_n':len(train),'test_n':len(test),'auc':None}
            if len(train)>=MIN_SPLIT_COUNT and len(test)>=MIN_SPLIT_COUNT:
                direction=auc([e['horizons'][k]['positive_close'] for e in train],[float(e['features'][field]) for e in train])
                test_auc=auc([e['horizons'][k]['positive_close'] for e in test],[float(e['features'][field]) for e in test])
                if direction is not None and test_auc is not None:
                    sign=1 if direction>=.5 else -1
                    result={'status':'TEMPORAL_DIAGNOSTIC_ONLY','train_n':len(train),'test_n':len(test),
                        'train_direction':'HIGH' if sign==1 else 'LOW',
                        'auc':auc([e['horizons'][k]['positive_close'] for e in test],[sign*float(e['features'][field]) for e in test]),
                        'feature_provenance':'ASOF_PRICE_AND_VOLUME_UNCERTIFIED','approved_as_predictor':False}
            stats[field]=result
        groups[k]={'pr87_original_observed':original,'qc_valid':len(valid),'qc_excluded':original-len(valid),
            'positive_qc_valid':sum(e['horizons'][k]['positive_close'] for e in valid),
            'split_date':cutoff,'train_matured_before_split':len(train),
            'test_after_split':len(test),'auc_by_feature':stats}
    common=[e for e in events if all(e['horizons'].get(str(h),{}).get('quality')=='QC_VALID_EXPLORATORY' for h in (5,10,20))]
    continuation={'common_quality_valid_20':len(common)}
    for h in (5,10,20):
        continuation[f'up_{h}d']=sum(e['horizons'][str(h)]['positive_close'] for e in common)
    for h in (5,10):
        continuation[f'up_{h}d_then_up_20d']=sum(e['horizons'][str(h)]['positive_close'] and e['horizons']['20']['positive_close'] for e in common)
    continuation['up_all_5_10_20d']=sum(all(e['horizons'][str(h)]['positive_close'] for h in (5,10,20)) for e in common)
    return {'schema':'C3_TEMPORAL_QUALITY_VALIDATION_V1',
        'market_sessions':len(days),'events_input':len(feature_cohort.get('events',[])),
        'unique_tickers':len({e['ticker'] for e in events}),
        'asof_qc_excluded':sum(bool(e['asof_quality']) for e in events),
        'future_outcomes_never_used_for_asof_features':True,
        'same_ticker_20_session_lockout_unchanged':True,
        'horizon_groups':groups,'continuation_common20':continuation,'events':events,
        'minimum_market_sessions_met':len(days)>=min_market_sessions,
        'source_quality_certified':False,'corporate_actions_certified':False,
        'financial_pit':'BLOCKED_UNVERIFIED','benchmark_relative_strength':'BLOCKED_NO_ASOF_INDEX',
        'foreign_institutional_flow':'BLOCKED_NO_ASOF_FLOW',
        'operational_top2_same_date':'BLOCKED_NO_MATCHING_SNAPSHOT',
        'feature_weights_changed':False,'operational_top2_changed':False,
        'ledger_changed':False,'trading_approved':False,'decision':'CASH',
        'predictor_promotion':'BLOCKED_NO_NEW_INDEPENDENT_PIT_VALIDATION'}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--end',required=True)
    p.add_argument('--cohort',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    from official_krx_120d_replay import history,weekdays
    rows,_=history(a.root,weekdays(a.end,160))
    result=evaluate(rows,json.loads(a.cohort.read_text(encoding='utf-8')))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('C3_TEMPORAL_QC',json.dumps({k:v for k,v in result.items() if k not in ('events','horizon_groups')},ensure_ascii=False))

if __name__=='__main__':main()
