#!/usr/bin/env python3
"""v6.2 fixed resistance-reaction diagnostics on dated historical signals.

Only fully completed PRE-SIGNAL bars label resistance. Five strictly later
completed sessions evaluate subsequent barrier interactions independently of
order fills. This is a biased, source-uncertified historic observation, NOT an
out-of-sample validation, tradable support/resistance, or BUY recommendation.
The nearest wick remains a hard veto regardless of post-signal outcome.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from entry_strategy_v58 import METHODS,rows,safe_json
from entry_fill_frontier_v60 import pos,valid_bars_history
from resistance_tiers_v61 import tier_levels,MODES
from shadow_five_day_v59 import signal_rows_for_historic_selected_universe

SCHEMA="C3_K100_WICK_BARRIER_REACTION_V62"
HORIZON=5
LOOKBACK=60
REJECTION_HIGH_BELOW_ATR=0.20
REJECTION_HIGH_ABOVE_ATR=0.25
REJECTION_CLOSE_BELOW_ATR=0.10
REJECTION_UPPER_WICK_ATR=0.15
BREAKOUT_CLOSE_ABOVE_ATR=0.25
SEPARATE_TEST_BARS=3
LABELS=("NO_PRIOR_NEAR_BARRIER","TICK_ROUNDED_BARRIER_AT_ENTRY",
        "HISTORIC_CLOSE_THROUGH_BARRIER",
        "REPEATED_PRE_SIGNAL_REJECTION","ONE_PRE_SIGNAL_REJECTION",
        "NO_PRE_SIGNAL_REJECTION")
FIELDS=("ticker","name","method","variant","signal_asof",
        "entry_reference","stop_reference","nearest_barrier",
        "signal_close","signal_close_over_near_atr",
        "nearby_barrier_below_signal_close",
        "signal_close_confirms_barrier_reclaim",
        "confirmed_pivot_resistance","clustered_pivot_resistance",
        "signal_atr14","prior_rejection_days","prior_independent_rejection_count",
        "prior_close_through_count","prior_cluster_pivot_count",
        "pre_signal_barrier_label","barrier_status_is_proven_resistance",
        "forward_bar_count","forward_first_touch_day",
        "forward_any_touch","forward_any_close_break",
        "forward_first_close_break_day","forward_two_consecutive_close_break",
        "forward_any_rejection","forward_max_high_over_barrier_atr",
        "forward_last_close_over_barrier_atr",
        "comparison_not_order_fill","historically_selected_universe",
        "regular_only_source_certified","trade_approved","orders_enabled")

def frozen_inputs_valid(status,data,asof):
    if (not isinstance(status,dict) or
        status.get("schema")!="C3_K100_RESISTANCE_EVIDENCE_V61" or
        status.get("asof")!=str(asof) or
        status.get("absolute_nearest_wick_is_hard_barrier_for_buy_approval") is not True or
        status.get("trade_approved") is not False or
        status.get("orders_enabled") is not False or
        status.get("actual_regular_session_provider_verified") is not False or
        not isinstance(status.get("original_research_signals"),int) or
        not isinstance(data,list) or
        len(data)!=status.get("evaluated_entry_rows") or
        len(data)!=2*status["original_research_signals"]):
        raise ValueError("V61_DATE_OR_FULL_EVIDENCE_UNVERIFIED")
    seen=set()
    for row in data:
        if not isinstance(row,dict):raise ValueError("INVALID_V61_ROW")
        key=(row.get("ticker"),row.get("method"),row.get("signal_asof"),
             row.get("variant"))
        if (key in seen or key[1] not in METHODS or key[3] not in MODES
            or len(key[0] or "")!=6 or not (key[0] or "").isdigit()
            or row.get("trade_approved")!="False"
            or row.get("orders_enabled")!="False"
            or row.get("regular_price_certified")!="False"):
            raise ValueError("V61_DUPLICATE_OR_UNSAFE_TRADE_ROW")
        try:day=date.fromisoformat(key[2])
        except (TypeError,ValueError):raise ValueError("V61_SIGNAL_DATE_INVALID")
        if day>=asof:raise ValueError("V61_FUTURE_OR_ASOF_SIGNAL")
        seen.add(key)
    if len({(t,m,d) for t,m,d,v in seen})!=status["original_research_signals"]:
        raise ValueError("V61_MISSING_FIRST_SECOND_PAIR")
    for ticker,method,day in {(t,m,d) for t,m,d,v in seen}:
        if {(ticker,method,day,variant) for variant in MODES} - seen:
            raise ValueError("V61_MISSING_FIRST_SECOND_PAIR")
    return True

def pre_signal_rejections(prefix,near,atr):
    """Approach + rejected closing price on past completed daily OHLC only."""
    if near is None or atr is None or atr<=0:return [],0
    past=prefix[-61:-1]
    rejects=[]
    crossed=0
    for i,b in enumerate(past):
        if b["close"]>near+BREAKOUT_CLOSE_ABOVE_ATR*atr:
            crossed+=1
        if (near-REJECTION_HIGH_BELOW_ATR*atr<=b["high"]<=near+REJECTION_HIGH_ABOVE_ATR*atr
            and b["close"]<=near-REJECTION_CLOSE_BELOW_ATR*atr
            and b["high"]-b["close"]>=REJECTION_UPPER_WICK_ATR*atr):
            rejects.append((i,b["date"]))
    independent=[]
    for i,dt in rejects:
        if not independent or i-independent[-1][0]>=SEPARATE_TEST_BARS:
            independent.append((i,dt))
    return [d.isoformat() for _,d in independent],crossed

def classify_barrier(near,entry,crossed,rejections):
    if near is None:return LABELS[0]
    if entry is not None and near<=entry:return LABELS[1]
    if crossed>0:return LABELS[2]
    if rejections>=2:return LABELS[3]
    if rejections==1:return LABELS[4]
    return LABELS[5]

def future_reactions(forward,near,atr):
    """Five completed sessions. Does NOT infer within-bar event ordering."""
    result=dict(forward_bar_count=len(forward),
        forward_first_touch_day=None,forward_any_touch=False,
        forward_any_close_break=False,forward_first_close_break_day=None,
        forward_two_consecutive_close_break=False,
        forward_any_rejection=False,
        forward_max_high_over_barrier_atr=None,
        forward_last_close_over_barrier_atr=None)
    if len(forward)!=HORIZON:raise ValueError("FORWARD_FIVE_SESSION_WINDOW_MISSING")
    if near is None or atr is None or atr<=0:return result
    breaks=[]
    for bar in forward:
        if not result["forward_any_touch"] and bar["high"]>=near:
            result["forward_any_touch"]=True
            result["forward_first_touch_day"]=bar["date"].isoformat()
        br=bar["close"]>near+BREAKOUT_CLOSE_ABOVE_ATR*atr
        breaks.append(br)
        if br and result["forward_first_close_break_day"] is None:
            result["forward_first_close_break_day"]=bar["date"].isoformat()
        if (bar["high"]>=near and bar["close"]<near
            and bar["high"]-bar["close"]>=REJECTION_UPPER_WICK_ATR*atr):
            result["forward_any_rejection"]=True
    result["forward_any_close_break"]=any(breaks)
    result["forward_two_consecutive_close_break"]=any(
        a and b for a,b in zip(breaks,breaks[1:]))
    result["forward_max_high_over_barrier_atr"]=round(
        (max(b["high"] for b in forward)-near)/atr,4)
    result["forward_last_close_over_barrier_atr"]=round(
        (forward[-1]["close"]-near)/atr,4)
    return result

def analyze(archive,source_status,source_rows,asof):
    frozen_inputs_valid(source_status,source_rows,asof)
    candidates,histories,issues=signal_rows_for_historic_selected_universe(archive,asof)
    if not candidates or not histories or any(
        not x.startswith("HISTORY_EXCLUDED_") for x in issues):
        raise ValueError("DATED_RECOVERY_HISTORY_INCOMPLETE")
    output=[]
    observed_dates=set()
    for record in source_rows:
        ticker=record["ticker"]
        bars=histories.get(ticker)
        if bars is None:raise ValueError("MISSING_DATED_CANDIDATE_HISTORY")
        signal_day=date.fromisoformat(record["signal_asof"])
        at=next((i for i,b in enumerate(bars) if b["date"]==signal_day),None)
        if at is None or at<80 or at+HORIZON>=len(bars):
            raise ValueError("MISSING_SIGNAL_OR_COMPLETE_FORWARD_WINDOW")
        prefix=bars[:at+1]
        if not valid_bars_history(prefix,signal_day):
            raise ValueError("INVALID_PREFIX_OR_PRICE_DATE")
        forward=bars[at+1:at+1+HORIZON]
        if any(b["date"]<=signal_day for b in forward):
            raise ValueError("FUTURE_SESSION_DATE_NOT_LATER")
        entry=pos(record.get("entry_reference"))
        stop=pos(record.get("daily_pivot_stop"))
        signal_close=prefix[-1]["close"]
        if (entry is None)!=(record.get("entry_reference") in (None,"")):
            raise ValueError("INVALID_ENTRY_REFERENCE")
        if stop is None and record.get("daily_pivot_stop") not in (None,""):
            raise ValueError("INVALID_STOP_REFERENCE")
        if entry is not None and stop is not None and not 0<stop<entry:
            raise ValueError("INVALID_STRUCTURE_STOP_GEOMETRY")
        data=(tier_levels(prefix,entry) if entry is not None and
              stop is not None else None)
        if data is None:
            data=dict(atr=None,near=None,pivot=None,cluster=None,cluster_count=0)
        for k,present in (("near","nearest_wick_reference"),
                          ("pivot","confirmed_pivot_resistance"),
                          ("cluster","clustered_pivot_resistance")):
            if pos(data[k])!=pos(record.get(present)):
                raise ValueError("V61_DAILY_PRICE_TIER_DRIFT_"+k)
        atr=data["atr"]
        dates,crossed=pre_signal_rejections(prefix,data["near"],atr)
        label=classify_barrier(data["near"],entry,crossed,len(dates))
        close_over_near=((signal_close-data["near"])/atr
                         if data["near"] is not None and atr is not None else None)
        # A small historical wick above a DEEP entry can already sit below
        # the close when the signal is frozen. That is not an unbroken
        # overhead resistance at the SIGNAL CLOSE. For a pullback limit,
        # it may still be a hurdle on the way back up; do not delete it.
        is_below_close=(data["near"] is not None and data["near"]<signal_close)
        signal_reclaimed=(close_over_near is not None and
                          close_over_near>BREAKOUT_CLOSE_ABOVE_ATR)
        forward_status=future_reactions(forward,data["near"],atr)
        observed_dates.add((ticker,record["signal_asof"],record["method"]))
        output.append(dict(
            ticker=ticker,name=record.get("name"),
            method=record["method"],variant=record["variant"],
            signal_asof=record["signal_asof"],
            entry_reference=entry,stop_reference=stop,
            nearest_barrier=data["near"],
            signal_close=signal_close,
            signal_close_over_near_atr=(
                round(close_over_near,4) if close_over_near is not None else None),
            nearby_barrier_below_signal_close=bool(is_below_close),
            signal_close_confirms_barrier_reclaim=bool(signal_reclaimed),
            confirmed_pivot_resistance=data["pivot"],
            clustered_pivot_resistance=data["cluster"],
            signal_atr14=round(atr,4) if atr is not None else None,
            prior_rejection_days=";".join(dates),
            prior_independent_rejection_count=len(dates),
            prior_close_through_count=crossed,
            prior_cluster_pivot_count=data["cluster_count"],
            pre_signal_barrier_label=label,
            barrier_status_is_proven_resistance=False,
            **forward_status,
            comparison_not_order_fill=True,
            historically_selected_universe=True,
            regular_only_source_certified=False,
            trade_approved=False,orders_enabled=False))
    if len(output)!=len(source_rows) or len(observed_dates)!=source_status["original_research_signals"]:
        raise ValueError("INCOMPLETE_EVIDENCE_OR_SIGNAL_UNIVERSE")
    return output,issues

def aggregate(records,asof,issues):
    cats={}
    for category in LABELS:
        group=[r for r in records if r["pre_signal_barrier_label"]==category]
        usable=[r for r in group if r["nearest_barrier"] is not None and
                r["nearest_barrier"]>r["entry_reference"]]
        cats[category]=dict(rows=len(group),
            valid_nearest_barrier_rows=len(usable),
            next_five_day_touch_count=sum(r["forward_any_touch"] for r in usable),
            next_five_day_close_break_count=sum(r["forward_any_close_break"] for r in usable),
            next_five_day_two_close_break_count=sum(
                r["forward_two_consecutive_close_break"] for r in usable),
            next_five_day_rejection_count=sum(r["forward_any_rejection"] for r in usable),
            observed_past_repeated_rejection_count=sum(
                r["prior_independent_rejection_count"]>=2 for r in group),
            signal_close_above_near_count=sum(
                r["nearby_barrier_below_signal_close"] for r in group),
            signal_close_above_near_by_quarter_atr_count=sum(
                r["signal_close_confirms_barrier_reclaim"] for r in group),
            not_a_validated_prediction=True)
    by_variant={}
    for variant in MODES:
        pair=[r for r in records if r["variant"]==variant]
        by_variant[variant]=dict(
            rows=len(pair),
            historically_closed_through=sum(
                r["pre_signal_barrier_label"]=="HISTORIC_CLOSE_THROUGH_BARRIER"
                for r in pair),
            close_already_above_near=sum(
                r["nearby_barrier_below_signal_close"] for r in pair),
            close_already_reclaimed_by_quarter_atr=sum(
                r["signal_close_confirms_barrier_reclaim"] for r in pair),
            repeated_prior_rejection=sum(
                r["pre_signal_barrier_label"]=="REPEATED_PRE_SIGNAL_REJECTION"
                for r in pair),
            five_day_close_break=sum(
                r["forward_any_close_break"] for r in pair))
    return dict(schema=SCHEMA,asof=str(asof),
        input_rows=len(records),original_signal_count=len(records)//2,
        categories=cats,by_entry_variant=by_variant,source_issues=issues,
        hypothesis_thresholds_fixed_before_outcomes=True,
        category_post_signal_reactions_are_hindsight_biased=True,
        nearest_barrier_remains_veto_even_if_historic_breakout=True,
        signal_close_reclaim_is_diagnostic_not_trading_permission=True,
        exact_regular_session_source_verified=False,
        full_market_asof_universe_verified=False,
        official_daily_volume_profile_available=False,
        observed_post_20261023_true_forward_trades=0,
        validated_win_probability_available=False,
        final_independent_80_score_available=False,
        trade_approved=False,orders_enabled=False,decision="CASH")

def mobile(report):
    lines=["# v6.2 일봉 저항 반응 진단 · 과거 탐색용", "",
      f"기준 원본: {report['asof']} · **최종 CASH / 자동주문 0건**", "",
      "시그널 이전 60봉의 독립적인 윗꼬리 거절과 종가 돌파를 계산하고,",
      "각 신호 다음 5거래일은 결과 측정에만 사용했습니다.",
      "23일에 선별된 종목의 과거를 재생해 선택편향이 있으며, 정규장 시세 인증도 없습니다.",
      "", "| 신호 전 저항 진단 | 사례 | 5일 내 고가 터치 | 5일 내 종가 돌파 | 2일 연속 종가 돌파 |",
      "|---|---:|---:|---:|---:|"]
    for name in LABELS:
        group=report["categories"][name]
        lines.append(f"| {name} | {group['rows']} | {group['next_five_day_touch_count']} | {group['next_five_day_close_break_count']} | {group['next_five_day_two_close_break_count']} |")
    lines+=["", "## 1차와 2차 대체가격 각각의 신호일 장벽 상태",
      "| 시나리오 | 평가행 | 과거 종가가 장벽 돌파 | 신호일 종가가 장벽 위 | 신호일 0.25ATR 이상 회복 |",
      "|---|---:|---:|---:|---:|"]
    for variant in MODES:
        v=report["by_entry_variant"][variant]
        lines.append(f"| {variant} | {v['rows']} | {v['historically_closed_through']} | "+
            f"{v['close_already_above_near']} | {v['close_already_reclaimed_by_quarter_atr']} |")
    lines+=["",
      "**위 숫자는 같은 신호의 1차·2차 대체안을 각각 포함하며 독립 승률 표본이 아닙니다.**",
      "가까운 저항의 반복 증거가 없더라도 높은 목표를 곧바로 매수 승인에 사용하지 않습니다.",
      "성과를 보고 저항의 '약함' 기준을 바꾸거나 최종 예상수익률로 승격하지 않습니다.",
      "", "## 다음에 필요한 자료",
      "정규장 09:00~15:30 독립 공급원·동일 종목 과거 일별 전수 스캔·공시 시각·5거래일 미래 신호축적·실측 거래대금/호가.",
      ""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--recovery",type=Path,required=True)
    p.add_argument("--v61",type=Path,required=True)
    p.add_argument("--asof",required=True)
    p.add_argument("--outdir",type=Path,required=True)
    args=p.parse_args()
    try:asof=date.fromisoformat(args.asof)
    except (TypeError,ValueError):raise SystemExit("INVALID_DATE")
    status=safe_json(args.v61/"resistance_tiers_v61_status.json")
    data=rows(args.v61/"resistance_tiers_v61_all.csv")
    result,issues=analyze(args.recovery,status,data,asof)
    report=aggregate(result,asof,issues)
    args.outdir.mkdir(parents=True,exist_ok=True)
    (args.outdir/"wick_barrier_v62_status.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (args.outdir/"wick_barrier_v62_all.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
        w.writeheader();w.writerows(result)
    (args.outdir/"wick_barrier_v62_mobile.md").write_text(
        mobile(report)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in
        ("asof","input_rows","original_signal_count","decision")},
        ensure_ascii=False))
    print("V62_BARRIER_REACTION_COUNTS",json.dumps(report["categories"],ensure_ascii=False))

if __name__=="__main__":main()
