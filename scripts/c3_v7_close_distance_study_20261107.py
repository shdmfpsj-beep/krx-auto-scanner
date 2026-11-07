#!/usr/bin/env python3
"""C3 V7 zero-mutation same-clock 95-name study of close distance vs R1 risk.

The two V7 stress prescriptions are fixed before reading historical future
prices. V2 HIGH baseline must reproduce exactly the frozen V5 rows.
Persist only grouped numerical diagnostics; no raw source, PII or ledgers.
"""
from __future__ import annotations

import json, os, statistics
from collections import Counter, defaultdict
from pathlib import Path

from c3_v5_continuation_study_20261107 import (
    _rows, SOURCE_LAST, HORIZONS, market_map, indexed_benchmark,
)
from c3_v7_close_distance_frontier import (
    POLICIES, prior_distance_diagnostics, make_prior_close_plans, execute_frozen
)
from c3_entry_v2_preopen import exit_model
from c3_entry_v2_study_20261107 import (
    STATE, load_historical, require, jsonout,
)
from c3_selection_factors_v6 import choose,nonoverlap
from c3_entry_practical_v7 import prepare

OUT=Path("/tmp/c3-v7-close-distance")
FOLDS=("DEVELOPMENT","HOLDOUT")
GROUPS=("ALL_REPEATED","NONOVERLAP_20")

def _average(nums):
    return round(statistics.mean(nums),6) if nums else None

def _median(nums):
    return round(statistics.median(nums),6) if nums else None

def summarize(rows):
    n=len(rows)
    buckets=defaultdict(list)
    for row in rows:
        buckets[row["prior_distance"]["gap_bucket"]].append(row)
    def agg(sub):
        count=len(sub)
        policy_stats={}
        for policy in POLICIES:
            results=[z["outcome"][policy] for z in sub]
            fills=[z for z in results if z["filled"]]
            policy_stats[policy]=dict(
                selected=count,submitted=sum(z["submitted"] for z in results),
                raised_bids=sum(z["uplifted"] for z in results),
                model_fills=len(fills),
                open_fills=sum(z["at_open"] for z in fills),
                unverified_intraday_proxy_fills=sum(z["intraday_proxy"] for z in fills),
                unsafe_gap_below_or_at_stop_count=sum(z["at_or_below_stop"] for z in fills),
                model_fill_rate_pct=round(100*len(fills)/count,4) if count else None,
                mean_cash_inclusive_net_pct=_average([z["net_pct"] if z["filled"] else 0. for z in results]),
                mean_filled_trade_net_pct=_average([z["net_pct"] for z in fills]),
                missed_positive_hypothetical_open_reference=sum(
                    (r["reference"]>0 and not r["outcome"][policy]["filled"])
                    for r in sub),
                avoided_negative_hypothetical_open_reference=sum(
                    (r["reference"]<0 and not r["outcome"][policy]["filled"])
                    for r in sub),
                preclose_policy_status_counts=dict(sorted(Counter(
                    z["status"] for z in results).items())),
                mean_delta_vs_V2_pp=_average([
                    (r["outcome"][policy]["net_pct"] if r["outcome"][policy]["filled"] else 0.)
                    -(r["outcome"]["V2_HIGH"]["net_pct"] if r["outcome"]["V2_HIGH"]["filled"] else 0.)
                    for r in sub]),
            )
        gaps=[r["prior_distance"]["high_to_prior_close_gap_pct"] for r in sub]
        atrs=[r["prior_distance"]["high_to_prior_close_gap_atr"] for r in sub]
        safe_more=sum(
            r["outcome"]["V7_CLOSE_R1_GUARDED"]["filled"]
            and not r["outcome"]["V2_HIGH"]["filled"] for r in sub)
        stress_more=sum(
            r["outcome"]["V7_CLOSE_UPLIFT_UNGUARDED"]["filled"]
            and not r["outcome"]["V2_HIGH"]["filled"] for r in sub)
        return dict(n=count,median_prior_close_to_high_gap_pct=_median(gaps),
                    median_prior_close_to_high_gap_in_atr=_median(atrs),
                    baseline_high_rr_ge_1_count=sum(
                        (r["prior_distance"]["original_high_geometry"] is not None
                        and r["prior_distance"]["original_high_geometry"]["net_first_resistance_rr"] is not None
                        and r["prior_distance"]["original_high_geometry"]["net_first_resistance_rr"]>=1.)
                        for r in sub),
                    extra_model_fills_stress=stress_more,
                    extra_model_fills_guarded=safe_more,
                    policies=policy_stats)
    return dict(
        total_original_eligible=n,
        fully_paired_immutable_prior_close=True,
        all=agg(rows),
        by_preclose_price_distance_bucket={
            bucket:agg(items) for bucket,items in sorted(buckets.items())},
        bucket_boundaries_predefined_no_holdout_fitting=True)

def audit(panel,sessions,selection,fold,horizon,indices,markets):
    original,excluded,base=_rows(panel,sessions,selection,fold,horizon,indices,markets)
    original_plans=prepare(selection,panel,sessions,"A_SUPPORT_LIMIT")[1]
    cells={(c["ticker"],c["decision_date"]):c for c in original_plans}
    priors={(c["ticker"],c["decision_date"]):c for c in selection}
    require(len(cells)==len(original_plans) and len(priors)==len(selection),
            "V7_ORIGINAL_FROZEN_SELECTION_KEYS_DUPLICATED")
    bars={t:{b["date"]:b for b in xs} for t,xs in panel.items()}
    evaluated=[];without_plan=0
    for old in original:
        key=(old["ticker"],old["decision_date"])
        require(key in cells and key in priors,"V7_ORIGINAL_PLAN_NOT_FOUND")
        p=cells[key]["plan"]
        if p is None:
            without_plan+=1
            continue
        # Time-safe: all V7 risk and new caps are fixed before reading next bar.
        distance,plans=make_prior_close_plans(p,priors[key])
        require(distance["eligible"],"V7_BAD_PRIOR_CLOSE_GEOMETRY")
        # This bar is used only AFTER the preclose plan was fixed.
        first=bars[old["ticker"]][old["entry_date"]]
        by=bars[old["ticker"]]
        values={}
        for policy in POLICIES:
            frozen=plans[policy]
            ent=execute_frozen(p,frozen,first)
            actual=exit_model(p,old["entry_date"],ent,by,sessions,horizon,
                              include_unsafe_mechanical=True)
            require(actual["status"] in ("COMPLETE","NO_ENTRY"),
                    "V7_SAME_CLOCK_EXIT_MISSING")
            fill=bool(ent["filled"])
            require(fill==(actual["status"]=="COMPLETE"),
                    "V7_FILL_AND_EXIT_COHORT_MISMATCH")
            if policy=="V2_HIGH":
                old_control=old["output"][policy]
                require(old_control["filled"]==fill
                    and old_control["entry_status"]==ent["status"]
                    and old_control["limit"]==frozen["limit"]
                    and old_control["completed_net_pct"]==
                        (actual["net_pct"] if fill else None),
                    "V7_ORIGINAL_V2_RESULT_PARITY_FAILED")
            values[policy]=dict(
                submitted=bool(frozen["submitted"]),
                uplifted=bool(frozen.get("uplifted",False)),
                cap=frozen.get("limit"),
                status=frozen["status"],
                filled=fill,
                net_pct=actual["net_pct"] if fill else None,
                at_open=bool(fill and ent["individual_fills"][0]["when"]=="AT_OPEN"),
                intraday_proxy=bool(fill and ent["individual_fills"][0]["when"]=="INTRADAY_LIMIT_ASSUMED"),
                at_or_below_stop=bool(fill and ent.get("open_at_or_below_stop",False)),
                stop_exit=bool(fill and actual.get("exit_reason")=="CLOSE_BELOW_FROZEN_STOP_NEXT_OPEN"),
            )
        evaluated.append(dict(prior_distance=distance,outcome=values,
                              reference=old["independent_next_open_reference_net_pct"]))
    return dict(original_selection=len(selection),common_clock=base,
                without_original_support_plan=without_plan,
                excluded_full_clocks=excluded,
                observed_with_original_plan=len(evaluated),
                analysis=summarize(evaluated))

def main():
    os.environ["C3_KEY_ENVELOPES_DIR"]=str((STATE/"key_envelopes").resolve())
    panel,sessions,pool,provenance=load_historical()
    require(provenance["source_end"]==SOURCE_LAST,
            "V7_ORIGINAL_SOURCE_END_DRIFTED")
    indices=indexed_benchmark(sessions); markets=market_map(panel)
    report={}
    for fold in FOLDS:
        decisions=choose(pool,sessions,"B","DAILY",fold)
        if fold=="HOLDOUT":
            require(len(decisions)==150,"V7_FROZEN_HOLDOUT_SELECTION_DRIFT")
        report[fold]={}
        for group in GROUPS:
            selected=(decisions if group=="ALL_REPEATED"
                      else nonoverlap(decisions,sessions,20))
            report[fold][group]={}
            for horizon in HORIZONS:
                report[fold][group][str(horizon)]=audit(
                    panel,sessions,selected,fold,horizon,indices,markets)
    result=dict(
        schema="C3_V7_FROZEN_PRIOR_CLOSE_DISTANCE_AND_R1_FRONTIER_V1",
        source_end=SOURCE_LAST,
        source=provenance,
        prior_price_buckets=["CLOSE_AT_OR_BELOW_HIGH",
            "ABOVE_HIGH_0_TO_2","ABOVE_HIGH_2_TO_5",
            "ABOVE_HIGH_5_TO_10","ABOVE_HIGH_OVER_10"],
        fixed_hypotheses=list(POLICIES),
        experiment_guarded="RAISE_UP_TO_MIN_PRIOR_CLOSE_HIGH_PLUS_HALF_ATR_WITH_12PCT_STOP_1R_COSTED_R1_1PCT_NET_REWARD",
        experiment_unguarded="FALSIFICATION_STRESS_ONLY_NOT_BUY_APPROVAL",
        comparison_clock="FROZEN_B_DAILY_ORIGINAL_SELECTION_COMPLETE_5_10_20_SESSIONS",
        future_prices_used_only_for_model_fill_and_outcome=True,
        results=report,
        restrictions=[
            "Only retrospectively curated 95-name cohort; not PIT whole-market.",
            "Regular 09:00-15:30 prices, turnover, actual preopen quotes and queue fills not independently certified.",
            "A precommitted BUY resting limit may fill under the structural stop at auction.",
            "The next-open open-to-next-open reference is hypothetical and not broker executed.",
            "Intraday trade-through is a model, never a verified fill.",
            "Overlapping selections are dependent; nonoverlap samples very small.",
            "Post-close price buckets are calculated strictly from the preceding decision session.",
            "No re-ranking, ledger writes, Telegram sends, orders or scheduled alerts.",
        ],
        original_ledger_mutations=0,real_orders=0,telegram=0,
        new_strategy_approved=False,live_action="CASH",
    )
    OUT.mkdir(parents=True,exist_ok=True)
    jsonout(OUT/"v7_close_distance_frontier.json",result)
    brief={fold:{group:{h:dict(
        n=r["observed_with_original_plan"],
        all=r["analysis"]["all"],
        by_bucket={k:dict(n=v["n"],
            v2=v["policies"]["V2_HIGH"]["model_fills"],
            extra_guarded=v["extra_model_fills_guarded"],
            gap_pct=v["median_prior_close_to_high_gap_pct"])
            for k,v in r["analysis"]["by_preclose_price_distance_bucket"].items()})
        for h,r in x.items()}for group,x in groups.items()}
        for fold,groups in report.items()}
    print("C3_V7_FRONTIER="+json.dumps(dict(status="PASS",summary=brief,
        original_ledger_mutations=0,real_orders=0,telegram=0,
        approved=False),ensure_ascii=False,allow_nan=False),flush=True)

if __name__=="__main__":main()
