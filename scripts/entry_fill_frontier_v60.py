#!/usr/bin/env python3
"""v6.0 PRE-SPECIFIED fill / RR frontier in hindsight-selected KRX universe.

Five entry options per archived v5.9 signal. Every candidate price uses ONLY
data through historical signal date, not the subsequent 7 OHLC bars. All
counterfactuals are independent: no simultaneous orders or averaging down.
No source certification, learned hit-rate, expected ROI, BUY, or brokerage API.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from free_structural_v52 import atr14
from first_pullback_v55 import down,net_reward_risk
from entry_strategy_v58 import nearest_ceiling, rows as read_csv, safe_json, METHODS
from shadow_five_day_v59 import (
    simulate, signal_rows_for_historic_selected_universe,
    ENTRY_DAYS, HOLD_DAYS, ROUNDTRIP_COST_PCT)

SCHEMA="C3_K100_FIXED_ENTRY_FILL_FRONTIER_V60"
VARIANTS=("V58_FIRST","V58_PIVOT_SECOND",
          "ATR_HALF_RETRACE","ATR_ONE_RETRACE","COST_2R_BOUNDARY")
ROW_FIELDS=("signal_asof","ticker","method","variant","entry_reference",
   "stop_reference","nearest_overhead_target","actual_signal_close",
   "atr14","distance_below_signal_close_atr","risk_pct",
   "cost_adjusted_rr","geometry_2r_ok","has_confirmed_second_support",
   "price_is_unconfirmed_support_proxy","geometry_blocker",
   "sim_outcome","sim_entry_date","sim_entry_price","sim_exit_date",
   "sim_exit_reason","sim_net_return_pct","sim_net_r",
   "unfilled_and_five_day_stock_gain_over_3pct",
   "hindsight_universe","regular_session_certified","trade_approved")

def pos(value):
    if isinstance(value,bool):return None
    try:
        x=float(value)
        return x if math.isfinite(x) and x>0 else None
    except (ValueError,TypeError):return None

def valid_bars_history(h,asof):
    if not h or h[-1]["date"]!=asof or len(h)<81:return False
    return all(a["date"]<b["date"] for a,b in zip(h,h[1:]))

def archived_signals(shadow_rows,asof):
    """Strictly pair FIRST/SECOND across a historical per-method signal."""
    seen=defaultdict(dict)
    for r in shadow_rows:
        if not isinstance(r,dict):raise ValueError("INVALID_V59_ROW")
        ticker=r.get("ticker")
        method=r.get("method")
        variant=r.get("entry_variant")
        when=r.get("signal_asof")
        if (not isinstance(ticker,str) or len(ticker)!=6 or not ticker.isdigit()
            or method not in METHODS or variant not in ("FIRST","SECOND")):
            raise ValueError("BAD_V59_IDENTITY")
        try:d=date.fromisoformat(when)
        except (TypeError,ValueError):raise ValueError("BAD_V59_SIGNAL_DATE")
        if d>=asof:raise ValueError("FUTURE_OR_ASOF_V59_SIGNAL")
        k=(ticker,method,d)
        if variant in seen[k]:raise ValueError("DUPLICATE_V59_VARIANT")
        if r.get("trade_approved")!="False" or r.get("regular_session_certified")!="False":
            raise ValueError("UNSAFE_OR_CERTIFIED_ARCHIVED_SIGNAL")
        if r.get("hindsight_selected_ticker")!="True":
            raise ValueError("HINDSIGHT_FLAG_MISSING")
        seen[k][variant]=r
    for k,pair in seen.items():
        if set(pair)!=set(("FIRST","SECOND")):
            raise ValueError("UNPAIRED_ARCHIVED_V59_ALTERNATIVES")
        first,second=pair["FIRST"],pair["SECOND"]
        for f in ("stop_reference","signal_first_reference",
                  "signal_second_reference","target_reference","signal_close"):
            if first.get(f)!=second.get(f):
                raise ValueError("DIFFERING_ARCHIVED_SIGNAL_REFERENCES")
    return [(k,pair["FIRST"],pair["SECOND"]) for k,pair in sorted(seen.items())]

def bounded_two_r_price(signal_bars,first,stop,atr):
    """Highest in-sample-entry candidate with >=2 net R on nearest resistance.

    Fixed ATR increments known before the next day. This does NOT establish
    support or guarantee future fills, and is never auto promoted to an order.
    """
    for q in (.5,.75,1,1.25,1.5,1.75,2):
        entry=down(first-q*atr)
        if not entry or entry<=stop or entry>=first:continue
        target=nearest_ceiling(signal_bars,entry)
        if target is None or target<=entry:continue
        rr=net_reward_risk(entry,stop,target,ROUNDTRIP_COST_PCT)
        if rr is not None and rr>=2:
            return entry
    return None

def entry_levels(signal_bars,first,second,stop):
    atr=atr14(signal_bars)
    if atr is None or not math.isfinite(atr) or atr<=0:raise ValueError("INVALID_ATR")
    return {"V58_FIRST":first,"V58_PIVOT_SECOND":second,
        "ATR_HALF_RETRACE":down(first-.5*atr),
        "ATR_ONE_RETRACE":down(first-atr),
        "COST_2R_BOUNDARY":bounded_two_r_price(signal_bars,first,stop,atr)}

def simulate_variants(archive,shadow_rows,asof):
    candidates,histories,source_issues=signal_rows_for_historic_selected_universe(archive,asof)
    if (not candidates or not histories or any(not x.startswith("HISTORY_EXCLUDED_")
         for x in source_issues)):
        raise ValueError("INVALID_ARCHIVED_UNIVERSE_OR_ASOF")
    signals=archived_signals(shadow_rows,asof)
    result=[];blocked=Counter()
    for (ticker,method,sigday),control,alternate in signals:
        bars=histories.get(ticker)
        if not bars:raise ValueError("V59_SIGNAL_TICKER_NOT_IN_VALID_HISTORY")
        at=next((i for i,x in enumerate(bars) if x["date"]==sigday),None)
        if at is None or at<80 or at+ENTRY_DAYS+HOLD_DAYS>=len(bars):
            raise ValueError("OUT_OF_SCOPE_SIGNAL_HISTORY_OR_FORWARD")
        prefix=bars[:at+1]
        future=bars[at+1:at+1+ENTRY_DAYS+HOLD_DAYS]
        if not valid_bars_history(prefix,sigday) or len(future)!=7:
            raise ValueError("SIGNAL_ASOF_OR_FUTURE_WINDOW_INVALID")
        first=pos(control["signal_first_reference"])
        second=pos(control["signal_second_reference"])
        stop=pos(control["stop_reference"])
        close=pos(control["signal_close"])
        if None in (first,stop,close) or not 0<stop<first:
            # The entire signal is counted; no convenient exclusion of losers.
            blocked["CONTROL_REFERENCE_INVALID"]+=1
            for v in VARIANTS:
                result.append(dict(signal_asof=str(sigday),ticker=ticker,
                    method=method,variant=v,entry_reference=None,
                    stop_reference=stop,nearest_overhead_target=None,
                    actual_signal_close=close,atr14=None,
                    distance_below_signal_close_atr=None,risk_pct=None,
                    cost_adjusted_rr=None,geometry_2r_ok=False,
                    has_confirmed_second_support=(second is not None),
                    price_is_unconfirmed_support_proxy=v not in ("V58_FIRST","V58_PIVOT_SECOND"),
                    geometry_blocker="INVALID_ARCHIVED_STOP_OR_FIRST",
                    sim_outcome="NO_VALID_ENTRY",sim_entry_date=None,sim_entry_price=None,
                    sim_exit_date=None,sim_exit_reason=None,sim_net_return_pct=None,
                    sim_net_r=None,unfilled_and_five_day_stock_gain_over_3pct=False,
                    hindsight_universe=True,regular_session_certified=False,
                    trade_approved=False))
            continue
        atr=atr14(prefix)
        levels=entry_levels(prefix,first,second,stop)
        missed_run=(future[4]["close"]/close-1)>0.03
        for variant in VARIANTS:
            entry=levels[variant]
            target=(pos(control["target_reference"]) if variant in
                    ("V58_FIRST","V58_PIVOT_SECOND") else
                    nearest_ceiling(prefix,entry) if entry is not None else None)
            rr=net_reward_risk(entry,stop,target,ROUNDTRIP_COST_PCT) if (
                entry is not None and target is not None) else None
            risk=(100*(entry-stop)/entry if entry is not None and entry>stop else None)
            dist=((close-entry)/atr if entry is not None else None)
            issues=[]
            if entry is None:issues.append("NO_PREDEFINED_ENTRY")
            elif entry<=stop:issues.append("ENTRY_BELOW_STRUCTURAL_STOP")
            elif entry>=close+0.03*atr:issues.append("OVER_CLOSING_CHASE_LIMIT")
            if target is None or (entry is not None and target<=entry):
                issues.append("NO_NEAREST_VALID_OVERHEAD_TARGET")
            if rr is None or rr<2:issues.append("COST_ADJUSTED_RR_BELOW_2")
            if risk is None or not 1<=risk<=12:
                issues.append("STOP_RISK_OUT_OF_1_TO_12_PERCENT")
            if dist is None or dist>2:
                issues.append("ENTRY_OVER_TWO_ATR_BELOW_CLOSE")
            if variant=="V58_FIRST" and (risk is None or risk<2 or dist is None or dist>1):
                issues.append("FIRST_ENTRY_V58_SAFETY_RANGE")
            if variant=="V58_PIVOT_SECOND" and second is None:
                issues.append("NO_CONFIRMED_SECOND_SUPPORT")
            if variant.startswith("ATR_") or variant=="COST_2R_BOUNDARY":
                issues.append("NO_INDEPENDENT_DAILY_SUPPORT_CONFIRMATION")
            numeric_safe=(entry is not None and stop<entry and
                          target is not None and target>entry)
            # Record simulations for every numeric plan, even those failing
            # 2R or support, but do NOT call these investable strategy trades.
            p=dict(asof=str(sigday),ticker=ticker,method=method,
                asof_close_research=close,first_entry_reference=entry,
                second_entry_reference=None,stop_reference=stop,
                nearest_resistance_reference=target,
                first_net_rr=rr,second_net_rr=None)
            sim=(simulate(p,future,"FIRST") if numeric_safe else None)
            status=(sim["outcome"] if sim else "NO_VALID_ENTRY")
            filled=sim and status in ("NET_WIN","NET_LOSS","NET_FLAT")
            unfilled=status in ("NOT_FILLED_WITHIN_2_SESSIONS",
                "CANCEL_OPENED_BELOW_STOP","CANCEL_BROKEN_STOP_BEFORE_ENTRY")
            result.append(dict(signal_asof=str(sigday),ticker=ticker,
                method=method,variant=variant,entry_reference=entry,
                stop_reference=stop,nearest_overhead_target=target,
                actual_signal_close=close,atr14=round(atr,4),
                distance_below_signal_close_atr=round(dist,4) if dist is not None else None,
                risk_pct=round(risk,4) if risk is not None else None,
                cost_adjusted_rr=round(rr,4) if rr is not None else None,
                geometry_2r_ok=(rr is not None and rr>=2 and risk is not None
                     and 1<=risk<=12 and dist is not None and dist<=2
                     and variant in ("V58_FIRST","V58_PIVOT_SECOND")),
                has_confirmed_second_support=(second is not None),
                price_is_unconfirmed_support_proxy=(variant not in
                    ("V58_FIRST","V58_PIVOT_SECOND")),
                geometry_blocker=";".join(issues),
                sim_outcome=status,
                sim_entry_date=sim.get("entry_date") if sim else None,
                sim_entry_price=sim.get("entry_price") if sim else None,
                sim_exit_date=sim.get("exit_date") if sim else None,
                sim_exit_reason=sim.get("exit_reason") if sim else None,
                sim_net_return_pct=sim.get("net_return_pct") if filled else None,
                sim_net_r=sim.get("net_r") if filled else None,
                unfilled_and_five_day_stock_gain_over_3pct=bool(unfilled and missed_run),
                hindsight_universe=True,
                regular_session_certified=False,trade_approved=False))
    if len(result)!=len(signals)*len(VARIANTS):
        raise ValueError("COUNTERFACTUAL_GRID_INCOMPLETE")
    return result,dict(signals=len(signals),archived_issues=source_issues)

def summary(rows,asof,diagnostics,upstream):
    out={}
    n=diagnostics["signals"]
    for m in METHODS:
        out[m]={}
        for v in VARIANTS:
            setrows=[x for x in rows if x["method"]==m and x["variant"]==v]
            filled=[x for x in setrows if x["sim_outcome"] in ("NET_WIN","NET_LOSS","NET_FLAT")]
            eligible=[x for x in setrows if x["geometry_2r_ok"]]
            eg=[x for x in eligible if x["sim_outcome"] in ("NET_WIN","NET_LOSS","NET_FLAT")]
            # Signal-weighted payoff treats an unfilled scenario as zero realized
            # return on theoretical order budget, not as invested P&L.
            # No opportunity cost / cash yield / other strategy imputed.
            payoff=sum(x["sim_net_return_pct"] for x in filled)
            out[m][v]=dict(
                signals=len(setrows),numeric_entries=sum(x["entry_reference"] is not None for x in setrows),
                filled=len(filled),not_filled=sum(x["sim_outcome"]=="NOT_FILLED_WITHIN_2_SESSIONS" for x in setrows),
                cancelled=sum(x["sim_outcome"].startswith("CANCEL") for x in setrows),
                fill_pct_all_signals=round(100*len(filled)/len(setrows),2) if setrows else None,
                mean_net_return_filled_pct=round(payoff/len(filled),4) if filled else None,
                win_rate_filled_pct=(round(100*sum(x["sim_outcome"]=="NET_WIN" for x in filled)/len(filled),2)
                      if len(filled)>=30 else None),
                signal_weighted_hypothetical_payoff_pct=round(payoff/len(setrows),4) if setrows else None,
                missed_gt3pct_move_when_unfilled=sum(x["unfilled_and_five_day_stock_gain_over_3pct"]
                                                   for x in setrows),
                valid_2r_supported_price_entries=len(eligible),
                valid_2r_supported_price_fills=len(eg),
                valid_2r_supported_price_fill_pct=round(100*len(eg)/len(eligible),2)
                     if eligible else None,
                strategy_is_forward_verified=False)
    return dict(schema=SCHEMA,asof=str(asof),retro_selected_universe=True,
        same_signal_control_and_all_counterfactual_variants=True,
        research_signals=n,research_rows=len(rows),
        variants=list(VARIANTS),cost_pct_roundtrip=ROUNDTRIP_COST_PCT,
        signal_weighted_zeros_for_unfilled_are_not_pnl_on_deployed_capital=True,
        historic_120bar_pit_market_universe_verified=False,
        regular_market_ohlc_independently_verified=False,
        foreign_institution_investor_flows_required=False,
        independent_date_20261023_after_signal_return_verified=False,
        observed_true_post_20261023_outcomes=0,
        opportunity_cost_is_diagnostic_not_claim_of_obtainable_alternative=True,
        historical_n30_threshold_for_winrate=True,
        support_proxy_variants_can_never_be_traded_without_additional_validation=True,
        category_stats=out,source_errors=diagnostics["archived_issues"],
        winner_variant_not_selected_from_hindsight=True,
        certified_final_score_80=False,
        validated_live_trade_count=0,trade_approved=False,orders_enabled=False,
        decision="CASH")

def mobile(report):
    lines=["# v6.0 매수가 체결가능성·손익비 비교 (무료 그림자검증)","",
      f"**기준일**: {report['asof']} · **신규매수 CASH** · 자동주문 없음",
      f"23일 후보로 과거를 재생한 선택편향 검증. 신호 {report['research_signals']}건 × 5가지 사전 가격정책.",
      "가상 수익, 실측 거래대금·정규장 시세·당시 전체시장 종목이 인증되지 않았습니다.",
      "ATR 기반 중간 가격과 2R 경계 가격은 실제 지지선 확인이 없어 주문 불가입니다.",
      "1차 체결 후 2차 추가매수는 하지 않습니다.",
      "", "| 방법 | 가격안 | 신호 | 가상체결 | 미체결 | 손익비 2R+·지지 충족 | 2R+ 체결 |",
      "|---|---|---:|---:|---:|---:|---:|"]
    for m in METHODS:
        for v in VARIANTS:
            s=report["category_stats"][m][v]
            lines.append(f"| {m} | {v} | {s['signals']} | {s['filled']} | {s['not_filled']} | {s['valid_2r_supported_price_entries']} | {s['valid_2r_supported_price_fills']} |")
    lines +=["",
      "## 함께 확인할 함정",
      "1. 거래비용 후 순수익은 체결된 종목에만 의미가 있으며, 미체결 0%는 투자수익이 아닙니다.",
      "2. 가상 2R 경계가 계산됐더라도 해당 가격이 실제 지지선이라는 증거가 없습니다.",
      "3. 정규장 장후 혼합 여부와 종목선정 편향이 해결되지 않은 자료이므로 승률 및 수익예측으로 해석하지 않습니다.",
      "4. 모의매매에 사용한 고저가 순서가 미확인이므로 손절/목표 동시 달성은 손절을 우선합니다.",
      "",
      "## Required Next Data",
      "당시 날짜별 KRX 전체 종목선정 자료, 정규장 가격 출처, 그날 실측 거래대금과 섹터 수급, 이후 최소 7거래일 실제 완료 봉, 계좌 현금/보유종목.",
      ""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--recovery",type=Path,required=True)
    p.add_argument("--v59",type=Path,required=True)
    p.add_argument("--asof",required=True)
    p.add_argument("--outdir",type=Path,required=True)
    args=p.parse_args()
    try:asof=date.fromisoformat(args.asof)
    except (TypeError,ValueError):raise SystemExit("ASOF_INVALID")
    # Only v5.9 evidence actually compiled from this 23 Oct signal archive.
    control_path=args.v59/"shadow_v59_status.json"
    control=safe_json(control_path)
    if (control.get("schema")!="C3_K100_FIVE_DAY_SHADOW_V59" or
        control.get("asof")!=str(asof) or
        control.get("retrospective_universe_selection_bias") is not True or
        control.get("trade_approved") is not False or
        control.get("orders_enabled") is not False or
        control.get("total_simulated_alternative_scenarios") !=
        len(read_csv(args.v59/"shadow_v59_all.csv"))):
        raise SystemExit("SOURCE_V59_FULL_RETROSPECTIVE_EVIDENCE_INVALID")
    base=read_csv(args.v59/"shadow_v59_all.csv")
    result,diagnostics=simulate_variants(args.recovery,base,asof)
    if diagnostics["signals"]*2!=len(base):
        raise SystemExit("ARCHIVED_V59_SIGNAL_COUNT_INCONSISTENT")
    report=summary(result,asof,diagnostics,control)
    args.outdir.mkdir(parents=True,exist_ok=True)
    (args.outdir/"entry_fill_frontier_v60_status.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (args.outdir/"entry_fill_frontier_v60_all.csv").open(
        "w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=ROW_FIELDS,extrasaction="ignore")
        w.writeheader();w.writerows(result)
    (args.outdir/"entry_fill_frontier_v60_mobile.md").write_text(
        mobile(report)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("asof","research_signals","research_rows",
        "variants","validated_live_trade_count","decision")},ensure_ascii=False))

if __name__=="__main__":main()
