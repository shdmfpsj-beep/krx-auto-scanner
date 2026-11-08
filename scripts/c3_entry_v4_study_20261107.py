#!/usr/bin/env python3
"""C3 V4 pre-registered (within this PR) geometric entry research.

- Reuse original v6 B DAILY selections unchanged; no new stock choice.
- Same 95-name retrospective (NOT PIT full-KRX) cohort, hash-verified input.
- Freeze V2 support-plan geometry at each prior *completed* decision close.
- Compare V2 one resting limit, half-band midpoint, and costed 1.0x/1.5x
  first resistance geometry limit caps, no post-open discretionary veto.
- Full common clock of 5/10/20 daily closes plus next exit OPEN.
- Exits use old V2 frozen structural stop; identical fees/slippage.
- Cash for *predeclared no-order* or *did not fill* (not a fabricated 0 trade).
- Mechanical fill AT/BELOW stop is counted, even when highly negative.
- Development / HOLDOUT and per-issuer 20-day nonoverlap; block selection bias
  claims. No trading, main changes, model promotion or notifications.
"""
from __future__ import annotations
import json,os,statistics
from collections import Counter,defaultdict
from pathlib import Path
from c3_entry_v4_geometry import VARIANTS,model_entry
from c3_entry_v2_preopen import exit_model,_bar_ok,entry as old_entry
from c3_entry_v2_study_20261107 import load_historical,require,jsonout,STATE
from c3_selection_factors_v6 import choose,nonoverlap
from c3_entry_practical_v7 import prepare

HORIZONS=(5,10,20)
OUT=Path("/tmp/c3-v4-entry-geometry")
CONFIG=dict(
    variants=list(VARIANTS),
    fixed_budgets=dict(V4_BALANCED=dict(net_first_r1_rr_min=1.,maximum_stop_pct=12.,
                                       minimum_costed_reward_pct=1.,lower_extension_atr_max=.5),
                       V4_DEFENSIVE=dict(net_first_r1_rr_min=1.5,maximum_stop_pct=8.,
                                         minimum_costed_reward_pct=2.,lower_extension_atr_max=.5),
                       V4_MIDPOINT=dict(price="QUOTE_DOWN((OLD_LOW+OLD_HIGH)/2)"),
                       V2_HIGH=dict(price="OLD_SUPPORT_PLAN_HIGH")),
    selection_model="B_DAILY_ORIGINAL_V6_UNCHANGED",
    original_r1_inference="ONLY_FROZEN_PRIOR_SESSION_CONFIRMED",
    original_stop_inference="ONLY_FROZEN_PRIOR_SESSION_CONFIRMED",
    first_eligible_day="FIRST_SESSION_AFTER_DECISION",
    order_expiration="ONE_NEXT_SESSION",
    stop_rule="CLOSE_BELOW_FROZEN_STRUCTURAL_STOP_EXIT_NEXT_OPEN",
    realized_costs="BUY0.0015_SELL0.005_ENTRY_AND_EXIT_SLIP0.001",
    post_open_orders_not_reconstructed=True,
    no_ordering_claim_for_intra_day_high_low=True,
    variant_choice_not_selected_by_holdout=True,
    cash_zeros_only_no_order_or_no_fill=True)

def _avg(a):
    return round(statistics.mean(a),6) if a else None

def metrics(rows,variant):
    n=len(rows)
    ent=[r for r in rows if r["result"][variant]["filled"]]
    outcomes=[r["result"][variant]["outcome"] for r in ent]
    returns=[x["net_pct"] for x in outcomes]
    costs=[r["result"][variant]["cash_adjusted_pct"] for r in rows]
    if len(costs)!=n:raise AssertionError("MISSING_CASH_DENOMINATOR")
    stops=sum(x.get("exit_reason")=="CLOSE_BELOW_FROZEN_STOP_NEXT_OPEN" for x in outcomes)
    by_status=Counter(r["result"][variant]["status"] for r in rows)
    no_order=sum(x["status"] in ("CAP_TOO_FAR_BELOW_FROZEN_BAND","UNKNOWN_OR_INVALID_R1",
        "CAP_BELOW_STOP","BAD_FROZEN_PLAN","BAD_FROZEN_GEOMETRY",
        "QUOTE_OR_COST_CONSTRAINT_FAILED") for r in rows for x in
        [r["result"][variant]])
    return dict(
        common_clock_plans=n,
        preclose_order_rejected=no_order,
        filled=len(ent),fill_rate_pct=round(len(ent)/n*100,3) if n else None,
        failed_or_nonfill=n-len(ent),
        complete_exits=len(outcomes),
        avg_net_of_completed_trades_pct=_avg(returns),
        median_net_of_completed_trades_pct=round(statistics.median(returns),6) if returns else None,
        win_rate_pct=round(100*sum(x>0 for x in returns)/len(returns),3) if returns else None,
        equal_opportunity_cash_adjusted_mean_pct=_avg(costs),
        stop_exit_count=stops,
        unsafe_open_at_or_below_stop_count=sum(r["result"][variant]["unsafe_open_stop"] for r in rows),
        first_day_low_touched_stop_count=sum(r["result"][variant]["same_day_low_touched_stop"] for r in rows),
        open_at_or_below_entry_limit_count=sum(r["result"][variant]["at_open_fill"] for r in rows),
        limit_extension_below_old_low=sum(r["result"][variant]["below_old_low_limit"] for r in rows),
        status_counts=dict(sorted(by_status.items())))

def compare(rows,variant):
    a=[];outliers=[]
    for r in rows:
        old=r["result"]["V2_HIGH"]["cash_adjusted_pct"]
        newer=r["result"][variant]["cash_adjusted_pct"]
        diff=newer-old
        a.append(diff)
        if abs(diff)>0.000001:
            outliers.append(dict(ticker=r["ticker"],decision_date=r["decision_date"],
                change_pp=round(diff,6),
                original_filled=r["result"]["V2_HIGH"]["filled"],
                adjusted_filled=r["result"][variant]["filled"]))
    paired_loo=[statistics.mean(a[:i]+a[i+1:]) for i in range(len(a))] if len(a)>1 else []
    outliers.sort(key=lambda x:abs(x["change_pp"]),reverse=True)
    return dict(paired_plans=len(a),
        mean_v4_minus_v2_equal_opportunity_pp=_avg(a),
        median_delta_pp=round(statistics.median(a),6) if a else None,
        improved_count=sum(x>1e-6 for x in a),
        worsened_count=sum(x<-1e-6 for x in a),
        unchanged_count=sum(abs(x)<=1e-6 for x in a),
        largest_winner_delta_pp=round(max(a),6) if a else None,
        largest_loser_delta_pp=round(min(a),6) if a else None,
        leave_one_signal_out_delta_pp_min=_avg([min(paired_loo)]) if paired_loo else None,
        leave_one_signal_out_delta_pp_max=_avg([max(paired_loo)]) if paired_loo else None,
        largest_changes=outliers[:5],all_observations_correlated=True,
        not_statistically_certified=True)

def assess_group(panel,sessions,decisions,fold,study_group):
    _,cells=prepare(decisions,panel,sessions,"A_SUPPORT_LIMIT")
    grid={s:i for i,s in enumerate(sessions)}
    by={ticker:{b["date"]:b for b in bars} for ticker,bars in panel.items()}
    results={}
    for horizon in HORIZONS:
        rows=[];invalid=Counter()
        for cell in cells:
            plan=cell["plan"]
            if not plan:
                invalid["NO_OLD_SUPPORT_PLAN"]+=1
                continue
            i=grid[cell["decision_date"]]
            # >= historical V2 group clock requirement, never extend study.
            if i+horizon+2>=len(sessions):
                invalid["INSUFFICIENT_FUTURE_FOR_COMMON_CLOCK"]+=1
                continue
            future=sessions[i+1:i+horizon+3]
            series=by[cell["ticker"]]
            if any(day not in series or not _bar_ok(series[day]) for day in future):
                invalid["MISSING_INVALID_UNTRADABLE_OR_ACTION_BOUNDARY"]+=1
                continue
            entry_day=future[0]
            variants={}
            for variant in VARIANTS:
                e,frozen=model_entry(plan,series[entry_day],variant)
                out=exit_model(plan,entry_day,e,series,sessions,horizon,
                               include_unsafe_mechanical=True)
                require(out["status"] in ("COMPLETE","NO_ENTRY"),
                        "V4_COMPLETE_COMMON_CLOCK_REQUIRED")
                if variant=="V2_HIGH":
                    old=old_entry(plan,series[entry_day],"RESTING_ONE")
                    require(e["status"]==old["status"] and
                            e["filled"]==old["filled"] and
                            (not e["filled"] or e["price"]==old["price"]),
                            "ORIGINAL_V2_RESTING_HIGH_IDENTITY_FAILED")
                variants[variant]=dict(
                    status=e["status"],filled=bool(e["filled"]),
                    plan_limit=frozen["limit"],
                    below_old_low_limit=(frozen.get("limit") is not None and
                                        frozen["limit"]<plan["low"]),
                    cash_adjusted_pct=out["net_pct"] if out["status"]=="COMPLETE" else 0.,
                    at_open_fill=bool(e.get("filled") and
                             e.get("individual_fills",[{}])[0].get("when")=="AT_OPEN"),
                    unsafe_open_stop=bool(e.get("open_at_or_below_stop")),
                    same_day_low_touched_stop=bool(e.get("same_day_low_touched_stop")),
                    outcome=out if out["status"]=="COMPLETE" else {})
            rows.append(dict(ticker=cell["ticker"],decision_date=cell["decision_date"],
                limit_prior_high=plan["high"],prior_low=plan["low"],
                prior_stop=plan["stop"],prior_r1=plan.get("resistance"),
                results_used_until=series[future[-1]]["date"],
                result=variants))
        for row in rows:
            for variant in VARIANTS:
                require(row["result"][variant]["filled"]==
                        (bool(row["result"][variant]["outcome"])),
                        "FILLED_STATUS_AND_COMPLETE_OUTCOME_DISAGREE")
        result=dict(selected_original_B_decisions=len(decisions),
            valid_support_plans=sum(c["plan"] is not None for c in cells),
            common_clock_plans=len(rows),
            exclusions=dict(invalid),
            baseline=metrics(rows,"V2_HIGH"),
            variants={variant:dict(metrics=metrics(rows,variant),
                paired_vs_v2=compare(rows,variant))
                for variant in VARIANTS if variant!="V2_HIGH"})
        results[str(horizon)]=result
    return dict(fold=fold,group=study_group,horizons=results)

def main():
    os.environ["C3_KEY_ENVELOPES_DIR"]=str((STATE/"key_envelopes").resolve())
    panel,sessions,pool,provenance=load_historical()
    res={}
    for fold in ("DEVELOPMENT","HOLDOUT"):
        selection=choose(pool,sessions,"B","DAILY",fold)
        if fold=="HOLDOUT":require(len(selection)==150,"B_ORIGINAL_HOLDOUT_RANKING_HAS_CHANGED")
        res[fold]={
          "ALL_REPEATED":assess_group(panel,sessions,selection,fold,"ALL_REPEATED"),
          "NONOVERLAP_20":assess_group(panel,sessions,nonoverlap(selection,sessions,20),fold,"NONOVERLAP_20")}
    output=dict(schema="C3_V4_FROZEN_GEOMETRY_RESEARCH_V1",
       source=provenance,
       experiment_protocol=CONFIG,
       results=res,
       structural_limits=[
           "Retrospectively selected 95-ticker curated cohort; NOT point-in-time whole KOSPI/KOSDAQ market.",
           "Nov6 actual result cannot be counted as a registered pre-09:00 recommendation: Nov5 preview was generated AFTER market opening.",
           "Full daily OHLCV does not confirm limit-order queue / partial volumes; trade-through is a hypothetical model.",
           "Pre-open resting order CAN fill below structural stop; there is no post hoc gap veto and all such adverse fills are INCLUDED.",
           "Next-day close exit after frozen structural stop is a model; not a same-day stop market order.",
           "Calendar and market session provenance not independently regular-only verified.",
           "Development and Holdout from same retrospective cohort; repeated observations serially dependent.",
           "Comparing three new rules invites multiple-testing bias. No selection or promotion based on best backtest row.",
           "All trades have an equal notional reference. Cash zeros for no order/fill, not a multi-slot capital-constrained performance.",
           "No new transaction, no telegram, no orders, no overwrite of registered decisions."],
       no_main_mutations=True,no_ledger_writes=True,
       official_krx_regular_only_certified=False,
       all_policy_variants_research_only=True,
       recommended_live_action="CASH")
    out=OUT/"v4_entry_geometry_study.json"
    jsonout(out,output)
    brief=dict(status="PASS",source_end=provenance["source_end"],
       cohort=provenance["selected_cohort_names"],
       results={fold:{group:{
           h:dict(n=z["common_clock_plans"],
               old=dict(fills=z["baseline"]["filled"],
                        equal_opportunity_cash=z["baseline"]["equal_opportunity_cash_adjusted_mean_pct"]),
               variants={v:dict(
                    fills=x["metrics"]["filled"],
                    no_order=x["metrics"]["preclose_order_rejected"],
                    opportunity_cash=x["metrics"]["equal_opportunity_cash_adjusted_mean_pct"],
                    mean_completed_net=x["metrics"]["avg_net_of_completed_trades_pct"],
                    paired_delta=x["paired_vs_v2"]["mean_v4_minus_v2_equal_opportunity_pp"],
                    improved=x["paired_vs_v2"]["improved_count"],
                    worsened=x["paired_vs_v2"]["worsened_count"],
                    changed_cases=x["paired_vs_v2"]["largest_changes"][:3])
                    for v,x in z["variants"].items()})
               for h,z in details["horizons"].items()}
           for group,details in groups.items()}
           for fold,groups in res.items()},
       no_registration=True,no_orders=True,no_alerts=True)
    print("C3_V4_GEOMETRY_RESEARCH="+json.dumps(brief,ensure_ascii=False,allow_nan=False),
          flush=True)

if __name__=="__main__":main()
