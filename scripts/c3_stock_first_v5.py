#!/usr/bin/env python3
"""C3 v5 stock-first discovery, practical pullback and future breakout research.

Only original completed-day price bars; optional same-date declared participant data.
No historical P/L backtests, brokerage fills, live quotes, auto-orders or alerts.
"""
from __future__ import annotations
import argparse,csv,hashlib,json
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
from c3_stock_first_v4 import analyze as v4_analyze, quote, net_r
from c3_stock_first_v4 import load as original_load

SCHEMA='C3_STOCK_FIRST_V5_OPPORTUNITY_NO_TRADING'
RESEARCH_DATE='2026-10-30'
FLOW_COLUMNS={'ticker','asof','foreign_net_buy_krw','institution_net_buy_krw',
              'session','source','value_verified'}

def read_verified_flows(path,asof):
    """CSV-supplied flows can be displayed but NOT trusted to alter ranking."""
    if not path:return {},'NOT_SUPPLIED'
    f=pd.read_csv(path,dtype={'ticker':str,'asof':str,'source':str,'session':str,'value_verified':str})
    if not FLOW_COLUMNS<=set(f.columns):raise ValueError('FLOW_REQUIRED_COLUMNS_MISSING')
    if f['ticker'].duplicated().any() or (f['asof']!=asof).any():
        raise ValueError('FLOW_DUPLICATE_OR_ASOF_DATE_MISMATCH')
    if (f['session']!='KRX_REGULAR_ONLY').any():raise ValueError('FLOW_SESSION_NOT_REGULAR_ONLY')
    if not f['source'].str.fullmatch(r'(?:KRX_OFFICIAL|BROKER_VERIFIED_KRX)',na=False).all():
        raise ValueError('UNVERIFIED_FLOW_SOURCE')
    if not f['value_verified'].str.lower().eq('true').all():
        raise ValueError('UNVERIFIED_FLOW_VALUE')
    for col in ('foreign_net_buy_krw','institution_net_buy_krw'):
        v=pd.to_numeric(f[col],errors='coerce')
        if not np.isfinite(v).all():raise ValueError('NON_FINITE_FLOW_AMOUNT')
        f[col]=v
    return f.set_index('ticker')[['foreign_net_buy_krw','institution_net_buy_krw']].to_dict('index'),'DECLARED_ONLY_NOT_INDEPENDENTLY_AUDITED'

def trend_phase(row,bar):
    """Reflex rebound is not the same as a durable early uptrend."""
    c=bar.close.astype(float)
    close=float(c.iloc[-1]);r5=100*(close/float(c.iloc[-6])-1)
    r12=100*(close/float(c.iloc[-13])-1)
    ma10=float(c.tail(10).mean());ma20=float(c.tail(20).mean())
    prior20=float(c.iloc[-25:-5].mean())
    if r12<=-8 and r5>=6:return 'REFLEX_REBOUND',r12
    if r12<-6:return 'WEAK_12D_TREND',r12
    if r12>=2 and ma10>ma20 and ma20>prior20:
        return 'SUSTAINED_EARLY_LEADER',r12
    if row['track']=='PRE_BREAKOUT_BASE' and abs(r12)<8 and close>=ma20:
        return 'BASE_TO_BREAKOUT',r12
    return 'UNCONFIRMED_TREND',r12

def consecutive_participation(bar):
    b=bar.tail(25)
    v=b.volume.astype(float);c=b.close.astype(float)
    if len(b)<25 or (v<=0).any() or (c<=0).any():return None
    earlier=float((v.iloc[-25:-5]*c.iloc[-25:-5]).median())
    recent=float((v.tail(5)*c.tail(5)).median())
    return round(recent/earlier,3) if earlier>0 else None

def breakout_plan(row,bar,phase):
    """Watch future completed candle, then reprice next session: never buy now."""
    close=float(row['close']);atr=float(row['atr14'])
    if not 0<atr<=.1*close:
        return dict(breakout_state='BAD_ATR',breakout_trigger=None,
                    breakout_trigger_raw=None)
    previous_high=float(bar.high.astype(float).iloc[-21:-1].max())
    trigger=quote(max(close+.12*atr,previous_high+.12*atr),'up')
    stop=float(row['stop']);first=row.get('first_resistance')
    second=row.get('second_resistance')
    candidates=sorted(float(v) for v in (first,second)
       if v is not None and pd.notna(v) and float(v)>trigger)
    next_res=candidates[0] if candidates else None
    gap_atr=(trigger-close)/atr
    risk=(trigger-stop)/trigger
    if phase=='REFLEX_REBOUND':state='BLOCK_REBOUND_NOT_LEADER'
    elif phase=='WEAK_12D_TREND':state='WAIT_TREND_REPAIR'
    elif gap_atr>1.1:state='TRIGGER_TOO_FAR_NO_CHASE'
    elif risk>.095:state='PRIOR_STOP_TOO_DEEP_RESTRUCTURE_REQUIRED'
    elif next_res is None:state='FUTURE_CLOSE_BREAKOUT_OBSTACLE_UNOBSERVED'
    elif net_r(trigger,stop,next_res)<1.15:state='INSUFFICIENT_NEXT_OVERHEAD_SPACE'
    else:state='FUTURE_CLOSE_BREAKOUT_ELIGIBLE_WATCH'
    eligible=trigger if state in ('FUTURE_CLOSE_BREAKOUT_ELIGIBLE_WATCH',
       'FUTURE_CLOSE_BREAKOUT_OBSTACLE_UNOBSERVED') else None
    return dict(breakout_state=state,breakout_trigger=eligible,
       breakout_trigger_raw=trigger,breakout_next_obstacle=next_res,
       breakout_gap_atr=round(gap_atr,2),breakout_old_structure_risk_pct=round(100*risk,2),
       required_confirmation='FUTURE_COMPLETED_CLOSE_GE_TRIGGER_AND_RVOL20_GE_1_25_AND_CLOSE_TOP_35PCT_THEN_NEXT_SESSION_REPRICE',
       new_support_stop_required_after_breakout=True,
       chase_order_allowed=False,broker_fill=False)

def pullback_plan(row,phase,participation):
    low=row.get('pullback_low');hi=row.get('pullback_high')
    close=float(row['close']);atr=float(row['atr14']);stop=float(row['stop'])
    first=row.get('first_resistance')
    supply=row.get('overhead_supply','UNKNOWN')
    if low is None or hi is None or pd.isna(low) or pd.isna(hi):
        return dict(pullback_state='NO_VALID_PRICE_CORRIDOR',watch_low=None,watch_high=None,
           stop_krw=int(stop),first_obstacle_krw=int(first) if first is not None else None)
    lo=int(low);high=int(hi)
    risk=(high-stop)/high
    rr=net_r(high,stop,float(first)) if first is not None and pd.notna(first) else None
    width=(high-lo)/atr
    if phase=='REFLEX_REBOUND':state='BLOCK_REFLEX_REBOUND'
    elif phase=='WEAK_12D_TREND':state='WAIT_TREND_REPAIR'
    elif not stop<lo<=high<close:state='INVALID_PRICE_ORDER'
    elif risk>.08:state='WAIT_LOWER_RISK_PRICE'
    elif width<.15:state='TOO_NARROW_FOR_PRACTICAL_ENTRY'
    elif first is None:state='FIRST_OBSTACLE_UNOBSERVED_WATCH'
    elif first/close-1<.035:state='OVERHEAD_TOO_CLOSE_TO_LATEST_CLOSE'
    elif rr is not None and rr<1.15-1e-6:state='FIRST_OBSTACLE_TOO_CLOSE'
    elif supply=='HIGH_SUPPLY' and rr is not None and rr<1.5:
        state='PIVOT_HEAVY_SUPPLY_WAIT'
    elif row['rvol20']<.5:state='LOW_LAST_SESSION_PARTICIPATION_WAIT'
    elif participation is not None and participation<.55:
        state='DROPPING_VOLUME_PARTICIPATION_WAIT'
    else:state='PULLBACK_SETUP_WATCH'
    return dict(pullback_state=state,watch_low=lo,watch_high=high,
       stop_krw=int(stop),first_obstacle_krw=int(first) if first is not None else None,
       price_corridor_atr_width=round(width,2),risk_at_upper_pct=round(100*risk,2),
       first_obstacle_net_r_at_upper=round(rr,2) if rr is not None else None,
       no_automatic_limit_order=True,next_session_recheck_price_and_support=True)

def prioritize(row,phase,pull,breakout,participation,flow):
    strength=float(row['stock_strength_score100'])
    adjust={'SUSTAINED_EARLY_LEADER':8,'BASE_TO_BREAKOUT':4,
       'UNCONFIRMED_TREND':-3,'WEAK_12D_TREND':-12,'REFLEX_REBOUND':-30}[phase]
    pstate=pull['pullback_state'];bstate=breakout['breakout_state']
    practical=(18 if pstate=='PULLBACK_SETUP_WATCH' else
       13 if pstate=='FIRST_OBSTACLE_UNOBSERVED_WATCH' else
       5 if pstate in ('PIVOT_HEAVY_SUPPLY_WAIT','TOO_NARROW_FOR_PRACTICAL_ENTRY') else 0)
    if bstate=='FUTURE_CLOSE_BREAKOUT_ELIGIBLE_WATCH':practical=max(practical,13)
    if bstate=='FUTURE_CLOSE_BREAKOUT_OBSTACLE_UNOBSERVED':practical=max(practical,7)
    if row['rvol20']<.6:practical-=4
    if row.get('overhead_supply')=='HIGH_SUPPLY':practical-=5
    if participation is not None and participation>=1.25:practical+=4
    if participation is not None and participation<.7:practical-=3
    flow_state='UNAVAILABLE_NEUTRAL'
    if flow is not None:
        total=flow['foreign_net_buy_krw']+flow['institution_net_buy_krw']
        flow_state=('DECLARED_BOTH_NET_BUY_NOT_AUDITED' if total>0 and
            flow['foreign_net_buy_krw']>0 and flow['institution_net_buy_krw']>0 else
            'DECLARED_NET_SELL_NOT_AUDITED' if total<0 else 'DECLARED_MIXED_NOT_AUDITED')
    # Important: a user-supplied CSV can fake "value_verified". Zero flow
    # influence until independent source authentication is built.
    flow_points=0
    score=round(max(0,min(100,.77*strength+adjust+practical+flow_points)),2)
    if phase=='REFLEX_REBOUND':grade='REBOUND_REPAIR_ONLY'
    elif pstate=='PULLBACK_SETUP_WATCH' and score>=56:grade='PRIORITY_PULLBACK'
    elif bstate=='FUTURE_CLOSE_BREAKOUT_ELIGIBLE_WATCH' and score>=56:
        grade='PRIORITY_BREAKOUT'
    elif pstate=='FIRST_OBSTACLE_UNOBSERVED_WATCH' and score>=55:
        grade='OPEN_SKY_UNVERIFIED'
    elif score>=48:grade='SECONDARY_WATCH'
    else:grade='LOW_PRIORITY'
    return dict(opportunity_score_not_probability=score,priority_class=grade,
       stock_component_pct=round(.77*strength,2),trend_adjust_points=adjust,
       entry_component_points=round(practical,2),
       real_investor_flow_points=flow_points,investor_flow_state=flow_state)

def run(source,output,flow_csv=None):
    base,rows=v4_analyze(source,Path(output)/'v4_reference')
    obs,hist,master,names,evid,scan=original_load(source)
    if base['asof']!=RESEARCH_DATE or str(base['source_run_id'])!='41051723762':
        raise ValueError('FROZEN_OCT30_SOURCE_MISMATCH')
    by={t:g.sort_values('date').reset_index(drop=True) for t,g in hist.groupby('ticker')}
    flows,flow_scope=read_verified_flows(flow_csv,base['asof'])
    out=[]
    for x in rows:
        bar=by[x['ticker']]
        phase,r12=trend_phase(x,bar)
        part=consecutive_participation(bar)
        p=pullback_plan(x,phase,part)
        b=breakout_plan(x,bar,phase)
        q=prioritize(x,phase,p,b,part,flows.get(x['ticker']))
        out.append(dict(ticker=x['ticker'],name=x['name'],sector=x['sector'],
           track=x['track'],asof=base['asof'],close=x['close'],
           ma20=x['ma20'],ma60=x['ma60'],atr14=x['atr14'],
           rvol20=x['rvol20'],price_volume_participation_5d_to_prior20=part,
           price_volume_participation_is_not_investor_flow=True,
           return5_pct=x['r5_pct'],return12_pct=round(r12,2),
           return20_pct=x['r20_pct'],return60_pct=x['r60_pct'],
           phase=phase,stock_strength_score_not_probability=x['stock_strength_score100'],
           overhead_supply=x.get('overhead_supply','UNKNOWN'),
           resistance_pivot_date=x.get('resistance_pivot_date'),
           support=x['support'],support_confirmation=x['support_confirmation'],
           structure_stop=x['stop'],**p,**b,**q,
           official_regular_only_close_certified=False,ordinary_share_certified=False,
           actual_turnover_certified=False,investor_flow_present=bool(x['ticker'] in flows),
           source_run_id='41051723762',entry_modes_are_alternatives=True,
           buy_approved=False,orders_enabled=False))
    grades=['PRIORITY_PULLBACK','PRIORITY_BREAKOUT','OPEN_SKY_UNVERIFIED',
      'SECONDARY_WATCH','REBOUND_REPAIR_ONLY','LOW_PRIORITY']
    out.sort(key=lambda x:(grades.index(x['priority_class']),
       -x['opportunity_score_not_probability'],x['ticker']))
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    dest=root/'c3_stock_first_v5_ranked.csv'
    with dest.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(out[0]))
        w.writeheader();w.writerows(out)
    # Quoteable research Top2 requires an observed first resistance.
    # Open-sky stocks are a separate investigation, not unearned BUY entries.
    price_screen=[x for x in out if x['watch_low'] is not None
       and x['first_obstacle_krw'] is not None and x['phase']!='REFLEX_REBOUND'
       and x['priority_class'] in ('PRIORITY_PULLBACK','SECONDARY_WATCH')]
    price_screen.sort(key=lambda x:(x['priority_class']!='PRIORITY_PULLBACK',
       -x['opportunity_score_not_probability'],x['ticker']))
    chosen=price_screen[:2]
    open_sky=[x for x in out if x['priority_class']=='OPEN_SKY_UNVERIFIED']
    status=dict(schema=SCHEMA,asof=base['asof'],source_run_id='41051723762',
       scanned=base['universe_total'],price_stage_cases=base['price_stage_total'],
       structured_candidates=len(out),
       category_counts=dict(Counter(x['priority_class'] for x in out)),
       top2=chosen,top2_approved_buy_count=0,
       open_sky_without_measured_first_resistance=open_sky[:5],
       near_misses=out[:8],official_regular_only_close_certified=False,
       real_investor_flow_scope=flow_scope,real_investor_flows_supplied=bool(flow_csv),
       stock_selection_and_entries_only=True,no_profitability_backtests=True,
       score_not_probabilities=True,trade_approved=False,orders_enabled=False,
       csv_sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
    (root/'c3_stock_first_v5_status.json').write_text(
       json.dumps(status,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return status,out

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--verified-flow-csv')
    args=p.parse_args()
    z,rows=run(args.input,args.output,args.verified_flow_csv)
    print(json.dumps({k:v for k,v in z.items()
       if k not in ('top2','near_misses','open_sky_without_measured_first_resistance')},
       ensure_ascii=False,indent=2))
    print(pd.DataFrame(rows).head(15)[['ticker','name','priority_class',
       'opportunity_score_not_probability','close','watch_low',
       'watch_high','structure_stop','first_obstacle_krw',
       'breakout_state','breakout_trigger','rvol20']].to_string(index=False))
