"""C3 v29 adaptive trend exits; research-only, paired to frozen v27 entry events.

All decisions use completed close j and execute next session open.
No optimization or claims of forward profitability.
"""
import argparse,csv,json,statistics
from pathlib import Path
from c3_entry_geometry_v23 import geometry
from c3_paired_entry_exit_v27 import evaluate as entry_events

def adaptive_exit(rows,entry_idx,entry,initial_stop,horizon=60):
    stop=float(initial_stop);peak_close=float(entry);peak_high=float(entry)
    trough=float(entry);active=False;strong_days=0;weak_days=0
    last=min(len(rows)-2,entry_idx+horizon-1)
    exit_idx=None;reason="DATA_END_CENSORED"
    for j in range(entry_idx,last+1):
        bar=rows[j];close=float(bar["close"])
        peak_close=max(peak_close,close)
        peak_high=max(peak_high,float(bar["high"]))
        trough=min(trough,float(bar["low"]))
        history=rows[:j+1]
        # Compute trend using only bars completed at close j.
        if len(history)>=51:
            ma20=sum(float(r["close"]) for r in history[-20:])/20
            ma50=sum(float(r["close"]) for r in history[-50:])/50
            prev_ma20=sum(float(r["close"]) for r in history[-21:-1])/20
            strong=close>ma20>ma50 and ma20>prev_ma20
            weak=close<ma20 or ma20<ma50
            strong_days=strong_days+1 if strong else 0
            weak_days=weak_days+1 if weak else 0
            atr=sum(max(float(history[k]["high"])-float(history[k]["low"]),
                        abs(float(history[k]["high"])-float(history[k-1]["close"])),
                        abs(float(history[k]["low"])-float(history[k-1]["close"])))
                    for k in range(len(history)-14,len(history)))/14
            # Loose during strong trends, tighter only after weakness persists.
            if peak_close>=entry*1.07:
                active=True
                lock_fraction=0.20 if strong_days>=2 else 0.40
                stop=max(stop,entry+lock_fraction*(peak_close-entry))
                atr_multiple=3.5 if strong_days>=2 else 2.5
                stop=max(stop,peak_close-atr_multiple*atr)
            if weak_days>=2:
                stop=max(stop,ma20-1.0*atr)
        if close<stop:
            exit_idx=j+1;reason="CLOSE_STOP_NEXT_OPEN";break
    if exit_idx is None:
        exit_idx=min(len(rows)-1,entry_idx+horizon)
        reason="HORIZON_NEXT_OPEN" if exit_idx==entry_idx+horizon else "DATA_END_CENSORED"
    exit_price=float(rows[exit_idx]["open"])
    mfe=100*(peak_high/entry-1)
    realized=100*(exit_price/entry-1)
    return {"return_pct":round(realized,3),"exit_date":rows[exit_idx]["date"],
            "exit_price":exit_price,"holding_sessions":exit_idx-entry_idx,
            "exit_reason":reason,"censored":reason=="DATA_END_CENSORED",
            "profit_lock_activated":active,
            "mfe_high_pct":round(mfe,3),
            "profit_capture_ratio":round(realized/mfe,3) if mfe>0 else None,
            "giveback_pct_points":round(max(0,mfe-realized),3),
            "max_adverse_pct":round(100*(trough/entry-1),3)}

def evaluate(rows):
    base=entry_events(rows)
    index={r["date"]:i for i,r in enumerate(rows)}
    pairs=[]
    for p in base["pairs"]:
        signal_idx=index[p["signal_date"]]
        initial=geometry(rows[:signal_idx+1])["structural_stop"]
        result=adaptive_exit(rows,index[p["entry_date"]],p["entry_price"],initial)
        fixed=p["fixed20"];trend=p["trend60"]
        complete=not any(x["censored"] for x in (fixed,trend,result))
        pairs.append({"entry_date":p["entry_date"],"signal_date":p["signal_date"],
                      "entry_price":p["entry_price"],"fixed20":fixed,
                      "trend60":trend,"adaptive60":result,"complete":complete})
    valid=[p for p in pairs if p["complete"]]
    def summary(key):
        values=[p[key]["return_pct"] for p in valid]
        return {"n":len(values),
                "mean_return_pct":round(statistics.mean(values),3) if values else None,
                "win_rate_pct":round(100*sum(v>0 for v in values)/len(values),2) if values else None}
    return {"paired_count":len(pairs),"complete_pairs":len(valid),
            "summary":{k:summary(k) for k in ("fixed20","trend60","adaptive60")},
            "mean_adaptive_minus_trend_pct_points":round(statistics.mean(p["adaptive60"]["return_pct"]-p["trend60"]["return_pct"] for p in valid),3) if valid else None,
            "mean_adaptive_giveback_pct_points":round(statistics.mean(p["adaptive60"]["giveback_pct_points"] for p in valid),3) if valid else None,
            "pairs":pairs}

def run(selection,history_dir,output):
    picks=json.loads(Path(selection).read_text(encoding="utf-8-sig"))
    items=[]
    for pick in picks.get("provisional_watch_top5",picks.get("provisional_watch_top2",[])):
        ticker=str(pick["ticker"]).zfill(6)
        source=Path(history_dir)/(ticker+".csv")
        item={"ticker":ticker,"name":pick.get("name"),"status":"NO_HISTORY","buy_approved":False}
        if source.is_file():
            with source.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
            if len(rows)>=90 and rows[-1]["date"]==pick.get("price_date"):
                item.update(status="RESEARCH_ONLY",**evaluate(rows))
            else:item["status"]="SHORT_OR_STALE"
        items.append(item)
    report={"schema":"C3_ADAPTIVE_EXIT_V29","items":items,"buy_approvals":0,"decision":"CASH",
            "limitations":"Retrospective current TOP5; no point-in-time candidate universe, fees, slippage, tick-size normalization or verified regular-session feed. Fixed 7%, 20%/40%, 3.5/2.5 ATR and two-close rules are unvalidated research hypotheses."}
    dest=Path(output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selection",required=True);p.add_argument("--history-dir",required=True);p.add_argument("--output",required=True)
    a=p.parse_args();print(json.dumps({"items":len(run(a.selection,a.history_dir,a.output)["items"])}))
