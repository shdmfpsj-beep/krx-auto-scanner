"""Compare existing C3 touch observations with earlier ICT signals, research only.

ICT signals must be strictly earlier than the C3 watch-touch date.
No same-day sequencing assumptions, no filled orders, no profitability claims.
"""
from c3_ict_sequence_research_v1 import detect
from c3_watch_touch_forward_outcomes_v1 import build

def compare(plans, prices, ict_lookback=10, signal_max_age=10):
    if signal_max_age<1:
        raise ValueError("INVALID_SIGNAL_MAX_AGE")
    baseline=build(plans,prices,require_top2=False)
    enriched=[]
    for result in baseline["results"]:
        ticker=result["ticker"]
        series=sorted((day,bar) for (code,day),bar in prices.items() if code==ticker)
        bars=[dict(bar,date=day) for day,bar in series]
        signals=detect(bars,lookback=ict_lookback)
        # Use only signals completed strictly before touch date.
        signal_days={s["date"] for s in signals if s["event"]=="FVG_RETEST_WATCH"}
        day_index={day:i for i,(day,_) in enumerate(series)}
        for event in result["events"]:
            i=day_index[event["date"]]
            preceding=[d for d in signal_days if d in day_index
                       and 0<i-day_index[d]<=signal_max_age]
            prior_signal=max(preceding) if preceding else None
            enriched.append(dict(ticker=ticker,plan_id=result["plan_id"],
                                 touch_date=event["date"],
                                 prior_ict_retest_date=prior_signal,
                                 ict_prior_signal=prior_signal is not None,
                                 status=event["status"],
                                 touch_day_execution_ambiguous=event["touch_day_execution_ambiguous"],
                                 outcomes=event["outcomes"],
                                 verified_fill=False))
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
                                       target_first=sum(x["stop_target_touch_order"]=="TARGET_FIRST" for x in complete),
                                       stop_first=sum(x["stop_target_touch_order"]=="STOP_FIRST" for x in complete),
                                       ambiguous_order=sum(x["stop_target_touch_order"]=="SAME_DAY_ORDER_UNKNOWN" for x in complete))
    return dict(schema="C3_ICT_MATCHED_COHORT_V1",rows=enriched,horizon_counts=counts,
                strategy_profitability_verified=False,trade_approved=False,orders_enabled=False)
