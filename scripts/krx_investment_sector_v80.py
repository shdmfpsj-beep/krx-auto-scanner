#!/usr/bin/env python3
"""v8.0: Immutable as-of-dated C3/K100 watch cohorts and later OHLCV follow-up.

RESEARCH ONLY. No BUY, intraday fill, or exchange-confirmed prices.
Candidates were prefiltered by the upstream scanner, NOT independently all-KRX validated.
Never backfills old scan files as if they had been prospectively selected.
"""
import argparse
import csv
import json
import hashlib
import math
import time
from collections import Counter
from statistics import mean, median
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

COHORT_FIELDS=['asof','account','rank','ticker','name','setup','score','signal_close','source','instrument_type',
               'eligibility','warnings','trade_approval','recorded_kst','signature','research_only']
FOLLOW_FIELDS=['asof','account','rank','ticker','name','horizon','valuation_date','valuation_close',
               'gross_close_to_close_pct','status','provider','checked_kst']
SCORE_FIELDS=['account','horizon','observed_rows','unique_cohort_dates','mean_gross_pct',
              'median_gross_pct','positive_row_pct','date_balanced_mean_pct',
              'positive_date_pct','readiness']


def num(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):
        return None


def load(path):
    if not Path(path).exists():return []
    with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def save(path,rows,fields):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    with open(tmp,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
    tmp.replace(path)


def clock():return datetime.now(ZoneInfo('Asia/Seoul'))


def immutable_key(r):return (r['asof'],r['account'],r['ticker'])


def rank_group(path,account,asof,topn):
    rows=load(path);field={'C3':'c3_preliminary_score','K100':'k100_preliminary_score'}[account]
    if not rows: return [],'EMPTY_'+account
    valid=[]
    for r in rows:
        if r.get('latest_date')!=asof:return [],'MIXED_OR_STALE_'+account
        ticker=r.get('ticker','').strip().zfill(6)
        px=num(r.get('close_reference')); score=num(r.get(field))
        if len(ticker)!=6 or not ticker.isdigit() or px is None or px<=0 or score is None:
            continue
        valid.append((score,ticker,r))
    if not valid:return [],'NO_VALID_'+account
    selected=[];seen=set()
    for score,ticker,r in sorted(valid,key=lambda x:(-x[0],x[1])):
        if ticker in seen:continue
        seen.add(ticker)
        data={"asof":asof,"account":account,"rank":str(len(selected)+1),"ticker":ticker,
              "name":r.get('name',''),"setup":r.get('setup',''),"score":str(score),
              "signal_close":str(num(r.get('close_reference'))),"source":r.get('data_source',''),
              "instrument_type":r.get('instrument_type','UNKNOWN'),"eligibility":r.get('eligibility',''),
              "warnings":r.get('warnings',''),"trade_approval":r.get('trade_approval','NO'),
              "recorded_kst":clock().isoformat(timespec='seconds'),"research_only":"YES"}
        contents='|'.join(str(data.get(k,'')) for k in COHORT_FIELDS if k not in ('signature','recorded_kst'))
        data['signature']=hashlib.sha256(contents.encode('utf-8')).hexdigest()
        selected.append(data)
        if len(selected)>=topn:break
    return selected,'READY_'+account


def snapshot(a,now,registry):
    today=now.date().isoformat(); candidates=load(a.candidates)
    audit={'snapshot_status':'SKIPPED','new_cohorts':0,'unchanged_cohorts':0,'conflicting_cohorts':0,
           'asof':today,'candidate_count':len(candidates),'candidate_date_counts':dict(Counter(r.get('latest_date','') for r in candidates))}
    # Freshness applies to upstream screener AND the two ranking outputs.
    if not candidates or any(r.get('latest_date')!=today for r in candidates):
        audit['snapshot_status']='SKIPPED_STALE_OR_MIXED_CANDIDATES';return registry,audit
    c3,c3state=rank_group(a.c3,'C3',today,a.topn)
    k100,kstate=rank_group(a.k100,'K100',today,a.topn)
    audit.update(c3_status=c3state,k100_status=kstate)
    if not c3 or not k100:
        audit['snapshot_status']='SKIPPED_STALE_OR_INVALID_RANKING';return registry,audit
    seen={immutable_key(r):r for r in registry}
    additions=[];conflicts=[];unchanged=0
    for row in c3+k100:
        key=immutable_key(row)
        if key not in seen:
            additions.append(row); seen[key]=row
        elif seen[key].get('signature')==row['signature']:
            unchanged+=1
        else:
            conflicts.append({'asof':row['asof'],'account':row['account'],'ticker':row['ticker'],
                             'old_signature':seen[key].get('signature',''), 'new_signature':row['signature']})
    registry=sorted(registry+additions,key=lambda x:(x['asof'],x['account'],int(x['rank']),x['ticker']))
    audit.update(snapshot_status='FROZEN_RESEARCH_ONLY',new_cohorts=len(additions),
                 unchanged_cohorts=unchanged,conflicting_cohorts=len(conflicts),conflicts=conflicts,
                 watchlist_C3=[x['ticker'] for x in c3],watchlist_K100=[x['ticker'] for x in k100])
    return registry,audit


def read_bars(path):
    rows=load(path);valid=[]
    for r in rows:
        try:
            dt=(r.get('Date') or '').strip()[:10];date.fromisoformat(dt)
            o,h,l,c=[num(r.get(k)) for k in ('Open','High','Low','Close')]
            volume=num(r.get('Volume'))
            if any(x is None for x in (o,h,l,c,volume)) or min(o,h,l,c)<=0 or volume<0 or h<max(o,c,l) or l>min(o,c,h):return []
            valid.append({'date':dt,'open':o,'high':h,'low':l,'close':c,'volume':volume})
        except (ValueError,TypeError):return []
    if len(valid)!=len({r['date'] for r in valid}):return []
    return sorted(valid,key=lambda x:x['date'])


def fetch_bars(ticker,start,end,cache):
    """Refresh every evaluation. Quarantine on partial response or large historic changes."""
    import FinanceDataReader as fdr
    frame=fdr.DataReader(ticker,start,(date.fromisoformat(end)+timedelta(days=1)).isoformat())
    if frame is None or frame.empty:return None,'FETCH_EMPTY',0
    frame=frame.reset_index()
    frame['Date']=frame['Date'].dt.strftime('%Y-%m-%d')
    cols=['Date','Open','High','Low','Close','Volume']
    cache.parent.mkdir(parents=True,exist_ok=True)
    temp=cache.with_suffix('.fetch.tmp')
    try:
        frame[cols].to_csv(temp,index=False,encoding='utf-8-sig')
        fresh=read_bars(temp)
        if not fresh:return None,'INVALID_FRESH_DATA',0
        old=read_bars(cache);oldmap={r['date']:r for r in old if start<=r['date']<=end}
        newmap={r['date']:r for r in fresh if start<=r['date']<=end}
        if not newmap:return None,'NO_RECENT_BARS',0
        if set(oldmap)-set(newmap):return None,'PARTIAL_FRESH_RESPONSE',0
        maxdiff=0.0
        for dt in set(oldmap)&set(newmap):
            x,y=oldmap[dt],newmap[dt]
            maxdiff=max(maxdiff,max(abs(y[k]/x[k]-1) for k in ('open','high','low','close')))
        if maxdiff>0.005:return None,'REVISED_GT_0P5_QUARANTINE',round(maxdiff*100,6)
        merged={**oldmap,**newmap}
        save(cache,[{'Date':r['date'],'Open':r['open'],'High':r['high'],'Low':r['low'],
                     'Close':r['close'],'Volume':r['volume']} for r in sorted(merged.values(),key=lambda x:x['date'])],cols)
        return sorted(merged.values(),key=lambda x:x['date']),'REFRESH_OK',round(maxdiff*100,6)
    finally:
        if temp.exists():temp.unlink()


def evaluate(a,now,registry):
    today=now.date().isoformat();output=[];logs=[]
    if not registry:return output,logs
    # Fetch once per ticker, not once per account. Restrict to entries strictly older than today.
    groups={}
    for r in registry:
        if r['asof']<today:groups.setdefault(r['ticker'],[]).append(r)
    groups=sorted(groups.items(),key=lambda x:x[0])
    for ticker,cohorts in groups[:a.max_tickers]:
        start=min(x['asof'] for x in cohorts)
        cpath=Path(a.forward_cache)/(ticker+'.csv')
        try:
            if a.fetch:
                bars,state,maxdiff=fetch_bars(ticker,start,today,cpath)
            else:
                bars=read_bars(cpath);state='CACHE_ONLY_UNVERIFIED';maxdiff=0
                if not bars:state='NO_CACHE'
        except Exception as e:
            bars=None;state='FETCH_ERROR_'+type(e).__name__;maxdiff=0
        logs.append({'ticker':ticker,'status':state,'revision_pct':maxdiff})
        for r in cohorts:
            signal=num(r['signal_close'])
            asofbar=next((b for b in (bars or []) if b['date']==r['asof']),None)
            discrep=(abs(asofbar['close']/signal-1)*100 if asofbar and signal else None)
            status='PENDING_FUTURE_DATA' if state in ('REFRESH_OK','CACHE_ONLY_UNVERIFIED') else 'DATA_INTEGRITY_QUARANTINE'
            if asofbar is None or discrep is None or discrep>0.5:
                status='MISSING_OR_MISMATCHED_SIGNAL_CLOSE'
            fw=[b for b in (bars or []) if b['date']>r['asof'] and b['date']<=today]
            for horizon in (1,3,5,10):
                finished=status=='PENDING_FUTURE_DATA' and len(fw)>=horizon
                px=fw[horizon-1]['close'] if finished else None
                output.append({'asof':r['asof'],'account':r['account'],'rank':r['rank'],'ticker':ticker,'name':r['name'],
                               'horizon':horizon,'valuation_date':fw[horizon-1]['date'] if finished else '',
                               'valuation_close':px if finished else '',
                               'gross_close_to_close_pct':round((px/signal-1)*100,4) if finished else '',
                               'status':'GROSS_OBSERVED_NOT_EXECUTABLE' if finished else status,
                               'provider':'FDR_AUTO_UNVERIFIED','checked_kst':now.isoformat(timespec='seconds')})
        if a.fetch:time.sleep(0.3)
    unattempted=set(dict(groups))-set(k for k,_ in groups[:a.max_tickers])
    for r in registry:
        if r['asof']>=today or r['ticker'] in unattempted:
            for h in (1,3,5,10):
                output.append({'asof':r['asof'],'account':r['account'],'rank':r['rank'],'ticker':r['ticker'],
                               'name':r['name'],'horizon':h,'valuation_date':'','valuation_close':'',
                               'gross_close_to_close_pct':'', 'status':'PENDING_NOT_YET_ELIGIBLE' if r['asof']>=today else 'PENDING_FETCH_CAP',
                               'provider':'','checked_kst':now.isoformat(timespec='seconds')})
    return sorted(output,key=lambda x:(x['asof'],x['account'],int(x['rank']),int(x['horizon']))),logs


def make_scorecard(outcomes):
    """Date-balanced descriptive scorecard only. Same-day stock outcomes aren't independent trials."""
    result=[]
    for account in ('C3','K100'):
        for horizon in (1,3,5,10):
            valid=[r for r in outcomes if r['account']==account and int(r['horizon'])==horizon
                   and r['status']=='GROSS_OBSERVED_NOT_EXECUTABLE']
            vals=[float(r['gross_close_to_close_pct']) for r in valid]
            bydate={}
            for r in valid:bydate.setdefault(r['asof'],[]).append(float(r['gross_close_to_close_pct']))
            date_means=[mean(v) for v in bydate.values()]
            result.append({'account':account,'horizon':horizon,'observed_rows':len(vals),
                           'unique_cohort_dates':len(bydate),
                           'mean_gross_pct':round(mean(vals),4) if vals else '',
                           'median_gross_pct':round(median(vals),4) if vals else '',
                           'positive_row_pct':round(100*sum(v>0 for v in vals)/len(vals),2) if vals else '',
                           'date_balanced_mean_pct':round(mean(date_means),4) if date_means else '',
                           'positive_date_pct':round(100*sum(v>0 for v in date_means)/len(date_means),2) if date_means else '',
                           'readiness':'INSUFFICIENT_INDEPENDENT_DATES' if len(bydate)<30 else 'DESCRIPTIVE_ONLY_BIASES_REMAIN'})
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--candidates',default='reports/candidates.csv')
    p.add_argument('--c3',default='reports/c3_preliminary.csv')
    p.add_argument('--k100',default='reports/k100_preliminary.csv')
    p.add_argument('--outdir',default='reports')
    p.add_argument('--forward-cache',default='reports/v80_forward_cache')
    p.add_argument('--topn',type=int,default=3)
    p.add_argument('--max-tickers',type=int,default=40)
    p.add_argument('--fetch',action='store_true')
    a=p.parse_args()
    if a.topn<1 or a.max_tickers<1:p.error('Positive topn and max-tickers required')
    now=clock();out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    registry=load(out/'v80_cohort_registry.csv')
    registry,snap=snapshot(a,now,registry)
    save(out/'v80_cohort_registry.csv',registry,COHORT_FIELDS)
    following,fetchlog=evaluate(a,now,registry)
    save(out/'v80_forward_close_returns.csv',following,FOLLOW_FIELDS)
    scorecard=make_scorecard(following)
    save(out/'v80_descriptive_scorecard.csv',scorecard,SCORE_FIELDS)
    audit={'version':'8.0','run_kst':now.isoformat(timespec='seconds'),'research_only':True,
           'purpose':'prospective frozen as-of daily TOP3 watchlists, not historical reconstruction or trading authorization',
           'source_pool':'upstream prefiltered candidate shortlist; NOT exhaustive verified whole KRX',
           'snapshot':snap,'cumulative_cohorts':len(registry),
           'evaluations_completed':sum(x['status']=='GROSS_OBSERVED_NOT_EXECUTABLE' for x in following),
           'pending_or_quarantined':sum(x['status']!='GROSS_OBSERVED_NOT_EXECUTABLE' for x in following),
           'fetch_requested':a.fetch,'fetch_log':fetchlog,'scorecard':scorecard,
           'gross_only_no_fills_costs_or_targets':True,
           'caveats':['Date-freshness required; old snapshots are never backfilled as prospective signals',
                      'TOP3 inputs are scanner pre-filtered, may include UNKNOWN instrument or unverified liquidity',
                      'Signal-date closing values and source adjustments are not independently exchange-verified',
                      'Close-to-close gross outcomes do not establish ability to execute entry orders or win rates',
                      'Point-in-time universe and survivorship issues are not resolved',
                      'FDR chooses its own backend; source and quote finality not verified',
                      'Changing ranker rules in the future will create mixed-method cohorts; do not pool without stratification',
                      'TOP3 same-day picks overlap; date-balanced results still do not imply independent samples']}
    (out/'v80_prospective_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False))

if __name__=='__main__':main()
