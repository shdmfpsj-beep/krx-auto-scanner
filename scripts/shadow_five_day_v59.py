#!/usr/bin/env python3
"""v5.9 honest 5-session shadow fills for the 2026-10-23 retrospectively selected universe.

NOT a walk-forward KRX-wide performance estimate. Candidate selection was made
on 23 October, BEFORE this old history was replayed. Therefore all historic
trade returns are selection-biased diagnostic and may use after-hours-mixed
PyKRX OHLC. Only fully observed post-signal bars may resolve an exit.
NO broker calls, order placement, probability forecast or BUY authorization.
"""
from __future__ import annotations
import argparse,csv,json,math
from collections import Counter,defaultdict
from datetime import date
from pathlib import Path
from free_structural_v52 import history_check
from entry_strategy_v58 import (METHODS,evaluate,rows,safe_json)

VERSION="C3_K100_FIVE_DAY_SHADOW_V59"
ENTRY_DAYS=2
HOLD_DAYS=5
ROUNDTRIP_COST_PCT=.5
MAX_METHOD_ROWS=20000
DETAIL_FIELDS=("ticker","method","entry_variant","signal_asof",
    "signal_close","signal_first_reference","signal_second_reference",
    "stop_reference","target_reference","signal_first_rr",
    "signal_second_rr","entered_at","entry_date","entry_price",
    "exit_date","exit_price","exit_reason","sessions_held",
    "net_return_pct","net_r","outcome","path_ambiguity",
    "signal_variant_rr","signal_geometric_2r_pass",
    "target_hit_but_net_loss",
    "hypothetical_only","trade_approved")
VALID_EXITS=("STOP","TARGET","TIME_EXIT")

def finite_positive(x):
    try:
        if isinstance(x,bool):return None
        n=float(x)
        return n if math.isfinite(n) and n>0 else None
    except (TypeError,ValueError):return None

def commission_exit(entry,stop,exit_price,cost_pct=ROUNDTRIP_COST_PCT):
    entry=finite_positive(entry);stop=finite_positive(stop)
    exit_price=finite_positive(exit_price)
    if None in (entry,stop,exit_price) or not stop<entry:return None
    if not 0<=cost_pct<=5:return None
    fee=cost_pct/200
    paid=entry*(1+fee)
    sold=exit_price*(1-fee)
    stopped=stop*(1-fee)
    risk=paid-stopped
    if risk<=0:return None
    return (round((sold/paid-1)*100,4),round((sold-paid)/risk,4))

def geometric_two_r_gate(plan,variant):
    """Only risk geometry, NEVER issuer eligibility or buy permission."""
    rr=finite_positive(plan.get("first_net_rr" if variant=="FIRST" else "second_net_rr"))
    risk=finite_positive(plan.get("first_stop_risk_pct" if variant=="FIRST"
                                 else "second_stop_risk_pct"))
    if rr is None or rr<2 or risk is None:return False
    if variant=="FIRST":
        dist=plan.get("first_entry_below_close_atr")
        if not isinstance(dist,(int,float)) or not math.isfinite(dist) or dist>1:
            return False
        return 2<=risk<=12
    return 1<=risk<=12

def blank(plan,variant):
    rr=plan.get("first_net_rr" if variant=="FIRST" else "second_net_rr")
    gate=geometric_two_r_gate(plan,variant)
    return dict(ticker=plan["ticker"],method=plan["method"],
        entry_variant=variant,signal_asof=plan["asof"],
        signal_close=plan.get("asof_close_research"),
        signal_first_reference=plan.get("first_entry_reference"),
        signal_second_reference=plan.get("second_entry_reference"),
        stop_reference=plan.get("stop_reference"),
        target_reference=plan.get("nearest_resistance_reference"),
        signal_first_rr=plan.get("first_net_rr"),
        signal_second_rr=plan.get("second_net_rr"),
        entered_at=None,entry_date=None,entry_price=None,
        exit_date=None,exit_price=None,exit_reason=None,sessions_held=0,
        net_return_pct=None,net_r=None,outcome="UNRESOLVED",
        path_ambiguity=None,signal_variant_rr=rr,
        signal_geometric_2r_pass=gate,target_hit_but_net_loss=False,
        hypothetical_only=True,trade_approved=False)

def simulate(plan,future_bars,variant="FIRST",entry_days=ENTRY_DAYS,hold_days=HOLD_DAYS):
    """Conservative daily OHLC. No same-candle TARGET credit after limit fill.

    Each variant is an alternative *independent* order simulation, never
    simultaneous/averaged-down orders. No full post-signal horizon = pending,
    even when a partial series appears to contain a winner or a stop.
    """
    if variant not in ("FIRST","SECOND"):raise ValueError("INVALID_ENTRY_VARIANT")
    if not 1<=entry_days<=5 or not 1<=hold_days<=20:
        raise ValueError("INVALID_HORIZON")
    r=blank(plan,variant)
    stop=finite_positive(plan.get("stop_reference"))
    limit=finite_positive(plan.get("first_entry_reference" if variant=="FIRST"
                                   else "second_entry_reference"))
    target=finite_positive(plan.get("nearest_resistance_reference"))
    if None in (stop,limit,target) or not 0<stop<limit<target:
        r["outcome"]="INVALID_ENTRY_GEOMETRY"
        return r
    if len(future_bars)<entry_days+hold_days:
        r["outcome"]="PENDING_FULL_FORWARD_HORIZON"
        return r
    # Limit orders expire after at most two next sessions. A 2nd order must
    # be selected in place of 1st; no automatic averaging on a 1st fill.
    idx=None
    for i,bar in enumerate(future_bars[:entry_days]):
        op,high,low=(bar[k] for k in ("open","high","low"))
        if op<=stop:
            r["outcome"]="CANCEL_OPENED_BELOW_STOP"
            return r
        if low<=stop and low>limit:
            r["outcome"]="CANCEL_BROKEN_STOP_BEFORE_ENTRY"
            return r
        if op<=limit:
            idx=i
            entry=op # better fill at open, but never buy below stop.
            r["entered_at"]="OPEN_AT_OR_BELOW_LIMIT"
            break
        if low<=limit<=high:
            idx=i
            entry=limit
            r["entered_at"]="ASSUMED_LIMIT_TOUCH_NO_QUEUE_PROOF"
            break
    if idx is None:
        r["outcome"]="NOT_FILLED_WITHIN_2_SESSIONS"
        return r
    r.update(entry_date=future_bars[idx]["date"].isoformat(),
             entry_price=entry)
    ambiguity=0
    # Entry-day high may have preceded the limit fill. Only credit
    # entry-day TARGET if the position was filled at OPEN, and only if
    # the STOP did not touch; STOP always precedes TARGET on same candle.
    for held in range(hold_days):
        bar=future_bars[idx+held]
        op,lo,hi,cl=(bar[k] for k in ("open","low","high","close"))
        exit_price=None;reason=None;path=None
        if held==0:
            if lo<=stop:
                exit_price=stop
                reason="STOP"
                if hi>=target:path="ENTRY_CANDLE_BOTH_STOP_AND_TARGET_ASSUME_STOP"
            elif hi>=target:
                if r["entered_at"]=="OPEN_AT_OR_BELOW_LIMIT":
                    exit_price=target;reason="TARGET"
                else:
                    ambiguity+=1
                    path="ENTRY_CANDLE_TARGET_TIMING_UNPROVEN_DEFERRED"
        else:
            if op<=stop:
                exit_price=op;reason="STOP_GAP_BELOW_STOP"
            elif lo<=stop:
                exit_price=stop;reason="STOP"
                if hi>=target:path="SAME_BAR_STOP_AND_TARGET_ASSUME_STOP"
            elif op>=target:
                exit_price=target;reason="TARGET_GAP_CAPPED"
            elif hi>=target:
                exit_price=target;reason="TARGET"
        if reason is None and held==hold_days-1:
            exit_price=cl;reason="TIME_EXIT_5TH_SESSION"
        if path:
            r["path_ambiguity"]=path
        if reason is not None:
            p=commission_exit(entry,stop,exit_price)
            if p is None:
                r["outcome"]="INVALID_COST_OR_STOP_GEOMETRY"
                return r
            net_pct,net_r=p
            r.update(exit_date=bar["date"].isoformat(),exit_price=exit_price,
               exit_reason=reason,sessions_held=held+1,
               net_return_pct=net_pct,net_r=net_r,
               target_hit_but_net_loss=(reason.startswith("TARGET") and net_pct<=0),
               outcome=("NET_WIN" if net_pct>0 else "NET_LOSS" if net_pct<0
                        else "NET_FLAT"))
            return r
    raise AssertionError("FIVE_SESSION_EXIT_NOT_RESOLVED")

def signal_rows_for_historic_selected_universe(recovery,asof,min_warmup=80):
    """Research-only: 23 Oct candidate list imposes hindsight selection bias."""
    if not isinstance(asof,date):raise ValueError("ASOF_DATE_REQUIRED")
    status=safe_json(recovery/"status.json")
    candidates=rows(recovery/"candidates.csv")
    history=rows(recovery/"candidate_daily_history_v52.csv")
    issues=[]
    if status.get("market_data_date")!=str(asof):
        issues.append("ARCHIVED_RECOVERY_ASOF_MISMATCH")
    if status.get("scan_complete") is not True or status.get("data_date_verified") is not True:
        issues.append("ARCHIVED_RECOVERY_INCOMPLETE")
    if not candidates or not history:issues.append("CANDIDATE_OR_HISTORY_EMPTY")
    if any(c.get("latest_date")!=str(asof) for c in candidates):
        issues.append("CANDIDATE_PIT_DATE_INCONSISTENT")
    if issues:return [],{},issues
    grouped=defaultdict(list)
    for r in history:grouped[str(r.get("ticker","")).zfill(6)].append(r)
    rejected=Counter()
    histories={}
    for c in candidates:
        ticker=str(c.get("ticker","")).strip()
        converted,error=history_check(grouped.get(ticker,[]),ticker,asof)
        if error:
            rejected[error]+=1
        else:
            histories[ticker]=converted
    return candidates,histories,issues+[f"HISTORY_EXCLUDED_{k}_{v}" for k,v in rejected.items()]

def historical_shadow(candidates,histories,asof,limit=MAX_METHOD_ROWS):
    """Separate comparator for each strategy and each possible entry plan.

    Uses only bars through the signal date to design levels; observes five
    sessions AFTER the signal. An 80-bar warmup leaves ~33 valid signal dates
    per ticker in the 120-bar archive. Dates beyond asof are not used.
    Tickers are hindsight-selected as of asof, so never claim unbiased returns.
    """
    results=[];trigger_counts=Counter()
    historical_signal_days=0;overlapping_skipped=Counter()
    methods=METHODS
    for candidate in candidates:
        ticker=str(candidate.get("ticker","")).strip()
        bars=histories.get(ticker)
        if bars is None:continue
        if bars[-1]["date"]!=asof:
            raise ValueError("HISTORY_NOT_DATE_LOCKED")
        source_rows=[dict(ticker=ticker,date=b["date"].isoformat(),
            open=str(b["open"]),high=str(b["high"]),low=str(b["low"]),
            close=str(b["close"]),volume=str(b["volume"]),
            data_source=b["source"]) for b in bars]
        # Do not let early historical signals see the last 7 bars, ensuring
        # two entry sessions PLUS five holding sessions are available.
        cooldown_until={m:-1 for m in methods}
        for index in range(80,len(bars)-(ENTRY_DAYS+HOLD_DAYS)):
            if bars[index]["date"]>=asof:break
            prefix=source_rows[:index+1]
            mock={**candidate,
                "latest_date":bars[index]["date"].isoformat(),
                "close":str(bars[index]["close"])}
            for method in methods:
                if index<=cooldown_until[method]:
                    overlapping_skipped[method]+=1
                    continue
                plan=evaluate(mock,prefix,bars[index]["date"],method,paired=None)
                if plan["setup"]!="RESEARCH_TRIGGER_CONFIRMED_ASOF":
                    continue
                trigger_counts[method]+=1
                historical_signal_days+=1
                # Each method gets a non-overlapping 7-session signal window.
                # This is NOT a live reconstructed PIT universe/ranking.
                cooldown_until[method]=index+ENTRY_DAYS+HOLD_DAYS-1
                # Forbid counting simulated 'signals' as a trade when stop
                # or reference is invalid; diagnostic rejection is still kept.
                for variant in ("FIRST","SECOND"):
                    r=simulate(plan,bars[index+1:index+1+ENTRY_DAYS+HOLD_DAYS],
                               variant)
                    r["signal_blockers"]=plan["blocking_reasons"]
                    r["signal_technical_research_ready"]=plan["technical_research_ready"]
                    r["hindsight_selected_ticker"]=True
                    r["regular_session_certified"]=False
                    results.append(r)
                    if len(results)>limit:raise ValueError("SHADOW_RESULT_LIMIT_EXCEEDED")
    return results,dict(trigger_counts=dict(trigger_counts),
        historical_signal_days=historical_signal_days,
        cooldown_skipped=dict(overlapping_skipped))

def stats(rows,variant,method,only_geometric_two_r=False):
    subset=[x for x in rows if x["entry_variant"]==variant and x["method"]==method
       and (not only_geometric_two_r or x.get("signal_geometric_2r_pass") is True)]
    n=len(subset)
    filled=[x for x in subset if x["outcome"] in ("NET_WIN","NET_LOSS","NET_FLAT")]
    wins=[x for x in filled if x["outcome"]=="NET_WIN"]
    exits=[x["exit_reason"] for x in filled]
    rets=[x["net_return_pct"] for x in filled]
    return dict(signals=n,filled=len(filled),
        fill_rate_pct=round(100*len(filled)/n,2) if n else None,
        wins=len(wins),
        win_rate_pct=round(100*len(wins)/len(filled),2) if filled else None,
        mean_net_return_pct=round(sum(rets)/len(rets),3) if filled else None,
        median_net_return_pct=(round(sorted(rets)[len(rets)//2],3) if len(rets)%2
          else round((sorted(rets)[len(rets)//2-1]+sorted(rets)[len(rets)//2])/2,3))
          if filled else None,
        stop_exits=sum(x.startswith("STOP") for x in exits),
        target_exits=sum(x.startswith("TARGET") for x in exits),
        time_exits=sum(x.startswith("TIME") for x in exits),
        targets_that_lost_after_cost=sum(x.get("target_hit_but_net_loss") is True for x in filled),
        not_filled=sum(x["outcome"]=="NOT_FILLED_WITHIN_2_SESSIONS" for x in subset),
        pending=sum(x["outcome"]=="PENDING_FULL_FORWARD_HORIZON" for x in subset),
        invalid_count=sum(x["outcome"].startswith(("INVALID","CANCEL")) for x in subset),
        return_is_a_valid_strategy_win_probability=False)

def build_report(candidates,histories,asof,replay,diagnostics,upstream_v58=None,source_errors=None):
    summary=defaultdict(dict)
    two_r=defaultdict(dict)
    for method in METHODS:
        for variant in ("FIRST","SECOND"):
            summary[method][variant]=stats(replay,variant,method)
            two_r[method][variant]=stats(replay,variant,method,only_geometric_two_r=True)
    return dict(schema=VERSION,asof=str(asof),
        universe_selection_date=str(asof),selected_universe_size=len(candidates),
        historical_bars_per_ticker_max=max((len(x) for x in histories.values()),default=0),
        observation_period_start=min((x[0]["date"].isoformat() for x in histories.values()),default=None),
        compared_methods=list(METHODS),
        historical_replay_signals=diagnostics["historical_signal_days"],
        signal_counts=diagnostics["trigger_counts"],
        total_simulated_alternative_scenarios=len(replay),
        stats=summary,geometric_2r_only_stats=two_r,
        target_hit_but_net_loss_total=sum(x.get("target_hit_but_net_loss") is True for x in replay),
        only_geometric_2r_scenarios=sum(x.get("signal_geometric_2r_pass") is True for x in replay),
        # Even the >=2R group is not independent/PIT/session-verified.
        geometric_2r_group_is_validated_win_probability=False,
        source_errors=source_errors or [],
        retrospective_universe_selection_bias=True,
        historical_daily_price_regular_session_certified=False,
        point_in_time_historical_stock_universe_verified=False,
        issuer_and_trading_value_point_in_time_verified=False,
        same_day_low_high_order_unknown=True,
        simulated_order_fill_queue_unverified=True,
        full_history_forward_asof_observed_only=True,
        cost_assumption_roundtrip_pct=ROUNDTRIP_COST_PCT,
        entry_valid_sessions=ENTRY_DAYS,holding_sessions=HOLD_DAYS,
        alternative_entry_not_averaging_down=True,
        validated_live_strategy_trade_count=0,
        trade_approved=False,orders_enabled=False,decision="CASH",
        evidence_level="HINDSIGHT_UNIVERSE_RESEARCH_ONLY_NO_EXPECTED_RETURN_PROOF",
        note="No verified 23 Oct + 5 future days available. Any replay metrics are non-PIT source-uncertified diagnostics, not forecast probabilities.")

def markdown(report):
    lines=["# C3/K100 v5.9 5거래일 모의 체결 연구", "",
      f"**선정 기준일**: {report['asof']}",
      "**최종 실행: CASH / 주문 0건**",
      f"23일 이후 5거래일을 관측한 결과가 아닙니다. 23일 선정된 {report['selected_universe_size']}개 종목의 지난 일봉을 다시 돌린 **선정편향 탐색**입니다.",
      "일봉 정규장 세션 미인증, 날짜별 사전 종목선정 미검증, 체결 대기열 및 장중 고저가 순서 미상.",
      f"왕복비용 {report['cost_assumption_roundtrip_pct']}%, 진입유효 {ENTRY_DAYS}거래일, 매수 후 {HOLD_DAYS}거래일 이내 시간청산.",
      "1차와 2차는 **독립된 대체 시나리오**; 동시에 매수하거나 추가매수하지 않습니다.",
      "",
      "## 구조손절과 비용후 2R 이상인 시나리오만 (여전히 검증 전)",
      "| 전략 | 방식 | 2R 가격조건 충족 | 가정 체결 | 순승률(극소표본 주의) | 순수익 평균 |",
      "|---|---|---:|---:|---:|---:|"]
    for m in METHODS:
        for v in ("FIRST","SECOND"):
            s=report["geometric_2r_only_stats"][m][v]
            rate=(f"{s['win_rate_pct']}%" if s["win_rate_pct"] is not None
                  else "표본 없음")
            ret=(f"{s['mean_net_return_pct']}%" if s["mean_net_return_pct"] is not None
                 else "표본 없음")
            lines.append(f"| {m} | {v} | {s['signals']} | {s['filled']} | {rate} | {ret} |")
    lines.extend(["",
      "## 2R 등 품질 제한 없는 전체 모의 기술 신호 (투자전략 승률 아님)",
      "| 전략 | 방식 | 역사적 신호 | 체결 가정 | 순승률(탐색용) | 평균 순수익(탐색용) |",
      "|---|---|---:|---:|---:|---:|"])
    for m in METHODS:
        for v in ("FIRST","SECOND"):
            s=report["stats"][m][v]
            rate=(f"{s['win_rate_pct']}%" if s["win_rate_pct"] is not None
                  else "표본 없음")
            ret=(f"{s['mean_net_return_pct']}%" if s["mean_net_return_pct"] is not None
                 else "표본 없음")
            lines.append(f"| {m} | {v} | {s['signals']} | {s['filled']} | {rate} | {ret} |")
    lines.extend(["",
      f"**가까운 목표가를 맞혔어도 거래비용 때문에 실제 순손실인 모의 건수: {report['target_hit_but_net_loss_total']}건.**",
      "목표 터치율을 수익 승률로 사용하면 매매성과가 과대평가됩니다.",
      "## 엄격한 실전 평가", "",
      "미통과: 원본 정규장 가격 인증, 당시 전체 종목/상장/퇴출 구성, 실측 거래대금, 시장점수 및 계좌자금 인증.",
      "위 숫자는 실거래 가능 종목의 승률·5일 급등확률·수익보장이 아닙니다.",
      "당일 저가와 고가에 손절·목표가 둘 다 닿으면 **손절 우선** 처리.",
      "매수 체결 시각이 모호한 같은 봉의 목표 도달은 수익으로 인정하지 않음.",
      "갭 하락 시 손절보다 낮은 시가 청산, 갭 상승 시 목표 이상 초과수익은 인정하지 않음.",
      "",
      "## Required Next Data",
      "23일 이후 완료된 정규장 최소 7거래일, 날짜별 당시 전체주식 후보·상장제외 기록, 공식 정규장 분봉 및 거래대금, 매매비용.",
      ""]) 
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--recovery",type=Path,required=True)
    p.add_argument("--entry-report",type=Path,required=True)
    p.add_argument("--asof",required=True)
    p.add_argument("--outdir",type=Path,required=True)
    args=p.parse_args()
    try:asof=date.fromisoformat(args.asof)
    except ValueError:raise SystemExit("ASOF_NOT_VALID")
    source=safe_json(args.entry_report)
    if (source.get("schema")!="C3_K100_FREE_ENTRY_V58"
      or source.get("asof")!=str(asof)
      or source.get("source_errors")!=[]
      or source.get("trade_approved") is not False
      or source.get("orders_enabled") is not False
      or source.get("regular_only_session_certified") is not False):
        raise SystemExit("V58_DATED_SOURCE_INVALID_NO_SHADOW")
    candidates,histories,issues=signal_rows_for_historic_selected_universe(
        args.recovery,asof)
    if not candidates or not histories or any(
        x for x in issues if not x.startswith("HISTORY_EXCLUDED_")):
        raise SystemExit("HISTORICAL_ARCHIVE_INVALID_NO_REPLAY")
    result,diagnostics=historical_shadow(candidates,histories,asof)
    report=build_report(candidates,histories,asof,result,diagnostics,source,issues)
    args.outdir.mkdir(parents=True,exist_ok=True)
    (args.outdir/"shadow_v59_status.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (args.outdir/"shadow_v59_all.csv").open(
            "w",encoding="utf-8-sig",newline="") as f:
        columns=DETAIL_FIELDS+("signal_technical_research_ready",
                               "hindsight_selected_ticker",
                               "regular_session_certified",
                               "signal_blockers")
        w=csv.DictWriter(f,fieldnames=columns,extrasaction="ignore")
        w.writeheader()
        w.writerows([{**r,"signal_blockers":";".join(r.get("signal_blockers",[]))}
                    for r in result])
    (args.outdir/"shadow_v59_mobile.md").write_text(
        markdown(report)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in (
        "asof","selected_universe_size","historical_replay_signals",
        "total_simulated_alternative_scenarios","signal_counts",
        "validated_live_strategy_trade_count","decision")},ensure_ascii=False))

if __name__=="__main__":main()
