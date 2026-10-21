#!/usr/bin/env python3
"""Research-only structural second-entry candidates computed at signal close.

Three alternative, mutually labelled methods. Each uses completed bars only.
Do not interpret an OHLC-derived level as verified intraday executable support.
"""
import argparse,csv,json,statistics
from collections import Counter
from pathlib import Path
from batch_five_day_setup_audit import load
from five_day_setup_comparison import setup,pivot_stop
from staged_entry_research import simulate

METHODS=("PIVOT_RETEST","BREAKOUT_RETEST","SMA20_PULLBACK")

def levels(bars,i,stop,entry):
    if i<65 or not (0<stop<entry):return {}
    out={}
    # Most recent confirmed five-candle swing low: confirmed by 2 later bars.
    for j in range(i-2,max(1,i-20)-1,-1):
        low=float(bars[j]["low"])
        if low<min(float(bars[k]["low"]) for k in (j-2,j-1)) and low<=min(
                float(bars[k]["low"]) for k in (j+1,j+2)):
            if stop<low<entry and all(float(bars[k]["close"])>=low for k in range(j+1,i+1)):
                out["PIVOT_RETEST"]=low
                break
    # Previously broken 20-session high, established before signal session.
    old_high=max(float(b["high"]) for b in bars[i-20:i])
    if (stop<old_high<entry and float(bars[i-1]["close"])<=old_high
            and float(bars[i]["close"])>old_high):
        out["BREAKOUT_RETEST"]=old_high
    # 20-session average through signal close, not a future moving average.
    ma20=statistics.mean(float(b["close"]) for b in bars[i-19:i+1])
    if stop<ma20<entry:
        out["SMA20_PULLBACK"]=round(ma20,4)
    return out

def compare(prices,asof,horizon=5):
    rows=[]
    counts=Counter()
    for ticker,bars in sorted(prices.items()):
        next_allowed=65
        for i in range(65,len(bars)-horizon):
            if i<next_allowed or bars[i+horizon]["date"]>asof:continue
            label=setup(bars,i)
            if not label:continue
            stop=pivot_stop(bars,i)
            if stop is None:continue
            entry=float(bars[i+1]["open"])
            if entry<=stop or not .02<=(entry-stop)/entry<=.12:continue
            candidates=levels(bars,i,stop,entry)
            counts["signals_eligible"]+=1
            baseline=simulate(bars,i,split=(1.,0.),horizon=horizon)
            if "net_account_pct" not in baseline:
                counts["baseline_unresolved"]+=1
                next_allowed=i+horizon+1
                continue
            for method in METHODS:
                limit=candidates.get(method)
                if limit is None:
                    counts[method+"_no_level"]+=1
                    continue
                result=simulate(bars,i,split=(.6,.4),horizon=horizon,second_limit=limit)
                if "net_account_pct" not in result:
                    counts[method+"_unresolved"]+=1
                    continue
                counts[method+"_paired"]+=1
                rows.append({"ticker":ticker,"signal_date":bars[i]["date"],
                    "setup":label,"method":method,"second_limit":round(limit,4),
                    "second_filled":result["second_filled"],
                    "full_net_account_pct":baseline["net_account_pct"],
                    "split_net_account_pct":result["net_account_pct"],
                    "delta_pctpt":round(result["net_account_pct"]-baseline["net_account_pct"],4)})
            next_allowed=i+horizon+1
    return rows,dict(counts)

def summarize(rows,counts):
    out={"trade_approval":"NO","universe":"CURRENT_WATCHLIST_ONLY",
         "counts":counts,"methods":{},"limitations":[
             "same current watchlist retroactively selected; no point-in-time universe",
             "daily OHLC ambiguous paths excluded; may bias outcomes",
             "methods have different eligible subsets: do not rank raw means across methods",
             "no independent parameter optimization or portfolio drawdown"]}
    for method in METHODS:
        x=[r for r in rows if r["method"]==method]
        d=[r["delta_pctpt"] for r in x]
        out["methods"][method]={"paired_n":len(x),
          "mean_delta_pctpt":round(statistics.mean(d),4) if d else None,
          "median_delta_pctpt":round(statistics.median(d),4) if d else None,
          "filled_n":sum(str(r["second_filled"]).lower()=="true" for r in x),
          "outperform_count":sum(v>0 for v in d)}
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--watchlist",type=Path,required=True)
    p.add_argument("--asof",required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    with a.watchlist.open(encoding="utf-8-sig",newline="") as f:
        tickers={r["ticker"] for r in csv.DictReader(f)}
    prices=load(a.evidence,tickers,a.asof)
    rows,counts=compare(prices,a.asof)
    a.out.mkdir(parents=True,exist_ok=True)
    fields=["ticker","signal_date","setup","method","second_limit","second_filled",
            "full_net_account_pct","split_net_account_pct","delta_pctpt"]
    with (a.out/"structural_support_comparison.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    result=summarize(rows,counts)
    (a.out/"structural_support_summary.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("STRUCTURAL_SUPPORT_SUMMARY="+json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
