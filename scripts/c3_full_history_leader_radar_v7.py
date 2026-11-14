#!/usr/bin/env python3
"""C3 v7: recover overlooked confirmed resistance from the full dated history.

Does not predict earnings/news, backtest historical profits or place orders.
A price-volume proxy is NOT measured exchange turnover or investor net buying.
"""
from __future__ import annotations
import argparse,csv,gzip,hashlib,io,json,math,zipfile
from collections import Counter
from pathlib import Path
import pandas as pd

SCHEMA='C3_V7_FULL_HISTORY_RESISTANCE_LEADER_RADAR_NO_TRADES'
COST=0.0065
ASOF='2026-10-30'

def tick(p):
    if p<2000:return 1
    if p<5000:return 5
    if p<20000:return 10
    if p<50000:return 50
    if p<200000:return 100
    if p<500000:return 500
    return 1000

def qdown(price):
    if not math.isfinite(price) or price<=0:raise ValueError('INVALID_PRICE')
    k=int(math.floor(price))
    while k>0 and k%tick(k)!=0:k-=1
    return k

def qup(price):
    if not math.isfinite(price) or price<=0:raise ValueError('INVALID_PRICE')
    k=int(math.ceil(price))
    while k%tick(k)!=0:k+=1
    return k

def net_r(entry,stop,res):
    return (res-entry*(1+COST))/(entry-stop+COST*entry)

def ceiling_at_resistance(first,stop,minimum_r=1.15):
    return (first+minimum_r*stop)/((1+minimum_r)*(1+COST))

def full_pivots(b,asof,close):
    if b.empty or len(b)<120 or str(b.date.iloc[-1])!=asof:
        raise ValueError('HISTORY_MISSING_OR_ASOF_MISMATCH')
    if b.date.duplicated().any() or not b.date.is_monotonic_increasing:
        raise ValueError('DUPLICATE_OR_UNSORTED_SESSIONS')
    px=b[['open','high','low','close','volume']].astype(float)
    if not px.notna().all().all() or (px<=0).any().any():
        raise ValueError('ZERO_OR_MISSING_OHLCV')
    if (px.high<px[['open','close']].max(axis=1)).any() or (px.low>px[['open','close']].min(axis=1)).any():
        raise ValueError('IMPOSSIBLE_BAR_RANGE')
    if float(px.close.iloc[-1])!=float(close):
        raise ValueError('DATE_CLOSE_SOURCE_MISMATCH')
    highs=px.high.to_numpy();vol=px.volume.to_numpy();n=len(b);out=[]
    for j in range(2,n-2):
        price=highs[j]
        if price<=close or price!=max(highs[j-2:j+3]):continue
        if not any(highs[j-2:j+3]<price) or max(highs[j+1:])>price:continue
        previous=vol[max(0,j-20):j]
        ratio=float(vol[j]/pd.Series(previous).median()) if len(previous) and pd.Series(previous).median()>0 else None
        position=float((px.close.iloc[j]-px.low.iloc[j])/(px.high.iloc[j]-px.low.iloc[j])) if px.high.iloc[j]>px.low.iloc[j] else .5
        supply=('HIGH_SUPPLY' if ratio is not None and ratio>=1.6 and position<.4 else
                'MODERATE_SUPPLY' if ratio is not None and ratio>=1.2 and position<.55 else 'LOW_OBSERVED_SUPPLY')
        out.append(dict(price=int(price),pivot_date=str(b.date.iloc[j]),
             confirmed_at=str(b.date.iloc[j+2]),sessions_ago=n-1-j,
             pivot_volume_vs_prev20=round(ratio,2) if ratio is not None else None,
             pivot_close_position=round(position,2),pivot_supply=supply))
    return sorted(out,key=lambda x:(x['price'],-x['sessions_ago']))

def safe_num(v):
    return float(v) if v is not None and pd.notna(v) else None

def select_band(row,first):
    close,stop,support,atr=map(float,(row['close'],row['structure_stop'],row['support'],row['atr14']))
    old_lo,old_hi=safe_num(row.get('watch_low')),safe_num(row.get('watch_high'))
    if old_lo is not None and old_hi is not None:
        lo=qup(old_lo);hi=qdown(old_hi);origin='PRESERVED_V5_PRICE_BAND'
    else:
        proposed_lo=max(support+.15*atr,close-.95*atr,stop+2*tick(stop))
        proposed_hi=min(close-.12*atr,support+1.85*atr,stop/.92)
        lo=qup(proposed_lo);hi=qdown(proposed_hi)
        origin='RECOVERED_AFTER_FULL_HISTORY_FIRST_RESISTANCE'
    if first is not None:
        hi=min(hi,qdown(ceiling_at_resistance(float(first),stop)))
    if not (0<stop<lo<=hi<close):
        return dict(watch_low=None,watch_high=None,band_origin=origin,
            band_status='NO_PRACTICAL_GEOMETRY',net_r_to_first=None)
    r=net_r(hi,stop,first) if first is not None else None
    width=(hi-lo)/atr
    maxrisk=(hi-stop)/hi
    if first is None:
        status='UNOBSERVED_TARGET_NOT_A_BUY'
    elif maxrisk>.08:
        status='STRUCTURAL_RISK_TOO_HIGH'
    elif width<.15:
        status='WATCH_BAND_TOO_NARROW'
    elif r is None or r<1.149:
        status='FIRST_TARGET_NET_R_INSUFFICIENT'
    elif row['phase'] in ('REFLEX_REBOUND','WEAK_12D_TREND'):
        status='TREND_NOT_ESTABLISHED'
    elif row.get('overhead_supply')=='HIGH_SUPPLY' or row.get('_first_supply')=='HIGH_SUPPLY':
        status='HEAVY_HISTORICAL_SUPPLY'
    else:
        status='PRACTICAL_PRICE_WATCH'
    return dict(watch_low=lo,watch_high=hi,band_origin=origin,
        band_status=status,net_r_to_first=round(r,2) if r is not None else None,
        width_atr=round(width,2),stop_risk_pct_upper=round(100*maxrisk,2),
        first_upside_pct_upper=round(100*(first/hi-1),2) if first else None)

def evaluate(row,b,asof):
    close=float(row['close']);pivots=full_pivots(b,asof,close)
    first=pivots[0] if pivots else None
    second=next((p for p in pivots if first and p['price']>first['price']),None)
    old=safe_num(row.get('first_obstacle_krw'))
    if old and (not first or old!=first['price']):
        raise ValueError('OLD_FIRST_RESISTANCE_CONFLICTS_WITH_FULL_HISTORY')
    recovered=old is None and first is not None
    info=dict(row)
    info['_first_supply']=first['pivot_supply'] if first else 'UNKNOWN'
    band=select_band(info,first['price'] if first else None)
    if not first:
        grade='PRICE_DISCOVERY_WITHOUT_VERIFIED_TARGET'
    elif recovered and row['priority_class']=='OPEN_SKY_UNVERIFIED' and band['band_status']=='PRACTICAL_PRICE_WATCH':
        grade='RECOVERED_EARLY_LEADER_CHALLENGER'
    elif recovered:
        grade='RECOVERED_OLD_PIVOT_WATCH'
    elif row['priority_class']=='PRIORITY_PULLBACK' and band['band_status']=='PRACTICAL_PRICE_WATCH':
        grade='INCUMBENT_PRIMARY_WATCH'
    elif row['priority_class']=='SECONDARY_WATCH':
        grade='INCUMBENT_SECONDARY_OR_STRUCTURAL_WAIT'
    else:
        grade='GENERAL_PRICE_RESEARCH'
    return dict(ticker=str(row['ticker']),name=str(row['name']),sector=str(row['sector']),
        asof=asof,close=int(close),original_priority_class=str(row['priority_class']),
        original_opportunity_score=float(row['opportunity_score_not_probability']),
        original_stock_strength=float(row['stock_strength_score_not_probability']),
        trend_phase=str(row['phase']),rvol20=float(row['rvol20']),
        relative_activity_5_to_20=float(row['price_volume_participation_5d_to_prior20']),
        structure_stop=int(row['structure_stop']),
        first_historical_target_krw=first['price'] if first else None,
        first_pivot_date=first['pivot_date'] if first else None,
        first_pivot_age_sessions=first['sessions_ago'] if first else None,
        first_pivot_supply=first['pivot_supply'] if first else 'UNKNOWN',
        second_historical_target_krw=second['price'] if second else None,
        second_pivot_date=second['pivot_date'] if second else None,
        recovered_overlooked_historical_resistance=recovered,
        candidate_class=grade,**band,
        no_fake_target_if_unobserved=True,
        no_news_requirement=True,no_profit_backtests=True,
        official_krx_regular_only_certified=False,real_foreign_institution_flow_verified=False,
        trade_approved=False,orders_enabled=False)

def run(source,ranked,output):
    source=Path(source);ranked=Path(ranked)
    with zipfile.ZipFile(source) as z:
        status=json.loads(z.read('status.json'))
        if status.get('market_data_date')!=ASOF or status.get('universe')!=2625:
            raise ValueError('EXPECTED_FROZEN_OCT30_SCAN')
        history=pd.read_csv(io.BytesIO(gzip.decompress(z.read('c3_premove_history_v1.csv.gz'))),dtype={'ticker':str})
    ranked_df=pd.read_csv(ranked,dtype={'ticker':str,'asof':str})
    if len(ranked_df)!=96 or ranked_df.ticker.duplicated().any() or (ranked_df['asof']!=ASOF).any():
        raise ValueError('INVALID_V5_RANKED_SOURCE')
    cohorts={t:g.sort_values('date').reset_index(drop=True) for t,g in history.groupby('ticker')}
    rows=[evaluate(x,cohorts[x['ticker']],ASOF) for x in ranked_df.to_dict('records')]
    ranked_order={z['ticker']:i for i,z in enumerate(ranked_df.to_dict('records'))}
    preserved=[x for x in rows if x['first_historical_target_krw'] is not None and
        x['watch_low'] is not None and x['original_priority_class'] in ('PRIORITY_PULLBACK','SECONDARY_WATCH')]
    preserved.sort(key=lambda x:(x['original_priority_class']!='PRIORITY_PULLBACK',
              ranked_order[x['ticker']]))
    top2=preserved[:2]
    recovered=sorted((x for x in rows if x['recovered_overlooked_historical_resistance']),
        key=lambda x:(x['candidate_class']!='RECOVERED_EARLY_LEADER_CHALLENGER',
          -x['original_stock_strength'],x['ticker']))
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    outcsv=output/'c3_v7_full_history_leader_radar.csv'
    with outcsv.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    report=dict(schema=SCHEMA,asof=ASOF,source_run='41051723762',researched=len(rows),
        resistance_newly_recovered_count=len(recovered),
        recovered_early_leader_challengers=[x for x in recovered if x['candidate_class']=='RECOVERED_EARLY_LEADER_CHALLENGER'][:5],
        additional_resistance_recovered=recovered[:20],
        top2_preserved_until_new_completed_date=top2,
        candidate_class_counts=dict(Counter(x['candidate_class'] for x in rows)),
        reason_top2_stable='NO_NEW_COMPLETED_MARKET_SESSION_AFTER_2026_10_30',
        not_an_instant_buy=True,no_backtests=True,
        no_verified_investor_flows=True,regular_only_price_not_certified=True,
        trade_approved=False,orders_enabled=False,
        result_csv_sha256=hashlib.sha256(outcsv.read_bytes()).hexdigest())
    (output/'c3_v7_full_history_leader_radar_status.json').write_text(
       json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True)
    p.add_argument('--ranked',required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    z=run(a.input,a.ranked,a.output)
    print(json.dumps({k:v for k,v in z.items() if k not in ('top2_preserved_until_new_completed_date',
       'additional_resistance_recovered')},ensure_ascii=False,indent=2))
