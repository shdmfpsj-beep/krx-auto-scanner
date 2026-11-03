"""v23 structural entry geometry: research only; no order authorization.
Requires chronological, unique, dated OHLC bars. Never infer an entry from a single close.
"""
import argparse,csv,json,math
from pathlib import Path

def finite(v):
    try:
        x=float(v)
        return x if math.isfinite(x) and x>0 else None
    except (TypeError,ValueError):return None

def geometry(rows):
    if len(rows)<35:return {"status":"INSUFFICIENT_HISTORY","buy_approved":False}
    dates=[r.get("date") for r in rows]
    if any(not d for d in dates) or dates!=sorted(set(dates)):
        return {"status":"INVALID_DATES","buy_approved":False}
    bars=[]
    for r in rows:
        o,h,l,c=(finite(r.get(k)) for k in ("open","high","low","close"))
        if None in (o,h,l,c) or l>min(o,c) or h<max(o,c):
            return {"status":"INVALID_OHLC","buy_approved":False}
        bars.append((o,h,l,c))
    close=bars[-1][3]
    # Exclude current candle from structural support and overhead resistance.
    prior=bars[:-1]
    supports=sorted({prior[i][2] for i in range(2,len(prior)-2)
                     if prior[i][2]<=min(prior[j][2] for j in range(i-2,i+3))
                     and prior[i][2]<close})
    resistance=sorted({prior[i][1] for i in range(2,len(prior)-2)
                       if prior[i][1]>=max(prior[j][1] for j in range(i-2,i+3))
                       and prior[i][1]>close})
    if not supports:return {"status":"NO_CONFIRMED_SWING_SUPPORT","buy_approved":False}
    support=supports[-1]
    if not resistance:return {"status":"NO_CONFIRMED_OVERHEAD_RESISTANCE","support_reference":support,"buy_approved":False}
    first=resistance[0]
    # ATR based on observed bars, not a fixed 3% stop gap.
    tr=[max(bars[i][1]-bars[i][2],abs(bars[i][1]-bars[i-1][3]),abs(bars[i][2]-bars[i-1][3]))
        for i in range(len(bars)-14,len(bars))]
    atr=sum(tr)/len(tr)
    stop=support-0.25*atr
    if stop<=0 or stop>=close:return {"status":"INVALID_STOP_GEOMETRY","buy_approved":False}
    # Entry is a study band near observed support, capped below first resistance.
    entry_low=support+0.25*atr
    entry_high=min(support+1.0*atr,first-0.5*atr)
    if entry_low>=entry_high:return {"status":"NO_USABLE_ENTRY_BAND","buy_approved":False}
    rr=(first-entry_high)/(entry_high-stop)
    return {"status":"RESEARCH_GEOMETRY_ONLY","price_date":dates[-1],
            "reference_close":round(close,4),"support":round(support,4),
            "structural_stop":round(stop,4),"entry_low":round(entry_low,4),
            "entry_high":round(entry_high,4),"first_resistance":round(first,4),
            "atr14":round(atr,4),"reward_risk_at_entry_high":round(rr,3),
            "quality_gate":"PASS_RESEARCH" if rr>=1.5 else "LOW_REWARD_RISK",
            "buy_approved":False,"note":"Raw research prices; source/session/tick-size/adjustment not certified."}
def run(path,out):
    with open(path,encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
    result=geometry(rows)
    result["schema"]="C3_ENTRY_GEOMETRY_V23"
    dest=Path(out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result
def batch(selection_path,history_dir,output):
    selection=json.loads(Path(selection_path).read_text(encoding="utf-8-sig"))
    root=Path(history_dir)
    items=[]
    for pick in selection.get("provisional_watch_top2",[]):
        ticker=str(pick.get("ticker","")).zfill(6)
        entry={"ticker":ticker,"name":pick.get("name"),"selection_price_date":pick.get("price_date")}
        source=root/(ticker+".csv")
        if not source.is_file():
            entry.update(status="HISTORY_MISSING",buy_approved=False)
        else:
            try:
                with source.open(encoding="utf-8-sig",newline="") as f:
                    bars=list(csv.DictReader(f))
                if not bars or bars[-1].get("date")!=pick.get("price_date"):
                    entry.update(status="HISTORY_DATE_MISMATCH",buy_approved=False)
                else:
                    entry.update(geometry(bars))
            except (OSError,ValueError,UnicodeError):
                entry.update(status="HISTORY_READ_ERROR",buy_approved=False)
        items.append(entry)
    result={"schema":"C3_ENTRY_GEOMETRY_BATCH_V23","items":items,
            "research_geometry_count":sum(x["status"]=="RESEARCH_GEOMETRY_ONLY" for x in items),
            "buy_approvals":0,"decision":"CASH",
            "note":"History files require explicit OHLC/date schema; no automatic certification or orders."}
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--ohlcv");p.add_argument("--selection");p.add_argument("--history-dir")
    p.add_argument("--output",required=True)
    a=p.parse_args()
    if a.selection and a.history_dir:
        result=batch(a.selection,a.history_dir,a.output)
    elif a.ohlcv and not (a.selection or a.history_dir):
        result=run(a.ohlcv,a.output)
    else:
        p.error("provide --ohlcv or both --selection and --history-dir")
    print(json.dumps(result,ensure_ascii=False))
