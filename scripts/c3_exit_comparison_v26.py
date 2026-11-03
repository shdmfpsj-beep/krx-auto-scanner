"""Walk-forward comparison of fixed-horizon and trend-held research exits.

Signals use data through day t. Fill at t+1 open; stop decisions at close
and fill at next open. Research only: no costs, liquidity, or order approval.
"""
import argparse,csv,json,statistics
from pathlib import Path
from c3_entry_geometry_v23 import geometry

def evaluate(rows,horizon,trend_hold=False):
    trades=[]
    i=65
    while i<len(rows)-2:
        signal=geometry(rows[:i+1])
        if signal.get("status")!="RESEARCH_GEOMETRY_ONLY" or signal.get("trend_state")!="UPTREND":
            i+=1;continue
        entry=float(rows[i+1]["open"])
        stop=signal["structural_stop"]
        if entry<=stop:
            i+=1;continue
        peak=entry;trough=entry;exit_idx=None;reason="END_OF_DATA"
        for j in range(i+1,min(len(rows)-1,i+1+(60 if trend_hold else horizon))):
            high=float(rows[j]["high"]);low=float(rows[j]["low"])
            peak=max(peak,high);trough=min(trough,low)
            daily=geometry(rows[:j+1])
            if trend_hold and daily.get("status")=="RESEARCH_GEOMETRY_ONLY":
                stop=max(stop,daily.get("trailing_stop_reference",stop))
            if float(rows[j]["close"])<stop:
                exit_idx=j+1;reason="CLOSE_STOP_NEXT_OPEN";break
            if not trend_hold and j==i+horizon:
                exit_idx=j+1;reason="HORIZON_NEXT_OPEN";break
        if exit_idx is None:
            exit_idx=min(len(rows)-1,i+61 if trend_hold else i+horizon+1)
            reason="MAX_HOLD_OR_DATA_END"
        exit_price=float(rows[exit_idx]["open"])
        trades.append({"signal_date":rows[i]["date"],"entry_date":rows[i+1]["date"],
                       "exit_date":rows[exit_idx]["date"],"entry":entry,"exit":exit_price,
                       "return_pct":round((exit_price/entry-1)*100,3),
                       "max_favorable_pct":round((peak/entry-1)*100,3),
                       "max_adverse_pct":round((trough/entry-1)*100,3),
                       "holding_sessions":exit_idx-(i+1),"exit_reason":reason})
        i=exit_idx+1
    returns=[t["return_pct"] for t in trades]
    return {"trades":trades,"count":len(trades),
            "mean_return_pct":round(statistics.mean(returns),3) if returns else None,
            "win_rate_pct":round(100*sum(x>0 for x in returns)/len(returns),2) if returns else None,
            "mean_holding_sessions":round(statistics.mean(t["holding_sessions"] for t in trades),2) if trades else None}

def run(selection,history_dir,output):
    obj=json.loads(Path(selection).read_text(encoding="utf-8-sig"))
    results=[]
    for pick in obj.get("provisional_watch_top5",obj.get("provisional_watch_top2",[])):
        ticker=str(pick["ticker"]).zfill(6);p=Path(history_dir)/(ticker+".csv")
        result={"ticker":ticker,"name":pick.get("name"),"status":"NO_HISTORY","buy_approved":False}
        if p.exists():
            with p.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
            if len(rows)>=70 and rows[-1]["date"]==pick.get("price_date"):
                result.update(status="RESEARCH_ONLY",fixed20=evaluate(rows,20),
                              trend60=evaluate(rows,60,True))
            else:result["status"]="STALE_OR_SHORT_HISTORY"
        results.append(result)
    report={"schema":"C3_EXIT_COMPARISON_V26","method":"ROLLING_IN_SAMPLE_RESEARCH",
            "warning":"Overlapping historical candidate selection may have survivorship bias. No trading fees, slippage or certified session prices. Results are not forward performance.",
            "items":results,"buy_approvals":0,"decision":"CASH"}
    dest=Path(output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selection",required=True);p.add_argument("--history-dir",required=True);p.add_argument("--output",required=True)
    a=p.parse_args()
    print(json.dumps({"items":len(run(a.selection,a.history_dir,a.output)["items"])}))
