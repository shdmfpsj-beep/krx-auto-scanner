"""Compare existing C3 touch observations with earlier ICT signals, research only.

ICT signals must be strictly earlier than the C3 watch-touch date.
No same-day sequencing assumptions, no filled orders, no profitability claims.
"""
import argparse,csv,json
from pathlib import Path
from c3_price_concordance_v1 import read_rows
from c3_ict_sequence_research_v1 import detect
from c3_watch_touch_forward_outcomes_v1 import build

def compare(plans, prices, ict_lookback=10, signal_max_age=10):
    if signal_max_age<1:
        raise ValueError("INVALID_SIGNAL_MAX_AGE")
    if ict_lookback<3:
        raise ValueError("LOOKBACK_TOO_SHORT")
    baseline=build(plans,prices,require_top2=False)
    enriched=[]
    for result in baseline["results"]:
        ticker=result["ticker"]
        series=sorted((day,bar) for (code,day),bar in prices.items() if code==ticker)
        if not series:
            raise ValueError("MISSING_TICKER_PRICE_HISTORY")
        bars=[dict(bar,date=day) for day,bar in series]
        signals=detect(bars,lookback=ict_lookback)
        # Use only signals completed strictly before touch date.
        signal_events={s["date"]:s for s in signals if s["event"]=="FVG_RETEST_WATCH"}
        day_index={day:i for i,(day,_) in enumerate(series)}
        # Count only first touch per plan to avoid repeat-event sample inflation.
        for event in result["events"][:1]:
            i=day_index[event["date"]]
            preceding=[d for d,s in signal_events.items() if d in day_index
                       and 0<i-day_index[d]<=signal_max_age
                       and all(series[j][1]["close"]>=s["sweep_invalidation_low"]
                               for j in range(day_index[d]+1,i+1))]
            prior_signal=max(preceding) if preceding else None
            enriched.append(dict(ticker=ticker,plan_id=result["plan_id"],
                                 touch_date=event["date"],
                                 prior_ict_retest_date=prior_signal,
                                 ict_prior_signal=prior_signal is not None,
                                 status=event["status"],
                                 touch_day_execution_ambiguous=event["touch_day_execution_ambiguous"],
                                 outcomes=event["outcomes"],
                                 verified_fill=False))
    # Retention is measured on independent first-touch plans, not repeat
    # touch events. A stricter filter may discard otherwise useful setups.
    eligible=[e for e in enriched if not e["touch_day_execution_ambiguous"]]
    ambiguous_count=sum(e["touch_day_execution_ambiguous"] for e in enriched)
    untouched_plan_count=len(baseline["results"])-len(enriched)
    with_ict=[e for e in eligible if e["ict_prior_signal"]]
    retention=dict(total_plans=len(baseline["results"]),
                   no_touch_plans=untouched_plan_count,
                   ambiguous_touch_plans=ambiguous_count,
                   eligible_first_touch_plans=len(eligible),
                   retained_with_prior_ict=len(with_ict),
                   excluded_without_prior_ict=len(eligible)-len(with_ict),
                   retained_pct=(round(100*len(with_ict)/len(eligible),2)
                                 if eligible else None))
    counts={}
    for h in (5,10,20):
        counts[str(h)]={}
        for label,selected in (("prior_ict",True),("no_prior_ict",False)):
            cohort=[e for e in enriched if e["ict_prior_signal"]==selected
                    and not e["touch_day_execution_ambiguous"]]
            complete=[next(x for x in e["outcomes"] if x["horizon_sessions"]==h)
                      for e in cohort]
            complete=[x for x in complete if x["complete"]]
            counts[str(h)][label]=dict(eligible_touch_events=len(cohort),
                                       completed_horizons=len(complete),
                                       mean_mfe_pct=(round(sum(x["observed_max_favorable_excursion_pct"] for x in complete)/len(complete),3) if complete else None),
                                       mean_mae_pct=(round(sum(x["observed_max_adverse_excursion_pct"] for x in complete)/len(complete),3) if complete else None),
                                       target_first=sum(x["stop_target_touch_order"]=="TARGET_FIRST" for x in complete),
                                       stop_first=sum(x["stop_target_touch_order"]=="STOP_FIRST" for x in complete),
                                       ambiguous_order=sum(x["stop_target_touch_order"]=="SAME_DAY_ORDER_UNKNOWN" for x in complete))
    return dict(schema="C3_ICT_MATCHED_COHORT_V1",rows=enriched,horizon_counts=counts,
                history_coverage_certified=False,
                regular_session_price_certified=False,
                observation_unit="FIRST_TOUCH_PER_PLAN",
                independent_plan_count=len({e["plan_id"] for e in enriched}),
                ict_filter_retention=retention,
                strategy_profitability_verified=False,trade_approved=False,orders_enabled=False)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True)
    p.add_argument("--prices",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    with open(a.plans,encoding="utf-8-sig",newline="") as f:
        plans=list(csv.DictReader(f))
    result=compare(plans,read_rows(a.prices))
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"plans":result["independent_plan_count"],"counts":result["horizon_counts"]},ensure_ascii=False))

if __name__=="__main__":
    main()
