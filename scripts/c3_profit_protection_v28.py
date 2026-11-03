"""C3 v28: paired profit-protection exit experiments on v27 identical entries.

Research only. At close of session j, decide exit for next session open.
Never use next-session OHLC for the decision. A trade is censored when
its requested horizon cannot be observed in the available history.
"""
import argparse,csv,json,statistics
from pathlib import Path
from c3_entry_geometry_v23 import geometry
from c3_paired_entry_exit_v27 import evaluate as v27_evaluate

def exit_model(rows,entry_idx,entry,initial_stop,mode,max_sessions=60):
    stop=initial_stop;peak_close=entry;peak_high=entry;lowest=entry
    exit_idx=None;reason=None;activated=False
    last=min(len(rows)-2,entry_idx+max_sessions-1)
    for j in range(entry_idx,last+1):
        bar=rows[j];close=float(bar["close"])
        peak_close=max(peak_close,close);peak_high=max(peak_high,float(bar["high"]))
        lowest=min(lowest,float(bar["low"]))
        # The rule can be evaluated only at the close of this session.
        if mode in ("atr_trend","profit_lock"):
            hist=geometry(rows[:j+1])
            if hist.get("status")=="RESEARCH_GEOMETRY_ONLY":
                # This close-based stop applies from the following session.
                stop=max(stop,hist["trailing_stop_reference"])
                atr=hist["atr14"]
            else:
                atr=None
            if mode=="profit_lock" and peak_close>=entry*1.07:
                activated=True
                # Lock 40% of the observed close-to-close gain, not a guessed high.
                stop=max(stop,entry+0.40*(peak_close-entry))
                if atr is not None:
                    stop=max(stop,peak_close-2.5*atr)
        if close<stop:
            exit_idx=j+1;reason="CLOSE_STOP_NEXT_OPEN";break
    if exit_idx is None:
        exit_idx=min(len(rows)-1,entry_idx+max_sessions)
        reason="HORIZON_NEXT_OPEN" if exit_idx==entry_idx+max_sessions else "DATA_END_CENSORED"
    out=float(rows[exit_idx]["open"])
    return {"return_pct":round((out/entry-1)*100,3),
            "exit_date":rows[exit_idx]["date"],"exit_price":out,
            "holding_sessions":exit_idx-entry_idx,"exit_reason":reason,
            "censored":reason=="DATA_END_CENSORED",
            "profit_lock_activated":activated,
            "mfe_close_pct":round((peak_close/entry-1)*100,3),
            "mfe_high_pct":round((peak_high/entry-1)*100,3),
            "mae_low_pct":round((lowest/entry-1)*100,3)}

def evaluate(rows):
    base=v27_evaluate(rows)
    date_index={row["date"]:i for i,row in enumerate(rows)}
    pairs=[]
    for p in base["pairs"]:
        i=date_index[p["entry_date"]]
        signal_idx=date_index[p["signal_date"]]
        initial=geometry(rows[:signal_idx+1])["structural_stop"]
        entry=p["entry_price"]
        models={mode:exit_model(rows,i,entry,initial,mode) for mode in ("atr_trend","profit_lock")}
        fixed=p["fixed20"];trend=p["trend60"]
        # Baseline v27 trend exit retained to highlight any implementation changes.
        complete=not any(x["censored"] for x in [fixed,trend,*models.values()])
        pairs.append({"signal_date":p["signal_date"],"entry_date":p["entry_date"],
                      "entry_price":entry,"fixed20":fixed,"v27_trend60":trend,
                      **models,"complete":complete})
    complete=[p for p in pairs if p["complete"]]
    def stats(key):
        vals=[p[key]["return_pct"] for p in complete]
        return {"n":len(vals),"mean_return_pct":round(statistics.mean(vals),3) if vals else None,
                "win_rate_pct":round(100*sum(v>0 for v in vals)/len(vals),2) if vals else None}
    return {"v27_signals":base["signals"],"v27_unfilled":base["unfilled_signals"],
            "paired_count":len(pairs),"complete_pairs":len(complete),"pairs":pairs,
            "comparable_summary":{k:stats(k) for k in ("fixed20","v27_trend60","atr_trend","profit_lock")}}

def run(selection,history_dir,output):
    picks=json.loads(Path(selection).read_text(encoding="utf-8-sig"))
    items=[]
    for pick in picks.get("provisional_watch_top5",picks.get("provisional_watch_top2",[])):
        ticker=str(pick["ticker"]).zfill(6);source=Path(history_dir)/(ticker+".csv")
        item={"ticker":ticker,"name":pick.get("name"),"status":"NO_HISTORY","buy_approved":False}
        if source.exists():
            with source.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
            if len(rows)>=90 and rows[-1]["date"]==pick.get("price_date"):
                item.update(status="RESEARCH_ONLY",**evaluate(rows))
            else:item["status"]="SHORT_OR_STALE"
        items.append(item)
    report={"schema":"C3_PROFIT_PROTECTION_V28","items":items,
            "limitations":"Current TOP5 selected retrospectively; survivorship bias. No fees, slippage, tick rounding, certified regular session, or execution proof. Profit-lock 7%/40%/2.5ATR are hypotheses, not optimized or validated. No order approval.",
            "buy_approvals":0,"decision":"CASH"}
    dest=Path(output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--selection",required=True);parser.add_argument("--history-dir",required=True);parser.add_argument("--output",required=True)
    a=parser.parse_args()
    result=run(a.selection,a.history_dir,a.output)
    print(json.dumps({"items":len(result["items"]),"pairs":sum(i.get("paired_count",0) for i in result["items"])}))
