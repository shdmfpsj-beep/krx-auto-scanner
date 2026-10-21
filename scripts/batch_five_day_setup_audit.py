#!/usr/bin/env python3
"""Batch historical setup audit from dated evidence daily_prices CSV files.

This is a WATCHLIST-ONLY retrospective audit, not full-KRX TOP10 testing.
Every signal uses historical bars through t; next five daily bars determine
hypothetical outcomes. No future dates beyond evidence asof are used.
"""
import argparse,csv,json
from collections import Counter,defaultdict
from pathlib import Path
from five_day_setup_comparison import inspect

def load(root,tickers,asof):
    bars=defaultdict(dict)
    for market in ("KOSPI","KOSDAQ"):
        folder=root/"market"/"daily_prices"/market
        if not folder.is_dir():continue
        for path in sorted(folder.glob("*.csv")):
            if path.stem>asof:continue
            with path.open(encoding="utf-8-sig",newline="") as f:
                for r in csv.DictReader(f):
                    t=r.get("ticker")
                    if t not in tickers:continue
                    try:
                        d=r["Date"]
                        o,h,l,c=(float(r[k]) for k in ("Open","High","Low","Close"))
                        if not (0<l<=min(o,c)<=max(o,c)<=h):continue
                        bars[t][d]={"date":d,"open":o,"high":h,"low":l,"close":c,
                                    "volume":r.get("Volume","")}
                    except (KeyError,ValueError,TypeError):continue
    return {t:[b[d] for d in sorted(b)] for t,b in bars.items()}

def audit_universe(prices,asof):
    out=[]
    for ticker,bars in sorted(prices.items()):
        for i in range(65,len(bars)-5):
            if bars[i+5]["date"]>asof:break
            r=inspect(bars,i)
            if r:out.append({"ticker":ticker,"signal_date":bars[i]["date"],**r})
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
    observations=audit_universe(prices,a.asof)
    a.out.mkdir(parents=True,exist_ok=True)
    fields=["ticker","signal_date","setup","status","entry","stop","target_2r",
            "risk_pct","hypothetical_net_pct","trade_approval"]
    with (a.out/"five_day_setup_observations.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(observations)
    counts=Counter((r["setup"],r["status"]) for r in observations)
    summary={"asof":a.asof,"scope":"CURRENT_WATCHLIST_ONLY_NOT_FULL_KRX",
             "watchlist_count":len(tickers),"tickers_with_ohlc":len(prices),
             "observations":len(observations),
             "setup_outcome_counts":[{"setup":setup,"status":status,"count":n}
                                     for (setup,status),n in sorted(counts.items())],
             "trade_approval":"NO","limitations":[
                 "signal-close hypothetical fill, not executable",
                 "30bps cost approximation; gap fills and liquidity not modeled",
                 "overlapping observations; no independent win-rate inference",
                 "not an all-KRX or historical top10 universe"]}
    (a.out/"five_day_setup_summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FIVE_DAY_AUDIT_SUMMARY="+json.dumps(summary,ensure_ascii=False))

if __name__=="__main__":main()
