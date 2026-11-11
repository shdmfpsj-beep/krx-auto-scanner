#!/usr/bin/env python3
"""Frozen PR87 vs 2026-09-16+ independent-date shadow cohort holdout.
All outcomes exploratory, never execution/P&L, no production write or weight change.
"""
import argparse
import json
import math
import random
from collections import Counter,defaultdict
from pathlib import Path
from c3_temporal_quality_validation import auc
from c3_selection_first_research import candidate
from official_krx_120d_replay import history,weekdays

FEATURES=("momentum_20d_pct","rvol_20d","ma20_extension_pct","ma20_vs_ma60_pct","stop_distance_pct")
HORIZONS=(5,10,20)
CUTOFF="2026-09-16"
SEED=20261111

def wilson(passed,total):
    if not total:return None
    z=1.959963984540054
    p=passed/total
    den=1+z*z/total
    mid=(p+z*z/(2*total))/den
    half=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return [round(max(0,mid-half),4),round(min(1,mid+half),4)]

def ci(vals,seed=SEED,reps=1200):
    if not vals:return None
    rng=random.Random(seed);k=len(vals)
    means=sorted(sum(vals[rng.randrange(k)] for _ in range(k))/k for _ in range(reps))
    return [round(means[int(.025*(reps-1))],4),round(means[int(.975*(reps-1))],4)]

def bootstrap_auc(obs,feature,sign,seed=SEED,reps=1200):
    if not obs:return None
    rng=random.Random(seed);k=len(obs);vals=[]
    for _ in range(reps):
        rows=[obs[rng.randrange(k)] for i in range(k)]
        x=auc([bool(e["horizon"]["close_return_pct"]>0) for e in rows],
              [sign*e["features"][feature] for e in rows])
        if x is not None:vals.append(x)
    if not vals:return None
    vals.sort()
    return [round(vals[int(.025*(len(vals)-1))],4),round(vals[int(.975*(len(vals)-1))],4)]

def bar_maps(rows):
    by=defaultdict(list);dayset=set()
    for r in rows:
        x={"ticker":str(r["ticker"]),"date":str(r["date"])}
        x.update({f:float(r[f]) for f in ("open","high","low","close","volume")})
        by[x["ticker"]].append(x);dayset.add(x["date"])
    for v in by.values():v.sort(key=lambda b:b["date"])
    return by,sorted(dayset)

def entry_touch(e,by,days):
    ticker,date=e["ticker"],e["date"]
    bars=by.get(ticker,[])
    i=next((j for j,b in enumerate(bars) if b["date"]==date),None)
    if i is None or date not in days or days.index(date)+1>=len(days):
        return {"status":"BLOCKED_NO_NEXT_MARKET_SESSION","trade_pnl":None}
    c=candidate(bars,i,{},None)
    if not c:return {"status":"BLOCKED_RECONSTRUCTION","trade_pnl":None}
    expected=e["features"].get("stop_distance_pct")
    actual=round((c["entry1_range"][1]/c["stop"]-1)*100,4)
    if expected is None or abs(float(expected)-actual)>.001:
        return {"status":"BLOCKED_ASOF_ENTRY_MISMATCH","trade_pnl":None}
    low,high=c["entry1_range"]
    next_date=days[days.index(date)+1]
    bar=next((b for b in bars if b["date"]==next_date),None)
    if bar is None:return {"status":"BLOCKED_NEXT_SESSION_TICKER_MISSING","trade_pnl":None}
    if bar["high"]<low or bar["low"]>high:
        return {"status":"PASS_ENTRY_RANGE_NOT_TOUCHED","trade_pnl":None}
    if bar["open"]<c["stop"]:
        return {"status":"TOUCH_BUT_GAP_BELOW_STOP","trade_pnl":None}
    if bar["low"]<=c["stop"]:
        return {"status":"TOUCH_SEQUENCE_UNCERTAIN","trade_pnl":None}
    return {"status":"HYPOTHETICAL_NEXT_SESSION_RANGE_TOUCH_NOT_EXECUTION",
            "entry1_range":[low,high],"stop":c["stop"],"trade_pnl":None}

def evaluate(frozen,extended,quality,root=None,cutoff=CUTOFF):
    old={(e["ticker"],e["date"]) for e in frozen["events"]}
    allrows={(e["ticker"],e["date"]) for e in extended["events"]}
    if len(old)!=frozen.get("deduplicated_events") or not old.issubset(allrows):
        raise ValueError("FROZEN_PR87_COHORT_NOT_PRESERVED")
    if len(old)!=78 or frozen.get("horizon_groups",{}).get("20",{}).get("observed")!=43:
        raise ValueError("PR87_BASELINE_INCOMPATIBLE")
    qc={(e["ticker"],e["date"]):e for e in quality["events"]}
    records=[]
    for e in extended["events"]:
        k=(e["ticker"],e["date"])
        if k not in qc:raise ValueError("MISSING_INDEPENDENT_QC_EVENT")
        q=qc[k]
        item={"ticker":e["ticker"],"date":e["date"],"features":e["features"],
              "asof_quality":q["asof_quality"],"horizons":{}}
        for h in HORIZONS:
            a=e["outcomes"][str(h)];b=q["horizons"][str(h)]
            item["horizons"][str(h)]={"quality":b.get("quality"),
                "maturity_date":b.get("maturity_date"),
                "close_return_pct":a.get("close_return_pct"),
                "mfe_pct":a.get("mfe_pct"),"mae_pct":a.get("mae_pct")}
        records.append(item)
    by={};days=[]
    if root is not None:
        rows,_=history(Path(root),weekdays("2026-11-10",160))
        by,days=bar_maps(rows)
    out={"schema":"C3_PR87_FROZEN_PROSPECTIVE_HOLDOUT_V1",
         "cutoff":cutoff,"original_selection_events":len(old),
         "original_selection_preserved":len(old & allrows),
         "new_events":sum(e["date"]>=cutoff for e in records),
         "historical_sessions":quality.get("market_sessions"),
         "periods":{},
         "entry_replay_summary":{},
         "cost_adjusted_certified_returns":False,
         "index_and_sector_regime":"BLOCKED_NO_DATE_ALIGNED_BENCHMARK_AND_SECTOR",
         "fundamental_and_flow":"UNVERIFIED_OR_BLOCKED_NO_PIT",
         "predictor_promotion":False,"trade_approved":False,
         "production_unchanged":True,"decision":"CASH"}
    for h in HORIZONS:
        k=str(h)
        valid=[e for e in records if e["horizons"][k]["quality"]=="QC_VALID_EXPLORATORY"]
        train=[e for e in valid if e["date"]<cutoff and e["horizons"][k]["maturity_date"]<cutoff]
        test=[e for e in valid if e["date"]>=cutoff]
        pos=sum(e["horizons"][k]["close_return_pct"]>0 for e in test)
        summary={"train_n":len(train),"holdout_n":len(test),"holdout_positive":pos,
            "holdout_win_rate":round(pos/len(test),4) if test else None,
            "holdout_win_rate_ci95":wilson(pos,len(test)),
            "holdout_selection_close_mean_pct":round(sum(e["horizons"][k]["close_return_pct"] for e in test)/len(test),4) if test else None,
            "holdout_selection_close_mean_ci95":ci([e["horizons"][k]["close_return_pct"] for e in test],SEED+h),
            "holdout_selection_mfe_mean_pct":round(sum(e["horizons"][k]["mfe_pct"] for e in test)/len(test),4) if test else None,
            "holdout_selection_mae_mean_pct":round(sum(e["horizons"][k]["mae_pct"] for e in test)/len(test),4) if test else None,
            "feature_auc":{}}
        for f in FEATURES:
            result={"status":"INSUFFICIENT_TRAIN_OR_TEST","auc":None}
            if len(train)>=20 and len(test)>=20:
                ytrain=[e["horizons"][k]["close_return_pct"]>0 for e in train]
                yt=[e["horizons"][k]["close_return_pct"]>0 for e in test]
                tr=auc(ytrain,[e["features"][f] for e in train])
                if tr is not None and len(set(yt))==2:
                    sign=1 if tr>=.5 else -1
                    value=auc(yt,[sign*e["features"][f] for e in test])
                    result={"status":"SHADOW_HOLDOUT_NOT_VALIDATED_PREDICTOR",
                            "train_direction":"HIGH" if sign==1 else "LOW",
                            "auc":value,"ci95":bootstrap_auc(
                                [{"horizon":e["horizons"][k],"features":e["features"]} for e in test],
                                f,sign,SEED+h)}
            summary["feature_auc"][f]=result
        out["periods"][k]=summary
    new=[e for e in records if e["date"]>=cutoff]
    touch=Counter(entry_touch(e,by,days)["status"] for e in new) if root else Counter()
    out["entry_replay_summary"]={"new_events":len(new),"next_session_entry_range_status":dict(touch),
        "calculation":"Historical as-of entry corridor vs next-date OHLC; not a fill receipt",
        "live_execution_or_net_pnl_verified":False,
        "PASS_if_not_touched":True}
    common=[e for e in new if all(e["horizons"][str(h)]["quality"]=="QC_VALID_EXPLORATORY" for h in HORIZONS)]
    out["continuation"]={"same_new_cohort_20day_qc":len(common),
        "up5":sum(e["horizons"]["5"]["close_return_pct"]>0 for e in common),
        "up10":sum(e["horizons"]["10"]["close_return_pct"]>0 for e in common),
        "up20":sum(e["horizons"]["20"]["close_return_pct"]>0 for e in common),
        "all_up":sum(all(e["horizons"][str(h)]["close_return_pct"]>0 for h in HORIZONS) for e in common)}
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--frozen",type=Path,required=True)
    p.add_argument("--extended",type=Path,required=True)
    p.add_argument("--quality",type=Path,required=True)
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    out=evaluate(json.loads(a.frozen.read_text()),json.loads(a.extended.read_text()),
                 json.loads(a.quality.read_text()),a.root)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("C3_FROZEN_HOLDOUT",json.dumps(out,ensure_ascii=False))

if __name__=="__main__":main()
