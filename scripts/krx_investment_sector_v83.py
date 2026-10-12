#!/usr/bin/env python3
"""v8.3: C3 and K100 Tactical research cohorts; K100 Core existing holdings only.

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

HOLDING_FIELDS=['asof','ticker','name','shares','average_buy','holding_source','data_status','price_date','close','ma20','ma60','ma120',
                'low20','high20','trend','action_review','pullback_reference','warning_reference',
                'structural_support_reference','resistance_reference','trade_approval','caveat']

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
    rows=load(path);field={'C3':'c3_preliminary_score','K100_TACTICAL':'k100_preliminary_score'}[account]
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


def verify_registry(registry):
    """Fail closed on changed, duplicated, or structurally invalid frozen signals."""
    seen_keys=set()
    seen_ranks=set()
    for r in registry:
        k=immutable_key(r)
        rk=(r.get('asof'),r.get('account'),r.get('rank'))
        if k in seen_keys or rk in seen_ranks:
            raise ValueError('FROZEN_REGISTRY_DUPLICATE_KEY_OR_RANK: '+str(k))
        seen_keys.add(k);seen_ranks.add(rk)
        contents='|'.join(str(r.get(col,'')) for col in COHORT_FIELDS if col not in ('signature','recorded_kst'))
        sig=hashlib.sha256(contents.encode('utf-8')).hexdigest()
        if r.get('signature')!=sig:
            raise ValueError('FROZEN_REGISTRY_SIGNATURE_CHANGED: '+str(k))
    for account in ('C3','K100','K100_TACTICAL'):
        dates={r['asof'] for r in registry if r['account']==account}
        for dt in dates:
            ranks=sorted(int(r['rank']) for r in registry if r['account']==account and r['asof']==dt)
            if ranks!=list(range(1,len(ranks)+1)):
                raise ValueError('FROZEN_REGISTRY_BAD_RANKS: '+dt+':'+account)


def snapshot(a,now,registry):
    today=now.date().isoformat(); candidates=load(a.candidates)
    audit={'snapshot_status':'SKIPPED','new_cohorts':0,'unchanged_cohorts':0,'conflicting_cohorts':0,
           'asof':today,'candidate_count':len(candidates),'candidate_date_counts':dict(Counter(r.get('latest_date','') for r in candidates))}
    # Freshness applies to upstream screener AND the two ranking outputs.
    if not candidates or any(r.get('latest_date')!=today for r in candidates):
        audit['snapshot_status']='SKIPPED_STALE_OR_MIXED_CANDIDATES';return registry,audit
    # Both tactical ranking inputs must be based on today's upstream daily snapshot.
    # Legacy K100 rows from v8.0 remain frozen history; new K100 Core is NOT screened.
    c3,c3state=rank_group(a.c3,'C3',today,a.topn)
    tac,tacstate=rank_group(a.k100,'K100_TACTICAL',today,a.topn)
    audit.update(c3_status=c3state,k100_tactical_status=tacstate,
                 k100_core_status='EXISTING_FOUR_HOLDINGS_ONLY')
    if not c3 or not tac:
        audit['snapshot_status']='SKIPPED_STALE_OR_INVALID_ONE_OR_BOTH_RANKINGS'
        return registry,audit
    additions=[];conflicts=[];unchanged=0;frozen={}
    for account,picks in [('C3',c3),('K100_TACTICAL',tac)]:
        prior=sorted((r for r in registry if r['asof']==today and r['account']==account),
                     key=lambda x:int(x['rank']))
        if prior:
            was={(int(r['rank']),r['ticker'],r['signature']) for r in prior}
            would={(int(r['rank']),r['ticker'],r['signature']) for r in picks}
            if was==would:unchanged+=len(prior)
            else:conflicts.append({'asof':today,'account':account,
                         'reason':'SAME_DAY_RERANK_BLOCKED_WHOLE_COHORT',
                         'frozen_top':[r['ticker'] for r in prior],
                         'attempted_top':[r['ticker'] for r in picks]})
            frozen[account]=prior
        else:
            additions.extend(picks)
            frozen[account]=picks
    registry=sorted(registry+additions,key=lambda x:(x['asof'],x['account'],int(x['rank']),x['ticker']))
    audit.update(snapshot_status='FROZEN_RESEARCH_ONLY' if not conflicts else 'FROZEN_WITH_RERANK_BLOCKED',
                 new_cohorts=len(additions),unchanged_cohorts=unchanged,
                 conflicting_cohorts=len(conflicts),conflicts=conflicts,
                 watchlist_C3=[x['ticker'] for x in frozen['C3']],
                 watchlist_K100_TACTICAL=[x['ticker'] for x in frozen['K100_TACTICAL']],
                 k100_core_new_screen_candidates=0,
                 k100_core_mode='EXISTING_HOLDINGS_ONLY',
                 selection_balance_gate='DISABLED_FOR_C3_AND_K100_TACTICAL',
                 selection_scope='UPSTREAM_PREFILTERED_NOT_EXHAUSTIVE_KRX',
                 archived_k100_legacy_cohorts=len([r for r in registry if r['account']=='K100']))
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
            if state in ('REFRESH_OK','CACHE_ONLY_UNVERIFIED') and (asofbar is None or discrep is None or discrep>0.5):
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
    for account in ('C3','K100_TACTICAL','K100'):
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

def monitor_k100(a,now):
    """K100 Core existing holdings only (Tactical candidates handled separately).

    Holdings CSV is manually maintained, not synchronized to the user's brokerage.
    Indicative levels are derived from price history, NOT validated limit orders.
    """
    holdings=load(a.k100_holdings)
    results=[];log=[];seen=set()
    for r in holdings:
        ticker=r.get('ticker','').strip().zfill(6)
        if len(ticker)!=6 or not ticker.isdigit():
            raise ValueError('INVALID_K100_HOLDING_TICKER: '+ticker)
        if ticker in seen:raise ValueError('DUPLICATE_K100_HOLDING: '+ticker)
        seen.add(ticker)
        name=r.get('name','')
        provenance=r.get('holding_source','USER_PROVIDED_HOLDINGS_SCREENSHOT')
        shares=num(r.get('shares'))
        average_buy=num(r.get('average_buy'))
        if shares is None or shares<=0 or not shares.is_integer() or average_buy is None or average_buy<=0:
            raise ValueError('INVALID_K100_CORE_HOLDING_POSITION: '+ticker)
        start=(now.date()-timedelta(days=260)).isoformat()
        today=now.date().isoformat()
        cache=Path(a.k100_cache)/(ticker+'.csv')
        state='NO_DATA'; bars=None;revision=0
        try:
            if a.fetch:
                bars,state,revision=fetch_bars(ticker,start,today,cache)
            else:
                bars=read_bars(cache)
                state='CACHE_ONLY_UNVERIFIED' if bars else 'NO_CACHE'
        except Exception as e:
            state='FETCH_ERROR_'+type(e).__name__
        log.append({'ticker':ticker,'status':state,'revision_pct':revision})
        clean=[b for b in (bars or []) if start<=b['date']<=today]
        record={k:'' for k in HOLDING_FIELDS}
        record.update({'asof':today,'ticker':ticker,'name':name,'shares':int(shares),'average_buy':round(average_buy,3),'holding_source':provenance,
                       'data_status':state,'trade_approval':'NO_AUTOMATED_TRADE',
                       'caveat':'PRIOR_HOLDINGS_MUST_BE_RECONFIRMED; LEVELS_TECHNICAL_REFERENCE_ONLY'})
        if state in ('REFRESH_OK','CACHE_ONLY_UNVERIFIED') and len(clean)>=120:
            px=clean[-1]['close']
            ma20=mean(b['close'] for b in clean[-20:])
            ma60=mean(b['close'] for b in clean[-60:])
            ma120=mean(b['close'] for b in clean[-120:])
            low20=min(b['low'] for b in clean[-20:])
            high20=max(b['high'] for b in clean[-20:])
            fresh=clean[-1]['date'] >= (now.date()-timedelta(days=5)).isoformat()
            trend=('UPTREND' if px>=ma20>=ma60>=ma120 else
                   'DOWNTREND' if px<ma60 and ma20<ma60 else 'MIXED')
            action=('HOLD_CONDITIONAL_ADD_REVIEW' if trend=='UPTREND' else
                    'TRIM_EXIT_RISK_REVIEW' if trend=='DOWNTREND' else 'HOLD_RISK_REVIEW')
            if not fresh:
                state='STALE_QUOTE_NO_ACTION';action='DATA_STALE_WAIT'
            record.update({'data_status':state,'price_date':clean[-1]['date'],
                           'close':round(px,3),'ma20':round(ma20,3),'ma60':round(ma60,3),
                           'ma120':round(ma120,3),'low20':round(low20,3),
                           'high20':round(high20,3),'trend':trend,'action_review':action,
                           'pullback_reference':round(ma20,3),
                           'warning_reference':round(ma60,3),
                           'structural_support_reference':round(low20,3),
                           'resistance_reference':round(high20,3)})
        elif state in ('REFRESH_OK','CACHE_ONLY_UNVERIFIED'):
            record.update({'data_status':'INSUFFICIENT_HISTORY','action_review':'DATA_INSUFFICIENT_WAIT'})
        else:
            record['action_review']='DATA_UNAVAILABLE_WAIT'
        results.append(record)
        if a.fetch:time.sleep(.3)
    return results,log

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--candidates',default='reports/candidates.csv')
    p.add_argument('--c3',default='reports/c3_preliminary.csv')
    p.add_argument('--k100',default='reports/k100_preliminary.csv')  # K100 Tactical candidate rank input
    p.add_argument('--k100-holdings',default='config/k100_holdings.csv')
    p.add_argument('--k100-cache',default='reports/v83_k100_core_history_cache')
    p.add_argument('--outdir',default='reports')
    p.add_argument('--forward-cache',default='reports/v80_forward_cache')
    p.add_argument('--topn',type=int,default=3)
    p.add_argument('--max-tickers',type=int,default=40)
    p.add_argument('--fetch',action='store_true')
    a=p.parse_args()
    if a.topn<1 or a.max_tickers<1:p.error('Positive topn and max-tickers required')
    now=clock();out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    core_config=load(a.k100_holdings)
    if len(core_config)!=4:
        raise ValueError('K100_CORE_CONFIG_COUNT_NOT_FOUR: update configuration to match the latest brokerage holdings')
    registry=load(out/'v80_cohort_registry.csv')
    verify_registry(registry)
    registry,snap=snapshot(a,now,registry)
    verify_registry(registry)
    save(out/'v80_cohort_registry.csv',registry,COHORT_FIELDS)
    for account,outname in [('C3','v83_c3_top3.csv'),('K100_TACTICAL','v83_k100_tactical_top3.csv')]:
        latest=[r for r in registry if r['account']==account and r['asof']==now.date().isoformat()]
        save(out/outname,sorted(latest,key=lambda x:int(x['rank'])),COHORT_FIELDS)
    following,fetchlog=evaluate(a,now,registry)
    save(out/'v80_forward_close_returns.csv',following,FOLLOW_FIELDS)
    k100hold,k100log=monitor_k100(a,now)
    save(out/'v83_k100_core_review.csv',k100hold,HOLDING_FIELDS)
    scorecard=make_scorecard(following)
    save(out/'v80_descriptive_scorecard.csv',scorecard,SCORE_FIELDS)
    audit={'version':'8.3','run_kst':now.isoformat(timespec='seconds'),'research_only':True,
           'purpose':'Separate C3 prospective TOP3 / K100 Tactical prospective TOP3 / four-stock K100 Core review',
           'source_pool':'C3 and K100 Tactical: upstream prefiltered candidates; K100 Core: confirmed four-stock user screenshot',
           'snapshot':snap,'cumulative_cohorts':len(registry),
           'evaluations_completed':sum(x['status']=='GROSS_OBSERVED_NOT_EXECUTABLE' for x in following),
           'pending_or_quarantined':sum(x['status']!='GROSS_OBSERVED_NOT_EXECUTABLE' for x in following),
           'fetch_requested':a.fetch,'fetch_log':fetchlog,'scorecard':scorecard,
           'k100_tactical_new_candidates':len([r for r in registry if r['account']=='K100_TACTICAL' and r['asof']==now.date().isoformat()]),'k100_core_holding_count':len(k100hold),'k100_core_fetch_log':k100log,
           'balance_used_in_selection':False,'position_size_calculated':False,
           'gross_only_no_fills_costs_or_targets':True,
           'caveats':['Date-freshness required; old snapshots are never backfilled as prospective signals',
                      'C3 and K100 Tactical TOP3 inputs are scanner pre-filtered, may include UNKNOWN instrument or unverified liquidity',
                      'Signal-date closing values and source adjustments are not independently exchange-verified',
                      'Close-to-close gross outcomes do not establish ability to execute entry orders or win rates',
                      'Point-in-time universe and survivorship issues are not resolved',
                      'FDR chooses its own backend; source and quote finality not verified',
                      'Legacy v8.0 account=K100 frozen cohorts are archival research, distinct from K100_TACTICAL and current Core',
                      'K100 Core positions derive from latest provided screenshot, not auto-synced to brokerage',
                      'K100 Core technical price references are descriptive, not executable orders',
                      'Changing ranker rules in the future will create mixed-method cohorts; do not pool without stratification',
                      'TOP3 same-day picks overlap; date-balanced results still do not imply independent samples',
                      'Complete C3 and K100_TACTICAL as-of-date TOP3 groups remain frozen on any same-day rerun',
                      'C3/K100 Tactical balances and per-share affordability intentionally do not influence rankings or price levels']}
    (out/'v83_prospective_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False))

if __name__=='__main__':main()
