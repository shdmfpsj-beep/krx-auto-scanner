#!/usr/bin/env python3
"""v6.9 historical sector coverage audit and 5/20 session strength, research only.
Uses existing v6.8 membership, market snapshot and cached daily OHLCV. No network.
"""
import argparse, csv, json, math
from collections import defaultdict
from datetime import date
from pathlib import Path

def readcsv(path):
    with open(path, encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))

def writecsv(path,rows,fields):
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)

def val(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError): return None

def median(xs):
    ys=sorted(xs); n=len(ys)
    return (ys[(n-1)//2]+ys[n//2])/2 if n else None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--members',default='reports/v68_investment_sector_members.csv')
    ap.add_argument('--market',default='reports/market_data_v56_merged.csv')
    ap.add_argument('--cache',default='reports/v36_ohlcv_cache')
    ap.add_argument('--outdir',default='reports')
    a=ap.parse_args(); out=Path(a.outdir); out.mkdir(parents=True,exist_ok=True)
    members=readcsv(a.members); market=readcsv(a.market)
    dates={r.get('snapshot_date','') for r in members}; marketdates={r.get('snapshot_date','') for r in market}
    if len(dates)!=1 or len(marketdates)!=1 or dates!=marketdates: raise SystemExit('Mixed or mismatched snapshot dates')
    asof=next(iter(dates)); date.fromisoformat(asof)
    lookup={r['ticker'].zfill(6):r for r in market}
    unique=sorted({r['ticker'].zfill(6) for r in members})
    audit=[]; usable={}
    for ticker in unique:
        snap=lookup.get(ticker)
        row={'ticker':ticker,'name':snap.get('name','') if snap else '', 'snapshot_date':asof,'history_last_date':'','history_sessions':0,'ret5_pct':'','ret20_pct':'','status':'','reason':''}
        fp=Path(a.cache)/(ticker+'.csv')
        if not snap: row['status']='FAIL';row['reason']='NOT_IN_MARKET_SNAPSHOT'
        elif not fp.exists(): row['status']='FAIL';row['reason']='CACHE_MISSING'
        else:
            try:
                hist=readcsv(fp); hist=sorted(hist,key=lambda r:r.get('Date',''))
                if len({r.get('Date') for r in hist})!=len(hist): raise ValueError('DUPLICATE_DATES')
                hist=[r for r in hist if r.get('Date','')<=asof]
                if not hist: raise ValueError('NO_ASOF_HISTORY')
                row['history_last_date']=hist[-1]['Date'];row['history_sessions']=len(hist)
                if row['history_last_date']!=asof: raise ValueError('STALE_LAST_DATE')
                if len(hist)<21: raise ValueError('LESS_THAN_21_SESSIONS')
                close=[val(r.get('Close')) for r in hist[-21:]]
                if any(x is None or x<=0 for x in close): raise ValueError('INVALID_CLOSE')
                snapclose=val(snap.get('close'))
                if snapclose is None or snapclose<=0: raise ValueError('INVALID_SNAPSHOT_CLOSE')
                if abs(close[-1]/snapclose-1)>0.03: raise ValueError('CLOSE_MISMATCH_GT_3PCT')
                r5=100*(close[-1]/close[-6]-1); r20=100*(close[-1]/close[-21]-1)
                row.update(ret5_pct=round(r5,4),ret20_pct=round(r20,4),status='VALID',reason='')
                usable[ticker]=(r5,r20)
            except (ValueError,KeyError,TypeError,IndexError) as e:
                row['status']='FAIL';row['reason']=str(e)
        audit.append(row)
    grouped=defaultdict(set)
    for r in members: grouped[r['investment_sector']].add(r['ticker'].zfill(6))
    sectors=[]
    for sector,tickers in sorted(grouped.items()):
        matched=[usable[t] for t in tickers if t in usable]; n=len(matched); total=len(tickers)
        five=[x[0] for x in matched]; twenty=[x[1] for x in matched]
        # >= 5 valid and >= 70% sector coverage required for a provisional descriptive metric.
        status='DESCRIPTIVE_ONLY' if n>=5 and n/total>=0.70 else 'INSUFFICIENT_HISTORY'
        sectors.append({'investment_sector':sector,'members':total,'valid_history':n,'coverage_pct':round(100*n/total,2) if total else 0,
                        'median_ret5_pct':round(median(five),3) if status=='DESCRIPTIVE_ONLY' else '',
                        'median_ret20_pct':round(median(twenty),3) if status=='DESCRIPTIVE_ONLY' else '',
                        'breadth5_positive_pct':round(100*sum(x>0 for x in five)/n,2) if status=='DESCRIPTIVE_ONLY' else '',
                        'breadth20_positive_pct':round(100*sum(x>0 for x in twenty)/n,2) if status=='DESCRIPTIVE_ONLY' else '',
                        'status':status})
    writecsv(out/'v69_history_coverage.csv',audit,['ticker','name','snapshot_date','history_last_date','history_sessions','ret5_pct','ret20_pct','status','reason'])
    writecsv(out/'v69_sector_strength.csv',sectors,['investment_sector','members','valid_history','coverage_pct','median_ret5_pct','median_ret20_pct','breadth5_positive_pct','breadth20_positive_pct','status'])
    report={'status':'RESEARCH_NOT_TRADE_READY','asof':asof,'sector_count':len(sectors),'member_tickers':len(unique),'valid_history_tickers':len(usable),'descriptive_sectors':sum(s['status']=='DESCRIPTIVE_ONLY' for s in sectors),
            'cache_directory':str(a.cache),'rules':['Only as-of-matched daily histories','21 sessions minimum','Close snapshot reconciliation <=3%','At least 5 stocks and 70% coverage per sector','Unverified theme membership','No benchmark relative strength, verified flows, catalysts or BUY signals']}
    (out/'v69_sector_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
