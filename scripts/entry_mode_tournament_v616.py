#!/usr/bin/env python3
"""v6.16 as-of entry-mode tournament on frozen v6.15 KRX October observations.

READ-ONLY; compares hypothetical next-session LIMIT, prior-breakout retest,
MA20 pullback, near-close, and conditional opening-price strategies. Identical
5-session stop-first, 0.5% cost, and one-at-a-time shadow portfolio convention.
No extra data after 2026-10-23 or independently verified regular-only market
prices/issuer/PIT/financial/account state. No BUY or brokerage execution.
"""
from __future__ import annotations
import argparse,csv,json,math,statistics
from pathlib import Path
from functools import lru_cache
from collections import Counter,defaultdict
from forward_ledger_v63 import digest,read_csv

SCHEMA="C3_V616_PREDECLARED_ENTRY_TOURNAMENT_READ_ONLY"
PARENT="C3_CONDITIONAL_OPPORTUNITY_FRONTIER_V615"
FEE_PCT=0.5
MODES=("ORIGINAL_LIMIT","BREAKOUT_RETEST_LIMIT","MA20_SUPPORT_LIMIT",
       "NEAR_CLOSE_LIMIT","NEXT_OPEN_GAP_CONDITION")
FIELDS=("asof","ticker","name","pattern","prior_v615_class",
  "mode","asof_close","entry_limit_reference","condition_ceiling_reference",
  "stop_reference","structural_risk_pct","distance_below_close_atr",
  "verified_prior_overhead","net_r_to_overhead",
  "model_two_R_target_unverified","score_rank_only","next_session",
  "future5_complete","next_day_limit_touch_not_broker_fill",
  "shadow_entry_reference","same_day_path_ambiguous",
  "shadow_outcome","shadow_exit_date","shadow_exit_reference","shadow_net_pct",
  "actual_broker_execution_verified","live_trade_approved","orders_enabled")
SUM_FIELDS=("mode","signals_total","unique_ticker_dates","matured_five_day_signals",
   "touch_proxy_events","shadow_stop_events","shadow_target_events",
   "shadow_open_at_day5_events","shadow_average_net_pct","shadow_median_net_pct",
   "shadow_win_proxy_pct","worst_shadow_net_pct",
   "one_slot_entry_decisions","one_slot_fill_proxy_count",
   "one_slot_avg_net_pct","one_slot_win_proxy_pct","one_slot_worst_net_pct",
   "approved_live_buys")

def n(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError):return None

def validate(parent,signals,zipper):
    status=json.loads(Path(parent).read_text(encoding="utf-8"))
    if (status.get("schema")!=PARENT or status.get("source_asof")!="2026-10-23"
        or status.get("sessions")!=15
        or status.get("sha256",{}).get("v615_all_setups.csv")!=digest(Path(signals).read_bytes())
        or status.get("trade_approved") is not False
        or status.get("orders_enabled") is not False
        or status.get("regular_session_only_1530_verified") is not False
        or status.get("strategy_net_profitability_proven") is not False):
        raise ValueError("V616_PARENT_SHA_ASOF_OR_SAFETY_POLICY_INVALID")
    rows=read_csv(Path(signals))
    if len(rows)!=status["unique_event_count"]:
        raise ValueError("V616_PARENT_EVENT_COUNT_CHANGED")
    seen=set()
    for e in rows:
        key=(e["asof"],e["ticker"],e["method"])
        if key in seen or e["asof"]>status["source_asof"]:
            raise ValueError("V616_DUPLICATE_OR_FUTURE_SIGNAL")
        seen.add(key)
        if any(e[k]!="False" for k in ("orders_enabled","trade_approved",
            "regular_1530_price_verified","final80_trade_score_verified")):
            raise ValueError("V616_UPSTREAM_RESEARCH_PROMOTED_TO_BUY")
    if not zipper.is_dir():
        raise ValueError("V616_V18_ARCHIVE_DIRECTORY_MISSING")
    return status,rows

def strategy_levels(e):
    """All setup thresholds fixed from completed signal-day rows ONLY."""
    c=n(e["asof_close"]);a=n(e["atr14"]);stop=n(e["structure_stop_study"])
    ma=n(e["sma20"]);p20=n(e["prior20_high"])
    if any(v is None for v in (c,a,stop,ma,p20)) or not (0<stop<c and a>0):
        return []
    # Overheated/wide signals remain in rejected C observation; never create
    # simulated setup rows with absurd risk. These are NOT live trade gates.
    if (n(e["relative_volume20"]) or 0)<.65 or a/c>.12 or c/ma>1.17:
        return []
    candidates=[("ORIGINAL_LIMIT",n(e["first_limit_study"])),
                ("NEAR_CLOSE_LIMIT",c-.25*a)]
    if ma<c and e["method"] in ("FIRST_MA20_RESUME","EARLY_MA20_RECLAIM"):
        candidates.append(("MA20_SUPPORT_LIMIT",max(ma+.25*a,c-.95*a)))
    if e["method"]=="FRESH_20D_BREAKOUT" and c>p20:
        candidates.append(("BREAKOUT_RETEST_LIMIT",p20+.15*a))
        candidates.append(("NEXT_OPEN_GAP_CONDITION",c))
    result=[]
    for mode,entry in candidates:
        if entry is None or not stop<entry<=c or (c-entry)/a>1.5:
            continue
        risk=100*(entry-stop)/entry
        if not 2<=risk<=12:continue
        head=n(e["nearby_confirmed_overhead"])
        rr=((head-entry-.005*entry)/(entry-stop+.005*entry)
            if head is not None and head>entry else None)
        result.append(dict(asof=e["asof"],ticker=e["ticker"],name=e["name"],
            pattern=e["method"],prior_v615_class=e["classification"],
            mode=mode,asof_close=round(c,3),
            entry_limit_reference=round(entry,3),
            condition_ceiling_reference=round(c+.25*a,3) if mode=="NEXT_OPEN_GAP_CONDITION" else "",
            stop_reference=round(stop,3),structural_risk_pct=round(risk,3),
            distance_below_close_atr=round((c-entry)/a,3),
            verified_prior_overhead=round(head,3) if head else "",
            net_r_to_overhead=round(rr,3) if rr is not None else "",
            model_two_R_target_unverified=round(
                entry+2*(entry-stop+.005*entry)+.005*entry,3),
            score_rank_only=n(e["discovery_index_only"]) or 0,
            next_session="",future5_complete=False,
            next_day_limit_touch_not_broker_fill=False,
            shadow_entry_reference="",same_day_path_ambiguous=False,
            shadow_outcome="NO_FUTURE_FIVE_SESSIONS",shadow_exit_date="",
            shadow_exit_reference="",shadow_net_pct="",
            actual_broker_execution_verified=False,
            live_trade_approved=False,orders_enabled=False))
    return result

def simulate(row,future):
    """Daily OHLC cannot prove filled orders. Pessimistic stop before target.

    Exactly next first session must touch resting limit OR its OPEN satisfies
    predeclared gap window; no intraday path assumed. If same day touches both
    stop and target, stop first. No day-one target claim from unknowable order.
    """
    out=dict(row)
    if len(future)<5:return out
    first=future[0]
    if first["Date"]<=out["asof"] or any(a["Date"]>=b["Date"] for a,b in zip(future,future[1:])):
        raise ValueError("V616_FORWARD_DATE_ORDER_INVALID")
    out["future5_complete"]=True
    stop=float(out["stop_reference"]);prior=float(out["entry_limit_reference"])
    if out["mode"]=="NEXT_OPEN_GAP_CONDITION":
        op=float(first["Open"])
        touched=prior<=op<=float(out["condition_ceiling_reference"])
        entry=op
    else:
        touched=float(first["Low"])<=prior
        entry=prior
    out["next_day_limit_touch_not_broker_fill"]=touched
    if not touched:
        out["shadow_outcome"]="MISSED_FIRST_SESSION_ENTRY"
        return out
    if not (0<stop<entry):
        out["shadow_outcome"]="STOP_BROKEN_BEFORE_VALID_ORDER"
        return out
    if float(first["Open"])<=stop:
        out["shadow_outcome"]="OPEN_BELOW_STRUCTURE_STOP_NO_ORDER"
        return out
    out["shadow_entry_reference"]=round(entry,3)
    out["same_day_path_ambiguous"]=out["mode"]!="NEXT_OPEN_GAP_CONDITION"
    risk=100*(entry-stop)/entry
    if not 2<=risk<=12:
        out["shadow_outcome"]="NEXT_OPEN_RISK_EXPANDED"
        out["shadow_entry_reference"]=""
        return out
    target=entry+2*(entry-stop+.005*entry)+.005*entry
    outcome="FIVE_DAY_CLOSE_PROXY"
    sell=float(future[-1]["Close"]);exitday=future[-1]["Date"]
    for idx,bar in enumerate(future):
        low=float(bar["Low"]);high=float(bar["High"]);op=float(bar["Open"])
        if low<=stop:
            outcome="STOP_FIRST_AMBIGUOUS_PRICE_PATH"
            sell=min(op,stop) if idx>0 else stop
            exitday=bar["Date"];break
        if idx>0 and high>=target:
            outcome="TWO_R_TARGET_PROXY";sell=target;exitday=bar["Date"];break
    out.update(shadow_outcome=outcome,shadow_exit_date=exitday,
       shadow_exit_reference=round(sell,3),
       shadow_net_pct=round(100*(sell/entry-1)-FEE_PCT,3))
    return out

def summarize(rows,dates):
    table=[];portfolios={}
    for mode in MODES:
        observed=[r for r in rows if r["mode"]==mode]
        mature=[r for r in observed if r["future5_complete"]]
        evaluated=[r for r in mature if r["shadow_net_pct"]!=""]
        nums=[float(r["shadow_net_pct"]) for r in evaluated]
        slots=[];lock="";single={}
        for day in dates:
            if lock and day<=lock:continue
            pool=sorted([r for r in observed if r["asof"]==day],
                key=lambda r:(-r["score_rank_only"],r["structural_risk_pct"],r["ticker"]))
            if not pool:continue
            one=pool[0];slots.append(one)
            if one["shadow_net_pct"]!="" and one["next_day_limit_touch_not_broker_fill"]:
                lock=one["shadow_exit_date"]
        slotnum=[float(r["shadow_net_pct"]) for r in slots if r["shadow_net_pct"]!=""]
        portfolios[mode]=slots
        table.append(dict(mode=mode,signals_total=len(observed),
            unique_ticker_dates=len(set((e["asof"],e["ticker"]) for e in observed)),
            matured_five_day_signals=len(mature),
            touch_proxy_events=sum(x["next_day_limit_touch_not_broker_fill"] for x in mature),
            shadow_stop_events=sum(x["shadow_outcome"].startswith("STOP_FIRST") for x in evaluated),
            shadow_target_events=sum(x["shadow_outcome"]=="TWO_R_TARGET_PROXY" for x in evaluated),
            shadow_open_at_day5_events=sum(x["shadow_outcome"]=="FIVE_DAY_CLOSE_PROXY" for x in evaluated),
            shadow_average_net_pct=round(statistics.mean(nums),3) if nums else "",
            shadow_median_net_pct=round(statistics.median(nums),3) if nums else "",
            shadow_win_proxy_pct=round(100*sum(x>0 for x in nums)/len(nums),2) if nums else "",
            worst_shadow_net_pct=round(min(nums),3) if nums else "",
            one_slot_entry_decisions=len(slots),
            one_slot_fill_proxy_count=len(slotnum),
            one_slot_avg_net_pct=round(statistics.mean(slotnum),3) if slotnum else "",
            one_slot_win_proxy_pct=round(100*sum(x>0 for x in slotnum)/len(slotnum),2) if slotnum else "",
            one_slot_worst_net_pct=round(min(slotnum),3) if slotnum else "",
            approved_live_buys=0))
    return table,portfolios

def calculate(v18,meta,signals):
    parent,raw=validate(meta,signals,v18)
    bypair=defaultdict(list)
    for e in raw:bypair[(e["asof"],e["ticker"])].append(e)
    # One signal per ticker/date prevents double-counting correlated patterns.
    pattern_priority={"FRESH_20D_BREAKOUT":0,"FIRST_MA20_RESUME":1,
                      "EARLY_MA20_RECLAIM":2}
    chosen=[sorted(group,key=lambda r:(pattern_priority[r["method"]],
        -float(r["discovery_index_only"])))[0] for group in bypair.values()]
    chosen.sort(key=lambda r:(r["asof"],r["ticker"]))
    days=sorted(set(e["asof"] for e in raw))
    if len(days)!=15 or days[0]!="2026-10-01" or days[-1]!="2026-10-23":
        raise ValueError("V616_PARENT_OCTOBER_DATES_BAD")
    @lru_cache(maxsize=3500)
    def hist(ticker):
        p=v18/"market/prices"/(ticker+".csv")
        if not p.is_file():raise ValueError("V616_MISSING_PRICE_ARCHIVE")
        data=read_csv(p)
        if len(data)<120 or any(a["Date"]>=b["Date"] for a,b in zip(data,data[1:])):
            raise ValueError("V616_HISTORICAL_ORDER_INVALID")
        return data
    results=[]
    for e in chosen:
        history=hist(e["ticker"])
        asof_rows=[b for b in history if b["Date"]==e["asof"]]
        if len(asof_rows)!=1 or float(asof_rows[0]["Close"])!=float(e["asof_close"]):
            raise ValueError("V616_V615_V18_CLOSING_PRICE_PARITY_FAILED")
        future=[b for b in history if e["asof"]<b["Date"]<=parent["source_asof"]][:5]
        for plan in strategy_levels(e):
            nextday=next((d for d in days if d>e["asof"]), "")
            plan["next_session"]=nextday
            results.append(simulate(plan,future))
    summary,slots=summarize(results,days)
    status=dict(schema=SCHEMA,source_asof=parent["source_asof"],
       parent_unchanged_SHA256=digest(Path(meta).read_bytes()),
       parent_signal_sha256=digest(Path(signals).read_bytes()),
       predeclared_modes=list(MODES),daily_price_source_last_day="2026-10-23",
       event_signals_raw_v615=len(raw),ticker_date_dedup_input=len(chosen),
       study_candidates=len(results),completed_five_session_upper_bound=
           sum(x["future5_complete"] for x in results),
       real_regular_only_session_PIT_verified=False,
       broker_order_placed_or_confirmed=False,
       account_available_cash_verified=False,
       fee_round_trip_pct=FEE_PCT,
       same_day_stop_conservative=True,
       bar_touch_is_not_execution=True,
       independent_per_trade_profits_unverified=True,
       study_2R_target_is_not_verified_resistance=True,
       no_live_BUY_score_gate_waived=True,
       K100_not_traded=True,C3_one_slot_shadow_separate_from_broker=True,
       trade_approved=False,orders_enabled=False,
       decision="RESEARCH_ONLY_CASH_UNTIL_LIVE_GATES")
    return status,summary,results,slots

def save(out,status,summary,results,slots):
    out.mkdir(parents=True,exist_ok=True)
    for name,fields,rows in (
        ("v616_all_entry_modes.csv",FIELDS,results),
        ("v616_mode_comparison.csv",SUM_FIELDS,summary),
        ("v616_one_slot_scenarios.csv",FIELDS,
          [q for xs in slots.values() for q in xs])):
        p=out/name
        with p.open("w",newline="",encoding="utf-8-sig") as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction="raise")
            w.writeheader();w.writerows(rows)
    status["artifacts_sha256"]={name:digest((out/name).read_bytes()) for name in (
        "v616_all_entry_modes.csv","v616_mode_comparison.csv","v616_one_slot_scenarios.csv")}
    (out/"v616_status.json").write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# C3 v6.16 · 초기 돌파 / 첫 눌림 5거래일 지정가 비교","",
       "기준 2026-10-23 일봉까지의 소급 연구. 실거래 자동주문 0건, 정규장-only/당시주권·원문재무/키움 계좌 미검증.",
       "계좌는 한 번에 한 종목만 보유하는 가상 포트폴리오; 거래일 중 동일 봉 체결/손절 순서는 확인할 수 없어 보수적 손절 우선.", "",
       "| 방식 | 과거 신호 | 5일 완료 | 진입가격 접촉 | 가상 승률 | 가상 평균순수익 | 1종목 가상체결 | 1종목 평균순수익 |",
       "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in summary:
        lines.append("| {mode} | {signals_total} | {matured_five_day_signals} | {touch_proxy_events} | {shadow_win_proxy_pct} | {shadow_average_net_pct} | {one_slot_fill_proxy_count} | {one_slot_avg_net_pct} |".format(**r))
    lines+=["","**주의:** 평균수익은 0.5% 왕복 비용 및 일봉 가정에 따른 중복/가상 결과다. 실전 성과·상승확률이 아님. 현물 시세나 정규장별 체결 인증이 없다. 1.5R~2R을 실전매수에 적용할 근거가 아님.","",
      "## 10월 23일 최신 완료일 기준 후보 (가격은 10/26 현재 시세가 아닌 역사적 참고가)", "",
      "| 연구모드 | 종목 | 1차 연구가 | 일봉 구조손절 | 연구상 진입 위험% |",
      "|---|---|---:|---:|---:|"]
    latest=[r for r in results if r["asof"]=="2026-10-23"]
    latest.sort(key=lambda r:(-r["score_rank_only"],r["structural_risk_pct"],r["ticker"]))
    seen=set()
    for e in latest:
        if e["ticker"] in seen:continue
        seen.add(e["ticker"])
        lines.append("| {} | {} ({}) | {} | {} | {} |".format(
            e["mode"],e["name"],e["ticker"],e["entry_limit_reference"],
            e["stop_reference"],e["structural_risk_pct"]))
        if len(seen)>=5:break
    if not seen:lines.append("| 해당 없음 | — | — | — | — |")
    lines+=["","**Required Next Data:** 향후 정규장 15:30 분리 시세, 실시간/과거 공시 원문, 거래소 과거 주권 종류, 키움 체결과 현금, 5일 이상 미래 독립검증 표본.",
      "**매수 지시가 아닙니다.** 신호 출현빈도에 맞춰 BUY를 강제로 만들지 않습니다."]
    (out/"v616_mobile.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--v18",required=True,type=Path)
    p.add_argument("--parent",required=True,type=Path)
    p.add_argument("--signals",required=True,type=Path)
    p.add_argument("--outdir",required=True,type=Path)
    a=p.parse_args()
    status,summary,results,slots=calculate(a.v18,a.parent,a.signals)
    save(a.outdir,status,summary,results,slots)
    print("V616_TOURNAMENT",json.dumps(status,ensure_ascii=False),flush=True)
    for row in summary:print("V616_MODE",json.dumps(row,ensure_ascii=False),flush=True)

if __name__=="__main__":main()
