#!/usr/bin/env python3
"""Produce price-only TOP2 decision sheets for charts: no orders, no backtests."""
import argparse,hashlib,json
from pathlib import Path
import pandas as pd

SCHEMA='C3_TOP2_PRACTICAL_ACTION_SHEET_V1_NO_ORDERS'

def prepare(row):
    close,lo,hi,stop,first=map(float,
        (row[k] for k in ('close','watch_low','watch_high','structure_stop','first_obstacle_krw')))
    if row['asof']!='2026-10-30' or not (0<stop<lo<=hi<close<first):
        raise ValueError('INVALID_ASOF_OR_STOP_WATCH_OBSTACLE')
    friction=.0065
    r=(first-hi*(1+friction))/(hi-stop+friction*hi)
    priority=row['priority_class']=='PRIORITY_PULLBACK' and row['pullback_state']=='PULLBACK_SETUP_WATCH'
    breakout=(int(row['breakout_trigger']) if pd.notna(row['breakout_trigger']) else None)
    return dict(ticker=row['ticker'],name=row['name'],
       close_asof_20261030_krw=int(close),
       pullback_watch_min_krw=int(lo),pullback_watch_max_krw=int(hi),
       structure_stop_study_krw=int(stop),first_obstacle_krw=int(first),
       upper_watch_below_close_pct=round(100*(close-hi)/close,2),
       lower_watch_below_close_pct=round(100*(close-lo)/close,2),
       structural_risk_lower_entry_pct=round(100*(lo-stop)/lo,2),
       structural_risk_upper_entry_pct=round(100*(hi-stop)/hi,2),
       hypothetical_to_first_obstacle_pct=round(100*(first/hi-1),2),
       estimated_net_r_to_first_obstacle=round(r,2),
       pullback_state=('RETEST_AND_COMPLETED_CLOSE_RECOVERY_WATCH' if priority
                       else 'RESISTANCE_SUPPLY_CLEARANCE_WAIT'),
       alternative_future_breakout_krw=breakout if priority else None,
       future_breakout_needs_completed_close_and_rvol125=bool(priority and breakout),
       alternative_modes_not_simultaneous_orders=True,
       price_touch_not_broker_fill=True,
       official_regular_only_price_certified=False,
       real_investor_flows_certified=False,
       buy_approved=False,orders_enabled=False)

def run(ranked,output):
    data=pd.read_csv(ranked,dtype={'ticker':str})
    if len(data)!=96 or data.ticker.duplicated().any():
        raise ValueError('ORIGINAL_96_RESEARCH_RANKING_MISSING')
    cases=[]
    for ticker in ('271560','026960'):
        match=data[data.ticker==ticker]
        if len(match)!=1:raise ValueError('CURRENT_TOP2_MISSING')
        cases.append(prepare(match.iloc[0].to_dict()))
    doc=dict(schema=SCHEMA,asof='2026-10-30',
       source_run_id='41051723762',top2=cases,
       ranked_sha256=hashlib.sha256(Path(ranked).read_bytes()).hexdigest(),
       risk_warning='Model stop not a guaranteed execution; gap/slippage possible',
       return_target_is_not_guaranteed=True,source_regular_session_uncertified=True,
       trade_approved=False,orders_enabled=False)
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    (root/'c3_top2_action_sheet_v1.json').write_text(
       json.dumps(doc,ensure_ascii=False,indent=2,allow_nan=False)+'\n',
       encoding='utf-8')
    return doc

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--ranked',required=True);p.add_argument('--output',required=True)
    a=p.parse_args()
    print(json.dumps(run(a.ranked,a.output)['top2'],ensure_ascii=False,indent=2))
