#!/usr/bin/env python3
"""C3 fixed v1.1: diagnose why alternative entries disappear.
Frozen selection events only, no strategy optimization or production mutation.
Not intraday executions. Horizon returns and transaction-adjusted realized P&L BLOCKED.
"""
import argparse,csv,json,math,statistics
from collections import Counter,defaultdict
from pathlib import Path
from c3_selection_first_research import candidate

MODELS=("MA20_PULLBACK","CLOSE_MINUS_1ATR","BREAKOUT_RETEST")
UPPER_WIDENING=(0,.005,.01,.02)  # prespecified, sensitivity only, no tuning

def read_history(root):
    days=[];by=defaultdict(list);bydate={}
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():continue
        mf=folder/"krx_v65_collect_status.json"
        if not mf.exists():continue
        manifest=json.loads(mf.read_text())
        if not manifest.get("official_dataset_usable"):continue
        day=folder.name
        if day!=manifest.get("asof"):raise ValueError("SOURCE_ASOF_MISMATCH")
        days.append(day)
        for market in ("KOSPI","KOSDAQ"):
            p=folder/(market+"_official.csv")
            import hashlib
            if hashlib.sha256(p.read_bytes()).hexdigest()!=manifest["market_file_sha256"][market]:
                raise ValueError("SOURCE_SHA_MISMATCH")
            with p.open(encoding="utf-8-sig",newline="") as f:
                for r in csv.DictReader(f):
                    if r["valid_daily_bar"]!="True":continue
                    b={"date":day,"ticker":r["ticker"],"market":market}
                    for col in ("open","high","low","close","volume"):
                        b[col]=float(r[col])
                    k=(r["ticker"],day)
                    if k in bydate:raise ValueError("DUPLICATE_DATE_TICKER")
                    bydate[k]=b;by[r["ticker"]].append(b)
    for s in by.values():s.sort(key=lambda b:b["date"])
    return days,by,bydate

def explain_model(bar_series,i):
    h=bar_series[:i+1]
    if i<60:raise ValueError("INSUFFICIENT_ASOF_BARS")
    cl=[b["close"] for b in h]
    now=cl[-1];ma20=sum(cl[-20:])/20
    tr=[max(b["high"]-b["low"],abs(b["high"]-h[j-1]["close"]),
            abs(b["low"]-h[j-1]["close"])) for j,b in enumerate(h) if j>0]
    atr=sum(tr[-14:])/14
    stop=min(b["low"] for b in h[-10:])
    resistance=max(b["high"] for b in h[-20:-1])
    sources={"MA20_PULLBACK":ma20*.995,
             "CLOSE_MINUS_1ATR":now-atr,"BREAKOUT_RETEST":resistance*1.005}
    out={}
    for model,p in sources.items():
        if p<=stop:reason="ENTRY_AT_OR_BELOW_STOP"
        elif (p-stop)/p>.12:reason="STOP_DISTANCE_GT_12PCT"
        elif model=="BREAKOUT_RETEST" and now<=resistance*1.005:
            reason="BREAKOUT_NOT_CONFIRMED"
        elif ((p+2*(p-stop) if model=="BREAKOUT_RETEST" else resistance)-p)/(p-stop)<2:
            reason="RISK_REWARD_BELOW_2R"
        else:reason="ELIGIBLE"
        out[model]={"reason":reason,"candidate_price":round(p,4),
            "stop":stop,
            "stop_distance_pct":round((p-stop)/p*100,4) if p>0 else None}
    return out

def range_status(bars,lower,upper,stop,target):
    if not bars:return "CENSORED"
    if any(b is None for b in bars):return "BLOCKED_MISSING_TICKER_SESSION"
    relevant=[b for b in bars if b["low"]<=upper and b["high"]>=lower]
    if not relevant:return "PASS_UNTOUCHED"
    first=relevant[0]
    if first["open"]<stop:return "GAP_BELOW_STOP_NOT_VALID_FILL"
    if first["low"]<=stop and first["high"]>=target:
        return "TOUCH_STOP_TARGET_SEQUENCE_UNKNOWN"
    if first["low"]<=stop:return "TOUCH_STOP_SEQUENCE_UNKNOWN"
    if first["high"]>=target:return "TOUCH_TARGET_SEQUENCE_UNKNOWN"
    return "RANGE_OVERLAP_NOT_EXECUTION"

def evaluate(root,cohort,quality=None):
    days,by,bydate=read_history(root)
    dayi={d:i for i,d in enumerate(days)}
    q={(r["ticker"],r["date"]):r for r in (quality or {}).get("events",[])}
    events=[e for e in cohort["events"] if e["date"]>="2026-09-16"]
    summaries=Counter();rowout=[];scenario_risk=defaultdict(list)
    for e in events:
        ticker,date=e["ticker"],e["date"]
        if date not in dayi:raise ValueError("MISSING_MARKET_SELECTION_DATE")
        bs=by[ticker]
        i=next((j for j,b in enumerate(bs) if b["date"]==date),None)
        if i is None:raise ValueError("MISSING_SELECTION_PRICE")
        c=candidate(bs,i,{},None)
        if c is None:raise ValueError("FROZEN_EVENT_NOT_RECONSTRUCTED")
        flags=explain_model(bs,i)
        for model in MODELS:
            summaries[f"{model}:{flags[model]['reason']}"]+=1
        has_second=c["entry2_range"] is not None
        summaries["ENTRY1_AVAILABLE"]+=1
        summaries["ENTRY2_AVAILABLE"]+=has_second
        if c["entry_model1"]!=next((name for name in MODELS if flags[name]["reason"]=="ELIGIBLE" and round(flags[name]["candidate_price"],4)==c["entry1_range"][1]),c["entry_model1"]):
            raise ValueError("ENTRY1_ASOF_INCONSISTENT")
        after=days[dayi[date]+1:dayi[date]+4]
        statuses={}
        for widen in UPPER_WIDENING:
            key=f"upper_plus_{widen*100:.1f}pct"
            upper=c["entry1_range"][1]*(1+widen)
            lower=c["entry1_range"][0]
            stopdist=(upper-c["stop"])/upper*100
            scenario_risk[key].append(stopdist)
            summaries[f"{key}:RISK_OVER_12PCT"]+=stopdist>12
            statuses[key]={}
            for horizon in (1,2,3):
                if len(after)<horizon:
                    status="CENSORED"
                else:
                    window=[bydate.get((ticker,d)) for d in after[:horizon]]
                    status=range_status(window,lower,upper,c["stop"],c["target1"])
                summaries[f"{key}:D{horizon}:{status}"]+=1
                statuses[key][str(horizon)]=status
        qc_flags=q.get((ticker,date),{}).get("asof_quality")
        summaries["QC_SOURCE_FLAGGED"]+=bool(qc_flags)
        rowout.append({"ticker":ticker,"date":date,
            "market":bs[i]["market"],"asof_quality":qc_flags,
            "entry1":c["entry1_range"],"entry2":c["entry2_range"],
            "entry_model1":c["entry_model1"],"entry_model2":c["entry_model2"],
            "stop":c["stop"],"target1":c["target1"],"target2":c["target2"],
            "model_rejections":flags,"sensitivity":statuses,
            "trade_approved":False})
    if len(events)!=51:raise ValueError("FROZEN_NEW_51_COHORT_CHANGED")
    return {"schema":"C3_ENTRY_GEOMETRY_DIAGNOSTIC_V11",
        "cutoff":"2026-09-16","events":len(events),
        "sources_120_session_min_met":len(days)>=120,
        "counts":dict(summaries),
        "scenario_worst_case_upper_entry_stop_pct_mean":{
            k:round(statistics.mean(v),3) for k,v in scenario_risk.items()},
        "range_overlap_is_not_trade_execution":True,
        "widened_upper_prices_are_sensitivity_not_strategy":True,
        "actual_trade_returns":"BLOCKED_NO_INTRADAY_EXECUTION",
        "brokerage_round_trip_cost_after_fill":"BLOCKED_NO_VERIFIED_FILL",
        "sector_regime":"BLOCKED_ASOF_SECTOR_PIT",
        "finance_pit":"UNVERIFIED_ORIGINAL_NUMERIC",
        "no_new_predictor_promotion":True,
        "operations_changed":False,"decision":"CASH","details":rowout}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--cohort",type=Path,required=True)
    p.add_argument("--quality",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    out=evaluate(a.root,json.loads(a.cohort.read_text()),json.loads(a.quality.read_text()))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    print("C3_ENTRY_V11",json.dumps({k:v for k,v in out.items() if k!="details"},ensure_ascii=False))
if __name__=="__main__":main()
