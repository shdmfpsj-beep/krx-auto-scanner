#!/usr/bin/env python3
"""Research-only 5-session entry setup comparison using daily OHLC.

Input per-ticker CSV: date,open,high,low,close,volume (ascending dates).
Each signal uses bars through date t, with conditional signal-close entry.
This is NOT a claim of executable closing-price fills. Stops are recent
completed pivot lows held through t. The next five candles determine
outcomes; same-bar stop and target are ambiguous, never wins.
"""
import argparse,csv,json,math
from pathlib import Path

def pivot_stop(bars,i,lookback=20):
    candidates=[]
    for j in range(max(2,i-lookback),i-2):
        lo=float(bars[j]["low"])
        if lo<min(float(bars[k]["low"]) for k in (j-2,j-1)) and lo<=min(
                float(bars[k]["low"]) for k in (j+1,j+2)):
            if all(float(bars[k]["close"])>=lo for k in range(j+1,i+1)):
                candidates.append(lo)
    return max(candidates) if candidates else None

def setup(bars,i):
    if i<65:return None
    close=float(bars[i]["close"])
    low=float(bars[i]["low"])
    ma20=sum(float(b["close"]) for b in bars[i-19:i+1])/20
    old20=sum(float(b["close"]) for b in bars[i-24:i-4])/20
    ma60=sum(float(b["close"]) for b in bars[i-59:i+1])/60
    prior_high=max(float(b["high"]) for b in bars[i-20:i])
    prior_close=float(bars[i-1]["close"])
    if prior_close<=prior_high<close:return "BREAKOUT_20D"
    if ma20>old20 and ma20>ma60 and close>=ma20 and .98*ma20<=low<=1.02*ma20:
        return "RISING_SMA20_PULLBACK"
    highs=[float(b["high"]) for b in bars]
    for j in range(max(2,i-25),i-2):
        if highs[j]>max(highs[j-2:j]) and highs[j]>=max(highs[j+1:j+3]):
            if prior_close<=highs[j]<close:return "RECLAIM_SWING_HIGH"
    return None

def inspect(bars,i,horizon=5,cost_bps=30):
    label=setup(bars,i)
    if label is None:return None
    entry=float(bars[i]["close"])
    stop=pivot_stop(bars,i)
    if stop is None or not 0<stop<entry:return {"setup":label,"status":"NO_STRUCTURAL_STOP"}
    risk=(entry-stop)/entry
    if not .02<=risk<=.12:return {"setup":label,"status":"RISK_OUTSIDE_2_TO_12_PCT"}
    if i+horizon>=len(bars):return {"setup":label,"status":"NO_FULL_FORWARD_HORIZON"}
    target=entry+2*(entry-stop)
    outcome="NEITHER"
    exit_price=float(bars[i+horizon]["close"])
    for k in range(i+1,i+horizon+1):
        lo,hi=float(bars[k]["low"]),float(bars[k]["high"])
        if lo<=stop and hi>=target:
            outcome="AMBIGUOUS_SAME_BAR";exit_price=None;break
        if lo<=stop:outcome="STOP_FIRST";exit_price=stop;break
        if hi>=target:outcome="TARGET_FIRST";exit_price=target;break
    net=round(100*(exit_price/entry-1)-cost_bps/100,3) if exit_price else None
    return {"setup":label,"status":outcome,"entry":entry,"stop":stop,
            "target_2r":round(target,3),"risk_pct":round(100*risk,3),
            "hypothetical_net_pct":net,"trade_approval":"NO"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("ohlc_csv",type=Path)
    p.add_argument("--out",type=Path,default=Path("setup_5d_audit.csv"))
    a=p.parse_args()
    with a.ohlc_csv.open(encoding="utf-8-sig",newline="") as f:bars=list(csv.DictReader(f))
    results=[]
    for i in range(65,len(bars)-5):
        r=inspect(bars,i)
        if r:results.append({"signal_date":bars[i]["date"],**r})
    if not results:raise SystemExit("NO_SETUP_OBSERVATIONS")
    fields=list(dict.fromkeys(k for r in results for k in r))
    with a.out.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(results)
    print(json.dumps({"observations":len(results),"outcomes":{s:sum(r["status"]==s for r in results)
         for s in sorted({r["status"] for r in results})},"trade_approval":"NO"}))
    print("RESEARCH_ONLY: signal-close hypothetical fills, 30bps flat cost; gaps not modeled")

if __name__=="__main__":main()
