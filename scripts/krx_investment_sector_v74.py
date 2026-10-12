#!/usr/bin/env python3
"""v7.4 bounded independent queue OHLCV validation, historical research only.
Uses v7.3 queue and frozen market snapshot; never authorizes trades.
"""
import argparse,csv,json,math,os,time
from datetime import date,timedelta
from pathlib import Path

def read(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,rows,cols):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp')
    with open(tmp,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)
    os.replace(tmp,p)
def num(x):
    try:
        v=float(x);return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None
def validate(rows,asof,close):
    if len(rows)<31:return 'LESS_THAN_31_SESSIONS'
    dates=[r.get('Date','') for r in rows]
    if len(set(dates))!=len(dates) or dates!=sorted(dates):return 'DUPLICATE_OR_UNSORTED_DATES'
    if dates[-1]!=asof:return 'LAST_DATE_MISMATCH'
    for r in rows:
        o,h,l,c,v=[num(r.get(k)) for k in ('Open','High','Low','Close','Volume')]
        if any(x is None for x in (o,h,l,c,v)) or min(o,h,l,c)<=0 or v<0 or h<max(o,c,l) or l>min(o,c):return 'INVALID_OHLCV'
    if close is None or close<=0:return 'INVALID_SNAPSHOT'
    if abs(num(rows[-1]['Close'])/close-1)>0.03:return 'CLOSE_MISMATCH_GT_3PCT'
    return 'VALID'
def normalize(df,asof):
    out=[]
    for idx,r in df.iterrows():
        d=str(idx.date() if hasattr(idx,'date') else idx)[:10]
        if d>asof:continue
        vals=[num(r.get(k)) for k in ('Open','High','Low','Close','Volume')]
        if any(v is None for v in vals):continue
        out.append(dict(zip(('Date','Open','High','Low','Close','Volume'),(d,*vals))))
    return sorted(out,key=lambda x:x['Date'])
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--queue',default='reports/v73_independent_research_queue.csv')
    p.add_argument('--market',default='reports/market_data_v56_merged.csv')
    p.add_argument('--cache',default='reports/v36_ohlcv_cache')
    p.add_argument('--outdir',default='reports')
    p.add_argument('--limit',type=int,default=30)
    p.add_argument('--sleep',type=float,default=0.5)
    p.add_argument('--offline',action='store_true')
    a=p.parse_args()
    if not 1<=a.limit<=30 or a.sleep<0:p.error('limit must be 1..30 and sleep nonnegative')
    q=read(a.queue);m=read(a.market)
    if not q or len(q)>30:raise SystemExit('INVALID_QUEUE_SIZE')
    asofs={r['snapshot_date'] for r in q}|{r['snapshot_date'] for r in m}
    if len(asofs)!=1:raise SystemExit('SNAPSHOT_DATE_MISMATCH')
    asof=asofs.pop();dt=date.fromisoformat(asof)
    markets={r['ticker'].zfill(6):r for r in m}
    codes=[r['ticker'].zfill(6) for r in q]
    if len(codes)!=len(set(codes)) or any(t not in markets for t in codes):raise SystemExit('INVALID_QUEUE_TICKERS')
    cache=Path(a.cache);cache.mkdir(parents=True,exist_ok=True)
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    start=(dt-timedelta(days=120)).isoformat();end=(dt+timedelta(days=1)).isoformat()
    result=[];fdr=None
    for item in q[:a.limit]:
        ticker=item['ticker'].zfill(6);snap=markets[ticker];close=num(snap['close']);fp=cache/f'{ticker}.csv'
        if snap.get('dated_ohlcv_valid','').lower()!='true':
            result.append({'ticker':ticker,'name':item['name'],'status':'FAILED','reason':'INVALID_MARKET_SNAPSHOT','rows':0,'source':''});continue
        previous='NO_CACHE'
        if fp.is_file():
            try:
                old=read(fp);previous=validate(old,asof,close)
                if previous=='VALID':
                    result.append({'ticker':ticker,'name':item['name'],'status':'CACHE_REUSED','reason':'','rows':len(old),'source':'CACHE'});continue
            except Exception as e:previous='CACHE_READ_'+type(e).__name__
        if a.offline:
            result.append({'ticker':ticker,'name':item['name'],'status':'MISSING','reason':previous,'rows':0,'source':''});continue
        if fdr is None:
            try:import FinanceDataReader as fdr
            except ImportError:raise SystemExit('Missing finance-datareader dependency')
        status='FAILED';reason='';rows=[]
        try:
            frame=fdr.DataReader('NAVER:'+ticker,start,end)
            rows=normalize(frame,asof)
            reason=validate(rows,asof,close)
            if reason=='VALID':
                write(fp,rows,['Date','Open','High','Low','Close','Volume']);status='COLLECTED_VALID';reason=''
        except Exception as e:reason=type(e).__name__+': '+str(e)[:140]
        result.append({'ticker':ticker,'name':item['name'],'status':status,'reason':reason,'rows':len(rows),'source':'NAVER' if status=='COLLECTED_VALID' else ''})
        if a.sleep:time.sleep(a.sleep)
    cols=['ticker','name','status','reason','rows','source'];write(out/'v74_independent_history_validation.csv',result,cols)
    report={'version':'7.4','asof':asof,'queue_total':len(q),'processed':len(result),'cache_reused':sum(r['status']=='CACHE_REUSED' for r in result),'collected_valid':sum(r['status']=='COLLECTED_VALID' for r in result),'missing_or_failed':sum(r['status'] in ('MISSING','FAILED') for r in result),'offline':a.offline,'trade_authorized':False,'status':'HISTORICAL_RESEARCH_ONLY','limitations':['Historical 2026-10-08 snapshot, not live','Only selected 30 independent names, not full-market validated','3% close tolerance does not verify corporate-action adjustments','No simulation or final TOP3 until validated histories and common scoring']}
    (out/'v74_independent_history_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
