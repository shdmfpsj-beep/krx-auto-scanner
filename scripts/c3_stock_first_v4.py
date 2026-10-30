#!/usr/bin/env python3
"""C3 stock-first v4 -- frozen Oct 30 research-only stock ranking / practical price zones.

No backtests, broker orders, alleged foreign/institution flows or live price data.
Prices are dated OHLCV *research*, not official regular-only KRX verification.
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json, math, zipfile
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
from c3_stock_first_v3 import source as _load_existing, sectors_now as _sectors_existing, evaluate as _evaluate_existing, clip

def load(path):
    scan,obs,history,master,names,evidence=_load_existing(path)
    return obs,history,master,names,evidence,scan

def group_strength(obs,master):
    return _sectors_existing(obs,master)

def score_one(ticker,obsrow,b,name,sector,evidence,sector_table):
    x=_evaluate_existing(ticker,b,obsrow,name,sector,evidence,sector_table)
    if x is None:return None
    s=sector_table.get(str(sector))
    known=s is not None and s['count']>=5
    return dict(x,
      ma60=round(float(b.close.astype(float).tail(60).mean()),2),
      r5_pct=x['return5_pct'],r20_pct=x['return20_pct'],
      r60_pct=x['return60_pct'],
      median20_close_volume_proxy_krw=x['turnover_proxy_median20_krw'],
      sector5_pct=round(float(s['r5']),2) if known else None,
      sector_coverage=int(s['count']) if known else 0,
      distance_ma20_atr=round((x['close']-x['ma20'])/x['atr14'],3),
      stop=x['stop_krw'],first_resistance=x['first_resistance_krw'],
      second_resistance=x['second_resistance_krw'],
      support_confirmation=x['confirmed_at'])


SCHEMA='C3_STOCK_FIRST_V4_PRICE_RESEARCH_NO_ORDERS'
COST=.0065

def tick(p):
    if not math.isfinite(float(p)) or p <= 0:raise ValueError('INVALID_PRICE')
    return 1 if p<2000 else 5 if p<5000 else 10 if p<20000 else 50 if p<50000 else 100 if p<200000 else 500 if p<500000 else 1000

def quote(p,mode='down'):
    if not math.isfinite(float(p)) or p<=0:raise ValueError('INVALID_PRICE')
    # Search the actual grid, including price-step transitions.
    if mode=='down':
        q=int(math.floor(p))
        while q>0 and q%tick(q):q-=1
    elif mode=='up':
        q=int(math.ceil(p))
        while q%tick(q):q+=1
    else:raise ValueError('UNKNOWN_QUOTE_SIDE')
    return q

def net_r(entry,stop,res):
    return (res-entry*(1+COST))/(entry-stop+COST*entry)

def ceiling_by_r(res,stop,min_r):
    return (res+min_r*stop)/((1+min_r)*(1+COST))

def score_strength(row,peer20,peer5):
    """Score the STOCK separately from whether today's price is affordable."""
    close=row['close'];ma20=row['ma20'];ma60=row['ma60'];
    r5=row['r5_pct'];r20=row['r20_pct'];r60=row['r60_pct']
    vratio=row['rvol20']
    # Recent upward trend plus sustained base; reject stale one-day spikes.
    trend= (10 if close>ma20 else 0)+(9 if ma20>ma60 else 0)+(7 if r20>3 else 0)+(4 if r60>0 else 0)
    relative=(12*clip((r20-peer20+3)/15,0,1)+6*clip((r5-peer5+1)/7,0,1))
    impulse=(8*clip((r5+1)/7,0,1)+7*clip((r20+2)/15,0,1))
    # A 1-day RVOL near 1 is not rejection if the 5-day participation holds.
    participation=(7*clip(vratio/1.5,0,1)+5*clip(row['median20_close_volume_proxy_krw']/1.2e10,0,1))
    sector=(9*clip((row['sector5_pct']+1)/7,0,1) if row['sector_coverage']>=5 and pd.notna(row['sector5_pct']) else 0)
    stage=6 if row['track']=='EARLY_LAUNCH' else 3 if row['track']=='PRE_BREAKOUT_BASE' else 0
    penalty= (min(12,max(0,-r60-10)*.35)
       +min(8,max(0,r20-28)*.45)
       +min(9,max(0,row['distance_ma20_atr']-1.5)*4)
       +(5 if vratio<.5 else 0))
    raw=trend+relative+impulse+participation+sector+stage-penalty
    return round(float(clip(raw,0,100)),1),dict(trend=round(trend,2),relative=round(relative,2),
       impulse=round(impulse,2),participation=round(participation,2),sector=round(sector,2),
       stage=stage,penalty=round(penalty,2))

def overhead_supply_pressure(resistance, history):
    """Last dated 120-bar pivot supply evidence, not order-book flow."""
    blank=dict(overhead_supply='UNKNOWN',pivot_relative_volume=None,
        pivot_close_position=None,resistance_pivot_date=None)
    if not resistance:return blank
    b=history.tail(120).reset_index(drop=True)
    exact=b.index[b.high.astype(float)==float(resistance)].tolist()
    if not exact:return dict(blank,overhead_supply='PIVOT_NOT_IN_RECENT120')
    j=exact[-1];p=b.iloc[j];h=float(p.high);l=float(p.low)
    prev=b.volume.iloc[max(0,j-20):j].astype(float)
    med=float(prev.median()) if len(prev) else 0
    rv=float(p.volume)/med if med>0 else None
    pos=(float(p.close)-l)/(h-l) if h>l else .5
    flag=('HIGH_SUPPLY' if rv is not None and rv>=1.6 and pos<.4
          else 'MODERATE_SUPPLY' if rv is not None and rv>=1.2 and pos<.55
          else 'LOW_CONFIRMED_SELL_PRESSURE')
    return dict(overhead_supply=flag,pivot_relative_volume=round(rv,2) if rv is not None else None,
                pivot_close_position=round(pos,2),resistance_pivot_date=str(p.date))

def design_entries(row,history):
    """Two ALTERNATIVE lanes, never simultaneous averaging orders.

    Pullback zone may clear the FIRST overhead obstacle at 1.15R net, while a
    target beyond it must be separately observed. No mandatory 2R-at-first rule.
    The momentum lane is a FUTURE conditional setup, not a market order today.
    """
    c=float(row['close']);atr=float(row['atr14']);stop=int(row['stop']);support=float(row['support'])
    first=row['first_resistance'];second=row['second_resistance']
    hi20=float(history.high.iloc[-21:-1].max())
    pivot_gap=first-c if first else None
    if not all(math.isfinite(v) and v>0 for v in (c,atr,support,stop)) or not stop<support<=c:
        return dict(price_lane='STRUCTURE_RECHECK',reason='INVALID_STOP_OR_SUPPORT',pullback_low=None,pullback_high=None,breakout_trigger=None)
    # A close-biased accessible pullback: approx 0.2 to 1.0 ATR below close.
    floor=max(support+.15*atr,c-.95*atr,stop+2*tick(stop))
    cap=min(c-.12*atr,support+1.85*atr,stop/.92)
    if first and first>c:
        # First overhead is an *obstacle*, not a blanket compulsory +2R exit.
        cap=min(cap,ceiling_by_r(first,stop,1.15))
    low=quote(floor,'up') if floor>0 else None
    high=quote(cap,'down') if cap>0 else None
    if low is None or high is None or low>high or high<=stop:
        low=high=None
    contact_r=round(net_r(high,stop,first),2) if high and first else None
    # A meaningful price range needs at least 3 correct minimum quote steps or 0.12 ATR.
    if low and high-low<max(3*tick(high),.12*atr):
        price_grade='LIMIT_TOO_NARROW_WAIT'
    elif not first:price_grade='NO_VERIFIED_OVERHEAD_WAIT'
    elif first/c-1<.025:price_grade='FIRST_RESISTANCE_TOO_NEAR'
    elif row['r20_pct']<-7 or row['r60_pct']<-20:price_grade='COUNTERTREND_RECOVERY_WATCH'
    elif row['rvol20']<.55:price_grade='THIN_RECENT_VOLUME_WAIT'
    else:price_grade='PULLBACK_WATCH'
    if low is None:price_grade='PULLBACK_GEOMETRY_UNAVAILABLE'
    # Breakout must occur in FUTURE on a *completed daily candle*, with
    # >=1.25x completed-session volume, high close position and next-day check.
    # No immediate entry from the historical 10/30 close.
    breakout=quote(max(hi20+.12*atr,c+.14*atr),'up')
    projected_stop_risk=(breakout-stop)/breakout
    # Requires actual resistance ABOVE trigger, not the pivot being broken.
    next_res=min([x for x in (first,second) if x is not None and x>breakout],default=None)
    breakout_r=net_r(breakout,stop,next_res) if next_res else None
    breakout_ok= bool(breakout>c and projected_stop_risk<=.085 and
             breakout-c<=1.1*atr and breakout_r is not None and breakout_r>=1.3)
    # No breakout direction if price has a nearby overhead wall without projected space.
    breakout_trigger=breakout if breakout_ok else None
    if row['r20_pct']<-7:breakout_trigger=None
    pressure=overhead_supply_pressure(first,history)
    return dict(price_lane=price_grade,reason='FIRST_RESISTANCE_1_15R_OBSTACLE_NOT_MANDATORY_2R_TARGET',
      pullback_low=low,pullback_high=high,first_obstacle_net_r_at_high=contact_r,
      **pressure,
      pullback_width_atr=round((high-low)/atr,2) if high is not None else None,
      pullback_below_close_pct=round(100*(c-high)/c,2) if high is not None else None,
      breakout_trigger=breakout_trigger,
      breakout_watch_only=breakout,
      breakout_next_resistance=next_res,
      breakout_first_net_r=round(breakout_r,2) if breakout_r is not None else None,
      breakout_rule='FUTURE_COMPLETED_CLOSE_ABOVE_TRIGGER_AND_RVOL_GE_1_25_AND_CLOSE_TOP_35PCT; REPRICE_NEXT_SESSION',
      breakouts_are_not_today_orders=True,
      no_chase_above=quote(c+1.1*atr,'down'),
      first_obstacle=first,second_obstacle=second,
      ordinary_share_verified=False,actual_turnover_verified=False,
      investor_flow_verified=False,regular_only_price_certified=False,
      buy_approved=False,orders_enabled=False)

def analyze(source,output):
    obs,hist,master,names,evid,scan=load(source)
    asof=scan['market_data_date']
    # Reference distribution: all observed valid dated price series, excluding missing returns.
    valid=obs[(obs['observation_status']=='PRICE_ONLY_OBSERVED') & obs.ret20.notna() & obs.ret5.notna()]
    peer20=float(valid.ret20.median());peer5=float(valid.ret5.median())
    sector_table=group_strength(obs,master)
    with zipfile.ZipFile(source) as archive:
        theme_members=pd.read_csv(io.BytesIO(archive.read('v68_investment_sector_members.csv')),dtype={'ticker':str})
        theme_strength=pd.read_csv(io.BytesIO(archive.read('v71_sector_strength.csv')))
    # This mapped subset is thematic research ONLY (not verified institutional flows).
    themes={z['ticker']:(str(z['investment_sector']),bool(z['theme_exposure_verified']))
            for z in theme_members.to_dict('records')}
    theme_stats={z['investment_sector']:z for z in theme_strength.to_dict('records')}

    sectors=master.drop_duplicates('ticker').set_index('ticker').sector.to_dict()
    namemap=names.drop_duplicates('ticker').set_index('ticker').name.to_dict()
    ev=evid.drop_duplicates('ticker').set_index('ticker')[['instrument_review','business_scope_status']].to_dict('index')
    pool=obs[(obs['price_stage_pass']==True)&(obs['observation_status']=='PRICE_ONLY_OBSERVED')]
    by={t:g.sort_values('date').reset_index(drop=True) for t,g in hist.groupby('ticker',sort=False)}
    out=[];skips=Counter()
    for x in pool.to_dict('records'):
        t=x['ticker'];b=by.get(t)
        if b is None:skips['MISSING_DATED_HISTORY']+=1;continue
        v3=score_one(t,x,b,namemap.get(t,t),sectors.get(t,''),ev.get(t,{}),sector_table)
        if v3 is None:skips['V3_LIQUIDITY_INSTRUMENT_OR_STRUCTURE']+=1;continue
        # A strong 5-day bounce after a sharp 12-session decline remains a
        # rebound WATCH, not an established rising-leader classification.
        r12=100*(float(b.close.iloc[-1])/float(b.close.iloc[-13])-1)
        v3['return12_pct']=round(r12,2)
        strength,components=score_strength(v3,peer20,peer5)
        theme,exposure_verified=themes.get(t,(None,False))
        theme_row=theme_stats.get(theme) if theme else None
        thematic_bonus=0.0
        if theme_row and theme_row.get('status')=='RESEARCH_READY' and theme_row.get('valid_members',0)>=8:
            # Capped bonus, explicitly provisional because theme_exposure_verified is false.
            thematic_bonus=3.0*clip((float(theme_row['median_5d_pct'])+2)/12,0,1) + 1.0*clip((float(theme_row['breadth_5d_pct'])-45)/45,0,1)
            strength=round(clip(strength+thematic_bonus,0,100),1)
        entry=design_entries(v3,b)

        if r12<=-8 and v3['r5_pct']>=6:
            grade='C_SHARP_REBOUND_NOT_CONFIRMED'
        elif strength>=65 and entry['price_lane']=='PULLBACK_WATCH':grade='A_HIGH_PRIORITY_RETEST'
        elif strength>=50 and entry['price_lane']=='PULLBACK_WATCH':grade='B_RETEST_WAIT'
        elif entry['breakout_trigger'] is not None and strength>=55:grade='C_CONDITIONAL_BREAKOUT'
        else:grade='D_OBSERVATION_ONLY'
        # Two transparent ranks; stock strength isn't entry quality.
        rr=entry.get('first_obstacle_net_r_at_high') or 0
        entry_edge=min(8,max(0,rr-1.10)*3)
        if entry.get('breakout_trigger') is not None:entry_edge+=4
        if entry.get('overhead_supply')=='HIGH_SUPPLY' and rr<1.50:entry_edge-=3
        combined=round(strength+entry_edge,1)
        v3.update(stock_strength_score100=strength,entry_priority_score=combined,
            stock_factor_components=components,
            investment_theme_provisional=theme,
            theme_exposure_verified=exposure_verified,
            theme_breadth5_pct=round(float(theme_row['breadth_5d_pct']),2) if theme_row else None,
            theme_median5_pct=round(float(theme_row['median_5d_pct']),2) if theme_row else None,
            thematic_bonus_provisional=round(thematic_bonus,2),
            v4_priority=grade,**entry,price_asof=asof,source_run_id='41051723762')
        out.append(v3)
    priority={'A_HIGH_PRIORITY_RETEST':0,'B_RETEST_WAIT':1,
             'C_SHARP_REBOUND_NOT_CONFIRMED':2,
             'C_CONDITIONAL_BREAKOUT':2,'D_OBSERVATION_ONLY':3}
    out.sort(key=lambda z:(priority[z['v4_priority']],-z['entry_priority_score'],
          -float(z['r20_pct']),z['ticker']))
    dest=Path(output);dest.mkdir(parents=True,exist_ok=True)
    columns=[k for k in out[0] if k!='stock_factor_components']
    csv_path=dest/'c3_stock_first_v4_ranked.csv'
    with csv_path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
        for x in out:w.writerow({k:x[k] for k in columns})
    lead=[x for x in out if x['v4_priority'].startswith('A_')]
    status=dict(schema=SCHEMA,asof=asof,source_run_id='41051723762',universe_total=int(scan['universe']),
        price_stage_total=len(pool),researched=len(out),score_reference_population=len(valid),
        market_median_5d_pct=round(peer5,2),market_median_20d_pct=round(peer20,2),
        filters=dict(skips),readiness_counts=dict(Counter(x['v4_priority'] for x in out)),
        top2=out[:2],other_leaders=out[2:6],no_backtest_requested=True,
        stock_quality_distinct_from_entry=True,
        first_obstacle_does_not_require_fixed_2R=True,
        regular_only_price_certified=False,actual_turnover_certified=False,
        real_investor_flows_certified=False,trade_approved=False,orders_enabled=False,
        csv_sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest())
    (dest/'c3_stock_first_v4_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return status,out

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--input',required=True);a.add_argument('--output',required=True)
    x=a.parse_args();report,ranked=analyze(x.input,x.output)
    print(json.dumps({k:v for k,v in report.items() if k not in ('top2','other_leaders')},ensure_ascii=False,indent=2))
    print(pd.DataFrame(ranked).head(15)[['ticker','name','stock_strength_score100','v4_priority','close','pullback_low','pullback_high','stop','first_resistance','first_obstacle_net_r_at_high','breakout_trigger','r20_pct','rvol20']].to_string(index=False))