#!/usr/bin/env python3
"""Paired staged-entry robustness: matched deltas, fill conditioning, monthly splits.

Descriptive only. Overlapping ticker/month observations and current-watchlist
selection make confidence intervals / independent significance inappropriate.
"""
import argparse,csv,json,statistics
from collections import defaultdict
from pathlib import Path
from staged_entry_research import SPLITS

BASE="A_100_0"
def analyze(rows):
    out={"observations":len(rows),"trade_approval":"NO",
         "universe":"CURRENT_WATCHLIST_ONLY",
         "method":"paired strategy difference on identical signals",
         "strategies":{},"by_signal_month":{},
         "limitations":["non-independent overlapping historical observations",
                        "current-watchlist selection bias",
                        "ambiguous candles excluded upstream",
                        "second support proxy not independently validated",
                        "not out-of-sample or portfolio drawdown"]}
    for key in SPLITS:
        if key==BASE:continue
        valid=[]
        for r in rows:
            try:
                a=float(r[BASE+"_net_account_pct"])
                b=float(r[key+"_net_account_pct"])
            except (KeyError,ValueError,TypeError):continue
            valid.append((r,a,b,str(r.get(key+"_second_filled","")).lower() in ("true","1")))
        diff=[b-a for _,a,b,_ in valid]
        filled=[b-a for _,a,b,f in valid if f]
        unfilled=[b-a for _,a,b,f in valid if not f]
        out["strategies"][key]={
            "matched_n":len(diff),
            "mean_delta_vs_full_pctpt":round(statistics.mean(diff),4) if diff else None,
            "median_delta_vs_full_pctpt":round(statistics.median(diff),4) if diff else None,
            "outperformed_full_count":sum(x>0 for x in diff),
            "underperformed_full_count":sum(x<0 for x in diff),
            "equal_count":sum(x==0 for x in diff),
            "second_filled_n":len(filled),
            "filled_mean_delta_pctpt":round(statistics.mean(filled),4) if filled else None,
            "unfilled_mean_delta_pctpt":round(statistics.mean(unfilled),4) if unfilled else None}
    groups=defaultdict(list)
    for r in rows:
        m=str(r.get("signal_date",""))[:7]
        if len(m)==7 and m[4]=="-":groups[m].append(r)
    for month,items in sorted(groups.items()):
        diffs={}
        for key in SPLITS:
            if key==BASE:continue
            ds=[]
            for r in items:
                try:ds.append(float(r[key+"_net_account_pct"])-float(r[BASE+"_net_account_pct"]))
                except (ValueError,KeyError,TypeError):continue
            diffs[key]=round(statistics.mean(ds),4) if ds else None
        out["by_signal_month"][month]={"observations":len(items),"mean_delta_pctpt":diffs}
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--paired",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    with a.paired.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
    result=analyze(rows)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("STAGED_ROBUSTNESS="+json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
