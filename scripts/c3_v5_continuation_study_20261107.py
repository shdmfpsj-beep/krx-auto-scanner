#!/usr/bin/env python3
"""C3 V5 original B selection continuation vs order access research.

A full same-clock, no-hindsight study. Strict separation between 1) next-5/10/20
session ex-post CONTINUATION LABELS, 2) original prior-session immutable signal
and 3) resting limit fill and exit with frozen structure. Never use ex-post
continuation labels to choose a trade.

No broker/Telegram, no ledger, no production or scheduled automation mutation.
"""
from __future__ import annotations
import csv,gzip,json,os,statistics
from collections import Counter,defaultdict
from pathlib import Path

from c3_v5_continuation_entry import POLICIES,simulate,prior_strong
from c3_entry_v2_preopen import entry as v2_entry,exit_model,_bar_ok,BUY_COST,SELL_COST,SLIPPAGE_EACH_SIDE
from c3_entry_v2_study_20261107 import BASE,STATE,load_historical,require,jsonout
from c3_selection_factors_v6 import choose,nonoverlap,load_indices
from c3_entry_practical_v7 import prepare

HORIZONS=(5,10,20)
OUT=Path("/tmp/c3-v5-continuation-entry")
CUT_DEVELOPMENT="2026-03-31"
START_HOLDOUT="2026-05-01"
SOURCE_LAST="2026-11-03"
EVAL_POLICIES=POLICIES

def mean_or_none(a):
    return round(statistics.mean(a),6) if a else None

def net_price_reference(buy,sell):
    # A purely hypothetical next OPEN-to-following OPEN benchmark, not
    # an executable order or a model fill; includes same cost assumptions.
    return 100*(sell*(1-SELL_COST)*(1-SLIPPAGE_EACH_SIDE)/
                (buy*(1+BUY_COST)*(1+SLIPPAGE_EACH_SIDE))-1)

def market_map(panel):
    path=BASE/"inputs/panel/official_panel.csv.gz"
    markets={}
    with gzip.open(path,"rt",encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["ticker"] in panel:
                if row["ticker"] in markets:
                    require(markets[row["ticker"]]==row["market"],
                            "MARKET_CLASSIFICATION_CHANGED_IN_PANEL")
                markets[row["ticker"]]=row["market"]
    require(set(markets)==set(panel),"SELECTED_TICKERS_MARKET_MAP_INCOMPLETE")
    return markets

def indexed_benchmark(sessions):
    # source-reconciled historical index prefix already written and SHA
    # validated by the frozen V2 load_historical() step.
    return load_indices(BASE/"dated_indices",sessions)[0]

def _rows(panel,sessions,selection,fold,horizon,indices,markets):
    cells=prepare(selection,panel,sessions,"A_SUPPORT_LIMIT")[1]
    prior={(r["ticker"],r["decision_date"]):r for r in selection}
    grid={date:i for i,date in enumerate(sessions)}
    prices={ticker:{b["date"]:b for b in bars} for ticker,bars in panel.items()}
    evaluated=[];excluded=Counter()
    for cell in cells:
        ticker=cell["ticker"];d=cell["decision_date"]
        i=grid[d];e=i+1;last=e+horizon+1
        if last>=len(sessions):
            excluded["HORIZON_NOT_MATURED"]+=1;continue
        if fold=="DEVELOPMENT" and sessions[last]>CUT_DEVELOPMENT:
            excluded["CROSSES_DEVELOPMENT_FOLD_BOUNDARY"]+=1;continue
        if fold=="HOLDOUT" and (d<START_HOLDOUT or sessions[e]<START_HOLDOUT):
            excluded["CROSSES_HOLDOUT_FOLD_BOUNDARY"]+=1;continue
        span=sessions[e:last+1]
        by=prices[ticker]
        if any(day not in by or not _bar_ok(by[day]) for day in span):
            excluded["INVALID_PRICE_OR_UNTRADABLE_INSIDE_FULL_COMMON_CLOCK"]+=1;continue
        p=cell["plan"]
        current=prior.get((ticker,d))
        require(current is not None and current["decision_date"]==d,
                "ORIGINAL_SELECTION_PAIRING_INVALID")
        require(d in by and _bar_ok(by[d]),"DECISION_SESSION_INVALID_OR_UNAVAILABLE")
        require(markets[ticker] in indices,"INDEX_MARKET_NOT_FOUND")
        index=indices[markets[ticker]]
        first=by[sessions[e]];final_close=by[sessions[e+horizon]]
        ref=net_price_reference(first["open"],by[sessions[last]]["open"])
        raw_pct=100*(final_close["close"]/by[d]["close"]-1)
        market_pct=100*(index[sessions[e+horizon]]/index[d]-1)
        relative=raw_pct-market_pct
        strong=prior_strong(current)
        require(not strong["missing"],"PRIOR_FACTOR_MISSING_IN_FROZEN_B_POOL")
        outcomes={}
        for policy in EVAL_POLICIES:
            planned,e_result=simulate(p,current,first,policy)
            if p is None:
                exit_result=dict(status="NO_ENTRY",net_pct=None)
            else:
                exit_result=exit_model(p,first["date"],e_result,by,sessions,horizon,
                    include_unsafe_mechanical=True)
            require(exit_result["status"] in ("COMPLETE","NO_ENTRY"),
                "V5_SHARED_CLOCK_ENTRY_EXIT_UNRESOLVED")
            filled=bool(e_result.get("filled",False))
            require(filled==(exit_result["status"]=="COMPLETE"),
                "V5_FILL_STATUS_EXIT_MISMATCH")
            if policy=="V2_HIGH" and p is not None:
                old=v2_entry(p,first,"RESTING_ONE")
                require(old["status"]==e_result["status"] and old["filled"]==filled
                    and (not filled or old["price"]==e_result["price"]),
                    "V2_SINGLE_RESTING_MODEL_PARITY_BROKEN")
            outcomes[policy]=dict(
                prior_status=planned["status"],
                limit=planned.get("limit"),
                submitted=planned["submitted"],
                filled=filled,
                entry_status=e_result["status"],
                completed_net_pct=exit_result["net_pct"] if filled else None,
                cash_opportunity_pct=exit_result["net_pct"] if filled else 0.0,
                exit_reason=exit_result.get("exit_reason"),
                at_open=bool(filled and e_result["individual_fills"][0]["when"]=="AT_OPEN"),
                same_session_low_touch_stop=bool(e_result.get("same_day_low_touched_stop",False)),
                unsafe_gap_at_or_below_stop=bool(e_result.get("open_at_or_below_stop",False)),
                model_intraday_limit_fill_assumed=bool(
                    filled and e_result["individual_fills"][0]["when"]!="AT_OPEN"),
            )
        evaluated.append(dict(ticker=ticker,decision_date=d,entry_date=first["date"],
            fold=fold,source_plan_present=p is not None,
            frozen_signal_rank=current.get("rank"),
            prior_market_regime=current["market_regime"],
            prior_strength=strong,
            price_horizon=horizon,
            stock_close_change_from_decision_pct=round(raw_pct,6),
            market_close_change_pct=round(market_pct,6),
            stock_excess_close_pct=round(relative,6),
            continuation_up=raw_pct>0,
            continuation_outperformed_market=relative>0,
            independent_next_open_reference_net_pct=round(ref,6),
            output=outcomes))
    return evaluated,dict(excluded),dict(
        original_selected=len(selection),full_clock=len(evaluated),
        with_preclose_support_plan=sum(r["source_plan_present"] for r in evaluated),
        without_plan=sum(not r["source_plan_present"] for r in evaluated))

def aggregate(rows,policy,baseline="V2_HIGH"):
    n=len(rows)
    completed=[r for r in rows if r["output"][policy]["filled"]]
    trades=[r["output"][policy]["completed_net_pct"] for r in completed]
    opportunity=[r["output"][policy]["cash_opportunity_pct"] for r in rows]
    deltas=[r["output"][policy]["cash_opportunity_pct"]-
        r["output"][baseline]["cash_opportunity_pct"] for r in rows]
    clustered=defaultdict(list)
    for r,diff in zip(rows,deltas):
        clustered[r["decision_date"]].append(diff)
    clusters=[statistics.mean(vals) for vals in clustered.values()]
    loo=[statistics.mean(deltas[:i]+deltas[i+1:]) for i in range(n)] if n>1 else []
    missed_up=sum(r["continuation_up"] and not r["output"][policy]["filled"]
        for r in rows)
    missed_ref_profit=sum(r["independent_next_open_reference_net_pct"]>0 and
        not r["output"][policy]["filled"] for r in rows)
    captured_ref_profit=sum(r["independent_next_open_reference_net_pct"]>0 and
        r["output"][policy]["filled"] for r in rows)
    passed_neg=sum(r["independent_next_open_reference_net_pct"]<0 and
        not r["output"][policy]["filled"] for r in rows)
    return dict(
        evaluated_preclose_B_picks=n,
        submitted=sum(r["output"][policy]["submitted"] for r in rows),
        preclose_rejected=sum(not r["output"][policy]["submitted"] for r in rows),
        filled=len(completed),
        fill_rate_pct=round(len(completed)*100/n,3) if n else None,
        skipped_or_unfilled=n-len(completed),
        at_open_fills=sum(r["output"][policy]["at_open"] for r in completed),
        hypothetical_intraday_trade_through_fills=sum(
            r["output"][policy]["model_intraday_limit_fill_assumed"] for r in completed),
        risky_below_stop_open_fills=sum(
            r["output"][policy]["unsafe_gap_at_or_below_stop"] for r in completed),
        first_session_low_touched_stop=sum(
            r["output"][policy]["same_session_low_touch_stop"] for r in completed),
        model_close_stop_exits=sum(
            r["output"][policy]["exit_reason"]=="CLOSE_BELOW_FROZEN_STOP_NEXT_OPEN"
            for r in completed),
        mean_completed_trade_net_pct=mean_or_none(trades),
        median_completed_trade_net_pct=round(statistics.median(trades),6) if trades else None,
        completed_win_rate_pct=round(100*sum(x>0 for x in trades)/len(trades),3)
            if trades else None,
        mean_cash_adjusted_return_per_original_selection_pct=mean_or_none(opportunity),
        paired_mean_delta_vs_V2_pp=mean_or_none(deltas),
        paired_median_delta_vs_V2_pp=round(statistics.median(deltas),6) if deltas else None,
        paired_improved_count=sum(x>1e-6 for x in deltas),
        paired_worsened_count=sum(x<-1e-6 for x in deltas),
        paired_unchanged_count=sum(abs(x)<=1e-6 for x in deltas),
        paired_leave_one_signal_out_delta_min=round(min(loo),6) if loo else None,
        paired_leave_one_signal_out_delta_max=round(max(loo),6) if loo else None,
        same_day_cluster_count=len(clustered),
        paired_equal_date_cluster_mean_delta_pp=mean_or_none(clusters),
        missed_next_open_reference_profitable_count=missed_ref_profit,
        captured_next_open_reference_profitable_count=captured_ref_profit,
        avoided_negative_reference_count=passed_neg,
        missed_positive_decision_close_continuations=missed_up,
        preclose_rejection_causes=dict(sorted(Counter(
           r["output"][policy]["prior_status"] for r in rows
           if not r["output"][policy]["submitted"]).items())),
        all_results_descriptive_not_proven_edge=True)

def continuation_cohorts(rows):
    by_label={}
    for label,cohort in (("PRIOR_STRONG",[
           r for r in rows if r["prior_strength"]["strong"]]),
            ("PRIOR_NOT_STRONG",[
           r for r in rows if not r["prior_strength"]["strong"]])):
        a=[r["stock_excess_close_pct"] for r in cohort]
        by_label[label]=dict(
            n=len(cohort),
            continuation_positive_count=sum(r["continuation_up"] for r in cohort),
            continuation_positive_rate_pct=round(
                sum(r["continuation_up"] for r in cohort)*100/len(cohort),3)
                if cohort else None,
            outperformed_market_count=sum(
                r["continuation_outperformed_market"] for r in cohort),
            excess_close_mean_pct=mean_or_none(a),
            next_open_reference_profit_count=sum(
                r["independent_next_open_reference_net_pct"]>0 for r in cohort),
            control_V2_high_fills=sum(r["output"]["V2_HIGH"]["filled"] for r in cohort))
    return by_label

def main():
    os.environ["C3_KEY_ENVELOPES_DIR"]=str((STATE/"key_envelopes").resolve())
    panel,sessions,pool,provenance=load_historical()
    require(provenance["source_end"]==SOURCE_LAST,
            "C3_ORIGINAL_HISTORICAL_END_CHANGED")
    index=indexed_benchmark(sessions)
    markets=market_map(panel)
    report={}
    for fold in ("DEVELOPMENT","HOLDOUT"):
        decisions=choose(pool,sessions,"B","DAILY",fold)
        if fold=="HOLDOUT":require(len(decisions)==150,"B_DAILY_HOLDOUT_CHANGED")
        report[fold]={}
        for label,selection in (("ALL_REPEATED",decisions),
                ("NONOVERLAP_20",nonoverlap(decisions,sessions,20))):
            metrics={}
            for horizon in HORIZONS:
                rows,excluded,base=_rows(panel,sessions,selection,fold,horizon,index,markets)
                metrics[str(horizon)]=dict(
                    **base,horizon_sessions=horizon,
                    source_eligible_exclusions=excluded,
                    prior_continuation_labels=continuation_cohorts(rows),
                    baseline=aggregate(rows,"V2_HIGH"),
                    policy_comparison={p:aggregate(rows,p)
                                       for p in POLICIES if p!="V2_HIGH"},
                    selection_not_reoptimized=True)
            report[fold][label]=metrics
    out=dict(schema="C3_V5_CONTINUATION_AND_FILL_OPPORTUNITY_V1",
        source=provenance,source_session_end=SOURCE_LAST,
        fixed_hypotheses=dict(
            baseline="V2_HIGH",policies=list(POLICIES),
            B_selection="IMMUTABLE_ORIGINAL_PRIOR_CLOSE_B_DAILY_TOP2",
            first_resistance="FROZEN_STRUCTURAL_R1_NOT_INTRADAY_LOOKAHEAD",
            trend_strong="PREDECISION_TREND60_TRUE_AND_TURNOVER_RATIO_GE_1",
            adaptive="STRONG_AT_OLD_HIGH_ELSE_MIDPOINT",
            strict_risk_guard="HIGH_OR_MID_COSTED_R1_RR_GE1_AND_RAW_STOP_LE12_AND_NET_REWARD_GE1PCT",
            continuation_label="future_session_CLOSE_vs_DECISION_CLOSE_AND_MATCHED_INDEX_CLOSE",
            profitable_missed_reference="HYPOTHETICAL_NEXT_OPEN_TO_EXIT_NEXT_OPEN_INCLUDING_V2_COSTS",
            entry="ONE_NEXT_SESSION_RESTING_BUY_LIMIT_AUCTION_OR_TRADE_THROUGH_ONLY",
            model_exit="FROZEN_STOP_CLOSE_BREACH_OR_HORIZON_THEN_FOLLOWING_OPEN",
            common_clock_maturity="ENTRY_OPEN_PLUS_H_OBSERVED_CLOSES_PLUS_FOLLOWING_OPEN",
            fold_scope="DEVELOPMENT_FUTURE_EXIT_MUST_NOT_CROSS_2026_03_31",
            model_selection_by_holdout="FORBIDDEN",
            strategy_deployment="NOT_APPROVED"),
        results=report,
        limitations=[
            "NOT a point-in-time full-market test; original 95-curated-name selection has survivorship and industry-vintage bias.",
            "Even ticker nonoverlap 20 does not remove same-day / common-market / serial dependence.",
            "Low number of complete model fills; future-positive stock labels are not probability estimates.",
            "The study treats modeled next-open reference as hypothetical; it is not a fillable market order verified by a broker.",
            "No intraday sequencing from daily OHLC or passive limit queue fill certainty.",
            "Preopen resting stop-gap fills are NOT posthoc canceled and may lose beyond original stop.",
            "Historical regular-only price-volume-turnover independent attestation remains unresolved.",
            "Nov5 plan preview was generated after Nov6 open and cannot be treated as preopen C3 published signal.",
            "No broker calls, no notifications, no mutation of preexisting C3 signals or ledger.",
        ],
        real_2026_11_06_forward_completed=0,
        official_krx_regular_only_certified=False,
        main_workflow_changed=False,
        auto_trade_authorized=False,
        default_live_action="CASH")
    jsonout(OUT/"v5_continuation_entry_study.json",out)
    short=dict(status="PASS",source_end=SOURCE_LAST,
        cohort=provenance["selected_cohort_names"],
        results={fold:{group:{
          h:dict(n=d["full_clock"],plans=d["with_preclose_support_plan"],
            continuation=d["prior_continuation_labels"],
            baseline={k:d["baseline"][k] for k in
              ("filled","mean_cash_adjusted_return_per_original_selection_pct",
               "missed_next_open_reference_profitable_count")},
            variants={p:{k:r[k] for k in
              ("filled","preclose_rejected",
               "mean_cash_adjusted_return_per_original_selection_pct",
               "paired_mean_delta_vs_V2_pp",
               "missed_next_open_reference_profitable_count",
               "captured_next_open_reference_profitable_count",
               "avoided_negative_reference_count")}
              for p,r in d["policy_comparison"].items()})
          for h,d in hs.items()}
          for group,hs in groups.items()}
          for fold,groups in report.items()},
        modified_original_decisions=0,broker_orders=0,telegram_messages=0,
        strategy_approved=False)
    print("C3_V5_CONTINUATION_STUDY="+json.dumps(short,ensure_ascii=False,allow_nan=False),
          flush=True)

if __name__=="__main__":main()
