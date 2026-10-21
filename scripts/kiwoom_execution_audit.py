#!/usr/bin/env python3
"""Conservative next-open execution research, not an executable trade engine.

Signal determined after close t. Enter at t+1 open, provided it has not
already crossed the structural stop. Check entry-day and subsequent daily
OHLC through t+horizon. Stops gap down at open fill OPEN (worse than stop);
target gaps up fill TARGET (conservative). Both intraday hit = ambiguous,
excluded from performance. Non-overlapping positions per ticker.
"""
import argparse,csv,json
from collections import defaultdict,Counter
from pathlib import Path
from five_day_setup_comparison import setup,pivot_stop
from kiwoom_ten_day_pipeline import valid

def outcome(bars,i,horizon=5,cost_bps=30):
    label=setup(bars,i)
    if not label:return None
    stop=pivot_stop(bars,i)
    if stop is None:return {"setup":label,"status":"NO_STRUCTURAL_STOP"}
    if i+horizon>=len(bars):return {"setup":label,"status":"NO_FULL_HORIZON"}
    entry=float(bars[i+1]["open"])
    if entry<=stop:return {"setup":label,"status":"ENTRY_OPEN_BELOW_STOP"}
    risk=(entry-stop)/entry
    if not .02<=risk<=.12:return {"setup":label,"status":"RISK_OUTSIDE_2_TO_12_PCT"}
    target=entry+2*(entry-stop)
    status="TIME_EXIT"
    exit_price=float(bars[i+horizon]["close"])
    for k in range(i+1,i+horizon+1):
        op=float(bars[k]["open"])
        lo=float(bars[k]["low"])
        hi=float(bars[k]["high"])
        if op<=stop:
            status="STOP_GAP_OPEN";exit_price=op;break
        if op>=target:
            status="TARGET_GAP_OPEN";exit_price=target;break
        if lo<=stop and hi>=target:
            status="AMBIGUOUS_SAME_BAR";exit_price=None;break
        if lo<=stop:
            status="STOP_FIRST";exit_price=stop;break
        if hi>=target:
            status="TARGET_FIRST";exit_price=target;break
    net=round((exit_price/entry-1)*100-cost_bps/100,4) if exit_price is not None else None
    return {"setup":label,"status":status,"entry":entry,"stop":stop,
            "target_2r":round(target,4),"risk_pct":round(risk*100,4),
            "net_pct":net,"trade_approval":"NO"}

def evaluate(rows,asof,horizon=5):
    by=defaultdict(dict)
    for r in rows:
        if valid(r) and r["Date"]<=asof:by[r["ticker"]][r["Date"]]=r
    results=[]
    for ticker,dates in sorted(by.items()):
        bars=[{"date":d,"open":float(r["Open"]),"high":float(r["High"]),
               "low":float(r["Low"]),"close":float(r["Close"])}
              for d,r in sorted(dates.items())]
        next_allowed=65
        for i in range(65,len(bars)-horizon):
            if i<next_allowed:continue
            result=outcome(bars,i,horizon)
            if result is None:continue
            if result["status"] in {"NO_STRUCTURAL_STOP","NO_FULL_HORIZON",
                                   "ENTRY_OPEN_BELOW_STOP","RISK_OUTSIDE_2_TO_12_PCT"}:
                continue
            results.append({"ticker":ticker,"signal_date":bars[i]["date"],
                            "entry_date":bars[i+1]["date"],**result})
            next_allowed=i+horizon+1
    return results

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--bars",type=Path,required=True)
    p.add_argument("--asof",required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    with a.bars.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
    results=evaluate(rows,a.asof)
    a.out.mkdir(parents=True,exist_ok=True)
    fields=["ticker","signal_date","entry_date","setup","status","entry","stop",
            "target_2r","risk_pct","net_pct","trade_approval"]
    with (a.out/"execution_audit.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(results)
    summary={"asof":a.asof,"trades":len(results),
             "outcomes":dict(Counter(r["status"] for r in results)),
             "mean_net_pct":round(sum(r["net_pct"] for r in results if r["net_pct"] is not None)/
                                  max(1,sum(r["net_pct"] is not None for r in results)),4),
             "universe_verified_full_krx":False,"trade_approval":"NO",
             "limitations":["daily OHLC, no intraday sequence",
                            "ambiguous same-bar excluded from mean",
                            "no liquidity/slippage model beyond 30bps",
                            "same ticker cooldown only; overlapping tickers possible"]}
    (a.out/"execution_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
