"""C3 v30 confirmed trend-break versus pullback, paired with v27 entries.

Daily OHLC research only. Close-based signals execute at next open.
No same-day intraday sequencing or point-in-time universe claims.
"""
import argparse,csv,json,statistics
from pathlib import Path
from c3_entry_geometry_v23 import geometry
from c3_paired_entry_exit_v27 import evaluate as entry_events

def confirmed_exit(rows,entry_idx,entry,initial_stop,horizon=60):
    stop=float(initial_stop);peak_close=float(entry);peak_high=float(entry)
    trough=float(entry);below20=0;weak_volume=0;pullbacks=0;breaks=0
    activated=False;reason="DATA_END_CENSORED";exit_idx=None
    last=min(len(rows)-2,entry_idx+horizon-1)
    for j in range(entry_idx,last+1):
        h=rows[:j+1];bar=h[-1];close=float(bar["close"])
        peak_close=max(peak_close,close);peak_high=max(peak_high,float(bar["high"]))
        trough=min(trough,float(bar["low"]))
        if close<float(initial_stop):
            exit_idx=j+1;reason="STRUCTURAL_CLOSE_BREAK_NEXT_OPEN";break
        if len(h)>=51:
            ma20=sum(float(r["close"]) for r in h[-20:])/20
            ma50=sum(float(r["close"]) for r in h[-50:])/50
            prev_ma20=sum(float(r["close"]) for r in h[-21:-1])/20
            atr=sum(max(float(h[k]["high"])-float(h[k]["low"]),
                        abs(float(h[k]["high"])-float(h[k-1]["close"])),
                        abs(float(h[k]["low"])-float(h[k-1]["close"])))
                    for k in range(len(h)-14,len(h)))/14
            below20=below20+1 if close<ma20 else 0
            vol=float(bar.get("volume") or 0)
            prev_vol=[float(r.get("volume") or 0) for r in h[-21:-1]]
            volume_confirmed=bool(vol>0 and any(v>0 for v in prev_vol)
                                  and vol>=1.2*sum(prev_vol)/len(prev_vol))
            weak_volume=weak_volume+1 if close<ma20 and volume_confirmed else 0
            rising=ma20>prev_ma20 and ma20>ma50
            # A single dip below a rising MA20 is a pullback, not an exit.
            if below20==1 and rising:pullbacks+=1
            # Confirm trend break by two closes below MA20, and either
            # MA20 slope/stack deterioration or heavy selling volume.
            confirmed=below20>=2 and (not rising or weak_volume>=1)
            if confirmed:
                exit_idx=j+1;reason="CONFIRMED_TREND_BREAK_NEXT_OPEN";break
            if peak_close>=entry*1.07:
                activated=True
                # In strong trends use a wider chandelier reference.
                # Stop is evaluated only after a confirmed close break,
                # avoiding forced liquidation on ordinary pullbacks.
                fraction=0.15 if rising else 0.35
                candidate=max(entry+fraction*(peak_close-entry),
                              peak_close-(3.5 if rising else 2.5)*atr)
                stop=max(stop,candidate)
                if below20>=2 and close<stop:
                    exit_idx=j+1;reason="CONFIRMED_PROFIT_STOP_NEXT_OPEN";break
        # Note: initial structural stop is never relaxed.
    if exit_idx is None:
        exit_idx=min(len(rows)-1,entry_idx+horizon)
        reason="HORIZON_NEXT_OPEN" if exit_idx==entry_idx+horizon else "DATA_END_CENSORED"
    out=float(rows[exit_idx]["open"])
    mfe=100*(peak_high/entry-1);realized=100*(out/entry-1)
    return {"exit_date":rows[exit_idx]["date"],"exit_price":out,
            "return_pct":round(realized,3),"holding_sessions":exit_idx-entry_idx,
            "exit_reason":reason,"censored":reason=="DATA_END_CENSORED",
            "profit_protection_activated":activated,"pullbacks_observed":pullbacks,
            "mfe_high_pct":round(mfe,3),"giveback_pct_points":round(max(0,mfe-realized),3),
            "profit_capture_ratio":round(realized/mfe,3) if mfe>0 else None,
            "max_adverse_pct":round(100*(trough/entry-1),3)}

def evaluate(rows):
    base=entry_events(rows);idx={r["date"]:i for i,r in enumerate(rows)}
    pairs=[]
    for p in base["pairs"]:
        initial=geometry(rows[:idx[p["signal_date"]]+1])["structural_stop"]
        model=confirmed_exit(rows,idx[p["entry_date"]],p["entry_price"],initial)
        fixed=p["fixed20"];trend=p["trend60"]
        complete=not any(x["censored"] for x in (fixed,trend,model))
        pairs.append({"entry_date":p["entry_date"],"entry_price":p["entry_price"],
                      "fixed20":fixed,"trend60":trend,"confirmed60":model,"complete":complete})
    valid=[p for p in pairs if p["complete"]]
    def summary(key):
        values=[p[key]["return_pct"] for p in valid]
        return {"n":len(values),"mean_return_pct":round(statistics.mean(values),3) if values else None,
                "win_rate_pct":round(100*sum(v>0 for v in values)/len(values),2) if values else None}
    return {"paired_count":len(pairs),"complete_pairs":len(valid),"pairs":pairs,
            "summary":{k:summary(k) for k in ("fixed20","trend60","confirmed60")},
            "mean_confirmed_minus_trend_pct_points":round(statistics.mean(p["confirmed60"]["return_pct"]-p["trend60"]["return_pct"] for p in valid),3) if valid else None,
            "mean_confirmed_giveback_pct_points":round(statistics.mean(p["confirmed60"]["giveback_pct_points"] for p in valid),3) if valid else None}

def run(selection,history_dir,output):
    picks=json.loads(Path(selection).read_text(encoding="utf-8-sig"));items=[]
    for pick in picks.get("provisional_watch_top5",picks.get("provisional_watch_top2",[])):
        ticker=str(pick["ticker"]).zfill(6);source=Path(history_dir)/(ticker+".csv")
        item={"ticker":ticker,"name":pick.get("name"),"status":"NO_HISTORY","buy_approved":False}
        if source.is_file():
            with source.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
            if len(rows)>=90 and rows[-1]["date"]==pick.get("price_date"):
                item.update(status="RESEARCH_ONLY",**evaluate(rows))
            else:item["status"]="SHORT_OR_STALE"
        items.append(item)
    result={"schema":"C3_CONFIRMED_TREND_BREAK_V30","items":items,"buy_approvals":0,"decision":"CASH",
            "limitations":"Retrospective TOP5 and unverified market session; 2-close, volume, 7% activation, ATR and lock fractions are hypotheses. No fees/slippage/tick normalization or live execution. All exits next open."}
    dest=Path(output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--selection",required=True)
    p.add_argument("--history-dir",required=True);p.add_argument("--output",required=True)
    a=p.parse_args();print(json.dumps({"items":len(run(a.selection,a.history_dir,a.output)["items"])}))
