#!/usr/bin/env python3
"""Compare 1/2/3-session research limit orders on the SAME stored KRX signals.
Never submit orders, alter the ledger, or certify investment returns.
"""
import argparse,json
from collections import defaultdict,Counter
from pathlib import Path
from official_krx_120d_replay import weekdays,history
from c3_three_entry_replay import MODELS,signals

def touch(bars,i,entry,stop,expiry):
    for delay in range(1,expiry+1):
        if i+delay>=len(bars):return "CENSORED",None
        b=bars[i+delay]
        if b["open"]<stop:return "GAP_BELOW_STOP_NO_ENTRY",delay
        if b["low"]<=stop:
            # OHLC cannot establish entry-before-stop sequence. Fail closed.
            return "STOP_TOUCHED_SEQUENCE_UNCERTAIN",delay
        if b["low"]<=entry:
            return "FILLED_RESEARCH",delay
    return "UNFILLED",None

def analyze(rows):
    by=defaultdict(list)
    for r in rows:
        b={"ticker":r["ticker"],"date":r["date"]}
        for k in ("open","high","low","close","volume"):b[k]=float(r[k])
        by[b["ticker"]].append(b)
    totals={m:{str(e):Counter() for e in (1,2,3)} for m in MODELS}
    missed={m:Counter() for m in MODELS}
    examples=[];base_signals=Counter()
    for ticker,bars in by.items():
        bars.sort(key=lambda b:b["date"])
        lock={m:60 for m in MODELS}
        for i in range(60,len(bars)-1):
            for model,entry,stop,target in signals(bars,i):
                if i<lock[model]:continue
                base_signals[model]+=1
                statuses={}
                for expiry in (1,2,3):
                    status,delay=touch(bars,i,entry,stop,expiry)
                    totals[model][str(expiry)][status]+=1
                    statuses[str(expiry)]=status
                if statuses["1"]=="UNFILLED":
                    if i+3<len(bars):
                        missed[model]["known_three_session_followup"]+=1
                        if bars[i+3]["close"]>bars[i]["close"]:
                            missed[model]["close_day3_above_signal_close"]+=1
                        if bars[i+3]["close"]>entry:
                            missed[model]["close_day3_above_limit"]+=1
                    else:missed[model]["followup_censored"]+=1
                if len(examples)<12:
                    examples.append({"ticker":ticker,"signal_date":bars[i]["date"],
                        "model":model,"entry":round(entry,4),"stop":round(stop,4),
                        "hypothetical_target":round(target,4),"order_expiry":statuses})
                # Preserve baseline one-day signal lockout semantics.
                if statuses["1"]=="FILLED_RESEARCH":lock[model]=i+21
    return {"status":"EXPLORATORY_ENTRY_EXPIRY_DIAGNOSTICS",
        "baseline_eligible_signals":dict(base_signals),
        "expiry_status_counts":{m:{e:dict(v) for e,v in d.items()} for m,d in totals.items()},
        "one_day_unfilled_followup":{m:dict(v) for m,v in missed.items()},
        "examples":examples,"extended_order_lockout_simulated":False,
        "historical_returns_certified":False,"performance_publication_allowed":False,
        "financial_pit_cohort_applied":False,"trade_approved":False,"decision":"CASH"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True)
    p.add_argument("--end",required=True);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();rows,_=history(a.root,weekdays(a.end,160))
    report=analyze(rows);a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("C3_ENTRY_EXPIRY_DIAGNOSTICS",json.dumps({k:v for k,v in report.items() if k!="examples"},ensure_ascii=False))
if __name__=="__main__":main()
