#!/usr/bin/env python3
"""Read-only 2026-11-11 C3 full-market re-selection of entry-feasible B candidates.

This is a NEW, retrospective, explicitly dated research ranking; original A/B
immutable selections and all Telegram receipts remain untouched.
Cannot certify KRX 09:00-15:30-only daily volume/turnover.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

DAY="2026-11-11"
ORIGINAL_SOURCE_RUN="43086941571"
ROOT_LANE="lanes/krx_unadjusted_v12"
ENTRIES=("A_SUPPORT_LIMIT","B_CONFIRMED_PULLBACK","C_LIMITED_BREAKOUT")
MAX_ENTRY_GAP_PCT=8.0
MAX_STRUCTURE_RISK_PCT=8.0
MIN_NET_R1_RR=1.5


def usable(plan, close):
    """Fixed diagnostic geometry, never a trading recommendation or new order."""
    if not plan:
        return False,"NO_EXISTING_ENTRY_PLAN",None
    required=("low","high","stop","resistance","risk_pct","net_r1_rr")
    try:
        vals={k:float(plan[k]) for k in required}
    except (TypeError,ValueError,KeyError):
        return False,"MISSING_FINITE_R1_OR_GEOMETRY",None
    if not all(math.isfinite(v) and v>0 for v in vals.values()):
        return False,"NONFINITE_OR_MISSING_GEOMETRY",None
    lo,hi,stop,r1=map(vals.get,("low","high","stop","resistance"))
    gap=100*max(0,close-hi)/close
    if not (0<stop<lo<=hi<r1):
        return False,"INVALID_PRICE_ORDER",None
    if gap>MAX_ENTRY_GAP_PCT:
        return False,"STALE_ENTRY_TOO_FAR_BELOW_CLOSE",gap
    if hi>close*1.03:
        return False,"UNBUDGETED_CHASE_ABOVE_CLOSE",gap
    if vals["risk_pct"]>MAX_STRUCTURE_RISK_PCT:
        return False,"STRUCTURE_STOP_TOO_FAR",gap
    if vals["net_r1_rr"]<MIN_NET_R1_RR:
        return False,"FIRST_RESISTANCE_REWARD_TOO_SMALL",gap
    return True,"PASS",gap


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--engine",type=Path,required=True)
    p.add_argument("--state",type=Path,required=True)
    p.add_argument("--outdir",type=Path,required=True)
    args=p.parse_args()
    args.outdir.mkdir(parents=True,exist_ok=True)
    engine=args.engine.resolve()
    state=args.state.resolve()
    from c3_bootstrap_cache_v13 import restore
    from c3_forward_ledger_v8 import read_record,hash_value
    from c3_daily_research_v8 import histories
    from c3_selection_scope_v5 import read_csv,unique_index,classify,selection_features,digest
    from c3_selection_factors_v6 import causal_factors,regime
    from c3_entry_practical_v7 import entry_plan,features

    original=json.loads((state/"reports/c3_forward_v8/latest.json").read_text())
    if (original.get("source_price_asof")!=DAY or
        original.get("source_run_id")!=ORIGINAL_SOURCE_RUN or
        original.get("research_top2_registered_for_source_session") is not True):
        raise ValueError("FROZEN_NOV11_SOURCE_NOT_AVAILABLE")
    expected=original["current_scope"]
    source_hashes=original["source_hashes"]

    lane=state/"reports/c3_forward_v8"/ROOT_LANE
    market=read_record(lane/"markets"/(DAY+".json.gz"))
    decision=read_record(lane/"decisions"/(DAY+".json"))
    if market["asof"]!=DAY or decision["decision_date"]!=DAY:
        raise ValueError("FROZEN_DATE_NOT_NOV11")
    if decision["source_snapshot_hash"]!=hash_value(market):
        raise ValueError("ORIGINAL_DECISION_AND_MARKET_HASH_MISMATCH")
    old_b=[r["ticker"] for r in decision["models"]["B"]]
    if old_b!=["028050","180640"]:
        raise ValueError("ORIGINAL_TOP2_BASELINE_CHANGED")
    if set(market["indices"])!={"KOSPI","KOSDAQ"}:
        raise ValueError("INDEX_MARKETS_INCOMPLETE")
    sessions=market["sessions"]
    if sessions[-1]!=DAY:
        raise ValueError("MARKET_SESSION_DATE_MISMATCH")
    prices={t:dict(row,ticker=t,asof=DAY)
            for t,row in market["rows"].items()}
    if len(prices)!=2769 or set(r["market"] for r in prices.values())!={"KOSPI","KOSDAQ"}:
        raise ValueError("FROZEN_FULL_MARKET_COUNT_MISMATCH")

    input_dir=Path("/tmp/c3-reselect-nov11-inputs")
    restore(engine/"reports/c3_work8_20261105/inputs.json",
            input_dir,state/"reports/c3_forward_v8",
            args.outdir/"bootstrap_audit_private.json")
    panel=input_dir/"panel/official_panel.csv.gz"
    quality=input_dir/"panel/quality_audit.json"
    basic=input_dir/"issuer/basic"
    scope=engine/"reports/c3_work5_20261105/sources"
    if digest(panel)!=source_hashes["panel"] or digest(quality)!=source_hashes["audit"]:
        raise ValueError("FROZEN_HISTORY_SHA256_MISMATCH")
    if digest(scope/"classification_sources.json")!=source_hashes["classification"]:
        raise ValueError("ORIGINAL_CLASSIFICATION_HASH_MISMATCH")
    bmeta=json.loads((basic/"krx_basic_v610_status.json").read_text())
    smeta=json.loads((scope/"classification_sources.json").read_text())
    basics=unique_index(read_csv(basic/"KOSPI_basic_v610.csv")+
                        read_csv(basic/"KOSDAQ_basic_v610.csv"))
    kind=unique_index(read_csv(scope/"kind_companies.csv"))
    secondary=defaultdict(list)
    for row in read_csv(scope/"secondary_industries.csv"):
        secondary[row["ticker"]].append(row)
    for m in ("KOSPI","KOSDAQ"):
        if digest(basic/(m+"_basic_v610.csv"))!=bmeta["source_file_sha256"][m]:
            raise ValueError("FROZEN_BASIC_HASH_MISMATCH")
    for name,sha in smeta["file_sha256"].items():
        if digest(scope/name)!=sha:
            raise ValueError("FROZEN_CLASSIFICATION_FILE_CHANGED")

    snapshots={rec["asof"]:rec for rec in (
        read_record(path) for path in sorted((lane/"markets").glob("*.json.gz")))}
    past,excluded=histories(panel,quality,prices,snapshots,sessions,DAY)
    market_regimes={m:regime([market["indices"][m][day] for day in sessions])
                    for m in ("KOSPI","KOSDAQ")}

    counts=Counter();pool=[];failures=Counter();all_plan_counts=Counter()
    for ticker,price in sorted(prices.items()):
        classification=classify(price,basics.get(ticker),kind.get(ticker),secondary[ticker])
        counts[classification]+=1
        if classification!="VERIFIED_NONBIO_COMMON_AS_REPORTED" or ticker not in past:
            continue
        bars=past[ticker]
        index=market["indices"][price["market"]]
        mret=100*(index[DAY]/index[bars[-21]["date"]]-1)
        f=selection_features(bars,mret)
        if f is None:continue
        factors=causal_factors(bars,index)
        pool.append(dict(ticker=ticker,name=price["name"],market=price["market"],
                         close=price["close"],sector=secondary[ticker][0]["sector"],
                         market_regime=market_regimes[price["market"]],
                         **factors,**f))

    pool.sort(key=lambda row:(-row["turnover20"],-row["rs20"],row["ticker"]))
    bpool=[r for r in pool if r["own_rs20"]>0 and r["rs_accel5"]>0]
    if ([r["ticker"] for r in bpool[:2]]!=old_b or len(pool)!=expected["a_candidates"] or
            len(bpool)!=expected["b_candidates"] or
            len(past)!=expected["continuous_history"] or
            sum(classify(prices[t],basics.get(t),kind.get(t),secondary[t])==
                "VERIFIED_NONBIO_COMMON_AS_REPORTED" for t in past)!=expected["analysis_eligible"]):
        raise ValueError("REPLAY_NOT_IDENTICAL_TO_ORIGINAL_FULL_MARKET_SCREEN")

    feasible=[];diagnostic=[]
    for row in bpool:
        ticker=row["ticker"];bars=past[ticker];idx=market["indices"][row["market"]]
        mret=100*(idx[DAY]/idx[bars[-21]["date"]]-1)
        featureset,error=features(bars,mret)
        checks=[]
        for variant in ENTRIES:
            plan,why=entry_plan(ticker,bars,featureset,variant,row["market_regime"]) if featureset else (None,error)
            ok,reason,gap=usable(plan,float(row["close"]))
            all_plan_counts[variant]+=int(bool(plan))
            if not ok:failures[reason]+=1
            item=dict(variant=variant,pass_geometry=ok,
                      rejection=None if ok else reason,
                      entry_gap_pct=round(gap,3) if gap is not None else None)
            if plan:
                item.update(entry_low=plan["low"],entry_high=plan["high"],
                            stop=plan["stop"],r1=plan["resistance"],
                            r2=plan["resistance2"],risk_pct=plan["risk_pct"],
                            net_r1_rr=plan["net_r1_rr"],
                            signal_key=plan["signal_key"],
                            original_plan_date=plan["decision_date"],
                            plan_valid_sessions=1)
            checks.append(item)
        good=[q for q in checks if q["pass_geometry"]]
        # Highest costed net R1 reward/risk first; equal values favor closer
        # entry, stronger RS, and the original turnover ranking.
        if good:
            winner=sorted(good,key=lambda q:(-q["net_r1_rr"],q["entry_gap_pct"],
                                             q["risk_pct"],q["variant"]))[0]
            feasible.append(dict(row,selected_plan=winner,
                                 technically_observable_only=True,
                                 source_session_regular_certified=False,
                                 buy_approved=False,live_action="CASH"))
        diagnostic.append(dict(ticker=ticker,name=row["name"],original_b_rank=(
            old_b.index(ticker)+1 if ticker in old_b else None),
            original_turnover_rank=bpool.index(row)+1,
            close=row["close"],rs20=row["rs20"],
            plans=checks))

    feasible.sort(key=lambda z:(-z["selected_plan"]["net_r1_rr"],
                                z["selected_plan"]["entry_gap_pct"],
                                -z["rs20"],-z["turnover20"],z["ticker"]))
    def public(row,rank):
        plan=row["selected_plan"]
        return dict(rank=rank,ticker=row["ticker"],name=row["name"],
            market=row["market"],sector=row["sector"],reference_close=row["close"],
            rs20_pct_points=round(row["rs20"],2),
            rs_accel5_pct_points=round(row["rs_accel5"],2),
            turnover20_krw=row["turnover20"],
            market_regime=row["market_regime"],entry_method=plan["variant"],
            watch_low=plan["entry_low"],watch_high=plan["entry_high"],
            stop=plan["stop"],resistance1=plan["r1"],
            resistance2=plan["r2"],net_r1_rr=round(plan["net_r1_rr"],3),
            stop_risk_pct=round(plan["risk_pct"],3),
            entry_gap_pct=plan["entry_gap_pct"],
            original_plan_signal_key=plan["signal_key"],
            watch_validity_sessions=1,buy_approved=False,live_action="CASH")
    top=[public(row,i+1) for i,row in enumerate(feasible[:2])]
    report={
       "schema":"C3_NOV11_READONLY_ENTRY_FEASIBILITY_RESELECTION_V1",
       "price_asof":DAY,"checked_at_utc":datetime.now(timezone.utc).isoformat(),
       "original_source_run_id":ORIGINAL_SOURCE_RUN,
       "original_decision_source_sha256":decision["source_snapshot_hash"],
       "original_b_top2":old_b,
       "research_only":True,"new_retroactive_registration":False,
       "original_signal_ledger_modified":False,"official_daily_cache_all_fields_matched":True,
       "session_regular_only_certified":False,
       "source_price_basis":"UNADJUSTED_AS_TRADED",
       "full_market_price_rows":len(prices),
       "continuous_history":len(past),
       "analysis_eligible":expected["analysis_eligible"],
       "stock_preselector_count":len(pool),
       "original_b_filter_count":len(bpool),
       "usable_plan_counts":dict(all_plan_counts),
       "geometry_rejected_reasons":dict(failures),
       "eligible_entry_feasible_tickers":len(feasible),
       "new_research_top2":top,
       "revision_status":("TWO_RESEARCH_ENTRY_FEASIBLE" if len(top)==2
                          else "ONE_RESEARCH_ENTRY_FEASIBLE" if len(top)==1
                          else "CASH_NO_ENTRY_FEASIBLE"),
       "thresholds":{"max_entry_gap_below_close_pct":MAX_ENTRY_GAP_PCT,
                     "max_structure_stop_risk_pct":MAX_STRUCTURE_RISK_PCT,
                     "minimum_costed_r1_reward_risk":MIN_NET_R1_RR},
       "trade_approved":False,"orders_enabled":False,"decision":"CASH",
       "telegram_sent":False,"telegram_original_date_resend_forbidden":True,
       "not_original_2026_11_11_frozen_top2":True
    }
    for filename,payload in [("reselection_summary.json",report),
                             ("b_pool_entry_diagnostics.json",
                              dict(schema="C3_NOV11_B_FULL_DIAGNOSTICS_V1",asof=DAY,
                                   rows=diagnostic))]:
        (args.outdir/filename).write_text(
            json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+"\n",
            encoding="utf-8")
    print("C3_NOV11_RESELECTION="+json.dumps({k:report[k] for k in (
        "full_market_price_rows","analysis_eligible","stock_preselector_count",
        "original_b_filter_count","eligible_entry_feasible_tickers",
        "new_research_top2","revision_status","decision")},ensure_ascii=False),
          flush=True)


if __name__=="__main__":
    main()
