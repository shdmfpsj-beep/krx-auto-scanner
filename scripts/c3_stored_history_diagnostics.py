#!/usr/bin/env python3
"""Research-only diagnostics from stored KRX bars; never report P&L as certified."""
import argparse,json
from collections import Counter,defaultdict
from pathlib import Path
from official_krx_120d_replay import weekdays,history
from c3_three_entry_replay import MODELS,signals,evaluate

def diagnose(rows):
    by=defaultdict(list)
    for r in rows:
        b={"ticker":r["ticker"],"date":r["date"]}
        for k in ("open","high","low","close","volume"):b[k]=float(r[k])
        by[r["ticker"]].append(b)
    signals_by=Counter();fills=Counter();unfilled=Counter();ambiguous=Counter()
    duplicate_dates=Counter();overlap=Counter();locked=Counter()
    examples=[]
    for ticker,bars in by.items():
        bars.sort(key=lambda b:b["date"])
        next_allowed={m:60 for m in MODELS}
        for i in range(60,len(bars)-1):
            events=signals(bars,i)
            if len(events)>1:overlap["multi_model_same_ticker_date"]+=1
            for model,entry,stop,target in events:
                signals_by[model]+=1
                if i<next_allowed[model]:
                    locked[model]+=1;continue
                e=evaluate(bars,i,model,entry,stop,target)
                if e["filled"]:
                    fills[model]+=1
                    if any(v["status"]=="CENSORED_ENTRY_SEQUENCE_UNCERTAIN" for v in e["outcomes"].values()):
                        ambiguous[model]+=1
                    next_allowed[model]=i+21
                else:unfilled[model]+=1
                if len(examples)<12:
                    examples.append({"ticker":ticker,"date":bars[i]["date"],"model":model,
                        "entry":e["entry"],"stop":e["stop"],"target":e["resistance"],
                        "filled":e["filled"],"outcomes":{h:v["status"] for h,v in e["outcomes"].items()}})
    return {"status":"EXPLORATORY_SIGNAL_DIAGNOSTICS_NOT_PERFORMANCE",
      "unique_tickers":len(by),"signals":dict(signals_by),"filled_research":dict(fills),
      "unfilled":dict(unfilled),"lockout_suppressed":dict(locked),
      "same_ticker_date_multi_model":overlap["multi_model_same_ticker_date"],
      "ambiguous_entry_day":dict(ambiguous),"examples":examples,
      "financial_pit_cohort_applied":False,"historical_returns_certified":False,
      "performance_publication_allowed":False,"trade_approved":False,"decision":"CASH"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True)
    p.add_argument("--end",required=True);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    rows,_=history(a.root,weekdays(a.end,160))
    report=diagnose(rows)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("C3_STORED_HISTORY_SIGNAL_DIAGNOSTICS",json.dumps({k:v for k,v in report.items() if k!="examples"},ensure_ascii=False))
if __name__=="__main__":main()
