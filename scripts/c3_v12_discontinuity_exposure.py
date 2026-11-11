#!/usr/bin/env python3
"""Frozen-window 410 raw-close discontinuity exposure, no outcome data changes.
Ex post audit only. ALL original 129 cohort events/51 new stay unchanged.
Source regular session and corporate actions remain uncertified.
"""
import argparse,json
from collections import Counter,defaultdict
from pathlib import Path
from c3_v11_entry_geometry_diagnostic import read_history

def flagged(prev_close,cur_close):
    return cur_close>=1.5*prev_close or cur_close<=prev_close*(2/3)

def audit(root,cohort):
    days,by,bydate=read_history(root)
    idx={d:i for i,d in enumerate(days)}
    gaps=defaultdict(list);counter=Counter()
    for ticker,bars in by.items():
        for p,c in zip(bars,bars[1:]):
            if flagged(p["close"],c["close"]):
                delta=idx[c["date"]]-idx[p["date"]]
                counter["GAP_AFTER_MISSING_TICKER_SESSION" if delta>1 else "CONSECUTIVE_MARKET_SESSION"]+=1
                gaps[ticker].append((idx[c["date"]],delta))
    if sum(counter.values())!=410:raise ValueError("FROZEN_410_CHANGED")
    e=cohort.get("events",[])
    if len(e)!=129:raise ValueError("FROZEN_129_COHORT_CHANGED")
    groups={"ALL":e,"INDEPENDENT_POST_SEP16":[x for x in e if x["date"]>="2026-09-16"]}
    result={}
    for group,rows in groups.items():
        counts=Counter()
        evidence=[]
        for ev in rows:
            ticker,day=ev["ticker"],ev["date"]
            if day not in idx:raise ValueError("MISSING_SELECTION_DAY")
            si=idx[day]
            hit={}
            for label,lo,hi in (
                ("ASOF_60_BARS",-60,0),("ASOF_20_BARS",-20,0),
                ("FORWARD_5",1,5),("FORWARD_10",1,10),("FORWARD_20",1,20)):
                matches=[(days[m],g) for m,g in gaps[ticker] if lo<=m-si<=hi]
                hit[label]=bool(matches)
                counts[label]+=bool(matches)
                counts[label+"_ADJACENT_MARKET_SESSION"]+=any(g==1 for _,g in matches)
            if any(hit.values()):evidence.append({"ticker":ticker,"date":day,"windows":hit})
        result[group]={"selection_events":len(rows),"counts":dict(counts),"flagged_event_evidence":evidence}
    return {
        "schema":"C3_V12_FROZEN_ANOMALY_EXPOSURE_WINDOWS",
        "original_selection_events":len(e),
        "original_new_independent_period_events":len(groups["INDEPENDENT_POST_SEP16"]),
        "total_price_discontinuities":sum(counter.values()),
        "price_discontinuity_types":dict(counter),
        "groups":result,
        "not_proof_of_corporate_action_correction":True,
        "not_proof_1530_only_regular_prices":True,
        "not_complete_inventory_below_50pct_rise_or_33pct_fall":True,
        "financial_pit_promoted":False,
        "new_strategy_weights":False,"orders_enabled":False,"decision":"CASH"
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True,type=Path)
    p.add_argument("--cohort",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    report=audit(a.root,json.loads(a.cohort.read_text()))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("C3_V12_ANOMALY_EXPOSURE",json.dumps({k:v for k,v in report.items() if k!="groups"},ensure_ascii=False))
    print("C3_V12_WINDOW_GROUPS",json.dumps({k:v["counts"] for k,v in report["groups"].items()}))
if __name__=="__main__":main()
