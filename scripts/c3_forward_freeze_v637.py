#!/usr/bin/env python3
"""Capture a dated, immutable research hypothesis from completed daily bars.

Independent forward eligibility still requires contemporaneously collected
certified sources. This utility never grants approval or places orders.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile
import numpy as np
import pandas as pd

from c3_event_replay_v637 import (Policy,BASE_COST,make_pending,resistance_clusters,
                                  confirmed_daily_stop,iso_day)
from c3_research_v637 import enrich,_bars,select_D,dump,FIRST


def canonical_digest(record):
    return hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False,
                                    allow_nan=False,separators=(',',':')).encode()).hexdigest()


def freeze_once(path,record):
    """Existing same-date model choices cannot be overwritten after outcomes."""
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    envelope=dict(record=record,sha256=canonical_digest(record))
    if p.exists():
        old=json.loads(p.read_text())
        if old!=envelope:
            raise ValueError('IMMUTABLE_FREEZE_ALREADY_EXISTS_WITH_DIFFERENT_CONTENT')
        return envelope
    with p.open('x',encoding='utf-8') as w:
        w.write(json.dumps(envelope,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n')
    return envelope


def candidate_on_D(df,ticker,asof,bench):
    """The v6.32 NEAR60 hypothesis, with causal 12-session signal cooldown."""
    x=enrich(df[df.Date<=asof].copy())
    if len(x)<65 or x.Date.iloc[-1]!=asof:return None
    c=x.Close
    for n in (5,10,20,60):x[f'ma{n}']=c.rolling(n).mean()
    x['ret5']=100*(c/c.shift(5)-1);x['ret20']=100*(c/c.shift(20)-1)
    x['previous20high']=x.High.shift(1).rolling(20).max()
    x['rv20']=x.Volume/x.Volume.shift(1).rolling(20).mean()
    x['stopD']=x.Low.rolling(3).min()-.15*x.atr14
    x['riskD_pct']=100*(c-x.stopD)/c
    x['range_position']=(c-x.Low)/(x.High-x.Low).replace(0,np.nan)
    x['turnover_accel']=x.TurnoverKRW/x.TurnoverKRW.shift(1).rolling(20).mean()
    ratio=x.ma20/x.ma60
    ok=((x.Date>=FIRST)&(c>=2000)&(x.TurnoverKRW>=3e9)&(x.atr14>0)&(x.stopD>0)
        &(x.atr14/c<=.12)&(x.ma5>x.ma10)&(x.ma10>x.ma20)
        &x.ret5.between(3,17)&x.ret20.between(-5,32)&(x.range_position>=.65)
        &(x.rv20>=.75)&(x.ma20slope>0)&(c>x.previous20high)
        &ratio.between(.92,1.02)&x.riskD_pct.between(2,8))
    last=-100
    accepted=[]
    for idx in np.flatnonzero(ok.fillna(False).to_numpy()):
        if idx-last<12:continue
        last=idx;accepted.append(idx)
    if not accepted or accepted[-1]!=len(x)-1:return None
    r=x.iloc[-1];b=bench.loc[asof]
    rs5=float(r.ret5-b.ret5);rs20=float(r.ret20-b.ret20)
    breakout=100*(r.Close/r.previous20high-1);turn=float(np.clip(r.turnover_accel,0,6))
    risk=float(r.riskD_pct);rv=float(r.rv20);bil=float(r.TurnoverKRW/1e9)
    original=float(r.ret5)*.4+min(rv,3)*2-risk*.45+min(breakout,5)*.3
    balanced=.5*rs5+.2*rs20+1.8*min(turn,4)+.5*np.log1p(bil)+.3*breakout-.9*risk
    history=_bars(x)
    res=resistance_clusters(history[-60:],float(r.Close),float(r.atr14))
    pivot=confirmed_daily_stop(history,float(r.atr14))
    return dict(asof=asof,ticker=ticker,model='NEAR60_RISK8',
                signal_close=float(r.Close),stopD=float(r.stopD),atr14=float(r.atr14),
                ret5=float(r.ret5),rv20=rv,riskD_pct=risk,
                V632_BASE=round(original,7),BALANCED_LEADER=float(balanced),
                market_trend=bool(b.Close>b.ma20 and b.ma20slope>0),
                confirmed_pivot_evidence=pivot,
                resistance=res['price'] if res else None)


def capture(source,eligibility,asof,out):
    iso_day(asof)
    elig=pd.read_csv(eligibility,dtype=str).fillna('')
    if elig.ticker.duplicated().any():raise ValueError('DUPLICATE_ELIGIBILITY')
    eligible={r['ticker']:r for r in elig.to_dict('records')
              if r['snapshot_research_allowed']=='True' and r['official_request_asof']<=asof}
    candidates=[];scanned=0;available=0;excluded=0
    with zipfile.ZipFile(source) as z:
        sessions=pd.read_csv(io.BytesIO(z.read('market/sessions.csv')),dtype=str).date.tolist()
        if asof not in sessions:raise ValueError('ASOF_NOT_COMPLETED_SOURCE_SESSION')
        b=enrich(pd.read_csv(io.BytesIO(z.read('market/etf_prices/069500.csv')),dtype={'Date':str}))
        b=b[b.Date<=asof].copy();b['ret5']=100*(b.Close/b.Close.shift(5)-1)
        b['ret20']=100*(b.Close/b.Close.shift(20)-1);bench=b.set_index('Date')
        for name in sorted(z.namelist()):
            if not(name.startswith('market/prices/') and name.endswith('.csv')):continue
            available+=1;ticker=Path(name).stem
            if ticker not in eligible:excluded+=1;continue
            p=pd.read_csv(io.BytesIO(z.read(name)),dtype={'Date':str})
            scanned+=1;s=candidate_on_D(p,ticker,asof,bench)
            if s:candidates.append(s)
    selections=[]
    if candidates:
        for rank in ('V632_BASE','BALANCED_LEADER'):
            chosen=select_D(candidates,rank)[0]
            for stop_model in ('ROLLING3_REFERENCE','CONFIRMED_PIVOT'):
                fixed=dict(chosen)
                if stop_model=='CONFIRMED_PIVOT':
                    fixed['requires_confirmed_pivot']=True
                    if chosen['confirmed_pivot_evidence']:
                        fixed['stopD']=chosen['confirmed_pivot_evidence']['stop']
                for ex in ('LEGACY_TRAIL7_D12','STRUCT_ATR_D12'):
                    p=Policy(entry='RETEST_2D',exit=ex)
                    order,reason=make_pending(fixed,p,BASE_COST,1e6,1e6,0)
                    selections.append(dict(rank=rank,exit=ex,stop_model=stop_model,ticker=chosen['ticker'],
                         source_features=fixed,policy=p.__dict__,policy_hash=p.digest(),
                         hypothetical_qty=order['qty'] if order else 0,
                         hypothetical_limit=order['cap'] if order else None,
                         stop=order['stop'] if order else fixed['stopD'],
                         decision='PAPER_HYPOTHESIS_ONLY' if order else 'CASH',reason=reason))
    record=dict(schema='C3_V637_DATED_IMMUTABLE_RESEARCH_FREEZE',asof=asof,
        source_archive_sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        eligibility_sha256=hashlib.sha256(Path(eligibility).read_bytes()).hexdigest(),
        source_price_files=available,eligible_files_scanned=scanned,
        excluded_or_unknown_type_industry=excluded,candidate_count=len(candidates),
        candidates=candidates,selections=selections,production_decision='CASH',
        stop_models_frozen_separately=['ROLLING3_REFERENCE','CONFIRMED_PIVOT'],
        fully_qualified_final_score80_and_net2R_verified=False,
        price_regular_only_attested=False,industry_historical_vintage_verified=False,
        broker_cash_or_fills_verified=False,trade_approved=False,orders_enabled=False,
        retrospective_if_date_already_seen=True,
        successful_capture_does_not_make_this_independent_forward_evidence=True)
    return freeze_once(out,record)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-zip',required=True);p.add_argument('--eligibility-csv',required=True)
    p.add_argument('--asof',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();r=capture(a.source_zip,a.eligibility_csv,a.asof,a.out)
    print(json.dumps({k:v for k,v in r['record'].items() if k not in ('candidates','selections')},ensure_ascii=False))
