#!/usr/bin/env python3
"""C3 V3 causal profit-protection exit comparison on identical V2 entry signals.

READ ONLY, no user orders, no Telegram messages, no registered decision writes.
Current 11/06 selected signals have no matured 5/10/20-session outcome.

Historical comparisons reuse pinned C3 B DAILY model and v7 A_SUPPORT_LIMIT
entry plans in the same retrospective 95-name cohort and same complete clocks.
These data cannot prove a deployment edge: non-PIT membership, source session
uncertified, serial dependence, tiny completed fills.
"""
from __future__ import annotations
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from c3_entry_v2_preopen import entry, exit_model, _bar_ok
from c3_entry_v2_study_20261107 import BASE, STATE, load_historical, require, jsonout
from c3_exit_v3_close_confirmed import (
    POLICIES, HORIZONS, aggregation, exit_strategy, TRAIL_TRIGGER_PCT,
    TRAIL_ATR_MULT)
from c3_selection_factors_v6 import choose, nonoverlap
from c3_entry_practical_v7 import prepare

ENTRY_METHODS=("LEGACY_GAP_VETO","RESTING_ONE","RESTING_TWO")
QUALITY_FILTERS=(
    ("NO_PRE_DECISION_EXTRA_GATE", None, None, None),
    ("PLAN_RR1_GE_1_RISK_LE_10", 1.,10.,None),
    ("PLAN_RR1_GE_1_5_RISK_LE_8_TURNOVER_GE_1B",1.5,8.,1_000_000_000),
)
OUT=Path("/tmp/c3-exit-v3-research/exit_v3_comparison.json")


def prior_eligibility(plan,rr_min,risk_max,turnover_min):
    if plan is None:return False
    if rr_min is None:return True
    ratio=plan.get("net_r1_rr")
    risk=plan.get("risk_pct")
    trn=plan.get("rank_turnover")
    return (
        ratio is not None and ratio>=rr_min and
        risk is not None and risk<=risk_max and
        (turnover_min is None or trn is not None and trn>=turnover_min)
    )


def paired_metrics(base,variant):
    require(len(base)==len(variant),"PAIRED_SAMPLE_N_MISMATCH")
    pairs=[]
    count_eligible=0
    for b,v in zip(base,variant):
        require(b["status"]==v["status"] or (
                b["status"]=="COMPLETE" and v["status"]=="COMPLETE"),
                "PAIRED_ENTRY_DISCREPANCY")
        if b["status"]!="COMPLETE":continue
        count_eligible+=1
        pairs.append(v["net_pct"]-b["net_pct"])
    return dict(
        paired_filled_count=count_eligible,
        mean_exit_only_improvement_pct=round(mean(pairs),6) if pairs else None,
        better_count=sum(x>1e-6 for x in pairs),
        worse_count=sum(x<-1e-6 for x in pairs),
        equal_count=sum(abs(x)<=1e-6 for x in pairs),
        tiny_dependent_sample=True)


def evaluate_group(panel,sessions,selection,group,fold):
    _,cells=prepare(selection,panel,sessions,"A_SUPPORT_LIMIT")
    baseline_stat=dict(
        selected=len(selection),
        with_a_support_plan=sum(c["plan"] is not None for c in cells),
        plan_absence=dict(Counter(c["status"] for c in cells if c["plan"] is None)))
    by={ticker:{b["date"]:b for b in bars} for ticker,bars in panel.items()}
    day_grid={d:i for i,d in enumerate(sessions)}
    horizon_rows={}
    for h in HORIZONS:
        raw=[]
        common_dates=0
        valid_plan_dates=0
        for c in cells:
            p=c["plan"]
            if not p:continue
            i=day_grid[c["decision_date"]]
            # Full, common denominator: entry is next open, h completed closes,
            # exit at a subsequent open. No last-day profit inference.
            if i+h+2>=len(sessions):continue
            dates=sessions[i+1:i+h+3]
            future=by[c["ticker"]]
            if any(d not in future or not _bar_ok(future[d]) for d in dates):
                continue
            common_dates+=1
            valid_plan_dates+=1
            entry_day=dates[0]
            for m in ENTRY_METHODS:
                ent=entry(p,future[entry_day],m)
                cases={policy:exit_strategy(p,entry_day,ent,future,sessions,h,policy)
                       for policy in POLICIES}
                if any(v["status"] not in ("COMPLETE","NO_ENTRY") for v in cases.values()):
                    raise ValueError("UNRESOLVED_EXIT_FOR_FULL_COMMON_CLOCK")
                # Reproduce precisely the prior frozen V2 baseline, including
                # cost and same-session stop / next-open semantics.
                original=exit_model(p,entry_day,ent,future,sessions,h,
                                    include_unsafe_mechanical=True)
                first=cases["BASELINE"]
                require(first["status"]==original["status"],"V2_EXIT_STATUS_PARITY_FAILED")
                if first["status"]=="COMPLETE":
                    require(first["exit_date"]==original["exit_date"],"V2_EXIT_DATE_PARITY_FAILED")
                    require(abs(first["net_pct"]-original["net_pct"])<0.000002,
                            "V2_EXIT_NET_RETURN_PARITY_FAILED")
                raw.append(dict(
                    ticker=c["ticker"],decision_date=c["decision_date"],entry_day=entry_day,
                    method=m,ent=ent,
                    entry_basis=p["reference_close"],
                    target_present=p.get("resistance") is not None,
                    prior_rr=p.get("net_r1_rr"),prior_risk=p.get("risk_pct"),
                    prior_liquidity=p.get("rank_turnover"),
                    plan=p,policies=cases))
        method_summary={}
        for method in ENTRY_METHODS:
            mr=[r for r in raw if r["method"]==method]
            filtered={}
            for label,rr,risk,turnover in QUALITY_FILTERS:
                sample=[r for r in mr if prior_eligibility(r["plan"],rr,risk,turnover)]
                bypolicy={policy:[r["policies"][policy] for r in sample] for policy in POLICIES}
                baseline=bypolicy["BASELINE"]
                filtered[label]=dict(
                    prior_decision_filter=dict(rr_min=rr,plan_risk_max_pct=risk,
                                               mean_turnover20_min_krw=turnover),
                    plans=len(sample),
                    has_frozen_r1=sum(r["target_present"] for r in sample),
                    entry_filled=sum(r["ent"].get("filled",False) for r in sample),
                    entries_at_or_below_stop=sum(r["ent"].get("open_at_or_below_stop",False)
                                                 for r in sample),
                    exit_policies={
                        policy:dict(aggregation(vals),
                                    difference_vs_baseline=paired_metrics(baseline,vals))
                        for policy,vals in bypolicy.items()})
            method_summary[method]=filtered
        horizon_rows[str(h)]=dict(
            fixed_selected=len(selection),
            plan_count=baseline_stat["with_a_support_plan"],
            complete_common_clock_plans=common_dates,
            variants=method_summary)
    return dict(fold=fold,selection_group=group,**baseline_stat,
                horizons=horizon_rows)


def main():
    os.environ["C3_KEY_ENVELOPES_DIR"]=str((STATE/"key_envelopes").resolve())
    panel,sessions,pool,provenance=load_historical()
    evaluations={}
    for fold in ("DEVELOPMENT","HOLDOUT"):
        decisions=choose(pool,sessions,"B","DAILY",fold)
        if fold=="HOLDOUT":
            require(len(decisions)==150,"V3_FROZEN_B_HOLDOUT_SELECTION_CHANGED")
        full=decisions
        unique=nonoverlap(decisions,sessions,20)
        evaluations[fold]={
            "ALL_REPEATED":evaluate_group(panel,sessions,full,"ALL_REPEATED",fold),
            "NONOVERLAP_20":evaluate_group(panel,sessions,unique,"NONOVERLAP_20",fold)
        }
    output=dict(
        schema="C3_EXIT_V3_CLOSE_CONFIRMED_RESEARCH_V1",
        original_engine_pinned="077113ac2f5e93fecc4c47850b36e5eda2173e3d",
        v2_research_ref="research/c3-entry-v2-preopen-gap-backtest-20261107",
        frozen_hypotheses=dict(policies=list(POLICIES),entry_methods=list(ENTRY_METHODS),
             horizons=list(HORIZONS),trail_activation_close_gain_pct=TRAIL_TRIGGER_PCT,
             trailing_stop_frozen_atr_multiple=TRAIL_ATR_MULT,
             partial_r1_fraction_original_position=.5,
             first_resistance_requires_session_CLOSE=True,
             target_order_execution= "NEXT_OPEN_NOT_HIGH_R1_PRICE",
             moving_stop_applies_from="NEXT_BAR_CLOSE_AFTER_UPDATE",
             stop_breach_execution="NEXT_OPEN",
             costs="FROZEN_V2_COSTS_WITH_BUY_AND_SELL_SLIPPAGE",
             full_exit_priority="CLOSE_STOP_BEFORE_HORIZON_BEFORE_PARTIAL"),
        source_provenance=provenance,
        results=evaluations,
        validations=dict(original_v2_full_exit_reproduced=True,
                         cohort_not_pit_market=True,
                         regular_market_source_independently_certified=False,
                         unique_registered_forward_11_06_matured_trades=0,
                         no_future_intraday_target_fill_assumed=True,
                         no_actual_orders_or_telegram_or_ledger_write=True,
                         no_live_rules_promoted=True),
        caution=[
            "Strategy returns are C3 hypothetical retrospective exits, not live trading returns.",
            "Original panel is a retrospectively chosen 95-stock basket: sector and survivorship selection biases remain.",
            "Data historical regular-only source is not independently certified.",
            "R1 confirmation and trailing threshold are based on prior confirmed CLOSE; decisions execute at NEXT OPEN.",
            "Same-session bar extremes are not used to claim a take-profit, stop-fill order or sequence.",
            "Only investable prior-session data may be used for eligibility. All tested variants are exploratory.",
            "Reports must distinguish repeated observations from 20-session nonoverlapping sensitivity, not cherry-pick positive dates.",
            "Real registered Nov6 model has 0 completed forward 5/10/20-session performance observations.",
        ])
    jsonout(OUT,output)
    short=dict(status="PASS",source_end=provenance["source_end"],
        source_cohort=provenance["selected_cohort_names"],
        results={fold:{
            group:{h:{
                "n":v["complete_common_clock_plans"],
                "resting_one_unfiltered":{p:dict(
                    completed=w["completed"],
                    partial_executions=w["partial_execution_count"],
                    trail_activated=w["trail_activated_count"],
                    conditional_mean_net_pct=w["conditional_mean_net_pct"],
                    opportunity_mean_with_cash_pct=w["opportunity_mean_with_cash_pct"],
                    paired_delta=w["difference_vs_baseline"]["mean_exit_only_improvement_pct"],
                    paired_n=w["difference_vs_baseline"]["paired_filled_count"])
                 for p,w in v["variants"]["RESTING_ONE"]["NO_PRE_DECISION_EXTRA_GATE"]["exit_policies"].items()},
                "rr15_risk8_1b_prior_n":v["variants"]["RESTING_ONE"][
                     "PLAN_RR1_GE_1_5_RISK_LE_8_TURNOVER_GE_1B"]["plans"]
            } for h,v in d["horizons"].items()}
            for group,d in groups.items()}
         for fold,groups in evaluations.items()},
        "no_actions":True,
        "no_model_promotion":True)
    print("C3_EXIT_V3_RESEARCH="+json.dumps(short,ensure_ascii=False,allow_nan=False),flush=True)


if __name__=="__main__":main()
