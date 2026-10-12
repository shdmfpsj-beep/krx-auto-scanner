#!/usr/bin/env python3
"""v7.3: audited full-universe daily discovery vs validated sector entry candidates.
Research only. No order instructions, no lookahead, no implied historical backtest.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd


def code(s):
    return s.astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(6)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--reports', default='reports')
    p.add_argument('--outdir', default='reports')
    a=p.parse_args()
    root=Path(a.reports); out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    names=['market_data_v56_merged.csv','v72_historical_watchlist.csv','v71_sector_strength.csv']
    for n in names:
        if not (root/n).is_file():raise SystemExit(f'MISSING_INPUT: {root/n}')
    market=pd.read_csv(root/names[0],dtype={'ticker':str},encoding='utf-8-sig')
    sector=pd.read_csv(root/names[1],dtype={'ticker':str},encoding='utf-8-sig')
    strength=pd.read_csv(root/names[2],encoding='utf-8-sig')
    market['ticker']=code(market['ticker']);sector['ticker']=code(sector['ticker'])
    required_market={'ticker','name','snapshot_date','open','high','low','close','volume','dated_ohlcv_valid'}
    required_sector={'ticker','asof','status','research_score','ideal_buy_low','ideal_buy_high','max_buy','no_chase_above','structural_stop','target_1','target_2','investment_sector'}
    if not required_market.issubset(market) or not required_sector.issubset(sector):raise SystemExit('SCHEMA_MISMATCH')
    dates=market['snapshot_date'].dropna().astype(str).unique().tolist()
    if len(dates)!=1 or not sector['asof'].astype(str).eq(dates[0]).all():raise SystemExit('DATE_MISMATCH_FAIL_CLOSED')
    if market['ticker'].duplicated().any():raise SystemExit('DUPLICATE_MARKET_TICKER')
    if not market['dated_ohlcv_valid'].astype(str).str.lower().eq('true').all():raise SystemExit('INVALID_MARKET_OHLCV')
    for c in ['open','high','low','close','volume']:
        market[c]=pd.to_numeric(market[c],errors='coerce')
    good=(market['open']>0)&(market['high']>=market[['open','close','low']].max(axis=1))&(market['low']>0)&(market['low']<=market[['open','close']].min(axis=1))&(market['volume']>=0)
    market['daily_valid']=good
    market['day_return_pct']=np.where(good,(market['close']/market['open']-1)*100,np.nan)
    market['close_location']=np.where(good&(market['high']>market['low']),(market['close']-market['low'])/(market['high']-market['low']),np.nan)
    market['turnover_proxy_krw']=np.where(good,market['close']*market['volume'],np.nan)
    # Daily snapshot: an observation, NOT multi-day strength, verified turnover, or BUY.
    m=market[good].copy()
    m['daily_observation_score']=((m['day_return_pct'].clip(-15,15)+15)*1.3 + m['close_location'].fillna(0.5)*20 + np.log1p(m['turnover_proxy_krw'].clip(lower=0))/2).round(3)
    m=m.sort_values(['daily_observation_score','ticker'],ascending=[False,True])
    validated_codes=set(sector['ticker'])
    m['has_validated_sector_entry']=m['ticker'].isin(validated_codes)
    m['candidate_class']=np.where(m['has_validated_sector_entry'],'SECTOR_ENTRY_VALIDATED_HISTORICAL','INDEPENDENT_DAILY_ONLY_HISTORY_NOT_VALIDATED')
    m['trade_authorized']='NO'
    m['limitation']='ONE_SESSION_ONLY|UNVERIFIED_TURNOVER|UNVERIFIED_INSTRUMENT|NO_20D_TREND|NO_LIVE_GATE'
    m[['ticker','name','market','snapshot_date','close','day_return_pct','close_location','turnover_proxy_krw','daily_observation_score','has_validated_sector_entry','candidate_class','trade_authorized','limitation']].to_csv(out/'v73_full_market_observations.csv',index=False,encoding='utf-8-sig')
    independent=m[~m['has_validated_sector_entry']].head(30).copy()
    independent.to_csv(out/'v73_independent_research_queue.csv',index=False,encoding='utf-8-sig')
    sector['research_score']=pd.to_numeric(sector['research_score'],errors='coerce')
    # Restrict to v7.2 audited geometry; never fabricate prices for independent candidates.
    candidates=sector[(sector['status']=='HISTORICAL_WATCH_ONLY')&sector['ticker'].isin(set(m['ticker']))].copy()
    for c in ['ideal_buy_low','ideal_buy_high','max_buy','no_chase_above','structural_stop','target_1','target_2']:
        candidates[c]=pd.to_numeric(candidates[c],errors='coerce')
    geometry=(candidates['structural_stop']>0)&(candidates['structural_stop']<candidates['ideal_buy_low'])&(candidates['ideal_buy_low']<=candidates['ideal_buy_high'])&(candidates['ideal_buy_high']<=candidates['max_buy'])&(candidates['max_buy']<=candidates['no_chase_above'])&(candidates['target_1']>candidates['max_buy'])&(candidates['target_2']>candidates['target_1'])
    candidates=candidates[geometry].copy()
    candidates=candidates.sort_values(['research_score','ticker'],ascending=[False,True]).drop_duplicates('ticker')
    selected=[];sector_counts={}
    for _,r in candidates.iterrows():
        s=r['investment_sector']
        if sector_counts.get(s,0)>=2:continue
        selected.append(r)
        sector_counts[s]=sector_counts.get(s,0)+1
        if len(selected)==3:break
    columns=list(sector.columns)+['selection_scope','trade_authorized','selection_note']
    if selected:
        top=pd.DataFrame(selected).copy()
        top['selection_scope']='124_MAPPED_STOCKS_ONLY_NOT_FULL_MARKET_TOP3'
        top['trade_authorized']='NO'
        top['selection_note']='HISTORICAL_RESEARCH_ONLY|SECTOR_MAPPING_UNVERIFIED|INDEPENDENT_CANDIDATES_UNVALIDATED|NO_LIVE_EXECUTION'
    else:top=pd.DataFrame(columns=columns)
    top.to_csv(out/'v73_provisional_sector_top3.csv',index=False,encoding='utf-8-sig')
    independent_covered=int(m['ticker'].nunique()-len(set(m['ticker'])&validated_codes))
    audit={'version':'7.3','asof':dates[0],'market_rows':len(market),'valid_daily_rows':len(m),'sector_entry_candidates':len(candidates),'independent_daily_only_rows':independent_covered,'independent_queue_rows':len(independent),'provisional_sector_top3_rows':len(top),'true_full_market_top3_authorized':False,'trade_authorized':False,'status':'RESEARCH_ONLY_INDEPENDENT_HISTORY_MISSING','limitations':['One-session independent scan cannot establish 5/20d trend or valid entry geometry','v7.2 historical sector membership not externally verified','No next-day fill simulation or performance attribution','No verified instrument classification, real turnover, index-relative strength, or live quotes'],'outputs':['v73_full_market_observations.csv','v73_independent_research_queue.csv','v73_provisional_sector_top3.csv']}
    (out/'v73_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
