#!/usr/bin/env python3
"""Walk-forward descriptive staged-entry evaluation without future parameter tuning.

Predeclared 2026-07-31 split: development <= July, holdout >= August.
This is a temporal audit of fixed rules, NOT a clean prospective validation:
the watchlist is selected using current information (survivorship bias).
"""
import argparse,csv,json,statistics
from pathlib import Path
from staged_entry_research import SPLITS

def metrics(rows):
    out={}
    for key in SPLITS:
        vals=[]
        for r in rows:
            try:vals.append(float(r[key+"_net_account_pct"]))
            except (KeyError,TypeError,ValueError):pass
        out[key]={"n":len(vals),
                  "mean_net_account_pct":round(statistics.mean(vals),4) if vals else None,
                  "worst_net_account_pct":round(min(vals),4) if vals else None,
                  "positive_pct":round(100*sum(x>0 for x in vals)/len(vals),2) if vals else None}
    return out

def analyze(rows,cutoff="2026-07-31",min_holdout=100):
    train=[r for r in rows if r.get("signal_date","")<=cutoff]
    hold=[r for r in rows if r.get("signal_date","")>cutoff]
    result={"cutoff":cutoff,"train":metrics(train),"holdout":metrics(hold),
            "train_n":len(train),"holdout_n":len(hold),
            "minimum_holdout_n":min_holdout,
            "holdout_sample_sufficient":len(hold)>=min_holdout,
            "trade_approval":"NO",
            "warnings":["Current-day watchlist used historically: not point-in-time",
                        "Fixed rules; no genuine historical universe reconstruction",
                        "Daily OHLC, ambiguous paths excluded, 30bps cost proxy"]}
    base=result["holdout"]["A_100_0"]["mean_net_account_pct"]
    result["holdout_deltas_vs_full_pctpt"]={
        key:round(x["mean_net_account_pct"]-base,4)
        if x["mean_net_account_pct"] is not None and base is not None else None
        for key,x in result["holdout"].items() if key!="A_100_0"}
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--paired",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--cutoff",default="2026-07-31")
    a=p.parse_args()
    with a.paired.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
    result=analyze(rows,a.cutoff)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("STAGED_TEMPORAL_HOLDOUT="+json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
