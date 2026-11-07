"""C3 V8 protocol: stop retrospective tuning; verify prospective evidence.

NO selection, orders, Telegram, alerts, ledger mutations, or strategy
promotion. Read an EXISTING immutable source report. Review two independent
questions, 'was this an original TOP2 pick?' vs 'was its frozen entry feasible?'.
Never treat a green unit test as evidence of a profitable trading edge.
"""
from __future__ import annotations
from datetime import datetime, date
from math import isfinite
from collections import Counter
import hashlib
import json

SCHEMA="C3_V8_PROSPECTIVE_EVIDENCE_CONTRACT_1"
HORIZONS=(5,10,20)
# V7 prior-defined *descriptive* risk geometry. Not a newly optimized buy rule.
RR_REVIEW_LEVEL=1.0
STOP_REVIEW_LEVEL_PCT=12.0
BUY_FACTOR=(1+0.0015)*(1+0.001)
SELL_FACTOR=(1-0.005)*(1-0.001)

def stamp(v):
    if not isinstance(v,str):raise ValueError("MISSING_TIME_EVIDENCE")
    try: t=datetime.fromisoformat(v.replace("Z","+00:00"))
    except ValueError as e:raise ValueError("INVALID_TIME_EVIDENCE") from e
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("NAIVE_TIME_IS_NOT_PROOF")
    return t

def price(v):
    try:
        n=float(v)
        return n if isfinite(n) and n>0 else None
    except (TypeError,ValueError):
        return None

def _plan_diagnostics(plan,close,ticker,decision_date):
    if plan is None:
        return dict(status="NO_ORIGINAL_PLAN",mechanical_order_eligible=False)
    if not isinstance(plan,dict) or (
        plan.get("ticker")!=ticker or plan.get("decision_date")!=decision_date
    ):
        raise ValueError("PLAN_SIGNAL_IDENTITY_MISMATCH")
    high=price(plan.get("high"));low=price(plan.get("low"))
    stop=price(plan.get("stop"));r1=price(plan.get("resistance"))
    if None in (high,low,stop) or not (stop<low<=high):
        return dict(status="INVALID_PRIOR_PLAN",mechanical_order_eligible=False)
    d=round(100*(close/high-1),6)
    risk=round(100*(high-stop)/high,6)
    r1rr=None
    reward=None
    if r1 is not None:
        buy=high*BUY_FACTOR
        stop_proceeds=stop*SELL_FACTOR
        r1_proceeds=r1*SELL_FACTOR
        r1rr=round((r1_proceeds-buy)/(buy-stop_proceeds),6)
        reward=round(100*(r1_proceeds/buy-1),6)
    # Never call a good selected stock "safe" just because a support plan exists.
    reasons=[]
    if r1 is None:reasons.append("FIRST_RESISTANCE_MISSING")
    elif r1rr is None or r1rr<RR_REVIEW_LEVEL:reasons.append("FIRST_RESISTANCE_RR_BELOW_1")
    if risk>STOP_REVIEW_LEVEL_PCT:reasons.append("FROZEN_STOP_DISTANCE_OVER_12_PCT")
    if d>10:reasons.append("ORIGINAL_LIMIT_MORE_THAN_10_PCT_BELOW_PRIOR_CLOSE")
    if d<0:reasons.append("ORIGINAL_LIMIT_ABOVE_PRIOR_CLOSE")
    return dict(
        status="GEOMETRY_REVIEW_FLAGS" if reasons else "GEOMETRY_REVIEW_NO_FLAGS",
        review_flags=reasons,
        high=high,low=low,stop=stop,r1=r1,
        gap_from_close_to_limit_pct=d,raw_stop_distance_pct=risk,
        costed_R1_RR=r1rr,costed_R1_reward_pct=reward,
        mechanically_routable_after_provenance_checks_only=False,
        mechanical_order_eligible=False,
        first_resistance_profit_not_guaranteed=True)

def _picks(source):
    if not isinstance(source,dict):raise ValueError("SOURCE_MISSING")
    if not source.get("research_top2_registered_for_source_session",False):
        return None
    records=source.get("research_top2")
    if not isinstance(records,list) or len(records)!=2:
        raise ValueError("REGISTERED_TOP2_REQUIRES_TWO_ORIGINAL_ROWS")
    ranks=set(); ids=set();tickers=set()
    for row in records:
        if not isinstance(row,dict):raise ValueError("INVALID_REGISTERED_ROW")
        if row.get("model")!="B" or row.get("decision_date")!=source.get("source_price_asof"):
            raise ValueError("NOT_ORIGINAL_B_TOP2_FOR_SOURCE_DATE")
        if row.get("rank") not in (1,2):raise ValueError("INVALID_FROZEN_RANK")
        sid=row.get("signal_id")
        ticker=row.get("ticker")
        if not isinstance(sid,str) or not sid or not isinstance(ticker,str) or not ticker:
            raise ValueError("REGISTERED_IDENTIFIERS_MISSING")
        ranks.add(row["rank"]);ids.add(sid);tickers.add(ticker)
    if len(ranks)!=2 or len(ids)!=2 or len(tickers)!=2:
        raise ValueError("DUPLICATE_OR_MISSING_TOP2_IDENTITY")
    return sorted(records,key=lambda x:x["rank"])

def evidence_snapshot(source,*,check_at,next_session_open,source_commit):
    """Strictly historical as-of view; generated clock is not proof of delivery.

    The next session open must be supplied from a separate calendar, not guessed
    from weekdays. A stale report does not magically become a new selection.
    """
    at=stamp(check_at);next_open=stamp(next_session_open)
    generated=stamp(source.get("generated_at"))
    completed=stamp(source.get("analysis_completed_at"))
    received=stamp(source.get("source_received_at"))
    if received>generated or completed>generated:
        raise ValueError("SOURCE_REPORT_TIME_ORDER_INVALID")
    day=date.fromisoformat(source.get("source_price_asof"))
    if day>=next_open.date():raise ValueError("NEXT_SESSION_NOT_AFTER_SOURCE_SESSION")
    if not isinstance(source_commit,str) or len(source_commit)!=40:
        raise ValueError("SOURCE_COMMIT_NOT_PINNED")
    if any(c not in "0123456789abcdef" for c in source_commit.lower()):
        raise ValueError("INVALID_SOURCE_COMMIT")
    common=dict(
        schema=SCHEMA,source_price_asof=day.isoformat(),
        source_commit=source_commit,
        next_session_open=next_session_open,
        report_generated_at=source["generated_at"],
        source_received_at=source["source_received_at"],
        original_analysis_completed_at=source["analysis_completed_at"],
        no_user_order=True,no_new_signal=True,no_telegram=True,
        time_of_delivery_independently_verified=False,
        distinct_original_registered_signals_not_new_registered_counter=True,
        official_regular_only_certified=source.get("source_regular_only_certified") is True,
        current_action="CASH",
    )
    if at<completed or at<generated:
        return dict(**common,status="ARCHIVED_REPORT_NOT_AVAILABLE_AS_OF_CHECK",
                    selected_count=None, selected=None,
                    evaluation_windows={str(h):"NOT_ASSESSABLE_AT_CHECK_TIME" for h in HORIZONS})
    picks=_picks(source)
    if picks is None:
        return dict(**common,status="NO_FROZEN_REGISTERED_TOP2_EVIDENCE",
                    selected_count=None,selected=None,
                    evaluation_windows={str(h):"NOT_REGISTERED_OR_UNKNOWN" for h in HORIZONS})
    selected=[]
    for row in picks:
        if stamp(row.get("registered_at"))>generated:
            raise ValueError("REGISTERED_TIMESTAMP_AFTER_REPORT")
        close=price(row.get("reference_close"))
        if close is None:raise ValueError("MISSING_ORIGINAL_REFERENCE_CLOSE")
        plans=row.get("entry_plans")
        if not isinstance(plans,dict):raise ValueError("ORIGINAL_PLANS_MISSING")
        plan_report={}
        for key in ("A_SUPPORT_LIMIT","B_CONFIRMED_PULLBACK","C_LIMITED_BREAKOUT"):
            value=plans.get(key)
            if not isinstance(value,dict):raise ValueError("ORIGINAL_PLAN_SLOT_MISSING")
            plan_report[key]=_plan_diagnostics(
                value.get("plan"),close,row["ticker"],row["decision_date"])
        selected.append(dict(
            name=row.get("name"),ticker=row["ticker"],
            rank=row["rank"],source_signal_id=row["signal_id"],
            original_model="B", stock_selection_status="ORIGINAL_B_TOP2_UNCALIBRATED",
            close=close,source_regular_only_certified=row.get("source_regular_only_certified") is True,
            original_buy_approved=row.get("buy_approved") is True,
            entry_plan_diagnostics=plan_report,
            forward_20pct_in_20d="UNKNOWN_UNTIL_MATURED",
            buy_recommendation="NOT_AUTHORIZED",
        ))
    if at>=next_open:
        status="AFTER_NEXT_OPEN_NOT_PREOPEN_DECISION"
    elif not common["official_regular_only_certified"] or any(
        not x["source_regular_only_certified"] for x in selected):
        status="TOP2_REGISTERED_BUT_SOURCE_UNCERTIFIED"
    else:
        status="TOP2_RECORDED_EVIDENCE_ONLY_NO_BROKER_FILL_PROOF"
    return dict(**common,status=status,selected_count=2,selected=selected,
                evaluation_windows={str(h):"FUTURE_OUTCOME_UNMATURED_OR_NOT_READ" for h in HORIZONS},
                no_claim_of_prospective_profitable_signal=True)

def review_gate(snapshots, *, minimum_distinct=60, minimum_complete_20d=30):
    """Process gate, not statistical-power or trading-alpha validation.

    Only independent newly registered, temporally eligible, verified-source
    episodes count. Unmatured, censored, repeated, after-the-fact, and uncertain
    scope episodes never satisfy the review threshold.
    """
    unique={}
    excluded=Counter()
    for x in snapshots:
        key=(x.get("decision_date"),x.get("ticker"))
        if not all(key):excluded["IDENTITY_MISSING"]+=1;continue
        if x.get("registered_in_advance") is not True:
            excluded["NOT_PUBLISHED_IN_ADVANCE"]+=1;continue
        if x.get("regular_only_certified") is not True:
            excluded["UNCERTIFIED_SOURCE"]+=1;continue
        if x.get("time_evidence_verified") is not True:
            excluded["UNVERIFIED_ASOF_CLOCK"]+=1;continue
        if x.get("independent_episode") is not True:
            excluded["OVERLAPPING_EPISODE"]+=1;continue
        if key in unique:excluded["DUPLICATE_EPISODE"]+=1;continue
        unique[key]=x
    completed=sum(x.get("complete_20d_evidence") is True
                  and x.get("censored") is not True for x in unique.values())
    enough=(len(unique)>=minimum_distinct and completed>=minimum_complete_20d)
    return dict(unique_valid_independent_signals=len(unique),
                genuinely_matured_20d=completed,exclude_reasons=dict(excluded),
                process_review_ready=enough,
                proof_of_statistical_edge=False,
                strategy_promotable=False,
                label="REVIEW_ONLY_NOT_PROFITABILITY_PROOF" if enough else "CONTINUE_FORWARD_COLLECTION",
                no_parameter_tuning_on_preexisting_95_name_holdout=True)
