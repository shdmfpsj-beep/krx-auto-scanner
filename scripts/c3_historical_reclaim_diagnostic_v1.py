#!/usr/bin/env python3
"""Selected-36 survivor-biased historical *diagnostic*, not investable backtest.

The 36 names were selected on 2026-10-29. Replaying them over older dates has
survivorship/lookahead UNIVERSE BIAS, even when each signal's prices are as-of.
No regular-session-only source proof, actual broker fills or BUY approval.
"""
from __future__ import annotations
import argparse,csv,gzip,hashlib,io,json,math
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
import numpy as np
import pandas as pd
from c3_entry_corridor_v1 import build_corridors
from c3_forward_watch_v2 import recovery_state
from practical_entry_quotes_v619 import krx_round

FILES=['c3_registered_followup_status_v1.json',
       'c3_registered_reclaim_registry_v1.json',
       'c3_registered_followup_history_v1.csv.gz']
SCHEMA='C3_SELECTED_36_HISTORICAL_RECLAIM_DIAGNOSTIC_V1_NO_BUY'
FEE=.0065

def pivot_floor(low,dates,i):
    # A 5-bar pivot at j requires both j+1 and j+2 already completed by i.
    for j in range(i-2,max(2,i-15)-1,-1):
        w=low[j-2:j+3];v=low[j]
        if (len(w)==5 and v==w.min() and (w>v).any()
                and low[j+1:i+1].min()>=v):
            return float(v),str(dates[j+2])
    return None

def first_overhead_high(high,close,i):
    values=[]
    for j in range(max(2,i-121),i-1):
        v=high[j]
        if v<=close or len(high[j-2:j+3])!=5:continue
        w=high[j-2:j+3]
        if (v==w.max() and (w<v).any() and
                high[j+1:i+1].max()<=v):
            values.append(v)
    return float(min(values)) if values else None

def model_return(opens,highs,lows,closes,entry_i,entry,stop,target,hold):

    if any(opens[j]<=0 or highs[j]<=0 or lows[j]<=0 or closes[j]<=0
           for j in range(entry_i,entry_i+hold)):
        raise ValueError('UNTRADEABLE_ZERO_OHLC_IN_EXIT_HORIZON')
    stop_hit=False;target_hit=False;exit_price=None;reason='TIME_EXIT'
    for j in range(entry_i,entry_i+hold):
        o,h,l=opens[j],highs[j],lows[j]
        if o<=stop:
            exit_price=o;stop_hit=True;reason='GAP_STOP_AT_OPEN';break
        if l<=stop:
            exit_price=stop;stop_hit=True;reason='STOP_FIRST_IF_BOTH';break
        if h>=target:
            exit_price=target;target_hit=True;reason='TARGET_FIRST_RESISTANCE';break
    if exit_price is None:exit_price=closes[entry_i+hold-1]
    net_pct=100*(float(exit_price)/float(entry)-1-FEE)
    risk=entry-stop+FEE*entry
    net_r=(float(exit_price)-entry-FEE*entry)/risk
    return dict(net_pct=round(net_pct,4),net_r=round(net_r,4),
                win=net_pct>0,stop_hit=stop_hit,target_hit=target_hit,
                exit_reason=reason)

def read_artifact(path):
    p=Path(path)
    if p.is_dir():raw={k:(p/k).read_bytes() for k in FILES}
    else:
        with ZipFile(p) as z:raw={k:z.read(k) for k in FILES}
    meta=json.loads(raw[FILES[0]]);reg=json.loads(raw[FILES[1]])
    if (meta['registry_id']!=reg['registry_id'] or
        meta['registered_count']!=36 or meta['asof']!='2026-10-30'):
        raise ValueError('FROZEN_36_OR_SOURCE_ASOF_WRONG')
    if hashlib.sha256(raw[FILES[2]]).hexdigest()!=meta['output_sha256'][FILES[2]]:
        raise ValueError('FROZEN_HISTORY_HASH_MISMATCH')
    df=pd.read_csv(io.BytesIO(gzip.decompress(raw[FILES[2]])),dtype={'ticker':str})
    if df.ticker.nunique()!=36 or len(df)!=meta['history_rows']:
        raise ValueError('FROZEN_HISTORY_COUNT_MISMATCH')
    return df,meta,reg

def run(source,output,from_date='2025-11-01',through_date='2026-09-30'):
    df,meta,reg=read_artifact(source)
    rows=[];diagnostics=Counter()
    names={x['ticker']:x['name'] for x in reg['setups']}
    for ticker,b in df.groupby('ticker',sort=True):
        b=b.sort_values('date').reset_index(drop=True)
        dates=b['date'].to_numpy(str);o=b.open.to_numpy(float)
        h=b.high.to_numpy(float);l=b.low.to_numpy(float)
        c=b.close.to_numpy(float);v=b.volume.to_numpy(float)
        if np.any(~np.isfinite(np.column_stack((o,h,l,c,v)))):
            raise ValueError('NONFINITE_BARS')
        n=len(b);last_taken=-100
        prev=np.r_[c[0],c[:-1]]
        tr=np.maximum(h-l,np.maximum(abs(h-prev),abs(l-prev)))
        invalid=((o<=0)|(h<=0)|(l<=0)|(c<=0)|(v<=0)
            |(l>np.minimum(o,c))|(h<np.maximum(o,c)))
        for i in range(125,n-12):
            date=dates[i]
            if date<from_date or date>through_date or i<=last_taken:continue
            diagnostics['signals_evaluated']+=1
            if np.any(invalid[max(0,i-119):i+1]):
                diagnostics['invalid_asof_120bar_price_prefix']+=1
                continue
            floor=pivot_floor(l,dates,i)
            if floor is None:continue
            overhead=first_overhead_high(h,c[i],i)
            if overhead is None:continue
            atr=float(tr[i-13:i+1].mean())
            if atr<=0 or not math.isfinite(atr) or floor[0]-.15*atr<=0:continue
            stop=krx_round(floor[0]-.15*atr,'down')
            if stop<=0:continue
            plan=build_corridors(asof=date,close=float(c[i]),atr14=atr,
                confirmed_support=floor[0],structural_stop=stop,
                verified_first_resistance=overhead,support_confirmed_at=floor[1],
                resistance_source='PREFIX_5BAR_UNBROKEN_PIVOT')
            primary=next((p for p in plan.get('corridors',[])
                if p['mode']=='SUPPORT_RETEST' and
                p['tier']=='PRIMARY_UP_TO_5PCT'),None)
            if primary is None:continue
            high_zone=primary['high_krw']
            if ((c[i]-high_zone)/c[i]>.04 or c[i]-high_zone>1.25*atr
                    or overhead/high_zone-1<.05):continue
            diagnostics['historic_near_watch']+=1
            d1=i+1;d2=i+2
            if invalid[d1] or invalid[d2]:
                diagnostics['untradeable_d1_or_d2_ohlcv_censored']+=1
                continue
            if (l[d1]<=stop or o[d1]<=stop or
                o[d1]<primary['low_krw'] or
                o[d1]>c[i]+min(.5*atr,.035*c[i])):
                diagnostics['d1_gap_or_stop_canceled']+=1
                continue
            if l[d1]>primary['high_krw'] or h[d1]<primary['low_krw']:
                diagnostics['d1_zone_not_touched']+=1
                continue
            diagnostics['d1_price_contacts_no_stop']+=1
            s=dict(asof=date,close=float(c[i]),atr14=atr,
              support=floor[0],stop=stop,watch_low=primary['low_krw'],
              watch_high=primary['high_krw'])
            dbar=dict(date=dates[d1],open=o[d1],high=h[d1],
              low=l[d1],close=c[d1],volume=v[d1])
            confirmed=(recovery_state(s,dbar)=='STRONG_CLOSE_CONFIRMED_WATCH_D2')
            span=h[d1]-l[d1]
            moderate=bool(span>0 and c[d1]>max(o[d1],floor[0],stop)
                and c[d1]>=l[d1]+.58*span)
            if confirmed:diagnostics['strong_reclaim_d1_confirmed']+=1
            if moderate:diagnostics['moderate_reclaim_d1_confirmed']+=1
            entry=o[d2]
            if entry<=stop or entry>c[d1]+.35*atr or entry<c[d1]-.30*atr:
                diagnostics['d2_gap_stop_rejected']+=1
                continue
            risk=(entry-stop)/entry
            rr=(overhead-entry*(1+FEE))/(entry-stop+entry*FEE)
            if not 0<risk<=.08 or rr<2:
                diagnostics['d2_risk_or_2r_rejected']+=1
                continue
            diagnostics['loose_paper_d2_eligible']+=1
            if confirmed:diagnostics['strict_paper_d2_eligible']+=1
            if moderate:diagnostics['moderate_paper_d2_eligible']+=1
            for hold in (5,10):
                if np.any(invalid[d2:d2+hold]):
                    diagnostics['untradeable_exit_horizon_censored_'+str(hold)]+=1
                    continue
                z=model_return(o,h,l,c,d2,entry,stop,overhead,hold)
                models=['CONTACT_ONLY']
                if moderate:models.append('MODERATE_RECOVERY')
                if confirmed:models.append('STRICT_RECOVERY')
                for model in models:
                    rows.append(dict(ticker=ticker,name=names[ticker],
                      signal_date=date,d1_date=dates[d1],d2_date=dates[d2],
                      market_partition='EARLY' if date<'2026-06-01' else 'LATE',
                      policy=model,hold=hold,asof_close=float(c[i]),
                      observed_support=floor[0],stop=stop,
                      first_resistance=overhead,watch_low=primary['low_krw'],
                      watch_high=high_zone,d1_confirmed_reclaim=confirmed,
                      entry_open_d2=entry,entry_net_R_to_first_resistance=round(rr,3),
                      **z,source_scope='AGGREGATOR_UNCERTIFIED',
                      price_contact_is_not_broker_fill=True,buy_approved=False))
            # Non-overlap per ticker for ten future holding sessions.
            last_taken=d2+9
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    f=out/'c3_historical_reclaim_diagnostic_v1.csv'
    if rows:
        with f.open('w',newline='',encoding='utf-8-sig') as dest:
            w=csv.DictWriter(dest,fieldnames=list(rows[0]))
            w.writeheader();w.writerows(rows)
    else:f.write_text('',encoding='utf-8')
    results=[]
    for policy in ('CONTACT_ONLY','MODERATE_RECOVERY','STRICT_RECOVERY'):
        for hold in (5,10):
            for partition in ('EARLY','LATE','ALL'):
                sub=[x for x in rows if x['policy']==policy and x['hold']==hold
                  and (partition=='ALL' or x['market_partition']==partition)]
                n=len(sub);values=[x['net_pct'] for x in sub]
                wins=sum(x['win'] for x in sub)
                pos=sum(x['net_pct'] for x in sub if x['net_pct']>0)
                neg=-sum(x['net_pct'] for x in sub if x['net_pct']<0)
                results.append(dict(policy=policy,hold=hold,partition=partition,
                  simulated_cases=n,net_win_rate_pct=round(wins/n*100,2) if n else None,
                  mean_net_return_pct=round(sum(values)/n,3) if n else None,
                  median_net_return_pct=round(float(np.median(values)),3) if n else None,
                  simulated_profit_factor=round(pos/neg,3) if neg else None,
                  worst_net_return_pct=round(min(values),3) if n else None))
    status=dict(schema=SCHEMA,source_run_id=meta['run_context']['run_id'],
      historical_cohort_selected_on='2026-10-29',history_end='2026-10-30',
      date_start=from_date,date_end=through_date,
      signals=len({(x['ticker'],x['signal_date']) for x in rows}),
      diagnostics=dict(diagnostics),results=results,
      methodology='D2_OPEN_SIMULATED_NOT_BROKER_FILLS; FIRST_RESISTANCE_TARGET; STOP_FIRST_SAME_BAR; COST_0.65PCT; 5_OR_10_BARS',
      major_bias='OCT29_SELECTED_36_STOCK_COHORT_USED_FOR_PAST_DATES; SURVIVORSHIP_AND_LOOKAHEAD_UNIVERSE_BIAS',
      regular_only_source_verified=False,market_regime_validated=False,
      strategy_profitability_proven=False,actual_broker_fills=0,
      trade_approved=False,orders_enabled=False,
      csv_sha256=hashlib.sha256(f.read_bytes()).hexdigest())
    (out/'c3_historical_reclaim_diagnostic_v1_status.json').write_text(
      json.dumps(status,ensure_ascii=False,indent=2,allow_nan=False)+'\n',
      encoding='utf-8')
    return status

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--from-date',default='2025-11-01')
    parser.add_argument('--through-date',default='2026-09-30')
    args=parser.parse_args()
    status=run(args.input,args.output,args.from_date,args.through_date)
    print(json.dumps(dict(diagnostics=status['diagnostics'],
      results=[x for x in status['results'] if x['partition']=='ALL']),
      ensure_ascii=False,indent=2))
