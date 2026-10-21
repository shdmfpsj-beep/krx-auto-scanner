#!/usr/bin/env python3
"""Retrospective monthly TOP10 pre-ignition diagnostic, never a trade signal.

Input: CSV with month,ticker,top,ma20_up,above_ma60,above_ma20,
near_high,pre5,vol_ratio. Features MUST be measured before the
ranking month begins. This script does not download prices.
"""
import argparse,csv
from collections import defaultdict
from pathlib import Path

def compute(rows, cutoff="2026-07"):
    conditions={
        "MA20_UP":lambda r:r["ma20_up"]=="1",
        "ABOVE_MA60":lambda r:r["above_ma60"]=="1",
        "NEAR_HIGH":lambda r:r["near_high"]=="1",
        "TREND_PULLBACK":lambda r:r["above_ma60"]=="1" and -8<=float(r["pre5"])<=0,
        "PREIGNITION_COMBO":lambda r:r["above_ma60"]=="1" and r["ma20_up"]=="1"
            and -8<=float(r["pre5"])<=0 and 0.5<=float(r["vol_ratio"])<=1.2,
    }
    out=[]
    for scope,part in (("TRAIN",[r for r in rows if r["month"]<=cutoff]),
                       ("HOLDOUT",[r for r in rows if r["month"]>cutoff])):
        if not part: continue
        base=sum(r["top"].lower()=="true" for r in part)/len(part)
        for name,rule in conditions.items():
            selected=[r for r in part if rule(r)]
            hits=sum(r["top"].lower()=="true" for r in selected)
            rate=hits/len(selected) if selected else None
            out.append({"scope":scope,"condition":name,"selected":len(selected),
                        "top10_hits":hits,"base_rate":round(base,6),
                        "precision":round(rate,6) if rate is not None else "",
                        "lift":round(rate/base,4) if rate is not None and base else ""})
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("input_csv",type=Path)
    p.add_argument("--out",type=Path,default=Path("preignition_diagnostics.csv"))
    p.add_argument("--cutoff",default="2026-07")
    a=p.parse_args()
    with a.input_csv.open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    if not rows: raise SystemExit("EMPTY_INPUT")
    result=compute(rows,a.cutoff)
    with a.out.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(result[0]))
        writer.writeheader();writer.writerows(result)
    print("RESEARCH_ONLY: retrospective monthly top10 selection, not win probability")
    for r in result:print(r)

if __name__=="__main__": main()
