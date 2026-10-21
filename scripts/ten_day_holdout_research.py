#!/usr/bin/env python3
"""10-trading-session research holdout; not an executable trading strategy.

Input: window,ticker,return_10d_pct,top10,ma20_up,above_ma60,
above_ma20,prior5_pct,volume5_20. Features must be observed BEFORE
the 10-session return window. No future-return fields are used in rules.
"""
import argparse,csv,statistics
from collections import defaultdict
from pathlib import Path

def eligible(row):
    try:
        ratio=float(row["volume5_20"])
        return row["ma20_up"]=="1" and 1.2<=ratio<=3.0
    except (ValueError,TypeError,KeyError):
        return False

def summarize(rows,train_end=12):
    out=[]
    for scope,subset in (
        ("TRAIN",[r for r in rows if int(r["window"])<=train_end]),
        ("HOLDOUT",[r for r in rows if int(r["window"])>train_end]),
    ):
        for label,group in (("ALL",subset),("MA20_UP_VOLUME_1_2_TO_3",list(filter(eligible,subset)))):
            returns=[float(r["return_10d_pct"]) for r in group]
            hits=sum(str(r["top10"]).lower()=="true" for r in group)
            out.append({"scope":scope,"rule":label,"n":len(group),"top10_hits":hits,
                        "mean_return_pct":round(statistics.mean(returns),3) if returns else "",
                        "median_return_pct":round(statistics.median(returns),3) if returns else "",
                        "positive_rate":round(sum(x>0 for x in returns)/len(returns),4) if returns else "",
                        "top10_rate":round(hits/len(group),4) if group else "",
                        "trade_approval":"NO"})
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("input_csv",type=Path)
    p.add_argument("--out",type=Path,default=Path("ten_day_holdout.csv"))
    a=p.parse_args()
    with a.input_csv.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
    if not rows:raise SystemExit("EMPTY_INPUT")
    result=summarize(rows)
    with a.out.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(result[0]))
        w.writeheader();w.writerows(result)
    for r in result:print(r)
    print("RESEARCH_ONLY: close-to-close retrospective returns; no execution, costs, or stop modeled")

if __name__=="__main__":main()
