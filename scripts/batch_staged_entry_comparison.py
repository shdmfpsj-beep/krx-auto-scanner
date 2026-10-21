#!/usr/bin/env python3
"""Paired retrospective staged-entry research over the SAME historical signals.

Evidence input is current watchlist, NOT point-in-time full KRX.
Second support is the lowest low of prior 10 completed bars above structural
stop, calculated at signal close (no future information). No 2nd price guess.
No fills when daily OHLC makes order uncertain; such observations excluded.
"""
import argparse,csv,json,statistics
from collections import Counter,defaultdict
from pathlib import Path
from batch_five_day_setup_audit import load
from staged_entry_research import SPLITS,simulate
from five_day_setup_comparison import setup,pivot_stop

def second_support(bars,i,stop,entry):
    lows=[float(b["low"]) for b in bars[max(0,i-9):i+1]]
    eligible=[v for v in lows if stop<v<entry]
    return min(eligible) if eligible else None

def compare(prices,asof,horizon=5):
    records=[]
    for ticker,bars in sorted(prices.items()):
        next_allowed=65
        for i in range(65,len(bars)-horizon):
            if i<next_allowed or bars[i+horizon]["date"]>asof:continue
            label=setup(bars,i)
            if not label:continue
            stop=pivot_stop(bars,i)
            if stop is None:continue
            entry=float(bars[i+1]["open"])
            if entry<=stop:continue
            if not .02<=(entry-stop)/entry<=.12:continue
            limit=second_support(bars,i,stop,entry)
            # Require support for a fair paired comparison of all 4 splits.
            if limit is None:continue
            outcomes={}
            for name,split in SPLITS.items():
                result=simulate(bars,i,split=split,horizon=horizon,
                                second_limit=limit if split[1] else None)
                outcomes[name]=result
            if not all("net_account_pct" in r for r in outcomes.values()):
                continue
            records.append({"ticker":ticker,"signal_date":bars[i]["date"],
                            "setup":label,"structural_stop":stop,
                            "second_support":limit,**{
                                name+"_net_account_pct":outcomes[name]["net_account_pct"]
                                for name in SPLITS},**{
                                name+"_second_filled":outcomes[name]["second_filled"]
                                for name in SPLITS}})
            next_allowed=i+horizon+1
    return records

def summary(records):
    by={}
    for name in SPLITS:
        vals=[r[name+"_net_account_pct"] for r in records]
        by[name]={"paired_trades":len(vals),
                  "mean_net_account_pct":round(statistics.mean(vals),4) if vals else None,
                  "median_net_account_pct":round(statistics.median(vals),4) if vals else None,
                  "positive_fraction":round(sum(v>0 for v in vals)/len(vals),4) if vals else None,
                  "worst_trade_account_pct":min(vals) if vals else None,
                  "second_fill_count":sum(bool(r[name+"_second_filled"]) for r in records)}
    return {"paired_observations":len(records),"strategies":by,
            "universe":"CURRENT_WATCHLIST_ONLY","point_in_time_universe":False,
            "trade_approval":"NO","limitations":[
                "selection bias from present-day watchlist",
                "daily OHLC cannot determine intraday order sequence",
                "ambiguous paths excluded from paired sample",
                "historical support approximated from 10-bar lows",
                "account normalized, fractional shares, 30bps flat costs",
                "not a portfolio-level drawdown or full-KRX backtest"]}

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
    records=compare(prices,a.asof)
    a.out.mkdir(parents=True,exist_ok=True)
    fields=["ticker","signal_date","setup","structural_stop","second_support"]
    for name in SPLITS:fields.extend([name+"_net_account_pct",name+"_second_filled"])
    with (a.out/"staged_entry_paired.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(records)
    result=summary(records)
    (a.out/"staged_entry_paired_summary.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("STAGED_ENTRY_PAIRED_SUMMARY="+json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
