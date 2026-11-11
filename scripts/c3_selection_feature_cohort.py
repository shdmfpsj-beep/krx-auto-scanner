#!/usr/bin/env python3
"""Read-only selection feature cohort study with per-ticker 20-session de-duplication.
No historical financial PIT, verified investor flows, trading orders or certified P&L.
"""
import argparse,json
from collections import defaultdict
from pathlib import Path
from official_krx_120d_replay import history,weekdays
from c3_selection_first_research import candidate,selection_outcome

FEATURES=("momentum_20d_pct","rvol_20d","ma20_extension_pct","ma20_vs_ma60_pct","stop_distance_pct")
def cohort(rows,lockout=20):
    by=defaultdict(list)
    for r in rows:
        b={"ticker":str(r["ticker"]),"date":str(r["date"])}
        for k in ("open","high","low","close","volume"):b[k]=float(r[k])
        by[b["ticker"]].append(b)
    pool=defaultdict(list)
    for ticker,bars in by.items():
        bars.sort(key=lambda x:x["date"])
        if len(set(x["date"] for x in bars))!=len(bars):raise ValueError("DUPLICATE_TICKER_DATE")
        for i in range(60,len(bars)):
            c=candidate(bars,i,{},None)
            if c is None:continue
            h=bars[:i+1];ma20=sum(x["close"] for x in h[-20:])/20
            ma60=sum(x["close"] for x in h[-60:])/60
            f={"momentum_20d_pct":c["momentum_20d_pct"],"rvol_20d":c["rvol_20d"],
               "ma20_extension_pct":round((h[-1]["close"]/ma20-1)*100,4),
               "ma20_vs_ma60_pct":round((ma20/ma60-1)*100,4),
               "stop_distance_pct":round((c["entry1_range"][1]/c["stop"]-1)*100,4)}
            pool[bars[i]["date"]].append((ticker,bars,i,c,f))
    next_allowed=defaultdict(int);raw=0;events=[];suppressed=0
    for day in sorted(pool):
        selected=sorted(pool[day],key=lambda x:(-x[0+3]["research_proxy"],x[0]))[:2]
        raw+=len(selected)
        for ticker,bars,i,c,features in selected:
            if i<next_allowed[ticker]:
                suppressed+=1;continue
            next_allowed[ticker]=i+lockout+1
            events.append({"ticker":ticker,"date":day,"features":features,
                "outcomes":selection_outcome(bars,i)})
    groups={}
    for n in (5,10,20):
        h=str(n);observed=[e for e in events if e["outcomes"][h]["status"]=="OBSERVED_EXPLORATORY"]
        rising=[e for e in observed if e["outcomes"][h]["close_return_pct"]>0]
        falling=[e for e in observed if e["outcomes"][h]["close_return_pct"]<=0]
        def stats(group):
            if not group:return {"count":0,"means":None}
            fields={k:round(sum(e["features"][k] for e in group)/len(group),4) for k in FEATURES}
            fields.update({k:round(sum(e["outcomes"][h][k] for e in group)/len(group),4)
              for k in ("close_return_pct","mfe_pct","mae_pct")})
            return {"count":len(group),"means":fields}
        groups[h]={"observed":len(observed),"rising":stats(rising),"non_rising":stats(falling),
            "censored":len(events)-len(observed)}
    return {"status":"EXPLORATORY_DEDUPED_SELECTION_FEATURES",
        "raw_daily_top2_events":raw,"deduplicated_events":len(events),
        "same_ticker_20_session_suppressed":suppressed,"lockout_sessions":lockout,
        "horizon_groups":groups,"events":events,
        "feature_differences_are_descriptive_not_validated_predictors":True,
        "financial_pit":"UNVERIFIED","benchmark_relative_strength":"UNVERIFIED",
        "foreign_institutional_flow":"UNVERIFIED",
        "operational_top2_same_date":"UNVERIFIED",
        "historical_returns_certified":False,"performance_publication_allowed":False,
        "trade_approved":False,"decision":"CASH"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True)
    p.add_argument("--end",required=True);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();r=cohort(history(a.root,weekdays(a.end,160))[0])
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n")
    print("C3_DEDUPED_SELECTION_FEATURES",json.dumps({k:v for k,v in r.items() if k!="events"},ensure_ascii=False))
if __name__=="__main__":main()
