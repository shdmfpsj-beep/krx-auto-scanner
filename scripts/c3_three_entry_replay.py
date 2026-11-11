#!/usr/bin/env python3
"""Three as-of entry alternatives; retrospective hypothetical fills only.
CSV: ticker,date,open,high,low,close,volume. No live trading or ledger writes.
Signal computed at close t; first eligible fill t+1. Same-bar stop wins.
"""
import argparse,csv,json
from collections import defaultdict
from pathlib import Path

MODELS={"MA20_PULLBACK":0.995,"CLOSE_MINUS_1ATR":None,"BREAKOUT_RETEST":1.005}
HORIZONS=(5,10,20)
def signals(bars,i):
    history=bars[:i+1]
    if len(history)<61:return []
    closes=[x["close"] for x in history]
    ma20=sum(closes[-20:])/20
    ma60=sum(closes[-60:])/60
    if not (closes[-1]>ma20>ma60):return []
    tr=[max(x["high"]-x["low"],abs(x["high"]-history[k-1]["close"]),abs(x["low"]-history[k-1]["close"])) for k,x in enumerate(history) if k>0]
    atr=sum(tr[-14:])/14
    stop=min(x["low"] for x in history[-10:])
    resistance=max(x["high"] for x in history[-20:-1])
    prices={"MA20_PULLBACK":ma20*.995,"CLOSE_MINUS_1ATR":closes[-1]-atr,"BREAKOUT_RETEST":resistance*1.005}
    return [(name,price,stop,resistance) for name,price in prices.items()
            if price>stop and (price-stop)/price<=.12 and (resistance-price)/(price-stop)>=2]
def evaluate(bars,i,model,entry,stop,resistance):
    # Only next session is eligible for limit order; later prices cannot create a fill.
    nxt=bars[i+1]
    filled=nxt["low"]<=entry<=nxt["high"] and nxt["open"]<=entry
    row={"ticker":bars[i]["ticker"],"signal_date":bars[i]["date"],"model":model,
         "entry":round(entry,5),"stop":round(stop,5),
         "resistance":round(resistance,5),"rr":round((resistance-entry)/(entry-stop),5),
         "filled":filled,"outcomes":{}}
    for horizon in HORIZONS:
        if i+horizon>=len(bars):
            row["outcomes"][str(horizon)]={"status":"CENSORED"};continue
        if not filled:
            row["outcomes"][str(horizon)]={"status":"UNFILLED"};continue
        end=min(i+horizon,len(bars)-1)
        outcome={"status":"HOLD","return_pct":round((bars[end]["close"]/entry-1)*100,4)}
        for j in range(i+1,end+1):
            b=bars[j]
            if b["open"]<stop:
                outcome={"status":"STOP_GAP","return_pct":round((b["open"]/entry-1)*100,4)};break
            if b["low"]<=stop:
                outcome={"status":"STOP","return_pct":round((stop/entry-1)*100,4)};break
            if b["high"]>=resistance:
                outcome={"status":"TARGET","return_pct":round((resistance/entry-1)*100,4)};break
        row["outcomes"][str(horizon)]=outcome
    return row
def replay(rows):
    by=defaultdict(list)
    for r in rows:
        x={"ticker":r["ticker"],"date":r["date"]}
        for f in ("open","high","low","close","volume"):x[f]=float(r[f])
        if not (0<x["low"]<=min(x["open"],x["close"])<=max(x["open"],x["close"])<=x["high"] and x["volume"]>=0):
            raise ValueError("INVALID_BAR")
        by[x["ticker"]].append(x)
    result=[]
    for ticker,bars in by.items():
        bars.sort(key=lambda x:x["date"])
        if len({b["date"] for b in bars})!=len(bars):raise ValueError("DUPLICATE_DATE")
        for i in range(60,len(bars)-1):
            for model,entry,stop,resistance in signals(bars,i):
                result.append(evaluate(bars,i,model,entry,stop,resistance))
    return result
def main():
    p=argparse.ArgumentParser();p.add_argument("--bars",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    with a.bars.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
    results=replay(rows);a.out.mkdir(parents=True,exist_ok=True)
    (a.out/"three_entry_events.json").write_text(json.dumps(results,ensure_ascii=False,indent=2))
    summary={}
    for model in MODELS:
        group=[r for r in results if r["model"]==model]
        completed={str(h):[r["outcomes"][str(h)] for r in group if r["outcomes"][str(h)]["status"] not in ("CENSORED","UNFILLED")] for h in HORIZONS}
        summary[model]={"signals":len(group),"fills":sum(r["filled"] for r in group),
            "fill_rate":None if not group else sum(r["filled"] for r in group)/len(group),
            "avg_rr":None if not group else sum(r["rr"] for r in group)/len(group),
            "horizons":{h:{"completed":len(v),"stop_rate":None if not v else sum(x["status"].startswith("STOP") for x in v)/len(v),
                "avg_return_pct":None if not v else sum(x["return_pct"] for x in v)/len(v)} for h,v in completed.items()}}
    report={"source":"USER_SUPPLIED_HISTORICAL_CSV_NOT_OFFICIAL_VERIFIED","models":summary,
            "signal_count":len(results),"trade_approved":False,"decision":"CASH",
            "limitations":["Retrospective sample; vintage PIT and corporate actions unverified",
                           "One-session hypothetical limit fills; no brokerage execution proof",
                           "No 15:30 regular-session certification","Overlapping signals are not independent"]}
    (a.out/"three_entry_summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("THREE_ENTRY_REPLAY",len(results),json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
