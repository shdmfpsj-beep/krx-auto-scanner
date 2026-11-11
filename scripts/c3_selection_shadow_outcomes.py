#!/usr/bin/env python3
"""Selection-first historical research: no fabricated financial PIT or flow.
Technical-only shadow cohort is NOT equivalent to finance-filtered TOP2.
"""
import argparse,json
from collections import defaultdict
from pathlib import Path
from official_krx_120d_replay import weekdays,history
from c3_selection_first_research import candidate,selection_outcome

def summarize(rows):
    by=defaultdict(list)
    dates=set()
    for r in rows:
        b={"ticker":r["ticker"],"date":r["date"]}
        for k in ("open","high","low","close","volume"):b[k]=float(r[k])
        by[b["ticker"]].append(b);dates.add(b["date"])
    bydate=defaultdict(list)
    for ticker,bars in by.items():
        bars.sort(key=lambda b:b["date"])
        if len({x["date"] for x in bars})!=len(bars):raise ValueError("DUPLICATE_DATE")
        for i in range(60,len(bars)):
            c=candidate(bars,i,{},None)
            if c:bydate[bars[i]["date"]].append((c,bars,i))
    top=[];totals={str(n):{"observed":0,"positive":0,"returns":[],"mfes":[],"maes":[],"target1_touch":0,"target2_touch":0} for n in (5,10,20)}
    for day in sorted(bydate):
        picks=sorted(bydate[day],key=lambda x:(-x[0]["research_proxy"],x[0]["ticker"]))[:2]
        for c,bars,i in picks:
            outcomes=selection_outcome(bars,i)
            for n in (5,10,20):
                k=str(n);o=outcomes[k]
                if o["status"]!="OBSERVED_EXPLORATORY":continue
                t=totals[k];t["observed"]+=1;t["positive"]+=o["close_return_pct"]>0
                t["returns"].append(o["close_return_pct"]);t["mfes"].append(o["mfe_pct"]);t["maes"].append(o["mae_pct"])
                future=bars[i+1:i+n+1]
                t["target1_touch"]+=any(b["high"]>=c["target1"] for b in future)
                t["target2_touch"]+=any(b["high"]>=c["target2"] for b in future)
            if len(top)<12:top.append({"date":day,"ticker":c["ticker"],"entry1_range":c["entry1_range"],"entry2_range":c["entry2_range"],"stop":c["stop"],"target1":c["target1"],"target2":c["target2"],"outcomes":outcomes})
    metrics={}
    for k,t in totals.items():
        n=t["observed"]
        metrics[k]={"observed":n,"positive_close":t["positive"],
            "positive_rate":round(t["positive"]/n,5) if n else None,
            "avg_close_return_pct":round(sum(t["returns"])/n,4) if n else None,
            "avg_mfe_pct":round(sum(t["mfes"])/n,4) if n else None,
            "avg_mae_pct":round(sum(t["maes"])/n,4) if n else None,
            "target1_touches_from_signal_close":t["target1_touch"],
            "target2_touches_from_signal_close":t["target2_touch"]}
    return {"status":"TECHNICAL_ONLY_SHADOW_NOT_FINANCIAL_TOP2","observed_market_dates":len(dates),
        "shadow_selection_dates":len(bydate),"shadow_selection_events":sum(min(2,len(x)) for x in bydate.values()),
        "horizon_metrics":metrics,"examples":top,
        "financial_filter_before_after_comparison":"BLOCKED_NO_VERIFIED_HISTORICAL_PIT",
        "operational_top2_comparison":"BLOCKED_NO_DATED_OPERATIONAL_SNAPSHOT",
        "benchmark_relative_strength":"UNVERIFIED","institutional_foreign_flow":"UNVERIFIED",
        "trade_pnl_measured":False,"corporate_actions_certified":False,
        "historical_returns_certified":False,"performance_publication_allowed":False,
        "trade_approved":False,"decision":"CASH"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--end",required=True);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();rows,_=history(a.root,weekdays(a.end,160))
    r=summarize(rows);a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n")
    print("C3_SELECTION_SHADOW_OUTCOMES",json.dumps({k:v for k,v in r.items() if k!="examples"},ensure_ascii=False))
if __name__=="__main__":main()
