#!/usr/bin/env python3
"""C3 2026-11-05 vs 2026-11-06 TOP2 retention and entry geometry audit.

Fully READ ONLY. This reconstructs the actual selection pool from hash-checked
owner-encrypted original bootstrap and the two immutable dated market snapshots.
It never registers decisions or writes to the original research ledger. No
notification code or broker is imported. Alternative ranks are NOT new signals.
"""
import json, math, os, statistics
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

from c3_bootstrap_cache_v13 import restore
from c3_daily_research_v8 import histories, choose
from c3_forward_ledger_v8 import read_record
from c3_selection_scope_v5 import load_sources, selection_features, classify
from c3_selection_factors_v6 import causal_factors, regime
from c3_entry_practical_v7 import entry_plan, features

REPO="shdmfpsj-beep/krx-auto-scanner"
STATE=Path("state/reports/c3_forward_v8")
BASE=Path("/tmp/c3-rank-audit")
DAYS=("2026-11-05","2026-11-06")
TOPS=("028050","030530")
SOURCE_LANE=STATE/"lanes/krx_unadjusted_v12"
ENGINE="077113ac2f5e93fecc4c47850b36e5eda2173e3d"

def must(ok,msg):
    if not ok:raise ValueError(msg)

def num(v):
    return round(v,5) if isinstance(v,(float,int)) else v

def candidate(row, bars, indices):
    m=row["market"];ix=indices[m]
    market_r20=100*(ix[bars[-1]["date"]]/ix[bars[-21]["date"]]-1)
    f,err=features(bars,market_r20)
    if not f:return dict(plan=None,reason=err,proximity_pct=None,rr=None,stop_risk_pct=None)
    plan,why=entry_plan(row["ticker"],bars,f,"A_SUPPORT_LIMIT",row["market_regime"])
    if not plan:return dict(plan=None,reason=why,proximity_pct=None,rr=None,stop_risk_pct=None)
    close=row["close"]
    # Positive: spot price is above the entry upper bound; negative: below.
    distance=100*(close-plan["high"])/close
    gap_to_stop=100*(close-plan["stop"])/close
    return dict(
        plan="A_SUPPORT_LIMIT",
        reason=None,
        proximity_pct=num(distance),
        stop_risk_pct=num(plan.get("risk_pct")),
        current_to_stop_pct=num(gap_to_stop),
        rr=num(plan.get("net_r1_rr")),
        low=num(plan["low"]),high=num(plan["high"]),
        stop=num(plan["stop"]),
        r1=num(plan.get("resistance")),
        r2=num(plan.get("resistance2"))
    )

def summarize(r, hist, indices, rank, include_plan=True):
    out=dict(ticker=r["ticker"],name=r["name"],market=r["market"],
             rank_turnover=rank,close=num(r["close"]),
             turnover20_krw=num(r["turnover20"]),
             rs20_pct_points=num(r["rs20"]),
             own_rs20_pct_points=num(r["own_rs20"]),
             rs_accel5_pct_points=num(r["rs_accel5"]),
             regime=r["market_regime"])
    if include_plan:out["entry"]=candidate(r,hist[r["ticker"]],indices)
    return out

def reconstructed_day(day, market, snapshots, panel, audit, basics,kind,secondary):
    assert market["asof"]==day
    sessions=market["sessions"]
    assert sessions[-1]==day and sessions==sorted(set(sessions))
    assert set(market["indices"])=={"KOSPI","KOSDAQ"}
    prices={t:dict(p,ticker=t,asof=day) for t,p in market["rows"].items()}
    must(len(prices)==2769,"PRICE_MARKET_SIZE_DIFFERENCE")
    histories_by_ticker,excluded=histories(panel,audit,prices,snapshots,sessions,day)
    idx=market["indices"]
    pool=[];scope=Counter()
    for ticker,price in sorted(prices.items()):
        why=classify(price,basics.get(ticker),kind.get(ticker),secondary[ticker])
        scope[why]+=1
        if why!="VERIFIED_NONBIO_COMMON_AS_REPORTED" or ticker not in histories_by_ticker:continue
        bars=histories_by_ticker[ticker];index=idx[price["market"]]
        market_r20=100*(index[day]/index[bars[-21]["date"]]-1)
        f=selection_features(bars,market_r20)
        if f is None:continue
        pool.append(dict(ticker=ticker,name=price["name"],market=price["market"],
            industry=secondary[ticker][0]["sector"],
            market_regime=regime([index[d] for d in sessions]),
            **f,**causal_factors(bars,index)))
    pool.sort(key=lambda r:(-r["turnover20"],-r["rs20"],r["ticker"]))
    b=[r for r in pool if r["own_rs20"]>0 and r["rs_accel5"]>0]
    bby={r["ticker"]:i+1 for i,r in enumerate(b)}
    selected_a=[r["ticker"] for r in pool[:2]]
    selected_b=[r["ticker"] for r in b[:2]]
    # Re-use production choose as an independent check of the manually rebuilt
    # pool ordering and its A/B output. Do not import registration/run().
    source=market["source"]
    meta=dict(asof=day,received_at=source["received_at"],
              regular_only_certified=False,price_basis="UNADJUSTED_AS_TRADED")
    models,count=choose(prices,histories_by_ticker,basics,kind,secondary,idx,sessions,
                        source["received_at"],meta,"READ_ONLY_REPLAY",ENGINE)
    must(selected_a==[r["ticker"] for r in models["A"]],"REBUILT_A_RANK_DIFFERS_FROM_PRODUCTION")
    must(selected_b==[r["ticker"] for r in models["B"]],"REBUILT_B_RANK_DIFFERS_FROM_PRODUCTION")
    must(count["a_candidates"]==len(pool) and count["b_candidates"]==len(b),"POOL_COUNTS_MISMATCH")

    # Alternative rankings are descriptive only. They do NOT alter frozen
    # production ranking, trading signals, historical orders or performance.
    by_rs=sorted(b,key=lambda r:(-r["own_rs20"],-r["turnover20"],r["ticker"]))
    by_accel=sorted(b,key=lambda r:(-r["rs_accel5"],-r["turnover20"],r["ticker"]))
    actionable=[]
    for r in b:
        entry=candidate(r,histories_by_ticker[r["ticker"]],idx)
        # Research-only demanding filter; do not use as a live trading approval.
        # More than 3% above the plan high is too far; below the low is also
        # disqualified. Net reward/risk >=1.5 and plan-risk <=8% required.
        proximity=entry["proximity_pct"]
        if (entry["plan"] is not None and proximity is not None and
            proximity>=-100*(entry["high"]-entry["low"])/r["close"] and
            proximity<=3 and entry["rr"] is not None and
            entry["rr"]>=1.5 and entry["stop_risk_pct"]<=8):
            actionable.append(r)
    # Same date frozen reference close is deliberately not a next-day fill.
    result=dict(
        asof=day,
        source_received_at=source["received_at"],
        source_provider=source.get("provider"),
        price_basis=source.get("price_basis"),
        regular_only_certified=False,
        full_market_price_rows=len(prices),
        current_scope_counts=dict(scope),
        continuous_history_count=len(histories_by_ticker),
        analysis_eligible=count["analysis_eligible"],
        a_candidates=len(pool),
        b_candidates=len(b),
        A_top2=selected_a,B_top2=selected_b,
        B_turnover_top10=[summarize(r,histories_by_ticker,idx,bby[r["ticker"]]) for r in b[:10]],
        B_rs_first_top10=[summarize(r,histories_by_ticker,idx,bby[r["ticker"]],False) for r in by_rs[:10]],
        B_acceleration_first_top10=[summarize(r,histories_by_ticker,idx,bby[r["ticker"]],False) for r in by_accel[:10]],
        B_accessible_entry_candidates=len(actionable),
        B_accessible_entry_top10=[summarize(r,histories_by_ticker,idx,bby[r["ticker"]]) for r in actionable[:10]],
        chosen=[summarize(r,histories_by_ticker,idx,bby[r["ticker"]]) for r in b[:2]],
        no_holdover_bonus_in_code=True,
        ranking_sort="descending_20d_average_turnover_then_descending_rs20_then_ticker",
        historical_only=True,
        no_retroactive_signal_registration=True,
        no_independent_regular_session_certification=True
    )
    return result,models

def main():
    must(bool(os.environ.get("KRX_AUTH_KEY")),"OWNER_READ_KEY_REQUIRED")
    must(STATE.exists(),"FROZEN_RESEARCH_STATE_MISSING")
    BASE.mkdir(parents=True,exist_ok=True)
    os.environ["C3_KEY_ENVELOPES_DIR"]=str((STATE/"key_envelopes").resolve())
    manifests=Path("reports/c3_work8_20261105/inputs.json")
    must(manifests.is_file(),"PINNED_BOOTSTRAP_MANIFEST_MISSING")
    proof=restore(manifests,BASE/"inputs",STATE,BASE/"bootstrap_recovery.json")
    must(len(proof)==3,"PINNED_BOOTSTRAP_INCOMPLETE")
    panel=BASE/"inputs/panel/official_panel.csv.gz"
    qa=BASE/"inputs/panel/quality_audit.json"
    old=BASE/"inputs/latest/requested-date-probe/2026-11-04"
    basic=BASE/"inputs/issuer/basic"
    _,basics,kind,secondary,_=load_sources(old,basic,"reports/c3_work5_20261105/sources",
                                                datetime.now(timezone.utc).isoformat())
    stored={}
    for day in DAYS:
        path=SOURCE_LANE/"markets"/(day+".json.gz")
        must(path.is_file(),"MISSING_IMMUTABLE_DATED_MARKET_"+day)
        stored[day]=read_record(path)
    source_5=stored[DAYS[0]];source_6=stored[DAYS[1]]
    five,models5=reconstructed_day(DAYS[0],source_5,{},panel,qa,basics,kind,secondary)
    six,models6=reconstructed_day(DAYS[1],source_6,{DAYS[0]:source_5},panel,qa,basics,kind,secondary)

    decision=read_record(SOURCE_LANE/"decisions/2026-11-06.json")
    frozenb=decision["models"]["B"]
    must([r["ticker"] for r in frozenb]==six["B_top2"],"REGISTERED_11_06_B_TOP2_REPLAY_DIFFERENCE")
    for calc,orig in zip(models6["B"],frozenb):
        must(calc["ticker"]==orig["ticker"],"FROZEN_IDENTITY_DIFFERENCE")
        must(abs(calc["reference_close"]-orig["reference_close"])<1e-8,"FROZEN_PRICE_DIFFERENCE")
        must(abs(calc["turnover20"]-orig["turnover20"])<1e-4,"FROZEN_TURNOVER_RANK_DIFFERENCE")
        must(abs(calc["rs20"]-orig["rs20"])<1e-7,"FROZEN_RS_RANK_DIFFERENCE")
        must(calc["entry_plans"]==orig["entry_plans"],"FROZEN_ENTRY_STOP_PLAN_DIFFERENCE")
    # 2026-11-05 is a previous-reference example, not a registered forward
    # decision. Compare the historical reference without claiming registration.
    must(not (SOURCE_LANE/"decisions/2026-11-05.json").exists(),
         "NOV5_RETROACTIVE_DECISION_PRESENT")
    base_5={r["ticker"]:r for r in five["chosen"]}
    base_6={r["ticker"]:r for r in six["chosen"]}
    delta=[]
    for ticker in sorted(set(base_5)|set(base_6)):
        a=base_5.get(ticker);b=base_6.get(ticker)
        delta.append(dict(ticker=ticker,name=(b or a)["name"],
                          retained_in_B=bool(a and b),
                          rank_11_05=a["rank_turnover"] if a else None,
                          rank_11_06=b["rank_turnover"] if b else None,
                          close_change_pct=num(100*(b["close"]/a["close"]-1)) if a and b else None,
                          rs20_change_pct_points=num(b["rs20_pct_points"]-a["rs20_pct_points"]) if a and b else None,
                          turnover20_change_pct=num(100*(b["turnover20_krw"]/a["turnover20_krw"]-1)) if a and b else None,
                          entry_proximity_pct_11_06=b["entry"]["proximity_pct"] if b else None,
                          net_r1_rr_11_06=b["entry"]["rr"] if b else None))
    report=dict(
        schema="C3_TOP2_TWO_SESSION_PERSISTENCE_AUDIT_V1",
        observed_sessions=list(DAYS),
        provenance="IMMUTABLE_KRX_RESEARCH_PRICE_LANE_AND_HASH_PINNED_BOOTSTRAP",
        source_replay_engine=ENGINE,
        five_session="HISTORICAL_REFERENCE_RANK_NOT_A_FORWARD_REGISTERED_DECISION",
        six_session="EXISTING_IMMUTABLE_REGISTERED_DECISION_REPRODUCED_EXACTLY",
        preserved_registered_signals=4,
        research_only_no_regular_session_certification=True,
        original_score_type="NO_WEIGHTED_100_POINT_SCORE_LEXICOGRAPHIC_TURNOVER_RANK",
        model_changes=False,
        orders_enabled=False,
        telegram_sends=0,
        retroactive_recommendations=0,
        results={"2026-11-05":five,"2026-11-06":six},
        paired_selected=delta,
        overlapping_B_selected=sorted(set(five["B_top2"])&set(six["B_top2"])),
        analysis_notes=[
            "B rank inherits A pool and first sorts by 20d average turnover; RS and RS acceleration are binary gates. No carry-over bonus.",
            "A research price plan may exist even when spot is far away or reward/risk is poor.",
            "Hypothetical RS-first and reachable-entry screens are not validated outperformers; do not promote without forward results.",
            "11/5 is a retrospective reference rather than a registered C3 forward signal.",
            "Both samples lack independent regular-only certification; no actual trade or real return is inferred.",
        ],
    )
    dest=BASE/"c3_1105_1106_persistence_audit.json"
    dest.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    slim={
        "status":"PASS","counts":{day:{key:report["results"][day][key] for key in
            ("full_market_price_rows","analysis_eligible","a_candidates","b_candidates","B_top2","B_accessible_entry_candidates")}
            for day in DAYS},
        "paired_selected":delta,
        "11_06_B_top10":six["B_turnover_top10"],
        "11_06_B_rs_top10":six["B_rs_first_top10"],
        "11_06_accessible_top10":six["B_accessible_entry_top10"],
        "orders_enabled":False,"telegram_sends":0
    }
    print("C3_TWO_DAY_PERSISTENCE_AUDIT="+json.dumps(slim,ensure_ascii=False,allow_nan=False),flush=True)

if __name__=="__main__":main()
