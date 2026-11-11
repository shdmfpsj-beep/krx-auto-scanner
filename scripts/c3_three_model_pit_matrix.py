#!/usr/bin/env python3
"""Read-only three-model opportunity matrix; dated financial evidence required."""
import argparse,csv,json
from pathlib import Path
from collections import defaultdict
from c3_three_entry_replay import MODELS,signals,evaluate

def matrix(bars_rows,financial_snapshots):
    by=defaultdict(list)
    for r in bars_rows:by[str(r["ticker"])].append({**r,**{k:float(r[k]) for k in ("open","high","low","close","volume")}})
    snapshots={}
    for s in financial_snapshots:
        ticker=str(s.get("ticker",""));day=str(s.get("asof",""))
        receipt=str(s.get("receipt_date",""))
        if not (len(ticker)==6 and ticker.isdigit() and receipt and receipt<=day and
                s.get("financial_screen_pass") is True and
                s.get("annual_plus_interim_growth_pass") is True and
                s.get("recent_financial_weakening_veto") is False and
                s.get("point_in_time_snapshot_verified") is True):
            continue
        snapshots[(ticker,day)]=s
    rows=[]
    for ticker,bars in by.items():
        bars.sort(key=lambda b:b["date"])
        if len({b["date"] for b in bars})!=len(bars):raise ValueError("DUPLICATE_TICKER_DATE")
        for i in range(60,len(bars)-1):
            day=bars[i]["date"]
            if (ticker,day) not in snapshots:continue
            candidates={x[0]:x for x in signals(bars,i)}
            record={"ticker":ticker,"signal_date":day,"models":{}}
            for name in MODELS:
                if name not in candidates:
                    record["models"][name]={"status":"NO_SIGNAL"}
                else:
                    _,entry,stop,target=candidates[name]
                    event=evaluate(bars,i,name,entry,stop,target)
                    record["models"][name]={"status":"FILLED" if event["filled"] else "UNFILLED",
                                            "entry":event["entry"],"stop":event["stop"],
                                            "hypothetical_target":event["resistance"],
                                            "outcomes":event["outcomes"]}
            rows.append(record)
    return {"status":"EXPLORATORY_PIT_COHORT_ONLY","opportunities":rows,
            "cohort_dates":len(rows),"model_names":list(MODELS),
            "historical_returns_certified":False,"performance_publication_allowed":False,
            "trade_approved":False,"decision":"CASH"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--bars",type=Path,required=True)
    p.add_argument("--financial-snapshots",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    with a.bars.open(newline="",encoding="utf-8-sig") as f:bars=list(csv.DictReader(f))
    evidence=json.loads(a.financial_snapshots.read_text())
    result=matrix(bars,evidence.get("snapshots",[]))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("C3_PIT_MATRIX",json.dumps({"cohort_dates":result["cohort_dates"],"certified":False,"decision":"CASH"}))
if __name__=="__main__":main()
