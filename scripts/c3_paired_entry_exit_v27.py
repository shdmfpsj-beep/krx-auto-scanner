"""C3 v27 paired exit comparison with the SAME support-band entry.

A signal uses bars through t; limit entry is eligible only on t+1 through t+3.
Fill at the limit if next open is above it and intraday low touches it;
if open gaps below the limit, use the open (adverse price movement).
No same-day stop on signal bar. Exit triggers at close, fill next open.
Research only. Does not model fees, liquidity, intraday stop or forward selection.
"""
import argparse,csv,json,statistics
from pathlib import Path
from c3_entry_geometry_v23 import geometry

def simulate(rows,entry_idx,entry,stop,horizon,trend):
    peak=entry;trough=entry;exit_idx=None;reason="DATA_END"
    for j in range(entry_idx,min(len(rows)-1,entry_idx+horizon)):
        bar=rows[j];peak=max(peak,float(bar["high"]));trough=min(trough,float(bar["low"]))
        # Trailing reference from previous completed session only.
        if trend and j>entry_idx:
            previous=geometry(rows[:j])
            if previous.get("status")=="RESEARCH_GEOMETRY_ONLY":
                stop=max(stop,previous["trailing_stop_reference"])
        if float(bar["close"])<stop:
            exit_idx=j+1;reason="CLOSE_STOP_NEXT_OPEN";break
    if exit_idx is None:
        exit_idx=min(len(rows)-1,entry_idx+horizon)
        reason="HORIZON_NEXT_OPEN" if exit_idx==entry_idx+horizon else "DATA_END_CENSORED"
    out=float(rows[exit_idx]["open"])
    return {"exit_date":rows[exit_idx]["date"],"exit_price":out,
            "return_pct":round(100*(out/entry-1),3),
            "holding_sessions":exit_idx-entry_idx,"exit_reason":reason,
            "max_favorable_pct":round(100*(peak/entry-1),3),
            "max_adverse_pct":round(100*(trough/entry-1),3),
            "censored":reason=="DATA_END_CENSORED"}

def evaluate(rows):
    pairs=[];i=65;missed=0;signals=0
    while i<len(rows)-23:
        sig=geometry(rows[:i+1])
        if sig.get("status")!="RESEARCH_GEOMETRY_ONLY" or sig.get("trend_state")!="UPTREND":
            i+=1;continue
        signals+=1
        # The upper support band is the actionable limit, not a forced market-open fill.
        limit=sig["entry_high"];found=None
        for j in range(i+1,min(i+4,len(rows)-21)):
            op=float(rows[j]["open"]);lo=float(rows[j]["low"])
            if op<=limit or lo<=limit:
                found=(j,min(op,limit));break
        if found is None:
            missed+=1;i+=4;continue
        j,entry=found
        if entry<=sig["structural_stop"]:
            i=j+1;continue
        fixed=simulate(rows,j,entry,sig["structural_stop"],20,False)
        trend=simulate(rows,j,entry,sig["structural_stop"],60,True)
        pairs.append({"signal_date":rows[i]["date"],"entry_date":rows[j]["date"],
                      "entry_price":entry,"entry_limit":limit,
                      "fixed20":fixed,"trend60":trend,
                      "trend_minus_fixed_pct":round(trend["return_pct"]-fixed["return_pct"],3)})
        exit_dates={fixed["exit_date"],trend["exit_date"]}
        i=max(j+1,max(k for k,row in enumerate(rows) if row["date"] in exit_dates)+1)
    complete=[p for p in pairs if not p["fixed20"]["censored"] and not p["trend60"]["censored"]]
    return {"signals":signals,"unfilled_signals":missed,"paired_count":len(pairs),
            "complete_pairs":len(complete),"pairs":pairs,
            "mean_trend_advantage_pct":round(statistics.mean(p["trend_minus_fixed_pct"] for p in complete),3) if complete else None,
            "trend_wins":sum(p["trend_minus_fixed_pct"]>0 for p in complete)}

def run(selection,history_dir,output):
    picks=json.loads(Path(selection).read_text(encoding="utf-8-sig"))
    items=[]
    for pick in picks.get("provisional_watch_top5",picks.get("provisional_watch_top2",[])):
        ticker=str(pick["ticker"]).zfill(6);source=Path(history_dir)/(ticker+".csv")
        item={"ticker":ticker,"name":pick.get("name"),"status":"NO_HISTORY","buy_approved":False}
        if source.is_file():
            with source.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
            if len(rows)>=90 and rows[-1]["date"]==pick.get("price_date"):
                item.update(status="RESEARCH_ONLY",**evaluate(rows))
            else:item["status"]="SHORT_OR_STALE"
        items.append(item)
    report={"schema":"C3_PAIRED_ENTRY_EXIT_V27","items":items,
            "limitations":"Current TOP5 retrospectively selected; no point-in-time universe, costs, certified session, or liquidity. Entry limit uses next sessions OHLC; gap fills simplified. No order authorization.",
            "buy_approvals":0,"decision":"CASH"}
    dest=Path(output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selection",required=True);p.add_argument("--history-dir",required=True);p.add_argument("--output",required=True)
    a=p.parse_args()
    print(json.dumps({"items":len(run(a.selection,a.history_dir,a.output)["items"])}))
