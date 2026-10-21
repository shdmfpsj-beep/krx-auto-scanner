#!/usr/bin/env python3
"""Compare staged allocations on the SAME historical OHLC signals.

Second support is computed using ONLY bars available at signal close:
median low in the preceding five sessions, provided stop < support < next open.
No hindsight support selection. Results are research only, not trade advice.
"""
import argparse,csv,json
from collections import defaultdict,Counter
from pathlib import Path
from kiwoom_ten_day_pipeline import valid
from staged_entry_research import SPLITS,simulate
from kiwoom_execution_audit import setup,pivot_stop

def compare(rows,asof,horizon=5):
    by=defaultdict(dict)
    for r in rows:
        if valid(r) and r["Date"]<=asof:by[r["ticker"]][r["Date"]]=r
    output=[]
    for ticker,series in sorted(by.items()):
        bars=[{"date":d,"open":float(r["Open"]),"high":float(r["High"]),
               "low":float(r["Low"]),"close":float(r["Close"])}
              for d,r in sorted(series.items())]
        next_allowed=65
        for i in range(65,len(bars)-horizon):
            if i<next_allowed or not setup(bars,i):continue
            stop=pivot_stop(bars,i)
            if stop is None:continue
            recent_lows=sorted(b["low"] for b in bars[max(0,i-4):i+1])
            support=recent_lows[len(recent_lows)//2]
            entry=bars[i+1]["open"]
            if not stop<support<entry:continue
            cohort=[]
            for key,split in SPLITS.items():
                r=simulate(bars,i,split=split,horizon=horizon,
                           second_limit=support if split[1] else None)
                cohort.append({"ticker":ticker,"signal_date":bars[i]["date"],
                               "second_support":support,"strategy":key,**r})
            # Preserve comparability: all four must produce a terminal or
            # ambiguous outcome on exactly the same signal.
            if any("net_account_pct" not in r and not str(r.get("status","")).startswith("AMBIGUOUS")
                   for r in cohort):continue
            output.extend(cohort)
            next_allowed=i+horizon+1
    return output

def summarize(rows,asof):
    summary={"asof":asof,"signals":len(rows)//len(SPLITS),
             "full_krx_universe_verified":False,"trade_approval":"NO",
             "strategies":{},"limitations":[
                 "no intraday ordering for ambiguous OHLC candles",
                 "hypothetical next-open fills and 30bps friction",
                 "no liquidity/slippage simulation",
                 "historical universe may have survivorship bias"]}
    for key in SPLITS:
        group=[r for r in rows if r["strategy"]==key]
        resolved=[r for r in group if r.get("net_account_pct") is not None]
        vals=[r["net_account_pct"] for r in resolved]
        summary["strategies"][key]={
            "observations":len(group),"resolved":len(resolved),
            "ambiguous":len(group)-len(resolved),
            "second_fill_rate_pct":round(100*sum(r.get("second_filled",False) for r in resolved)/len(resolved),2) if resolved else None,
            "mean_net_account_pct":round(sum(vals)/len(vals),4) if vals else None,
            "worst_net_account_pct":round(min(vals),4) if vals else None,
            "positive_pct":round(100*sum(v>0 for v in vals)/len(vals),2) if vals else None}
    return summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--bars",type=Path,required=True)
    p.add_argument("--asof",required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    with a.bars.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
    result=compare(rows,a.asof)
    a.out.mkdir(parents=True,exist_ok=True)
    cols=["ticker","signal_date","second_support","strategy","setup","status",
          "second_filled","invested_fraction","average_entry","stop","exit",
          "net_account_pct","trade_approval"]
    with (a.out/"staged_comparison.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols,extrasaction="ignore")
        w.writeheader();w.writerows(result)
    summary=summarize(result,a.asof)
    (a.out/"staged_comparison_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
