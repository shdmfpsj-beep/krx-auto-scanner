#!/usr/bin/env python3
"""v7.1: cached, point-in-time investment-sector 5/20 session strength (research only)."""
import argparse, csv, json, math, statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def load(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(path, rows, fields):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w=csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); w.writeheader(); w.writerows(rows)


def num(x):
    try:
        y=float(x)
        return y if math.isfinite(y) else None
    except (ValueError,TypeError): return None


def med(vals):
    return round(statistics.median(vals),6) if vals else ''


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--members',default='reports/v68_investment_sector_members.csv')
    p.add_argument('--market',default='reports/market_data_v56_merged.csv')
    p.add_argument('--cache',default='reports/v36_ohlcv_cache')
    p.add_argument('--outdir',default='reports')
    p.add_argument('--min-members',type=int,default=3)
    p.add_argument('--min-coverage',type=float,default=0.70)
    a=p.parse_args()
    members=load(a.members); market=load(a.market)
    if not members or not market: raise SystemExit('Missing market or membership data')
    dates={r['snapshot_date'] for r in market}|{r['snapshot_date'] for r in members}
    if len(dates)!=1: raise SystemExit('Mixed snapshot dates')
    asof=dates.pop(); datetime.strptime(asof,'%Y-%m-%d')
    market_by={r['ticker'].zfill(6):r for r in market}
    tickers={r['ticker'].zfill(6) for r in members}
    if not tickers.issubset(market_by): raise SystemExit('Membership contains unknown ticker')
    checks={}; metrics={}; cache=Path(a.cache)
    for ticker in sorted(tickers):
        fp=cache/f'{ticker}.csv'; status='VALID'; detail=''; prices=[]
        if not fp.is_file(): status='MISSING_CACHE'
        else:
            try:
                rows=load(fp)
                for r in rows:
                    day=r.get('Date',r.get('date',''))
                    if day > asof: continue
                    close=num(r.get('Close',r.get('close')))
                    if not day or close is None or close<=0: continue
                    prices.append((day,close))
                prices.sort()
                if len({d for d,_ in prices})!=len(prices): status='DUPLICATE_DATES'
                elif len(prices)<21: status='INSUFFICIENT_21_SESSIONS'
                elif prices[-1][0]!=asof: status='STALE_END_DATE'
                else:
                    snap=num(market_by[ticker].get('close'))
                    if snap is None or snap<=0 or abs(prices[-1][1]/snap-1)>0.03:
                        status='SNAPSHOT_CLOSE_MISMATCH'
                    else:
                        c=prices[-1][1]
                        metrics[ticker]={'r5':c/prices[-6][1]-1,'r20':c/prices[-21][1]-1,
                            'p5':prices[-6][1], 'p20':prices[-21][1], 'close':c}
            except Exception as exc: status='CACHE_READ_ERROR'; detail=str(exc)[:160]
        checks[ticker]={'ticker':ticker,'name':market_by[ticker].get('name',''),
                        'status':status,'rows':len(prices),'last_date':prices[-1][0] if prices else '',
                        'detail':detail}
    grouped=defaultdict(set)
    for r in members: grouped[r['investment_sector']].add(r['ticker'].zfill(6))
    sectors=[]; stockrows=[]
    for sector, universe in sorted(grouped.items()):
        good=sorted(universe & metrics.keys()); n=len(universe); coverage=len(good)/n
        r5=[metrics[t]['r5'] for t in good]; r20=[metrics[t]['r20'] for t in good]
        eligible=len(good)>=a.min_members and coverage>=a.min_coverage
        sectors.append({'investment_sector':sector,'members':n,'valid_members':len(good),
            'coverage_pct':round(coverage*100,2),'median_5d_pct':round(med(r5)*100,3) if good else '',
            'median_20d_pct':round(med(r20)*100,3) if good else '',
            'breadth_5d_pct':round(sum(x>0 for x in r5)/len(r5)*100,2) if good else '',
            'breadth_20d_pct':round(sum(x>0 for x in r20)/len(r20)*100,2) if good else '',
            'status':'RESEARCH_READY' if eligible else 'INSUFFICIENT_COVERAGE'})
    # No fabricated benchmark: calculate a 124-stock equal-weight sample benchmark,
    # explicitly label it as a sample benchmark, NOT KOSPI/KOSDAQ or market-wide RS.
    universe_metrics=[metrics[t] for t in sorted(metrics)]
    benchmark={h:statistics.median(m[f'r{h}'] for m in universe_metrics) if universe_metrics else None for h in (5,20)}
    for s in sectors:
        if s['status']=='RESEARCH_READY' and benchmark[5] is not None:
            s['sample_relative_5d_pp']=round(s['median_5d_pct']-benchmark[5]*100,3)
            s['sample_relative_20d_pp']=round(s['median_20d_pct']-benchmark[20]*100,3)
        else: s['sample_relative_5d_pp']=s['sample_relative_20d_pp']=''
    for r in members:
        ticker=r['ticker'].zfill(6); m=metrics.get(ticker)
        stockrows.append({'ticker':ticker,'name':r.get('name',''),
            'investment_sector':r['investment_sector'],'subtheme':r.get('subtheme',''),
            'status':checks[ticker]['status'],'return_5d_pct':round(m['r5']*100,3) if m else '',
            'return_20d_pct':round(m['r20']*100,3) if m else '',
            'theme_exposure_verified':r.get('theme_exposure_verified','')})
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    write(out/'v71_history_coverage.csv',list(checks.values()),['ticker','name','status','rows','last_date','detail'])
    write(out/'v71_sector_strength.csv',sectors,['investment_sector','members','valid_members','coverage_pct','median_5d_pct','median_20d_pct','breadth_5d_pct','breadth_20d_pct','sample_relative_5d_pp','sample_relative_20d_pp','status'])
    write(out/'v71_sector_stock_returns.csv',stockrows,['ticker','name','investment_sector','subtheme','status','return_5d_pct','return_20d_pct','theme_exposure_verified'])
    audit={'asof':asof,'total_unique_members':len(tickers),'valid_history_members':len(metrics),
        'sector_count':len(sectors),'research_ready_sector_count':sum(s['status']=='RESEARCH_READY' for s in sectors),
        'benchmark':'median return of valid unique 124-stock investment-sector sample; NOT entire KRX',
        'benchmark_5d_pct':round(benchmark[5]*100,3) if benchmark[5] is not None else None,
        'benchmark_20d_pct':round(benchmark[20]*100,3) if benchmark[20] is not None else None,
        'limitations':['Historical snapshot only; not a live trading signal',
          'Curated thematic memberships are unverified research hypotheses',
          'Sample relative strength is not KOSPI/KOSDAQ benchmark relative strength',
          'Cross-sector membership overlaps; unique-ticker sample benchmark deduplicated',
          'No turnover, investor flows, or TOP3 trade recommendation calculated']}
    (out/'v71_sector_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False))

if __name__=='__main__':main()
