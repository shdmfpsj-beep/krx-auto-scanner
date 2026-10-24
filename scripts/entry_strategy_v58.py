#!/usr/bin/env python3
"""Free v5.8 completed-day three-method entry research, strictly no orders.

Technical entries are hypothetical next-session *conditions*, not fills. Uses
at most the dated market candles. Never averages down a filled C3 position.
A second level is an ALTERNATIVE limit if first never filled. All output is
research-only until separate regular-session, issuer, financial, score and
account gates pass. No conditional BUY authority exists in this module.
"""
from __future__ import annotations
import argparse,csv,json,math
from collections import defaultdict,Counter
from datetime import date
from pathlib import Path
from free_structural_v52 import history_check,atr14,last_confirmed_pivot
from first_pullback_v55 import hma60,confirmed_turn,phase,up,down,net_reward_risk

VERSION="C3_K100_FREE_ENTRY_V58"
COST_PCT=0.5
MIN_RR=2.0
METHODS=("FIRST_PULLBACK_RECLAIM","BREAKOUT_RETEST","TREND_PULLBACK")
EXCLUSION_KEYWORDS=("바이오","제약","PHARMA","BIOTECH")
FIELDS=("asof","ticker","name","method","setup","signal_condition",
        "asof_close_research","atr14","daily_pivot_date","daily_pivot_low",
        "stop_reference","first_entry_reference","second_entry_reference",
        "second_entry_policy","nearest_resistance_reference",
        "first_stop_risk_pct","second_stop_risk_pct",
        "first_entry_below_close_atr","first_entry_timing",
        "first_net_rr","second_net_rr","first_rr_2r_pass","second_rr_2r_pass",
        "technical_research_ready","source_category","price_source_status",
        "blocking_reasons","trade_approved","orders_enabled")

def rows(path):
    path=Path(path)
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def safe_json(path):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError,OSError,TypeError):return {}

def mean(vals):
    return sum(vals)/len(vals)

def prev_ma(bars,lookback,end=None):
    stop=len(bars) if end is None else end
    return mean([r["close"] for r in bars[stop-lookback:stop]])

def confirmed_pivots(bars,lookback=35):
    """Two fully completed bars to the right, and no subsequent lower low."""
    end=len(bars)-1
    found=[]
    for i in range(max(2,end-lookback),end-1):
        low=bars[i]["low"]
        if (low<bars[i-1]["low"] and low<bars[i-2]["low"]
            and low<=bars[i+1]["low"] and low<=bars[i+2]["low"]
            and all(r["low"]>=low for r in bars[i+1:])):
            found.append((i,low))
    return found

def first_pullback(bars,atr):
    h=hma60([r["close"] for r in bars])
    if h[-1] is None:return None
    idx=confirmed_turn(h)
    if idx is None or phase(bars,h,atr,idx)!="FIRST_PULLBACK_RECLAIM":
        return None
    return dict(method="FIRST_PULLBACK_RECLAIM",
        signal_condition="ASOF_CLOSE_RECLAIMS_PREVIOUS_DAILY_HIGH_AFTER_FIRST_PULLBACK",
        first_hint=bars[-1]["close"],support_hint=None)

def breakout_retest(bars,atr):
    """Pre-existing 20d high breakout followed by observed retest and reclaim."""
    n=len(bars)
    for j in range(n-3,max(22,n-13)-1,-1):
        prior=max(x["high"] for x in bars[j-20:j])
        if bars[j]["close"]<=prior or bars[j-1]["close"]>prior:
            continue
        retested=any(
            bars[k]["low"]<=prior+0.20*atr and
            bars[k]["close"]>=prior-0.25*atr
            for k in range(j+1,n-1))
        if (retested and bars[-1]["close"]>prior and
            bars[-1]["close"]>bars[-2]["high"] and
            bars[-1]["close"]<=prior+1.5*atr):
            return dict(method="BREAKOUT_RETEST",
                signal_condition="COMPLETED_BREAKOUT_RETEST_AND_CLOSE_ABOVE_PREVIOUS_HIGH",
                first_hint=min(bars[-1]["close"],prior+0.2*atr),
                support_hint=prior)
    return None

def trend_pullback(bars,atr):
    """20MA above 60MA, rising, then actual prior-bar support touch/rebound."""
    if len(bars)<80:return None
    ma20=prev_ma(bars,20);ma60=prev_ma(bars,60)
    ma20_5=prev_ma(bars,20,len(bars)-5)
    if not(ma20>ma60 and ma20>ma20_5 and bars[-1]["close"]>ma20):
        return None
    touched=False
    for j in range(len(bars)-5,len(bars)-1):
        ma_at_j=prev_ma(bars,20,j+1)
        if bars[j]["low"]<=ma_at_j+0.20*atr and bars[j]["close"]>=ma_at_j-0.40*atr:
            touched=True
            break
    if not touched or bars[-1]["close"]<=bars[-2]["high"]:
        return None
    return dict(method="TREND_PULLBACK",
        signal_condition="MA20_ABOVE_MA60_AND_RISING_WITH_PRIOR_PULLBACK_AND_RECLAIM",
        first_hint=min(bars[-1]["close"],ma20+0.20*atr),
        support_hint=ma20)

def choose_second(bars,first,stop,atr,pivots):
    """Only historical confirmed daily pivots, not an unconfirmed MA proxy."""
    eligible=[]
    for i,low in pivots:
        level=up(low+0.15*atr)
        if (level and stop+0.30*atr<level<=first-0.50*atr
            and i<=len(bars)-3):
            eligible.append((i,level,low))
    if not eligible:return None,"NO_CONFIRMED_SEPARATE_SECOND_SUPPORT"
    # Prefer latest proven pivot, never invent an intermediate price.
    _,value,_=max(eligible,key=lambda t:t[0])
    return value,"ALTERNATIVE_LIMIT_IF_FIRST_NOT_FILLED_NO_AVERAGING_DOWN"

def nearest_ceiling(bars,first):
    # Real, completed bars only. Nearest overhead friction, not remote 60d high.
    levels=[x["high"] for x in bars[-61:-1] if x["high"]>first]
    return down(min(levels)) if levels else None

def price_gate(asof,forensics):
    """Fail closed even when all source closes match: shared provider != independent."""
    p=forensics if isinstance(forensics,dict) else {}
    if p.get("schema")!="free_krx_regular_source_forensics_v57":
        return {},["DATED_FULL_V57_SOURCE_FORENSICS_MISSING"]
    if p.get("asof")!=str(asof) or p.get("diagnosis_valid") is not True:
        return {},["SOURCE_FORENSICS_DATE_OR_INTEGRITY_INVALID"]
    values=p.get("comparisons")
    if not isinstance(values,list) or len(values)!=p.get("total_rows"):
        return {},["FULL_PRICE_COMPARISON_ROWS_MISSING"]
    index={}
    for r in values:
        t=r.get("ticker") if isinstance(r,dict) else None
        if not isinstance(t,str) or len(t)!=6 or not t.isdigit() or t in index:
            return {},["DUPLICATE_OR_MALFORMED_PRICE_PAIR"]
        index[t]=r
    if (sum(r.get("close_equal") is False for r in index.values())
        !=p.get("mismatches")):
        return {},["PRICE_PAIR_MISMATCH_COUNT_INVALID"]
    if p.get("trade_approved") is not False or p.get("orders_enabled") is not False:
        return {},["PRICE_FORENSICS_UNSAFE_ORDER_FLAG"]
    return index,[]

def base_row(asof,candidate,method):
    return dict(asof=str(asof),ticker=str(candidate.get("ticker","")).strip(),
        name=str(candidate.get("name","")),
        method=method,setup="UNVERIFIED",signal_condition="",
        asof_close_research=None,atr14=None,daily_pivot_date=None,
        daily_pivot_low=None,stop_reference=None,
        first_entry_reference=None,second_entry_reference=None,
        second_entry_policy="UNCONFIRMED_NOT_A_BUY",
        nearest_resistance_reference=None,
        first_stop_risk_pct=None,second_stop_risk_pct=None,
        first_entry_below_close_atr=None,
        first_entry_timing="NO_VALID_FIRST_ENTRY",
        first_net_rr=None,second_net_rr=None,
        first_rr_2r_pass=False,second_rr_2r_pass=False,
        technical_research_ready=False,source_category="NOT_PAIRED",
        price_source_status="NOT_SESSION_CERTIFIED",
        blocking_reasons=[],trade_approved=False,orders_enabled=False)

def evaluate(candidate,history,asof,method,paired=None):
    out=base_row(asof,candidate,method)
    ticker=out["ticker"]
    reasons=[]
    if str(candidate.get("latest_date"))!=str(asof):
        reasons.append("CANDIDATE_DATE_MISMATCH")
    instrument=str(candidate.get("instrument_type") or "")
    if instrument not in ("COMMON","COMMON_STOCK"):
        reasons.append("COMMON_SHARE_TYPE_UNVERIFIED_OR_SPECIAL")
    if candidate.get("turnover_source")!="SOURCE_REPORTED":
        reasons.append("ACTUAL_TRADED_VALUE_MISSING")
    if any(k in out["name"].upper() for k in EXCLUSION_KEYWORDS):
        reasons.append("BIO_PHARMA_EXCLUDED")
    if not isinstance(paired,dict):
        reasons.append("NO_EXACT_DATED_SOURCE_PAIR")
    else:
        out["source_category"]=paired.get("category","UNKNOWN")
        if paired.get("close_equal") is not True:
            reasons.append("CROSS_SOURCE_CLOSE_MISMATCH")
        if paired.get("category")!="OHLC_EXACT_MATCH_UNCERTIFIED":
            reasons.append("OHLC_SOURCE_GEOMETRY_CONFLICT")
        # This NEVER certifies order levels, even on exact-match rows.
        reasons.append("KRX_REGULAR_ONLY_HISTORY_NOT_INDEPENDENTLY_CERTIFIED")
    bars,error=history_check(history,ticker,asof)
    if error:
        out.update(setup="DATA_PENDING",blocking_reasons=list(dict.fromkeys(reasons+[error])))
        return out
    close=bars[-1]["close"]
    try:candidate_close=float(candidate.get("close"))
    except (ValueError,TypeError):candidate_close=None
    if (candidate_close is None or not math.isfinite(candidate_close)
        or candidate_close<=0 or candidate_close!=close
        or candidate.get("data_source")!=bars[-1]["source"]):
        out.update(setup="DATA_PENDING",
            blocking_reasons=list(dict.fromkeys(reasons+["CANDIDATE_HISTORY_PRICE_OR_PROVIDER_MISMATCH"])))
        return out
    atr=atr14(bars)
    out["asof_close_research"]=close
    out["atr14"]=round(atr,2)
    setups={"FIRST_PULLBACK_RECLAIM":first_pullback,
            "BREAKOUT_RETEST":breakout_retest,
            "TREND_PULLBACK":trend_pullback}
    setup=setups[method](bars,atr)
    if setup is None:
        out.update(setup="NO_CONFIRMED_SETUP",
            blocking_reasons=list(dict.fromkeys(reasons+["METHOD_TRIGGER_NOT_CONFIRMED"])))
        return out
    out["setup"]="RESEARCH_TRIGGER_CONFIRMED_ASOF"
    out["signal_condition"]=setup["signal_condition"]
    pivot_day,pivot_low=last_confirmed_pivot(bars)
    if pivot_low is None:
        out["blocking_reasons"]=list(dict.fromkeys(reasons+["NO_CONFIRMED_DAILY_STRUCTURE_STOP"]))
        return out
    stop=down(pivot_low-max(.25*atr,.003*close))
    if not stop or stop<=0:
        out["blocking_reasons"]=list(dict.fromkeys(reasons+["INVALID_STRUCTURE_STOP"]))
        return out
    out["daily_pivot_date"]=pivot_day.isoformat()
    out["daily_pivot_low"]=round(pivot_low,2)
    out["stop_reference"]=stop
    first=up(setup["first_hint"])
    if not first or first<=stop or first>close+0.03*atr:
        out["blocking_reasons"]=list(dict.fromkeys(reasons+["FIRST_LIMIT_NOT_ABOVE_STOP_OR_CHASE_CAP"]))
        return out
    out["first_entry_reference"]=first
    distance_atr=(close-first)/atr
    out["first_entry_below_close_atr"]=round(distance_atr,3)
    out["first_entry_timing"]=(
        "WAIT_DEEP_PULLBACK_NO_CHASE" if distance_atr>1 else
        "CONDITIONAL_LIMIT_NOT_ORDER")
    if distance_atr>1:
        reasons.append("FIRST_ENTRY_MORE_THAN_1_ATR_BELOW_ASOF_CLOSE")
    out["first_stop_risk_pct"]=round(100*(first-stop)/first,3)
    if not 2<=out["first_stop_risk_pct"]<=12:
        reasons.append("FIRST_ENTRY_STRUCTURAL_RISK_OUT_OF_2_TO_12_PCT")
    pivots=confirmed_pivots(bars)
    second,policy=choose_second(bars,first,stop,atr,pivots)
    out["second_entry_policy"]=policy
    if second is not None:
        out["second_entry_reference"]=second
        out["second_stop_risk_pct"]=round(100*(second-stop)/second,3)
        if not 1<=out["second_stop_risk_pct"]<=12:
            reasons.append("SECOND_ENTRY_STRUCTURAL_RISK_OUT_OF_1_TO_12_PCT")
    else:
        reasons.append("NO_VALID_SECOND_ENTRY_SUPPORT")
    ceiling=nearest_ceiling(bars,first)
    if ceiling is None or ceiling<=first:
        reasons.append("NO_VERIFIED_NEARBY_OVERHEAD_RESISTANCE")
    else:
        out["nearest_resistance_reference"]=ceiling
        rr1=net_reward_risk(first,stop,ceiling,COST_PCT)
        if rr1 is not None:
            out["first_net_rr"]=round(rr1,3)
            out["first_rr_2r_pass"]=rr1>=MIN_RR
        if second is not None:
            rr2=net_reward_risk(second,stop,ceiling,COST_PCT)
            if rr2 is not None:
                out["second_net_rr"]=round(rr2,3)
                out["second_rr_2r_pass"]=rr2>=MIN_RR
        if not out["first_rr_2r_pass"]:reasons.append("FIRST_COST_ADJUSTED_RR_BELOW_2")
        if second is not None and not out["second_rr_2r_pass"]:
            reasons.append("SECOND_COST_ADJUSTED_RR_BELOW_2")
    # Distinguish a geometric opportunity from a real executable BUY.
    technical=(out["first_rr_2r_pass"]
       and 2<=out["first_stop_risk_pct"]<=12
       and distance_atr<=1
       and out["second_entry_reference"] is not None
       and out["second_rr_2r_pass"]
       and 1<=out["second_stop_risk_pct"]<=12)
    out["technical_research_ready"]=technical
    out["blocking_reasons"]=list(dict.fromkeys(reasons+[
        "FINAL_80_SCORE_UNVERIFIED","SECTOR_MARKET_CAPITAL_GATE_PENDING",
        "EXECUTION_PRICE_NOT_VERIFIED"]))
    return out

def build(status,candidates,histories,forensics,asof):
    errors=[]
    if status.get("market_data_date")!=str(asof):
        errors.append("RECOVERY_STATUS_ASOF_MISMATCH")
    if status.get("scan_complete") is not True or status.get("data_date_verified") is not True:
        errors.append("INCOMPLETE_MARKET_SCANNER")
    try:coverage=float(status.get("coverage_ratio"))
    except (ValueError,TypeError):coverage=0
    if not math.isfinite(coverage) or coverage<0.95:
        errors.append("MARKET_COVERAGE_BELOW_95")
    index,issues=price_gate(asof,forensics)
    errors.extend(issues)
    grouped=defaultdict(list)
    for r in histories:
        grouped[str(r.get("ticker","")).strip().zfill(6)].append(r)
    result=[]
    for candidate in candidates:
        ticker=str(candidate.get("ticker","")).strip()
        for method in METHODS:
            result.append(evaluate(candidate,grouped.get(ticker,[]),asof,method,
                                   index.get(ticker) if not issues else None))
    phases=Counter((x["method"],x["setup"]) for x in result)
    triggers={method:sum(x["method"]==method and
        x["setup"]=="RESEARCH_TRIGGER_CONFIRMED_ASOF" for x in result)
        for method in METHODS}
    technically_ready=sorted((x for x in result if x["technical_research_ready"]),
        key=lambda x:(-min(x["first_net_rr"],x["second_net_rr"]),x["ticker"],x["method"]))
    # Technical research is not price-quality, earnings, 80-point, account or BUY.
    # Even a "perfect" technical score is NEVER promoted to executable orders.
    quality_ready=[x for x in technically_ready if not any(
        b in x["blocking_reasons"] for b in
        ("CROSS_SOURCE_CLOSE_MISMATCH","OHLC_SOURCE_GEOMETRY_CONFLICT",
         "COMMON_SHARE_TYPE_UNVERIFIED_OR_SPECIAL","ACTUAL_TRADED_VALUE_MISSING",
         "BIO_PHARMA_EXCLUDED","NO_EXACT_DATED_SOURCE_PAIR"))]
    if errors:quality_ready=[]
    triggered=[x for x in result if x["setup"]=="RESEARCH_TRIGGER_CONFIRMED_ASOF"]
    # Diagnostics, not an investable or 80+ stock ranking. Exclude pharma,
    # special issues and named SPACs from the short phone preview, but retain
    # every source row in the archived CSV for technical auditing.
    diagnostic_rows=[x for x in triggered if not any(
        key in x["name"].upper() for key in EXCLUSION_KEYWORDS)
        and "스팩" not in x["name"]]
    diagnostic_rows=sorted(diagnostic_rows,key=lambda x:(
        -(x["first_net_rr"] if isinstance(x["first_net_rr"],(int,float)) else -999),
         x["ticker"],x["method"]))[:8]
    exclusions=Counter(reason for x in triggered for reason in x["blocking_reasons"]
        if reason not in ("FINAL_80_SCORE_UNVERIFIED",
                          "SECTOR_MARKET_CAPITAL_GATE_PENDING",
                          "EXECUTION_PRICE_NOT_VERIFIED"))
    report=dict(schema=VERSION,asof=str(asof),candidates=len(candidates),
        evaluated_method_rows=len(result),source_errors=errors,
        method_trigger_counts=triggers,
        technical_research_ready_count=len(technically_ready),
        quality_preliminary_count=len(quality_ready),
        watch_tickers=list(dict.fromkeys(x["ticker"] for x in quality_ready))[:5],
        completed_signal_diagnostic_rows=diagnostic_rows,
        main_trigger_exclusion_counts=dict(exclusions.most_common(12)),
        first_entry_policy="NEXT_SESSION_CONDITIONAL_NO_CHASE_NOT_A_FILLED_ORDER",
        second_entry_policy="ALTERNATIVE_ONLY_IF_FIRST_NOT_FILLED_NEVER_AVERAGE_DOWN",
        first_entry_rr_threshold=MIN_RR,second_entry_rr_threshold=MIN_RR,
        roundtrip_cost_assumption_pct=COST_PCT,
        regular_only_session_certified=False,
        final_80_score_verified=False,
        orders_enabled=False,trade_approved=False,decision="CASH",
        note="Completed-bar setups with structurally confirmed stops and conditional research entry prices; never backfill future execution.")
    return result,report

def mobile(result,report):
    lines=["# C3·K100 3가지 타점 검토 v5.8","",
       f"**기준일:** {report['asof']}",
       "**매매결정: CASH / 실제 매수승인 0**",
       f"기술 후보: {report['candidates']}개 · 방법별 평가: {report['evaluated_method_rows']}행",
       "1차 미체결 시 2차 대체 진입만 검토. 1차 체결 후 하락 시 물타기 금지.",
       "가격 출처가 완전히 인증되지 않았으므로 아래 가격은 주문가가 아닙니다.",
       "", "| 매매방식 | 23일 확정 조건 |", "|---|---:|"]
    for m in METHODS:lines.append(f"| {m} | {report['method_trigger_counts'][m]} |")
    lines.extend(["","## 가격이 연구조건을 만족한 타점(승인 아님)", "",
      "| 종목·방식 | 손절 | 1차 | 2차 (대체) | 가장 가까운 저항 | 1차 순손익비 | 2차 순손익비 |",
      "|---|---:|---:|---:|---:|---:|---:|"])
    picks=sorted((x for x in result if x["technical_research_ready"]),
        key=lambda x:(-min(x["first_net_rr"],x["second_net_rr"]),x["ticker"]))[:8]
    for p in picks:
        lines.append("| {name}({ticker}) {method} | {stop_reference} | {first_entry_reference} | {second_entry_reference} | {nearest_resistance_reference} | {first_net_rr} | {second_net_rr} |".format(**p))
    if not picks:lines.append("| 충족 종목 없음 | — | — | — | — | — | — |")
    lines.extend(["","## 확정 진입으로 승인되지 않은 신호 진단 (매수 금지)", "",
      "| 종목·방식 | 손절 참고 | 1차 참고 | 2차 대체 참고 | 가까운 저항 | 1차 순손익비 | 판단 |",
      "|---|---:|---:|---:|---:|---:|---|"])
    def fmt(v):return str(v) if v is not None else "미확인"
    for x in report.get("completed_signal_diagnostic_rows",[]):
        reason=next((s for s in x["blocking_reasons"] if s in (
            "CROSS_SOURCE_CLOSE_MISMATCH","NO_VALID_SECOND_ENTRY_SUPPORT",
            "FIRST_COST_ADJUSTED_RR_BELOW_2",
            "FIRST_ENTRY_MORE_THAN_1_ATR_BELOW_ASOF_CLOSE",
            "FIRST_ENTRY_STRUCTURAL_RISK_OUT_OF_2_TO_12_PCT")), "가격·계좌 검증 보류")
        lines.append(f"| {x['name']}({x['ticker']}) {x['method']} | "+
            f"{fmt(x['stop_reference'])} | {fmt(x['first_entry_reference'])} | "+
            f"{fmt(x['second_entry_reference'])} | "+
            f"{fmt(x['nearest_resistance_reference'])} | {fmt(x['first_net_rr'])} | {reason} |")
    if not report.get("completed_signal_diagnostic_rows"):
        lines.append("| 해당 신호 없음 | — | — | — | — | — | — |")
    lines.extend(["","## 주요 탈락 사유 집계", ""])
    for reason,count in report.get("main_trigger_exclusion_counts",{}).items():
        lines.append(f"- {reason}: {count}건")
    lines.extend(["","## 참고: 2차 가격이 유효하지 않은 경우",
        "별도 일봉 피벗, 0.5ATR 이상 진입 간격, 구조손절 위 지지 여부가 미확인되면 미확정으로 표시합니다.",
        "## Required Next Data",
        "- 정규장 독립 가격 출처 · 65일 이상 일봉 · 실측 거래대금",
        "- 업종 수급·확산, 공시·실적, 최종 80점 점수, 계좌 현금·포지션",
        "- 1차/2차 중 선택한 *한 가지* 지정가의 실제 체결 여부(다음 거래일에만 검증)",
        ""])
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--recovery",type=Path,required=True)
    p.add_argument("--forensics",type=Path,required=True)
    p.add_argument("--asof",required=True)
    p.add_argument("--outdir",type=Path,required=True)
    a=p.parse_args()
    try:asof=date.fromisoformat(a.asof)
    except ValueError:raise SystemExit("INVALID_ASOF")
    status=safe_json(a.recovery/"status.json")
    candidates=rows(a.recovery/"candidates.csv")
    histories=rows(a.recovery/"candidate_daily_history_v52.csv")
    result,report=build(status,candidates,histories,safe_json(a.forensics),asof)
    a.outdir.mkdir(parents=True,exist_ok=True)
    (a.outdir/"entry_strategy_v58_status.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (a.outdir/"entry_strategy_v58_all.csv").open(
        "w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore");w.writeheader()
        w.writerows([{**x,"blocking_reasons":";".join(x["blocking_reasons"])} for x in result])
    (a.outdir/"entry_strategy_v58_mobile.md").write_text(mobile(result,report)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("asof","candidates","evaluated_method_rows",
        "method_trigger_counts","technical_research_ready_count",
        "watch_tickers","source_errors","decision")},ensure_ascii=False))
    if report["source_errors"]:raise SystemExit("V58_INPUT_SOURCE_INVALID_CASH")

if __name__=="__main__":main()
