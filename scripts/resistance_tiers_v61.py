#!/usr/bin/env python3
"""v6.1 confirmed-overhead-resistance sensitivity audit (NO BUY authorization).

Compare the conservative nearest preceding-bar HIGH to confirmed *historical*
swing highs / recurring pivot clusters. Signals and research entries are fixed
by v6.0; we do NOT choose whichever resistance yields the best backtest outcome.
Neither OHLC highs nor daily volume are a verified intraday volume profile.
The universe is retrospectively chosen and provider/session is unverified.
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
from entry_strategy_v58 import METHODS, nearest_ceiling, rows, safe_json
from entry_fill_frontier_v60 import (
    archived_signals, pos, valid_bars_history)
from shadow_five_day_v59 import (
    ENTRY_DAYS, HOLD_DAYS, ROUNDTRIP_COST_PCT, simulate,
    signal_rows_for_historic_selected_universe)

VERSION="C3_K100_RESISTANCE_EVIDENCE_V61"
MODES=("V58_FIRST","V58_PIVOT_SECOND")
COLUMNS=("ticker","name","method","signal_asof","variant",
         "entry_reference","daily_pivot_stop","signal_atr14",
         "nearest_wick_reference","nearest_wick_rr_net",
         "nearby_wick_touch_count","confirmed_pivot_resistance",
         "confirmed_pivot_rr_net","confirmed_pivot_date",
         "confirmed_pivot_touch_count","clustered_pivot_resistance",
         "cluster_rr_net","cluster_pivot_count",
         "cluster_dates","cluster_volume_ratio_vs_window",
         "target_gap_due_to_unconfirmed_barriers",
         "tier_status","conservative_2r_pass",
         "optimistic_pivot_2r_only","conservative_sim_outcome",
         "pivot_sim_outcome_research_only","conservative_sim_net_return_pct",
         "pivot_sim_net_return_pct","hindsight_selection","regular_price_certified",
         "trade_approved","orders_enabled")

def highs_confirmed(bars,window=60):
    """Pivot high has TWO fully closed bars on both sides as of signal close.

    The signal candle is deliberately excluded, as is each of the previous
    two candles which don't have 2 subsequent PRE-SIGNAL bars. Multiple
    overlapping pivots are preserved; clusters enforce 3-bar separation.
    """
    end=len(bars)-1
    start=max(2,end-window)
    pivots=[]
    for i in range(start,end-1):
        h=bars[i]["high"]
        if (h>bars[i-1]["high"] and h>bars[i-2]["high"]
            and h>=bars[i+1]["high"] and h>=bars[i+2]["high"]):
            pivots.append((i,h,bars[i]["date"],bars[i].get("volume",0)))
    return pivots

def tier_levels(bars,entry):
    """As-of resistance tiers; NEVER treat higher tier as executable by itself."""
    entry=pos(entry)
    if not entry or len(bars)<81:
        raise ValueError("ENTRY_OR_HISTORY_MISSING")
    atr=atr14(bars)
    if not isinstance(atr,(int,float)) or not math.isfinite(atr) or atr<=0:
        raise ValueError("INVALID_SIGNAL_ATR")
    window=bars[-61:-1]
    near=nearest_ceiling(bars,entry)
    if near is not None and near<=entry:
        raise ValueError("INVALID_NEAR_FRICTION")
    # Empirical nearby wick count using 0.25 ATR tolerance, not a real
    # intraday order-book / traded-price profile.
    near_touches=(sum(abs(b["high"]-near)<=.25*atr for b in window)
                  if near is not None else 0)
    pivots=[p for p in highs_confirmed(bars) if p[1]>entry]
    first=min(pivots,key=lambda p:(p[1],p[0])) if pivots else None
    pivot=down(first[1]) if first else None
    # A "strong cluster" is 2 or more independently separated confirmed
    # pivot highs at approximately same resistance, within .35 ATR. This
    # is an alternative diagnostic, not permission to ignore near wicks.
    clusters=[]
    for root in pivots:
        members=[]
        for p in pivots:
            if abs(p[1]-root[1])<=.35*atr and all(abs(p[0]-q[0])>=3 for q in members):
                members.append(p)
        if len(members)>=2:
            levels=[p[1] for p in members]
            # Lowest pivot in the band is the first obstacle, not mean/high.
            level=down(min(levels))
            if level and level>entry:
                clusters.append((level,members))
    cluster=min(clusters,key=lambda x:x[0]) if clusters else None
    cluster_price=cluster[0] if cluster else None
    volumes=[pos(b.get("volume")) for b in window]
    volumes=[v for v in volumes if v is not None]
    # Daily bar volume: can only support a rough count/relative activity.
    base_volume=sum(volumes)/len(volumes) if volumes else None
    cluster_ratio=(sum(pos(p[3]) or 0 for p in cluster[1])
                  /len(cluster[1])/base_volume if cluster and base_volume else None)
    return dict(atr=atr,near=near,near_touches=near_touches,
        pivot=pivot,pivot_date=(first[2].isoformat() if first else None),
        pivot_touch_count=len([p for p in pivots if pivot is not None and
                               abs(p[1]-pivot)<=.35*atr]),
        cluster=cluster_price,cluster_count=(len(cluster[1]) if cluster else 0),
        cluster_dates=([p[2].isoformat() for p in cluster[1]]
                       if cluster else []),
        cluster_volume_ratio=cluster_ratio)

def build(archive,v59_rows,v60_rows,asof):
    """Only original two limits, fixed by verified v5.9/v6.0 research reports."""
    candidates,histories,issues=signal_rows_for_historic_selected_universe(archive,asof)
    if not candidates or not histories or any(not x.startswith("HISTORY_EXCLUDED_") for x in issues):
        raise ValueError("DATED_RECOVERY_SOURCE_INVALID")
    signals=archived_signals(v59_rows,asof)
    v60={}
    allowed=set()
    for (ticker,method,when),_,_ in signals:
        allowed.update((ticker,method,str(when),variant) for variant in MODES)
    for r in v60_rows:
        if not isinstance(r,dict):raise ValueError("INVALID_V60_INPUT_ROW")
        key=(r.get("ticker"),r.get("method"),r.get("signal_asof"),r.get("variant"))
        if r.get("trade_approved")!="False" or r.get("regular_session_certified")!="False":
            raise ValueError("V60_RESEARCH_SAFETY_INVALID")
        if key in allowed:
            if key in v60:raise ValueError("DUPLICATE_V60_BASELINE")
            v60[key]=r
    if len(v60)!=2*len(signals):
        raise ValueError("V60_BASELINE_FIRST_SECOND_NOT_COMPLETE")
    allrows=[]
    names={str(c.get("ticker")):str(c.get("name","")) for c in candidates}
    for (ticker,method,when),first,second in signals:
        bars=histories.get(ticker)
        if not bars:raise ValueError("ARCHIVED_SIGNAL_STOCK_MISSING")
        index=next((i for i,b in enumerate(bars) if b["date"]==when),None)
        if index is None or index<80 or index+ENTRY_DAYS+HOLD_DAYS>=len(bars):
            raise ValueError("INVALID_SIGNAL_FORWARD_WINDOW")
        prefix=bars[:index+1]
        if not valid_bars_history(prefix,when):
            raise ValueError("SIGNAL_PRICE_HISTORY_INCONSISTENT")
        future=bars[index+1:index+1+ENTRY_DAYS+HOLD_DAYS]
        if len(future)!=ENTRY_DAYS+HOLD_DAYS:
            raise ValueError("INCOMPLETE_SHADOW_FORWARD")
        for variant in MODES:
            key=(ticker,method,str(when),variant)
            archived=first if variant=="V58_FIRST" else second
            base=v60[key]
            entry=pos(archived["signal_first_reference" if variant=="V58_FIRST"
                               else "signal_second_reference"])
            stop=pos(archived["stop_reference"])
            baseline_entry=pos(base.get("entry_reference"))
            baseline_stop=pos(base.get("stop_reference"))
            if entry!=baseline_entry or stop!=baseline_stop:
                raise ValueError("V59_V60_PRICE_OR_STOP_DISAGREE")
            level=None;rrnear=None;rrpivot=None;rrcluster=None
            conservative=None;pivotsim=None
            if entry is not None and stop is not None and 0<stop<entry:
                level=tier_levels(prefix,entry)
                nearest=level["near"];pivot=level["pivot"];cluster=level["cluster"]
                if (nearest is not None and
                    nearest!=pos(base.get("nearest_overhead_target"))):
                    raise ValueError("V60_BASELINE_NEAREST_FRICTION_MISMATCH")
                rrnear=(net_reward_risk(entry,stop,nearest,ROUNDTRIP_COST_PCT)
                        if nearest is not None else None)
                rrpivot=(net_reward_risk(entry,stop,pivot,ROUNDTRIP_COST_PCT)
                         if pivot is not None else None)
                rrcluster=(net_reward_risk(entry,stop,cluster,ROUNDTRIP_COST_PCT)
                           if cluster is not None else None)
                if nearest is not None and nearest>entry:
                    p=dict(asof=str(when),ticker=ticker,method=method,
                        stop_reference=stop,first_entry_reference=entry,
                        second_entry_reference=None,
                        nearest_resistance_reference=nearest)
                    conservative=simulate(p,future,"FIRST")
                if pivot is not None and pivot>entry:
                    p=dict(asof=str(when),ticker=ticker,method=method,
                        stop_reference=stop,first_entry_reference=entry,
                        second_entry_reference=None,
                        nearest_resistance_reference=pivot)
                    pivotsim=simulate(p,future,"FIRST")
            if level is None:
                level=dict(atr=None,near=None,near_touches=0,pivot=None,
                    pivot_date=None,pivot_touch_count=0,cluster=None,
                    cluster_count=0,cluster_dates=[],cluster_volume_ratio=None)
            nearest=level["near"];pivot=level["pivot"]
            risk=(100*(entry-stop)/entry if entry and stop and entry>stop else None)
            dist=((prefix[-1]["close"]-entry)/level["atr"]
                  if entry and level["atr"] else None)
            strict=(rrnear is not None and rrnear>=2 and risk is not None
                and 1<=risk<=12 and dist is not None and dist<=2
                and (variant!="V58_FIRST" or (risk>=2 and dist<=1))
                and (variant!="V58_PIVOT_SECOND" or
                    pos(first["signal_second_reference"]) is not None))
            soft=rrpivot is not None and rrpivot>=2 and not strict
            if nearest is None:label="NO_PRIOR_NEARBY_OVERHEAD"
            elif pivot is None:label="ONLY_SINGLE_BAR_HIGH_NO_CONFIRMED_PIVOT"
            elif soft:label="PIVOT_TARGET_2R_BUT_NEARBY_FRICTION_BLOCKS"
            elif strict:label="NEAREST_BARRIER_2R_RESEARCH_ONLY"
            else:label="INSUFFICIENT_NET_RR_TO_NEAREST_BARRIER"
            allrows.append(dict(ticker=ticker,name=names.get(ticker,""),
                method=method,signal_asof=str(when),variant=variant,
                entry_reference=entry,daily_pivot_stop=stop,
                signal_atr14=round(level["atr"],4) if level["atr"] else None,
                nearest_wick_reference=nearest,
                nearest_wick_rr_net=round(rrnear,4) if rrnear is not None else None,
                nearby_wick_touch_count=level["near_touches"],
                confirmed_pivot_resistance=pivot,
                confirmed_pivot_rr_net=round(rrpivot,4) if rrpivot is not None else None,
                confirmed_pivot_date=level["pivot_date"],
                confirmed_pivot_touch_count=level["pivot_touch_count"],
                clustered_pivot_resistance=level["cluster"],
                cluster_rr_net=round(rrcluster,4) if rrcluster is not None else None,
                cluster_pivot_count=level["cluster_count"],
                cluster_dates=";".join(level["cluster_dates"]),
                cluster_volume_ratio_vs_window=(
                    round(level["cluster_volume_ratio"],3)
                    if level["cluster_volume_ratio"] is not None else None),
                target_gap_due_to_unconfirmed_barriers=bool(
                    nearest is not None and pivot is not None and pivot>nearest),
                tier_status=label,conservative_2r_pass=bool(strict),
                optimistic_pivot_2r_only=bool(soft),
                conservative_sim_outcome=(conservative["outcome"] if conservative else "NO_VALID_PRICE"),
                pivot_sim_outcome_research_only=(pivotsim["outcome"] if pivotsim else "NO_CONFIRMED_PIVOT"),
                conservative_sim_net_return_pct=(conservative.get("net_return_pct") if conservative else None),
                pivot_sim_net_return_pct=(pivotsim.get("net_return_pct") if pivotsim else None),
                hindsight_selection=True,regular_price_certified=False,
                trade_approved=False,orders_enabled=False))
    return allrows,dict(signals=len(signals),issues=issues)

def summarize(rows,diag,asof):
    counts=Counter(x["tier_status"] for x in rows)
    methods={}
    for method in METHODS:
        ss=[x for x in rows if x["method"]==method]
        methods[method]=dict(rows=len(ss),
            confirmed_pivot_target_available=sum(x["confirmed_pivot_resistance"] is not None for x in ss),
            cluster_resistance_available=sum(x["clustered_pivot_resistance"] is not None for x in ss),
            nearer_unconfirmed_barrier_count=sum(x["target_gap_due_to_unconfirmed_barriers"] for x in ss),
            soft_pivot_2r_only=sum(x["optimistic_pivot_2r_only"] for x in ss),
            conservative_nearest_2r=sum(x["conservative_2r_pass"] for x in ss))
    return dict(schema=VERSION,asof=str(asof),
        universe_selection_is_retroactive=True,
        after_hours_or_unadjusted_data_not_resolved=True,
        actual_regular_session_provider_verified=False,
        required_roundtrip_cost_pct=ROUNDTRIP_COST_PCT,
        absolute_nearest_wick_is_hard_barrier_for_buy_approval=True,
        confirmed_pivot_tiers_are_diagnostic_not_approval=True,
        historical_pivot_detection_two_right_completed_bars=True,
        ordered_future_high_low_timestamps_unknown=True,
        original_research_signals=diag["signals"],
        evaluated_entry_rows=len(rows),tier_status_counts=dict(counts),
        method_stats=methods,
        nearest_2r_rows=sum(x["conservative_2r_pass"] for x in rows),
        pivot_only_2r_rows=sum(x["optimistic_pivot_2r_only"] for x in rows),
        provider_consensus_complete=False,real_five_day_forward_trades=0,
        full_market_point_in_time_selection=False,
        final_80_point_certification=False,
        independently_verified_market_price_count=0,
        auto_orders_permitted=False,trade_approved=False,orders_enabled=False,
        decision="CASH",
        source_notes="Research-only. No post-signal bars determine pivot/cluster levels, and a distant pivot never overrides closer wick friction.")

def mobile(r,rows):
    lines=["# v6.1 무료 지지·저항 증거강도 비교 (2026-10-23 기준 과거 재생)","",
      f"**결론: {r['decision']}, 신규매수 승인 0**",
      "기존 하루 고가(가까운 저항) / 좌우 2봉으로 확인된 스윙 고점 / 2개 이상의 피벗 군집을 분리했습니다.",
      "스윙 고점이 더 멀리 있다고 바로 그 가격을 목표로 승인하지 않습니다. 가까운 저항을 먼저 통과해야 합니다.",
      "모든 결과는 23일에 뽑힌 종목을 과거로 되돌린 탐색이며, 정규장 세션·미래 매매성과를 인증하지 않습니다.",
      "",
      "| 전략 | 연구 진입안 | 평가행 | 2봉 확인 피벗 있음 | 피벗 기준 2R만 통과 | 가까운 저항 기준 2R |",
      "|---|---|---:|---:|---:|---:|"]
    for m in METHODS:
        for v in MODES:
            ss=[x for x in rows if x["method"]==m and x["variant"]==v]
            lines.append(f"| {m} | {v} | {len(ss)} | "+
              f"{sum(x['confirmed_pivot_resistance'] is not None for x in ss)} | "+
              f"{sum(x['optimistic_pivot_2r_only'] for x in ss)} | "+
              f"{sum(x['conservative_2r_pass'] for x in ss)} |")
    lines +=["",f"**먼 피벗만 놓고는 2R 이상이지만 가까운 저항 때문에 탈락: {r['pivot_only_2r_rows']}건**.",
      "이 숫자는 추천종목 수가 아니며, 매수가에 맞는 가까운 저항을 제거하지 않은 것이 핵심입니다.",
      "", "## Required Next Data",
      "정규장 09:00–15:30 독립 OHLC, 거래소 일봉·수정주가 규칙, 10월 26일 이후 실거래일 신규 자료, 날짜별 전체시장 PIT 종목선정, 계좌체결·가용현금.",
      ""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--recovery",type=Path,required=True)
    p.add_argument("--v59",type=Path,required=True)
    p.add_argument("--v60",type=Path,required=True)
    p.add_argument("--asof",required=True)
    p.add_argument("--outdir",type=Path,required=True)
    a=p.parse_args()
    try:asof=date.fromisoformat(a.asof)
    except ValueError:raise SystemExit("INVALID_ASOF")
    status=safe_json(a.v60/"entry_fill_frontier_v60_status.json")
    older=safe_json(a.v59/"shadow_v59_status.json")
    if (status.get("schema")!="C3_K100_FIXED_ENTRY_FILL_FRONTIER_V60"
        or status.get("asof")!=str(asof)
        or status.get("trade_approved") is not False
        or status.get("orders_enabled") is not False
        or status.get("nearest_overhead_resistance_recomputed_for_each_limit_from_past_only") is not True
        or older.get("schema")!="C3_K100_FIVE_DAY_SHADOW_V59"
        or older.get("asof")!=str(asof)
        or older.get("nearest_overhead_target_recomputed_for_each_entry_variant") is not True
        or older.get("trade_approved") is not False
        or older.get("orders_enabled") is not False):
        raise SystemExit("V59_V60_IMMUTABLE_DATED_PROVENANCE_REQUIRED")
    v59_rows=rows(a.v59/"shadow_v59_all.csv")
    v60_rows=rows(a.v60/"entry_fill_frontier_v60_all.csv")
    if (len(v59_rows)!=older.get("total_simulated_alternative_scenarios")
        or len(v60_rows)!=status.get("research_rows")
        or len(v59_rows)!=392 or len(v60_rows)!=980):
        raise SystemExit("TRUNCATED_ASOF_ENTRY_EVIDENCE")
    result,diag=build(a.recovery,v59_rows,v60_rows,asof)
    summary=summarize(result,diag,asof)
    if summary["original_research_signals"]!=status.get("research_signals"):
        raise SystemExit("V60_SIGNAL_COUNT_DIVERGES")
    a.outdir.mkdir(parents=True,exist_ok=True)
    (a.outdir/"resistance_tiers_v61_status.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (a.outdir/"resistance_tiers_v61_all.csv").open(
        "w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=COLUMNS,extrasaction="ignore")
        w.writeheader();w.writerows(result)
    (a.outdir/"resistance_tiers_v61_mobile.md").write_text(
        mobile(summary,result)+"\n",encoding="utf-8")
    print(json.dumps({k:summary[k] for k in
        ("asof","original_research_signals","evaluated_entry_rows",
         "nearest_2r_rows","pivot_only_2r_rows","decision")},ensure_ascii=False))

if __name__=="__main__":main()
