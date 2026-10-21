#!/usr/bin/env python3
"""Offline-only bridge from normalized daily CSV to 5-session OHLC audit.

Input: ticker,Date,Open,High,Low,Close,Volume; no API credentials required.
Uses only dates <= asof. This audit is descriptive, NOT trade approval.
"""
import argparse,csv,json
from collections import defaultdict,Counter
from pathlib import Path
from five_day_setup_comparison import inspect
from kiwoom_ten_day_pipeline import valid

def evaluate(rows,asof):
    by=defaultdict(dict)
    for r in rows:
        if valid(r) and r["Date"]<=asof:
            by[r["ticker"]][r["Date"]]=r
    results=[]
    for ticker,dates in sorted(by.items()):
        bars=[{"date":d,**{k:float(v[k]) for k in ("open","high","low","close")}}
              for d,r in sorted(dates.items())
              for v in [{"open":r["Open"],"high":r["High"],"low":r["Low"],"close":r["Close"]}]]
        for i in range(65,len(bars)-5):
            x=inspect(bars,i)
            if x:results.append({"ticker":ticker,"signal_date":bars[i]["date"],**x})
    return results

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--bars",type=Path,required=True)
    p.add_argument("--asof",required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    with a.bars.open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    results=evaluate(rows,a.asof)
    a.out.mkdir(parents=True,exist_ok=True)
    fields=["ticker","signal_date","setup","status","entry","stop","target_2r",
            "risk_pct","hypothetical_net_pct","trade_approval"]
    with (a.out/"kiwoom_five_day_audit.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(results)
    summary={"asof":a.asof,"observations":len(results),
        "setup_status_counts":[{"setup":setup,"status":status,"count":n}
            for (setup,status),n in sorted(Counter((r["setup"],r["status"]) for r in results).items())],
        "read_only":True,"trade_approval":"NO",
        "limitations":["hypothetical signal-close entry","gap fills not modeled",
            "overlapping signals","universe completeness not verified"]}
    (a.out/"kiwoom_five_day_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
