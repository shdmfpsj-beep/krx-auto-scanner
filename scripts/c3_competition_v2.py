"""Frozen research competition on dated official prices, with explicit data gates.

No production import, orders, alerts, model promotion or future action adjustment.
The curated non-biotech cohort is retrospective: its selection bias remains.
"""
import argparse
import csv
import gzip
import hashlib
import json
import math
import random
import statistics
from collections import Counter,defaultdict
from pathlib import Path

from c3_entry_geometry_v23 import geometry
from c3_entry_benchmark_v1 import first_retest,net_return
from c3_ict_sequence_research_v1 import detect

TRAIN_END="2026-03-31"
HOLDOUT_START="2026-05-01"
HORIZONS=(5,10,20)
STRATEGIES=("C3_BASELINE","FIRST_RETEST","MA5_PULLBACK","MA10_PULLBACK","MA20_PULLBACK",
            "VOLUME_REEXPANSION","VCP_PREBREAKOUT","RS_FIRST_PULLBACK","ICT_RETEST",
            "C3_RISK_RR_GATE","FRESH_SUPPORT_LIMIT","COMPOSITE_HYPOTHESIS")
POLICIES=("STRUCTURE_CLOSE","STRUCTURE_INTRADAY","ATR_BUFFER_CLOSE","BREAKOUT_CLOSE",
          "TIME5","R1_RAISE_CLOSE","MONOTONE_TRAIL_CLOSE","INTRADAY_TAKE10")


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def avg(xs):return round(statistics.mean(xs),6) if xs else None
def rate(xs):return round(100*sum(xs)/len(xs),4) if xs else None


def load_official(panel_path,audit_path,members_path,exploratory_path):
    audit=json.loads(Path(audit_path).read_text())
    if sha(panel_path)!=audit["panel_sha256"]:
        raise ValueError("OFFICIAL_PANEL_HASH_MISMATCH")
    with Path(members_path).open(encoding="utf-8-sig") as f:members=list(csv.DictReader(f))
    excluded={r["ticker"] for r in members if any(x in r["investment_sector"] for x in ("바이오","제약","헬스케어"))}
    eligible={r["ticker"] for r in members}-excluded
    old=set(json.loads(Path(exploratory_path).read_text())["tickers"])
    panel=defaultdict(list);all_dates=set();all_tickers=set();count=0;seen=set()
    # Full source provenance and dated membership are retained by the collector.
    # Only the explicitly classified non-biotech subset is used for signals.
    with gzip.open(panel_path,"rt",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            count+=1;all_dates.add(r["date"]);all_tickers.add(r["ticker"])
            if r["ticker"] not in eligible:continue
            key=(r["ticker"],r["date"])
            if key in seen:raise ValueError("DUPLICATE_OFFICIAL_BAR")
            seen.add(key)
            b={k:float(r[k]) if r[k] not in ("","None") else None for k in
               ("open","high","low","close","volume","change_pct")}
            b.update(date=r["date"],name=r["name"],tradable=r["tradable"]=="True",
                     ohlc_valid=r["ohlc_valid"]=="True",halt_like=r["halt_like"]=="True")
            b["invalid_data"]=not b["ohlc_valid"] and not b["halt_like"]
            panel[r["ticker"]].append(b)
    if count!=audit["rows"]:raise ValueError("OFFICIAL_PANEL_ROW_COUNT_MISMATCH")
    sessions=sorted(all_dates)
    if not sessions:raise ValueError("EMPTY_OFFICIAL_PANEL")
    missing=audit["missing_market_dates"]
    if any(r["date"]<=sessions[-1] for r in missing):
        raise ValueError("INTERIOR_OFFICIAL_MARKET_GAP")
    # A source that has not published a trailing date is not silently a holiday.
    # This study explicitly ends at the last complete, published market date.
    events={(e["ticker"],e["date"]) for e in audit["reference_rebase_candidates"]}
    grid={d:i for i,d in enumerate(sessions)}
    for ticker,bars in panel.items():
        bars.sort(key=lambda b:b["date"]);segment=0;previous=None
        for b in bars:
            gap=previous is not None and grid[b["date"]]!=grid[previous["date"]]+1
            boundary=(ticker,b["date"]) in events
            if gap or boundary or not b["tradable"]:segment+=1
            b.update(segment=segment,action_boundary=boundary,internal_gap=gap)
            if not b["tradable"]:segment+=1
            previous=b
    return dict(panel),sessions,dict(
        panel_sha256=sha(panel_path),audit_sha256=sha(audit_path),
        members_sha256=sha(members_path),raw_source_rows=count,raw_source_tickers=len(all_tickers),
        effective_start=sessions[0],effective_end=sessions[-1],published_sessions=len(sessions),
        unpublished_requested_tail=missing,cohort_tickers=len(panel),cohort_bars=sum(map(len,panel.values())),
        excluded_prior_exploratory_tickers=sorted(old),
        confirmation_tickers=sorted(set(panel)-old),
        selection_scope="RETROSPECTIVE_CURATED_NON_BIOTECH_NOT_FULL_MARKET_STRATEGY_VALIDATION",
        point_in_time_sector_membership_verified=False,survivorship_bias_removed=False,
        regular_only_certified=False,official_calendar_verified=False,
        no_future_action_adjustment=True,source_basis="OFFICIAL_DATED_RAW_PRICE_UNITS")


def market_proxy(panel,sessions):
    level=100.;out={}
    for d in sessions:
        changes=[b["change_pct"] for bars in panel.values() for b in bars
                 if b["date"]==d and b["tradable"] and b["change_pct"] is not None]
        if not changes:raise ValueError("MISSING_COHORT_PROXY_RETURN")
        level*=1+statistics.mean(changes)/100
        out[d]=level
    return out


def signal_features(past,ict,proxy,sessions):
    g=geometry(past)
    if g.get("status")!="RESEARCH_GEOMETRY_ONLY" or g["trend_state"]!="UPTREND":return None
    close=past[-1]["close"];atr=g["atr14"]
    if atr<=0:return None
    ma={n:statistics.mean(b["close"] for b in past[-n:]) for n in (5,10,20)}
    recent=[]
    for i in range(max(2,len(past)-22),len(past)-3):
        if (past[i]["low"]<close and
            past[i]["low"]<=min(past[k]["low"] for k in range(i-2,i+3))):recent.append(i)
    fresh=past[recent[-1]]["low"] if recent else None
    v20=statistics.mean(b["volume"] for b in past[-21:-1])
    volume=v20>0 and past[-2]["volume"]<.8*v20 and past[-1]["volume"]>1.5*past[-2]["volume"] and close>past[-2]["close"]
    span=lambda xs:(max(b["high"] for b in xs)-min(b["low"] for b in xs))/statistics.mean(b["close"] for b in xs)
    contraction=span(past[-6:-1])<span(past[-11:-6])<span(past[-21:-11])
    high=max(b["high"] for b in past[-21:-1])
    vcp=contraction and close>=high-.5*atr and past[-1]["volume"]<v20
    retest=first_retest(past)
    day=past[-1]["date"];index=sessions.index(day)
    levels=[proxy[d] for d in sessions[:index+1]]
    regime="UP" if levels[-1]>statistics.mean(levels[-20:])>statistics.mean(levels[-60:]) else (
        "DOWN" if levels[-1]<statistics.mean(levels[-20:])<statistics.mean(levels[-60:]) else "SIDEWAYS")
    rs=100*((close/past[-21]["close"])/(proxy[day]/proxy[past[-21]["date"]])-1)
    touches=[b["low"]<=ma[20]<=b["close"] for b in past[-1:]]
    first_pullback=touches[0] and not any(
        past[k]["low"]<=statistics.mean(b["close"] for b in past[k-19:k+1])<=past[k]["close"]
        for k in range(len(past)-6,len(past)-1))
    return dict(geometry=g,ma=ma,fresh_support=fresh,volume=volume,vcp=vcp,retest=retest,
                rs=rs,rs_first=rs>0 and first_pullback,regime=regime,ict=ict.get(day))


def entry_cap(stop,resistance,slip=.001):
    """Costed first-resistance reward >= structural loss; not a fixed 3% band."""
    if resistance is None:return None
    return (resistance+stop)*(1-.005)*(1-slip)/(2*(1+.0015)*(1+slip))


def make_plan(ticker,past,f,strategy):
    g=f["geometry"];atr=g["atr14"];close=past[-1]["close"]
    stop=g["structural_stop"];support=g["support"]
    low,high=g["entry_low"],g["entry_high"];kind="LIMIT_WATCH"
    allowed=True
    if strategy in ("FIRST_RETEST","MA5_PULLBACK","MA10_PULLBACK","MA20_PULLBACK",
                    "VOLUME_REEXPANSION","VCP_PREBREAKOUT","RS_FIRST_PULLBACK","COMPOSITE_HYPOTHESIS"):
        kind="CONFIRMED_NEXT_OPEN"
        # New structural stop is frozen before the entry budget is determined.
        support=f["fresh_support"]
        if support is None:return None,"NO_FRESH_CONFIRMED_SUPPORT"
        if strategy=="FIRST_RETEST":
            allowed=f["retest"] is not None
            if allowed:support=f["retest"]
        stop=support-.5*atr
        low,high=stop+.1*atr,close+.5*atr
    if strategy.startswith("MA"):
        n=int(strategy[2:strategy.index("_")]);anchor=f["ma"][n]
        allowed=past[-1]["low"]<=anchor<=close and close>=past[-1]["open"]
    elif strategy=="VOLUME_REEXPANSION":allowed=f["volume"]
    elif strategy=="VCP_PREBREAKOUT":allowed=f["vcp"]
    elif strategy=="RS_FIRST_PULLBACK":allowed=f["rs_first"]
    elif strategy=="ICT_RETEST":
        allowed=f["ict"] is not None
        if allowed:
            s=f["ict"];stop=s["sweep_invalidation_low"]-.25*atr
            low,high=s["fvg_lower"],s["fvg_upper"]
    elif strategy=="FRESH_SUPPORT_LIMIT":
        support=f["fresh_support"]
        if support is None:return None,"NO_FRESH_CONFIRMED_SUPPORT"
        stop=support-.5*atr;low=support+.25*atr;high=support+atr
    elif strategy=="COMPOSITE_HYPOTHESIS":
        allowed=f["volume"] or (past[-1]["low"]<=f["ma"][20]<=close)
    if not allowed:return None,"SIGNAL_ABSENT"
    resistance=g["first_resistance"]
    if strategy in ("C3_RISK_RR_GATE","COMPOSITE_HYPOTHESIS"):
        cap=entry_cap(stop,resistance)
        if cap is None:return None,"FIRST_RESISTANCE_UNKNOWN"
        high=min(high,cap)
        # Eight percent is a predeclared exploratory risk budget, not validation.
        if high<=0 or (high-stop)/high>.08:return None,"RISK_BUDGET_EXCEEDED"
    if strategy=="C3_BASELINE" and resistance is not None and high>=resistance:
        return None,"BASELINE_RESISTANCE_GUARD"
    if kind=="CONFIRMED_NEXT_OPEN" and high<close-.5*atr:return None,"COSTED_REWARD_BUDGET_TOO_LOW"
    if not 0<stop<low<=high:return None,"NO_USABLE_ENTRY_BAND"
    return dict(ticker=ticker,decision_date=past[-1]["date"],stop=stop,low=low,high=high,
                resistance=resistance,atr=atr,kind=kind,strategy=strategy,
                breakout_support=f["retest"],regime=f["regime"],segment=past[-1]["segment"],
                planned_risk_pct=100*(high-stop)/high),None


def locate_entry(plan,rows,sessions):
    by={b["date"]:b for b in rows}
    days=[d for d in sessions if d>plan["decision_date"]][:5]
    for d in days:
        b=by.get(d)
        if b is None:return dict(status="DATA_GAP_OR_DISAPPEARANCE",date=d)
        if b.get("invalid_data"):return dict(status="INVALID_OFFICIAL_OHLC",date=d)
        if b["action_boundary"]:return dict(status="ACTION_REFERENCE_CHANGED",date=d)
        if not b["tradable"]:continue
        if b["segment"]!=plan["segment"]:return dict(status="SIGNAL_HISTORY_RESET",date=d)
        if b["open"]<=plan["stop"]:return dict(status="OPEN_BELOW_STRUCTURAL_STOP",date=d)
        if plan["kind"]=="CONFIRMED_NEXT_OPEN":
            if not plan["low"]<=b["open"]<=plan["high"]:return dict(status="NEXT_OPEN_OUTSIDE_FROZEN_BUDGET",date=d)
            return dict(status="MODEL_ENTRY",date=d,price=b["open"],at_open=True,order_unknown=False)
        if b["open"]<plan["low"]:return dict(status="GAP_BELOW_BAND",date=d)
        if b["low"]<=plan["high"] and b["high"]>=plan["low"]:
            return dict(status="MODEL_ENTRY",date=d,price=min(b["open"],plan["high"]),
                        at_open=b["open"]<=plan["high"],order_unknown=b["low"]<=plan["stop"])
        if b["close"]<plan["stop"]:return dict(status="INVALIDATED_BEFORE_ENTRY",date=d)
        if plan["resistance"] is not None and b["high"]>=plan["resistance"]:
            return dict(status="MISSED_RESISTANCE_WITHOUT_ENTRY",date=d)
    return dict(status="EXPIRED_NO_TOUCH" if len(days)==5 else "INCOMPLETE_WATCH_WINDOW")


def execute(plan,entry,rows,sessions,horizon,policy="STRUCTURE_CLOSE",slip=.001,optimistic=False):
    if policy not in POLICIES or not 0<=slip<.1:raise ValueError("INVALID_EXECUTION_PARAMETERS")
    by={b["date"]:b for b in rows};e=sessions.index(entry["date"])
    if e+horizon+1>=len(sessions):return dict(complete=False,reason="INCOMPLETE_HORIZON")
    scheduled=e+min(horizon,5) if policy=="TIME5" else e+horizon
    stop=plan["stop"]-(.5*plan["atr"] if policy=="ATR_BUFFER_CLOSE" else 0)
    if policy=="BREAKOUT_CLOSE":
        if plan["breakout_support"] is None:return dict(complete=False,reason="NO_BREAKOUT_SUPPORT")
        stop=plan["breakout_support"]-.5*plan["atr"]
        if stop>=entry["price"]:return dict(complete=False,reason="BREAKOUT_STOP_ABOVE_ENTRY")
    pending=None;ambiguous=False;trace=[];target=round(entry["price"]*1.1,8)
    def result(day,price,reason):
        return dict(complete=True,net_pct=net_return(entry["price"]*(1+slip),price*(1-slip)),
                    exit_date=day,exit_price=price,reason=reason,order_unknown=ambiguous,
                    stop_trace=trace,actual_fill_verified=False)
    for index in range(e,len(sessions)):
        d=sessions[index];b=by.get(d)
        if b is None:return dict(complete=False,reason="SECURITY_GAP_OR_DISAPPEARANCE",date=d)
        if b.get("invalid_data"):return dict(complete=False,reason="INVALID_OFFICIAL_OHLC",date=d)
        if b["action_boundary"]:return dict(complete=False,reason="UNRESOLVED_CORPORATE_ACTION",date=d)
        if not b["ohlc_valid"] and b["tradable"]:return dict(complete=False,reason="INVALID_TRADED_OHLC",date=d)
        if not b["tradable"]:
            if index>=scheduled:pending=pending or "TIME_EXIT_NEXT_TRADABLE_OPEN"
            continue
        if pending:return result(d,b["open"],pending)
        if index>scheduled:return result(d,b["open"],"TIME_EXIT_NEXT_OPEN")
        trace.append([d,stop])
        intraday=policy in ("STRUCTURE_INTRADAY","INTRADAY_TAKE10")
        take=policy=="INTRADAY_TAKE10"
        # An opening fill or pre-existing position has known opening precedence.
        opening_known=index>e or entry["at_open"]
        if intraday and opening_known and b["open"]<=stop:return result(d,b["open"],"GAP_STOP")
        if take and opening_known and b["open"]>=target:return result(d,target,"TAKE10")
        both=intraday and take and b["low"]<=stop and b["high"]>=target
        if both:
            ambiguous=True
            return result(d,target if optimistic else stop,"SAME_BAR_TARGET_SCENARIO" if optimistic else "SAME_BAR_STOP_SCENARIO")
        if intraday and b["low"]<=stop:return result(d,stop,"INTRADAY_STOP")
        # On a limit-touch day its earlier high may precede the fill.
        if take and b["high"]>=target and (index>e or entry["at_open"]):return result(d,target,"TAKE10")
        if not intraday and b["close"]<stop:pending="CLOSE_STOP_NEXT_TRADABLE_OPEN"
        if index>=scheduled:pending=pending or "TIME_EXIT_NEXT_OPEN"
        # Closing information only changes the NEXT session's frozen stop.
        if policy=="R1_RAISE_CLOSE" and plan["resistance"] and b["close"]>plan["resistance"]:
            stop=max(stop,entry["price"])
        if policy=="MONOTONE_TRAIL_CLOSE":
            history=[x["close"] for x in rows if x["date"]<=d and x["tradable"] and x["segment"]==b["segment"]][-20:]
            if len(history)==20:stop=max(stop,statistics.mean(history)-1.5*plan["atr"])
    return dict(complete=False,reason="NO_NEXT_TRADABLE_EXECUTION_WITHIN_DATA")


def observe(plan,entry,rows,sessions,horizon):
    by={b["date"]:b for b in rows};e=sessions.index(entry["date"])
    days=sessions[e+1:e+horizon+1]
    if len(days)!=horizon:return dict(complete=False,reason="INCOMPLETE_WINDOW")
    if any(d not in by for d in days):return dict(complete=False,reason="SECURITY_GAP_OR_DISAPPEARANCE")
    bars=[by[d] for d in days]
    if any(b["action_boundary"] for b in bars):return dict(complete=False,reason="UNRESOLVED_CORPORATE_ACTION")
    if any(not b["tradable"] for b in bars):return dict(complete=False,reason="HALT_OR_INVALID_BAR")
    price=entry["price"];stop=plan["stop"]
    stop_index=next((i for i,b in enumerate(bars) if b["low"]<=stop),None)
    resistance=plan["resistance"]
    break_index=next((i for i,b in enumerate(bars) if resistance and b["close"]>resistance),None)
    result=dict(complete=True,mfe_pct=max(0,100*(max(b["high"] for b in bars)/price-1)),
                mae_pct=min(0,100*(min(b["low"] for b in bars)/price-1)),
                up_close=bars[-1]["close"]>price,stop_touch=stop_index is not None,
                resistance_break=(break_index is not None) if resistance else None,
                continuation5=(bars[break_index+5]["close"]>bars[break_index]["close"] if break_index is not None and break_index+5<len(bars) else None),
                stop_rebound2=(any(b["close"]>=price for b in bars[stop_index+1:stop_index+3]) if stop_index is not None and stop_index+2<len(bars) else None),
                entry_day_extremes_excluded=True,post_stop_excursions_included=True)
    for pct in (5,10,15,20):
        target=round(price*(1+pct/100),8)
        hit=next((i for i,b in enumerate(bars) if b["high"]>=target),None)
        same=hit is not None and hit==stop_index
        opening=bars[hit]["open"] if hit is not None else None
        unknown=same and stop<opening<target
        before=hit is not None and (stop_index is None or hit<stop_index or (same and opening>=target))
        result.update({f"target{pct}":hit is not None,f"target{pct}_before_stop":before,
                       f"target{pct}_order_unknown":unknown})
    return result


def cluster_ci(pairs,seed=271560,reps=500):
    blocks=defaultdict(list)
    for month,value in pairs:blocks[month].append(value)
    # Few months and correlated stocks do not justify narrow independent CIs.
    if len(blocks)<4 or len(pairs)<20:return None
    totals=[(sum(v),len(v)) for v in blocks.values()];rng=random.Random(seed);means=[]
    for _ in range(reps):
        drawn=[rng.choice(totals) for _ in totals]
        means.append(sum(t for t,n in drawn)/sum(n for t,n in drawn))
    means.sort();return [round(means[int(.025*reps)],5),round(means[min(reps-1,int(.975*reps))],5)]


def summarize(records,fold,horizon,cohort,policy="STRUCTURE_CLOSE"):
    selected=[r for r in records if r["fold"]==fold and (cohort=="ALL_EXPLORATORY" or r["new_ticker_confirmation"])]
    filled=[r for r in selected if r["entry"]["status"]=="MODEL_ENTRY"]
    models=[(r,r["exits"][str(horizon)][policy]) for r in filled]
    complete=[(r,m) for r,m in models if m["complete"]]
    values=[m["net_pct"] for r,m in complete]
    obs=[r["observations"][str(horizon)] for r in filled if r["observations"][str(horizon)]["complete"]]
    result=dict(signals_after_cooldown=len(selected),entries=len(filled),completed=len(values),
        censored=len(models)-len(complete),entry_statuses=dict(Counter(r["entry"]["status"] for r in selected)),
        censor_reasons=dict(Counter(m["reason"] for r,m in models if not m["complete"])),
        mean_net_pct=avg(values),median_net_pct=round(statistics.median(values),6) if values else None,
        positive_rate_pct=rate([v>0 for v in values]),
        stop_exit_rate_pct=rate(["STOP" in m["reason"] for r,m in complete]),
        entry_day_order_unknown_count=sum(r["entry"]["order_unknown"] for r,m in complete),
        mean_excluding_uncertain_entry_days=avg([m["net_pct"] for r,m in complete if not r["entry"]["order_unknown"]]),
        mean_ci95_month_cluster_descriptive=cluster_ci([(r["decision_date"][:7],m["net_pct"]) for r,m in complete]),
        mean_mfe_pct=avg([o["mfe_pct"] for o in obs]),mean_mae_pct=avg([o["mae_pct"] for o in obs]),
        completed_observation_windows=len(obs),
        market_regime={reg:dict(n=sum(r["regime"]==reg for r,m in complete),mean_net_pct=avg([m["net_pct"] for r,m in complete if r["regime"]==reg])) for reg in ("UP","DOWN","SIDEWAYS")},
        portfolio_max_drawdown_pct=None,portfolio_simulated=False,
        outcome_inference="PROVISIONAL_SOURCE_SCOPE_AND_SELECTION_BIAS_BLOCK_PROMOTION")
    for key in ("target5","target10","target15","target20","stop_touch","resistance_break","continuation5","stop_rebound2"):
        known=[o[key] for o in obs if o[key] is not None]
        result[key+"_rate_pct"]=rate(known);result[key+"_n"]=len(known)
    for pct in (5,10,15,20):
        for suffix in ("before_stop","order_unknown"):
            key=f"target{pct}_{suffix}"
            result[key+"_rate_pct"]=rate([o[key] for o in obs])
    return result


def review_models(records):
    """Descriptive paired and calendar checks; never select on the best holdout."""
    def chosen(strategy):
        return [r for r in records[strategy] if r["fold"]=="HOLDOUT" and r["new_ticker_confirmation"]
                and r["entry"]["status"]=="MODEL_ENTRY"]
    baseline={(r["ticker"],r["decision_date"]):r for r in chosen("C3_BASELINE")
              if r["exits"]["20"]["STRUCTURE_CLOSE"]["complete"]}
    paired={};robustness={}
    for strategy in STRATEGIES:
        selected=chosen(strategy);pairs=[]
        for r in selected:
            b=baseline.get((r["ticker"],r["decision_date"]))
            m=r["exits"]["20"]["STRUCTURE_CLOSE"]
            if b and m["complete"]:
                pairs.append((r["decision_date"][:7],m["net_pct"]-b["exits"]["20"]["STRUCTURE_CLOSE"]["net_pct"]))
        paired[strategy]=dict(matched_decision_pairs=len(pairs),mean_delta_pct_points=avg([v for d,v in pairs]),
            delta_ci95_month_cluster_descriptive=cluster_ci(pairs),
            unmatched_opportunities_not_in_paired_estimate=True,causal_effect_established=False)
        policy_review={}
        for policy in POLICIES:
            complete=[(r,r["exits"]["20"][policy]) for r in selected if r["exits"]["20"][policy]["complete"]]
            monthly=defaultdict(list)
            for r,m in complete:monthly[r["decision_date"][:7]].append(m["net_pct"])
            policy_review[policy]=dict(
                monthly={d:dict(n=len(v),mean_net_pct=avg(v)) for d,v in sorted(monthly.items())},
                early_holdout=dict(n=sum(r["decision_date"]<"2026-08-01" for r,m in complete),
                    mean_net_pct=avg([m["net_pct"] for r,m in complete if r["decision_date"]<"2026-08-01"])),
                late_holdout=dict(n=sum(r["decision_date"]>="2026-08-01" for r,m in complete),
                    mean_net_pct=avg([m["net_pct"] for r,m in complete if r["decision_date"]>="2026-08-01"])))
        slippage={}
        for bps in ("0","10","25"):
            values=[r["slippage_sensitivity20"][bps]["net_pct"] for r in selected if r["slippage_sensitivity20"][bps]["complete"]]
            slippage[bps]=dict(n=len(values),mean_net_pct=avg(values))
        bounds=[]
        for r in selected:
            lo=r["exits"]["20"]["INTRADAY_TAKE10"];hi=r["ambiguity_optimistic20"]
            if lo["complete"] and hi["complete"]:bounds.append((lo,hi))
        robustness[strategy]=dict(policies=policy_review,slippage_each_side_bps=slippage,
            same_bar_bounds=dict(n=len(bounds),ambiguous=sum(lo["order_unknown"] for lo,hi in bounds),
                conservative_mean_net_pct=avg([lo["net_pct"] for lo,hi in bounds]),
                optimistic_mean_net_pct=avg([hi["net_pct"] for lo,hi in bounds]),
                optimistic_scenario_is_not_verified_execution=True))
    return dict(paired_strategy_comparisons=paired,robustness=robustness,
                inference="DESCRIPTIVE_MULTIPLE_HYPOTHESES_NOT_ADOPTION_EVIDENCE")


def run_competition(panel,sessions,audit):
    proxy=market_proxy(panel,sessions);records={s:[] for s in STRATEGIES}
    counts={s:Counter() for s in STRATEGIES};old=set(audit["excluded_prior_exploratory_tickers"])
    ict_frequency=Counter()
    for ticker,rows in sorted(panel.items()):
        segments=defaultdict(list)
        for b in rows:
            if b["tradable"] and b["ohlc_valid"]:segments[b["segment"]].append(b)
        next_index={s:0 for s in STRATEGIES}
        for segment,bars in segments.items():
            ict={s["date"]:s for s in detect(bars) if s["event"]=="FVG_RETEST_WATCH"}
            for day in ict:
                ict_frequency["ALL_REGIMES_ALL_DATES"]+=1
                if day>=HOLDOUT_START:
                    ict_frequency["HOLDOUT_ALL_REGIMES"]+=1
                    if ticker not in old:ict_frequency["HOLDOUT_NEW_TICKERS_ALL_REGIMES"]+=1
            for i in range(65,len(bars)):
                day=bars[i]["date"];global_i=sessions.index(day)
                if day<=TRAIN_END:
                    if global_i+26>=len(sessions) or sessions[global_i+26]>TRAIN_END:continue
                    fold="DEVELOPMENT"
                elif day>=HOLDOUT_START:fold="HOLDOUT"
                else:continue
                past=bars[:i+1];f=signal_features(past,ict,proxy,sessions)
                for strategy in STRATEGIES:
                    counts[strategy]["eligible_decision_days"]+=1
                    if f is None:
                        counts[strategy]["NO_UPTREND_GEOMETRY"]+=1;continue
                    p,rejection=make_plan(ticker,past,f,strategy)
                    if p is None:
                        counts[strategy][rejection]+=1;continue
                    counts[strategy]["raw_signals"]+=1
                    if global_i<next_index[strategy]:
                        counts[strategy]["cooldown_suppressed"]+=1;continue
                    # A fixed 26-session reservation applies even to no-fill plans.
                    next_index[strategy]=global_i+26
                    entry=locate_entry(p,rows,sessions)
                    r=dict(plan_id=f"{strategy}:{ticker}:{day}",ticker=ticker,decision_date=day,
                           fold=fold,new_ticker_confirmation=ticker not in old,regime=f["regime"],
                           plan=p,entry=entry,observations={},exits={})
                    if entry["status"]=="MODEL_ENTRY":
                        for h in HORIZONS:
                            r["observations"][str(h)]=observe(p,entry,rows,sessions,h)
                            r["exits"][str(h)]={policy:execute(p,entry,rows,sessions,h,policy) for policy in POLICIES}
                        r["slippage_sensitivity20"]={str(bps):execute(p,entry,rows,sessions,20,slip=bps/10000) for bps in (0,10,25)}
                        r["ambiguity_optimistic20"]=execute(p,entry,rows,sessions,20,"INTRADAY_TAKE10",optimistic=True)
                    records[strategy].append(r)
        print(json.dumps(dict(ticker=ticker,processed_rows=len(rows))),flush=True)
    summaries={s:{cohort:{fold:{str(h):summarize(records[s],fold,h,cohort) for h in HORIZONS}
                         for fold in ("DEVELOPMENT","HOLDOUT")} for cohort in ("ALL_EXPLORATORY","NEW_TICKER_CONFIRMATION")} for s in STRATEGIES}
    policies={s:{p:summarize(records[s],"HOLDOUT",20,"NEW_TICKER_CONFIRMATION",p) for p in POLICIES} for s in STRATEGIES}
    return dict(schema="C3_OFFICIAL_ENTRY_COMPETITION_V2",audit=audit,
                protocol=dict(train_end=TRAIN_END,holdout_start=HOLDOUT_START,embargo="2026-04",
                    cooldown_sessions=26,watch_sessions=5,buy_cost=.0015,sell_cost=.005,slippage_each_side=.001,
                    exit_clock="HORIZON_CLOSE_DECISION_NEXT_TRADABLE_OPEN",signal_close_is_not_a_fill=True,
                    stop_updates_effective_next_session=True,
                    market_proxy="CONTEMPORANEOUS_EQUAL_WEIGHT_CURATED_COHORT_OFFICIAL_DAILY_PRICE_RETURN",
                    historical_top2_ranking_reconstructed=False,multiple_comparisons_controlled=False,
                    confirmation_excludes_16_rule_design_tickers=True),
                opportunities={s:dict(c) for s,c in counts.items()},summaries=summaries,exit_policy_comparison=policies,
                independent_ict_frequency=dict(ict_frequency),
                model_review=review_models(records),
                records=records,strategy_adopted=None,promotion_blocked=True,decision="CASH",
                blockers=["REGULAR_SESSION_SCOPE_UNCERTIFIED","HISTORICAL_SECTOR_SELECTION_BIAS",
                          "CORPORATE_ACTION_LABELS_UNRESOLVED_AND_CENSORED","FEW_HOLDOUT_MONTH_CLUSTERS",
                          "MODEL_FILLS_NOT_VERIFIED","MULTIPLE_HYPOTHESES_REQUIRE_FRESH_CONFIRMATION"],
                orders_enabled=False)


def write_results(result,outdir):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    with gzip.open(root/"competition_ledger.json.gz","wt",encoding="utf-8") as f:
        json.dump(result["records"],f,ensure_ascii=False,separators=(",",":"))
    compact={k:v for k,v in result.items() if k!="records"}
    (root/"competition_report.json").write_text(json.dumps(compact,ensure_ascii=False,indent=2)+"\n")
    keys=("completed","entries","censored","censor_reasons","mean_net_pct","stop_exit_rate_pct",
          "mean_ci95_month_cluster_descriptive","mean_mfe_pct","mean_mae_pct","market_regime",
          "target5_rate_pct","target10_rate_pct","target15_rate_pct","target20_rate_pct",
          "entry_day_order_unknown_count","mean_excluding_uncertain_entry_days")
    summary=dict(schema="C3_COMPETITION_COMPACT_V2",audit=result["audit"],protocol=result["protocol"],
        new_ticker_holdout={s:{h:{k:result["summaries"][s]["NEW_TICKER_CONFIRMATION"]["HOLDOUT"][h][k] for k in keys}
                                for h in ("5","10","20")} for s in STRATEGIES},
        development20={s:result["summaries"][s]["NEW_TICKER_CONFIRMATION"]["DEVELOPMENT"]["20"]["mean_net_pct"] for s in STRATEGIES},
        paired_strategy_comparisons=result["model_review"]["paired_strategy_comparisons"],
        exit20={s:{p:{k:result["exit_policy_comparison"][s][p][k] for k in ("completed","mean_net_pct","stop_exit_rate_pct","mean_ci95_month_cluster_descriptive")}
                   for p in POLICIES} for s in STRATEGIES},
        independent_ict_frequency=result["independent_ict_frequency"],
        blockers=result["blockers"],strategy_adopted=None,decision="CASH",orders_enabled=False,
        code_sha256=sha(__file__))
    (root/"competition_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    rows=[]
    for strategy in STRATEGIES:
        stats=result["summaries"][strategy]["NEW_TICKER_CONFIRMATION"]["HOLDOUT"]
        rows.append(dict(strategy=strategy,n5=stats["5"]["completed"],mean5=stats["5"]["mean_net_pct"],
            n10=stats["10"]["completed"],mean10=stats["10"]["mean_net_pct"],n20=stats["20"]["completed"],
            mean20=stats["20"]["mean_net_pct"],stop_rate20=stats["20"]["stop_exit_rate_pct"],
            ci95_month_clusters=stats["20"]["mean_ci95_month_cluster_descriptive"],
            validation="PROVISIONAL_NOT_ADOPTED"))
    with (root/"strategy_comparison.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
    return rows


def main():
    p=argparse.ArgumentParser();p.add_argument("--panel",required=True);p.add_argument("--audit",required=True)
    p.add_argument("--members",default="reports/v68_investment_sector_members.csv")
    p.add_argument("--exploratory",default="reports/c3_work2_20261105/source_validation_cases.json")
    p.add_argument("--outdir",required=True);a=p.parse_args()
    panel,sessions,audit=load_official(a.panel,a.audit,a.members,a.exploratory)
    result=run_competition(panel,sessions,audit);rows=write_results(result,a.outdir)
    print(json.dumps(rows),flush=True)


if __name__=="__main__":main()
