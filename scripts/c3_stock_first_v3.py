#!/usr/bin/env python3
"""C3 v3 stock-first discovery from the frozen October 30 scan; research only.

Rank potential early rises BEFORE entry geometry. No historical backtest,
forward-trading approval, broker execution or independently verified KRX close.
Turnover (close*volume) and signed-volume pressure are PROXIES, not measured
exchange turnover or institutional/foreign investor flows.
"""
import argparse,gzip,io,json,re,zipfile
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
SCHEMA='C3_STOCK_FIRST_V3_ASOF_RESEARCH_ONLY'
RUN='41051723762'

def frame(raw):return pd.read_csv(io.BytesIO(raw),dtype={'ticker':str})
def source(path):
    with zipfile.ZipFile(path) as z:
        required=['status.json','c3_premove_observations_v1.csv',
          'c3_premove_history_v1.csv.gz','kind_sector_master.csv',
          'v65_sector_stock_map.csv','c3_candidate_evidence_v1.csv']
        if not set(required)<=set(z.namelist()):
            raise ValueError('FROZEN_SCAN_INPUT_MISSING')
        scan=json.loads(z.read('status.json'))
        if scan['market_data_date']!='2026-10-30' or scan['universe']!=2625:
            raise ValueError('UNEXPECTED_SOURCE_SCAN')
        obs=frame(z.read(required[1]))
        history=frame(gzip.decompress(z.read(required[2])))
        sectors=frame(z.read(required[3]))
        names=frame(z.read(required[4]))[['ticker','name']]
        evidence=frame(z.read(required[5]))[['ticker','instrument_review','business_scope_status']]
    if obs['ticker'].duplicated().any() or len(obs)!=2625:
        raise ValueError('UNIVERSE_COUNT_OR_DUPLICATE_INVALID')
    selected=obs[(obs['price_stage_pass']==True)&
        (obs['observation_status']=='PRICE_ONLY_OBSERVED')]
    if len(selected)!=457 or history.ticker.nunique()!=457:
        raise ValueError('PRE_MOVE_COHORT_COUNT_INVALID')
    return scan,obs,history,sectors,names,evidence

def clip(v,lo=0,hi=1):return max(lo,min(hi,v))
def price_grid_down(x):
    if x<2000:d=1
    elif x<5000:d=5
    elif x<20000:d=10
    elif x<50000:d=50
    elif x<200000:d=100
    elif x<500000:d=500
    else:d=1000
    return int(np.floor(x/d)*d)

def floor(b):
    low=b.low.to_numpy(float);n=len(b)
    for i in range(n-3,max(1,n-23)-1,-1):
        w=low[i-2:i+3]
        if len(w)==5 and low[i]==w.min() and (w>low[i]).any() and low[i+1:].min()>=low[i]:
            return float(low[i]),str(b.date.iloc[i]),str(b.date.iloc[i+2])
    return None

def first_resistances(b,close):
    h=b.high.to_numpy(float);n=len(b);out=[]
    for i in range(max(2,n-123),n-2):
        v=h[i];w=h[i-2:i+3]
        if (len(w)==5 and v>close and v==w.max() and
            (w<v).any() and h[i+1:].max()<=v):
            out.append((float(v),str(b.date.iloc[i])))
    return sorted(out)[:2]

def sectors_now(obs,master):
    q=obs[(obs.observation_status=='PRICE_ONLY_OBSERVED')
       &obs.ret5.notna()&obs.ret20.notna()].merge(master,on='ticker',how='left')
    t=q.groupby('sector').agg(count=('ticker','count'),
       r5=('ret5','median'),r20=('ret20','median'),
       breadth5=('ret5',lambda a:(a>0).mean())).reset_index()
    return {str(x.sector):x for _,x in t.iterrows() if pd.notna(x.sector)}

def evaluate(ticker,bar,ob,name,sector,evidence,sectors):
    if len(bar)<120 or bar.date.iloc[-1]!=ob['asof'] or bar.date.duplicated().any():
        return None
    cols=bar[['open','high','low','close','volume']].to_numpy(float)
    if not np.isfinite(cols).all() or (cols[-120:,:]<=0).any():
        return None
    if ((bar.low>bar[['open','close']].min(axis=1)) |
         (bar.high<bar[['open','close']].max(axis=1))).tail(120).any():
        return None
    close=bar.close.astype(float);high=bar.high.astype(float)
    low=bar.low.astype(float);volume=bar.volume.astype(float)
    c=float(close.iloc[-1])
    activity=close*volume
    med20=float(activity.tail(20).median())
    med5=float(activity.tail(5).median())
    if c<1500 or med20<8e8 or med5<1e9:return None
    name=str(name);sector=str(sector)
    if ('스팩' in name or '리츠' in name or
      re.search(r'(?:우B?|[0-9]우B?)$',name) or
      any(x in sector for x in ('의약품','의료용','의료기기','생물학적','자연과학 및 공학 연구개발')) or
      any(x in name for x in ('제약','바이오','HLB','셀트리온','항체')) or
      evidence.get('instrument_review') in ('EXCLUDE_SPECIAL','EXCLUDE_NON_DOMESTIC_COMMON') or
      evidence.get('business_scope_status')=='EXCLUDE_PHARMA_BIOTECH'):
        return None
    support=floor(bar)
    if support is None:return None
    prev=close.shift(1)
    atr=float(pd.concat([(high-low),(high-prev).abs(),(low-prev).abs()],axis=1)
          .max(axis=1).tail(14).mean())
    if not 0<atr/c<=.10:return None
    ma5=float(close.tail(5).mean());ma20=float(close.tail(20).mean())
    ma60=float(close.tail(60).mean())
    p20=float(close.iloc[-25:-5].mean());p60=float(close.iloc[-65:-5].mean())
    r5=100*(c/float(close.iloc[-6])-1)
    r20=100*(c/float(close.iloc[-21])-1)
    r60=100*(c/float(close.iloc[-61])-1)
    vm=float(volume.iloc[-21:-1].mean())
    rv=float(volume.iloc[-1]/vm) if vm>0 else 0.
    span=(high-low).replace(0,np.nan)
    relative=((close-bar.open)/span).fillna(0).clip(-1,1)
    pressure=float((relative.tail(5)*activity.tail(5)).sum()/activity.tail(5).sum())
    sector_row=sectors.get(sector);sector_known=(sector_row is not None and sector_row['count']>=5)
    sector_score=(5*clip((sector_row['r5']+2)/9)+
       4*clip((sector_row['r20']+2)/15)+
       4*clip((sector_row['breadth5']-.35)/.5)) if sector_known else 0.
    trend=(9*(ma5>=ma20)+8*(ma20>p20)+7*(ma20>ma60)+
       4*(ma60>p60)+5*(c>=ma20))
    momentum=(8*clip((r20+5)/18)+5*clip((r5+2)/8)+
       5*clip((float(ob['rsi14'])-40)/30)+
       4*clip((float(ob['rsi_change3'])+1)/12))
    volscore=(6*clip(np.log1p(med20/1e9)/np.log(20))+
      6*clip(rv/2)+6*clip((pressure+.1)/.5))
    prior_high=float(high.iloc[-21:-1].max())
    stop=price_grid_down(support[0]-.18*atr)
    if stop<=0:return None
    riskclose=100*(c-stop)/c
    ma20_dist=(c-ma20)/atr
    prev_high_dist=(prior_high-c)/atr
    entry_fit=(6*clip(1-abs(ma20_dist-.2)/2)+
       5*clip((8.5-riskclose)/6)+
       4*clip(1-abs(prev_high_dist-.35)/2)+
       4*clip((.9-float(ob['range10_previous20']))/.7)+
       4*(40<=float(ob['rsi14'])<=70))
    overheat=min(20,max(0,ma20_dist-1.4)*6+max(0,r20-25)*.4)
    score=round(float(trend+momentum+volscore+sector_score+entry_fit-overheat),1)
    rr=first_resistances(bar,c)
    resistance=rr[0][0] if rr else None
    max_for_2r=(resistance+2*stop)/(3*(1+.0065)) if resistance else None
    buylo=price_grid_down(max(support[0]-.25*atr,c-1.05*atr,stop+max(5,.05*atr)))
    buyhi=price_grid_down(min(support[0]+.75*atr,c+.05*atr))
    if max_for_2r is not None:buyhi=min(buyhi,price_grid_down(max_for_2r))
    if not stop<buylo<=buyhi:buylo=buyhi=None
    modelR=(resistance-buyhi-.0065*buyhi)/(buyhi-stop+.0065*buyhi) if resistance and buyhi else None
    if not buylo:label='NO_VALID_2R_ENTRY_OR_STRUCTURE'
    elif not resistance:label='RESISTANCE_UNOBSERVED_WATCH'
    elif 100*(resistance/c-1)<4:label='NEAR_RESISTANCE'
    elif rv<.5:label='WAIT_VOLUME_CONFIRMATION'
    elif riskclose>12:label='WAIT_DEEPER_PULLBACK'
    elif r20>35 or ma20_dist>2:label='EXTENDED_NO_CHASE'
    else:label='ACTIONABLE_RESEARCH_ZONE'
    breakout=price_grid_down(max(prior_high+.08*atr,c+.1*atr))
    breakout_R=((resistance-breakout-.0065*breakout)/
       (breakout-stop+.0065*breakout)) if resistance and breakout>stop else None
    # Momentum continuation is only a future-candle WATCH, never a stop-chase.
    if (breakout>c+1.15*atr or (breakout-stop)/breakout>.09 or
        breakout_R is None or breakout_R<2):breakout=None
    return dict(ticker=ticker,name=name,sector=sector,track=str(ob['track']),
      research_priority_score=score,trend=trend,
      volume_proxy_score=round(float(volscore),2),sector_score=round(float(sector_score),2),
      entry_fit_score=round(float(entry_fit),2),overheat_penalty=round(float(overheat),2),
      close=int(c),ma20=round(ma20,2),atr14=round(atr,2),
      return5_pct=round(r5,2),return20_pct=round(r20,2),
      return60_pct=round(r60,2),rvol20=round(rv,2),
      signed_volume_proxy=round(pressure,3),
      turnover_proxy_median20_krw=int(med20),
      support=int(support[0]),support_date=support[1],confirmed_at=support[2],
      stop_krw=stop,buy_low_krw=buylo,buy_high_krw=buyhi,
      first_resistance_krw=int(resistance) if resistance else None,
      second_resistance_krw=int(rr[1][0]) if len(rr)>1 else None,
      max_2r_entry_krw=price_grid_down(max_for_2r) if max_for_2r else None,
      first_resistance_net_R=round(float(modelR),2) if modelR else None,
      conditional_breakout_krw=breakout,
      continuation_requires_completed_daily_close=True,
      continuation_min_rvol20=1.2,
      continuation_requires_recheck_of_structure_and_resistance=True,
      sector_members=int(sector_row['count']) if sector_known else 0,
      entry_status=label,regular_only_verified=False,
      exchange_turnover_verified=False,foreign_institution_flow_verified=False,
      trade_approved=False,orders_enabled=False)

def run(source_path,outdir):
    scan,obs,hist,master,names,evidence=source(source_path)
    sector=master.drop_duplicates('ticker').set_index('ticker').sector.to_dict()
    name=names.drop_duplicates('ticker').set_index('ticker').name.to_dict()
    evid=evidence.drop_duplicates('ticker').set_index('ticker')[['instrument_review','business_scope_status']].to_dict('index')
    sectors=sectors_now(obs,master)
    histories={t:g.sort_values('date').reset_index(drop=True) for t,g in hist.groupby('ticker')}
    out=[]
    for _,row in obs[(obs.price_stage_pass==True)&
        (obs.observation_status=='PRICE_ONLY_OBSERVED')].iterrows():
        t=row.ticker
        x=evaluate(t,histories[t],row,name.get(t,t),sector.get(t,''),evid.get(t,{}),sectors)
        if x is not None:out.append(x)
    out.sort(key=lambda r:(r['entry_status']!='ACTIONABLE_RESEARCH_ZONE',
                           -r['research_priority_score'],r['ticker']))
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(out).to_csv(root/'c3_stock_first_v3_ranked.csv',index=False,encoding='utf-8-sig')
    result=dict(schema=SCHEMA,asof=scan['market_data_date'],source_run_id=RUN,
      full_market_scan=scan['universe'],premovement_stage_cases=457,
      structured_candidates=len(out),prior_top2=['271560','012630'],
      new_research_top2=out[:2],entry_status_counts=dict(Counter(x['entry_status'] for x in out)),
      score_not_calibrated_probability=True,no_performance_backtest=True,
      no_institutional_flow_data=True,no_verified_source_reported_turnover=True,
      regular_session_price_certified=False,
      original_scanner_unmodified=True,trade_approved=False,orders_enabled=False)
    (root/'c3_stock_first_v3_summary.json').write_text(
       json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True)
    p.add_argument('--output',required=True);args=p.parse_args()
    report=run(args.input,args.output)
    print(json.dumps(report,ensure_ascii=False,indent=2))
