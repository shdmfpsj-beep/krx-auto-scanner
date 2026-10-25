#!/usr/bin/env python3
"""v6.13 dated Top20 entry-readiness proof: first 2R independently from 2nd.

Pure read-only as-of signal/structure diagnostic. The first valid limit price
does NOT require a second alternative (which must never average a filled first).
No 15:30-only independent data, financial/PIT scoring or current account proof
=> NEVER emit BUY/order. All researched references are historic, not quotes.
"""
from __future__ import annotations
import argparse,csv,json,math
from collections import Counter
from datetime import date
from pathlib import Path
from forward_ledger_v63 import read_json,read_csv,digest
from full_market_scanner_v68 import parse_days,valid_bar
from entry_strategy_v58 import evaluate,METHODS,COST_PCT
from top20_quality_v612 import SCHEMA as V612
from official_issuer_entry_v610 import SCHEMA as V610

SCHEMA="C3_K100_FIRST_ENTRY_INDEPENDENT_READINESS_V613"
FIELDS=("rank","asof","ticker","name","market","risk_watch_top5",
    "discovery_index_not_trade_score","asof_close",
    "prior_day_high_observation","previous20_day_high_observation",
    "sma20_observation","next_day_condition_is_not_filled_order",
    "confirmed_trigger_methods","observed_daily_pivot_structure_count",
    "first_independent_cost_2R_structure_count",
    "first_only_valid_without_second_alternative_count",
    "second_alternative_research_count","best_trigger_method",
    "stop_from_confirmed_daily_pivot","first_limit_reference",
    "second_alternative_if_first_not_filled","nearest_historic_resistance",
    "first_cost_adjusted_R","first_risk_pct",
    "daily_regular_1530_only_verified","historic_PIT_financial_growth_verified",
    "full80_buy_score_verified","account_cash_verified","trade_approved",
    "orders_enabled","current_readiness","first_entry_blockers")
METHOD_FIELDS=("asof","ticker","name","method","setup",
    "daily_pivot_date","stop_reference","first_entry_reference",
    "second_entry_reference","nearest_resistance_reference",
    "first_net_rr","second_net_rr","first_risk_pct",
    "trigger_confirmed","first_independently_2R_eligible",
    "second_optional_2R_eligible","second_present",
    "valid_no_averaging_alternative","regular_1530_validated",
    "research_only_no_buy","trade_approved","orders_enabled")
MARKETS=("KOSPI","KOSDAQ")

def finite(x):
    try:
        if x is None or x=="" or isinstance(x,bool):return None
        v=float(x)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError):return None

def first_gate(method):
    """Candidate price geometry and 0.5% cost-adjusted 2R, no forced second."""
    if method.get("setup")!="RESEARCH_TRIGGER_CONFIRMED_ASOF":
        return False,"METHOD_DAILY_TRIGGER_NOT_CONFIRMED"
    stop=finite(method.get("stop_reference"))
    first=finite(method.get("first_entry_reference"))
    ceiling=finite(method.get("nearest_resistance_reference"))
    risk=finite(method.get("first_stop_risk_pct"))
    rr=finite(method.get("first_net_rr"))
    gap=finite(method.get("first_entry_below_close_atr"))
    if (stop is None or first is None or ceiling is None
        or not 0<stop<first<ceiling or risk is None or
        gap is None or not 2<=risk<=12 or gap>1
        or rr is None or rr<2):
        return False,"FIRST_STRUCTURE_STOP_RESISTANCE_OR_COST_2R_NOT_READY"
    if not method.get("daily_pivot_date"):
        return False,"DAILY_PIVOT_IS_NOT_DATE_CONFIRMED"
    return True,"FIRST_2R_HYPOTHESIS_SECOND_OPTIONAL_NOT_BUY"

def second_gate(method):
    firstok,_=first_gate(method)
    if not firstok:return False
    a=finite(method.get("first_entry_reference"))
    b=finite(method.get("second_entry_reference"))
    stop=finite(method.get("stop_reference"))
    r=finite(method.get("second_net_rr"))
    p=finite(method.get("second_stop_risk_pct"))
    return bool(a is not None and b is not None and stop is not None
                and stop<b<a and r is not None and r>=2
                and p is not None and 1<=p<=12
                and method.get("second_entry_policy")==
                "ALTERNATIVE_LIMIT_IF_FIRST_NOT_FILLED_NO_AVERAGING_DOWN")

def validate_inputs(top,issuer,v18):
    meta=read_json(top/"top20_quality_v612_status.json")
    base=read_json(issuer/"issuer_entry_v610_status.json")
    market=read_json(v18/"diagnostics/collection_status.json")
    if (meta.get("schema")!=V612 or base.get("schema")!=V610
        or meta.get("asof")!=base.get("asof") or base.get("asof")!=market.get("asof")
        or meta.get("trade_approved") is not False
        or meta.get("orders_enabled") is not False
        or base.get("trade_approved") is not False
        or base.get("orders_enabled") is not False
        or meta.get("regular_1530_verified") is not False
        or meta.get("final_80_score_verified") is not False
        or meta.get("financial_growth_verified") is not False
        or base.get("exact_regular_1530_prices_verified") is not False
        or meta.get("top20_count")!=20 or len(meta.get("top20_tickers",[]))!=20):
        raise ValueError("V613_EXACT_ASOF_PREDECESSOR_OR_NO_BUY_POLICY_INVALID")
    sha=meta.get("output_file_sha256",{})
    for fn in ("top20_quality_v612_all.csv","top20_quality_v612_selected.csv"):
        p=top/fn
        if not p.is_file() or sha.get(fn)!=digest(p.read_bytes()):
            raise ValueError("V613_TOP20_FROZEN_FILE_SHA_MISMATCH")
    selected=read_csv(top/"top20_quality_v612_selected.csv")
    if (len(selected)!=20 or
        [r["ticker"] for r in selected]!=meta["top20_tickers"] or
        {int(r["rank"]) for r in selected}!=set(range(1,21)) or
        len(set(r["ticker"] for r in selected))!=20):
        raise ValueError("V613_TOP20_TICKER_OR_RANK_CHANGED")
    risk=meta.get("top5_risk_watch_only",[])
    if len(risk)>5 or len(set(risk))!=len(risk) or not set(risk).issubset(meta["top20_tickers"]):
        raise ValueError("V613_RISK_TOP5_NOT_SUBSET")
    for marketname,hashvalue in base["v68_market_sha256"].items():
        p=v18/"market/daily_prices"/marketname/(meta["asof"]+".csv")
        if not p.is_file() or digest(p.read_bytes())!=hashvalue:
            raise ValueError("V613_ORIGINAL_OFFICIAL_AGREED_EOD_SHA_CHANGED")
    for relative,hashvalue in base["v69_flow_sha256"].items():
        p=v18/relative
        if not p.is_file() or digest(p.read_bytes())!=hashvalue:
            raise ValueError("V613_COMPLETED_FI_5DAY_SOURCE_SHA_CHANGED")
    return meta,selected,base

def calculate(top,issuer,v18):
    meta,stocks,issuer_meta=validate_inputs(top,issuer,v18)
    asof=meta["asof"]
    methodology=[];out=[]
    daily_signals=0;first_count=0;optional_count=0
    for row in stocks:
        code=row["ticker"]
        if (row["asof"]!=asof or row["buy_authorized"]!="False"
            or row["orders_enabled"]!="False" or row["regular_1530_verified"]!="False"
            or row["positive_fundamental_numbers_verified"]!="False"):
            raise ValueError("V613_UPSTREAM_STOCK_EXPLICIT_BUY_OR_FUTURE_DATA")
        hfile=v18/"market/prices"/(code+".csv")
        if not hfile.is_file():raise ValueError("V613_STOCK_HISTORY_MISSING")
        bars,err=parse_days(read_csv(hfile),code,date.fromisoformat(asof))
        if err or len(bars)<120 or any(not valid_bar(b) for b in bars[-120:]):
            raise ValueError("V613_STOCK_ASOF_VALID_HISTORY_INCOMPLETE")
        candle=bars[-120:]
        price=candle[-1]["close"]
        if finite(row["last_close"])!=price or candle[-1]["date"]!=asof:
            raise ValueError("V613_FROZEN_STOCK_PRICE_NOT_THE_SAME")
        basic=dict(ticker=code,name=row["name"],latest_date=asof,
            close=price,data_source="pykrx",instrument_type="COMMON",
            turnover_source="SOURCE_REPORTED")
        methods=[evaluate(basic,candle,asof,m,
            paired={"category":"OHLC_EXACT_MATCH_UNCERTIFIED","close_equal":True})
            for m in METHODS]
        confirmed=[];good=[];alternative=[];pivot=0
        for m in methods:
            trigger=m["setup"]=="RESEARCH_TRIGGER_CONFIRMED_ASOF"
            first,why=first_gate(m)
            second=second_gate(m)
            if trigger:confirmed.append(m);daily_signals+=1
            if m["daily_pivot_date"] and m["stop_reference"] is not None:pivot+=1
            if first:good.append(m);first_count+=1
            if second:alternative.append(m);optional_count+=1
            methodology.append(dict(asof=asof,ticker=code,name=row["name"],
                method=m["method"],setup=m["setup"],
                daily_pivot_date=m["daily_pivot_date"],
                stop_reference=m["stop_reference"],
                first_entry_reference=m["first_entry_reference"],
                second_entry_reference=m["second_entry_reference"],
                nearest_resistance_reference=m["nearest_resistance_reference"],
                first_net_rr=m["first_net_rr"],second_net_rr=m["second_net_rr"],
                first_risk_pct=m["first_stop_risk_pct"],
                trigger_confirmed=trigger,first_independently_2R_eligible=first,
                second_optional_2R_eligible=second,
                second_present=m["second_entry_reference"] is not None,
                valid_no_averaging_alternative=bool(second and m["second_entry_policy"]==
                      "ALTERNATIVE_LIMIT_IF_FIRST_NOT_FILLED_NO_AVERAGING_DOWN"),
                regular_1530_validated=False,research_only_no_buy=True,
                trade_approved=False,orders_enabled=False))
        chosen=sorted(good,key=lambda q:(
            -q["first_net_rr"],q["method"]))[0] if good else (
            confirmed[0] if confirmed else None)
        reasons=[]
        if row["risk_priority_top5_eligible"]!="True":
            reasons.append("RISK_TOP5_SCREEN_NOT_MET_OR_NOT_TOP5")
        if not confirmed:reasons.append("NO_COMPLETED_DAILY_TRIGGER")
        if not good:reasons.append("NO_INDEPENDENT_FIRST_LIMIT_DAILY_PIVOT_2R")
        reasons.extend(["REGULAR_1530_SOURCE_NOT_CERTIFIED",
            "DATED_ORIGINAL_FINANCIAL_RESULTS_NOT_CERTIFIED",
            "OFFICIAL_SECTOR_INDUSTRY_PIT_NOT_CERTIFIED",
            "FINAL_80_POINT_TRADE_SCORE_UNVERIFIED",
            "CURRENT_ACCOUNT_CASH_AND_POSITION_NOT_CHECKED",
            "FUTURE_FIVE_TRADING_DAYS_NOT_YET_OBSERVED"])
        if good:state="FIRST_LIMIT_2R_RESEARCH_ONLY_EVIDENCE_WAIT"
        elif confirmed:state="DAILY_SIGNAL_BUT_RISK_GEOMETRY_NOT_READY"
        else:state="NEXT_COMPLETED_SESSION_TRIGGER_WAIT"
        out.append(dict(rank=int(row["rank"]),asof=asof,ticker=code,
            name=row["name"],market=row["market"],
            risk_watch_top5=code in meta["top5_risk_watch_only"],
            discovery_index_not_trade_score=finite(row["discovery_index_100"]),
            asof_close=price,
            prior_day_high_observation=candle[-1]["high"],
            previous20_day_high_observation=max(x["high"] for x in candle[-20:]),
            sma20_observation=round(sum(c["close"] for c in candle[-20:])/20,2),
            next_day_condition_is_not_filled_order=True,
            confirmed_trigger_methods=len(confirmed),
            observed_daily_pivot_structure_count=pivot,
            first_independent_cost_2R_structure_count=len(good),
            first_only_valid_without_second_alternative_count=sum(
                first_gate(m)[0] and not second_gate(m) for m in methods),
            second_alternative_research_count=len(alternative),
            best_trigger_method=chosen["method"] if chosen else "",
            stop_from_confirmed_daily_pivot=chosen["stop_reference"] if chosen else None,
            first_limit_reference=chosen["first_entry_reference"] if chosen else None,
            second_alternative_if_first_not_filled=(
                chosen["second_entry_reference"] if chosen and second_gate(chosen) else None),
            nearest_historic_resistance=(
                chosen["nearest_resistance_reference"] if chosen else None),
            first_cost_adjusted_R=chosen["first_net_rr"] if chosen else None,
            first_risk_pct=chosen["first_stop_risk_pct"] if chosen else None,
            daily_regular_1530_only_verified=False,
            historic_PIT_financial_growth_verified=False,
            full80_buy_score_verified=False,account_cash_verified=False,
            trade_approved=False,orders_enabled=False,current_readiness=state,
            first_entry_blockers=";".join(reasons)))
    if len(out)!=20 or len(methodology)!=20*len(METHODS):
        raise ValueError("V613_ALL_TOP20_AND_METHODS_REQUIRED")
    top5=[x for x in out if x["risk_watch_top5"]]
    status=dict(schema=SCHEMA,asof=asof,
        previous_version="v6.12",asof_top20_count=len(out),
        asof_risk_screened_top5_count=len(top5),
        source_v612_selected_SHA256=meta["output_file_sha256"]["top20_quality_v612_selected.csv"],
        price_source_SHA256=issuer_meta["v68_market_sha256"],
        investor_source_SHA256=issuer_meta["v69_flow_sha256"],
        all_v612_bars_asof_replayed=True,
        method_evaluations=len(methodology),
        confirmed_technical_method_count=daily_signals,
        confirmed_first_cost_2r_reference_method_count=first_count,
        first_valid_without_optional_second_count=sum(
            x["first_only_valid_without_second_alternative_count"] for x in out),
        optional_second_2r_reference_method_count=optional_count,
        verified_1530_session=False,verified_historic_financials=False,
        verified_80point_buy_score=False,current_account_capital_verified=False,
        trade_approved=False,orders_enabled=False,decision="CASH",
        earliest_new_data_type="NEXT_COMPLETED_KRX_REGULAR_SESSION",
        planned_daily_market_source_kst="20:15 weekdays sector_evidence_v18",
        v68_retry_kst="08:50 following weekday if same-day EOD missing",
        earliest_5_complete_future_session_outcome_date_only_for_20261023_frozen_cohort="2026-10-30",
        five_session_forward_results_observed=0,
        risk_top5_tickers=[x["ticker"] for x in top5],
        key_gap_counts=dict(Counter(
            reason for row in out for reason in row["first_entry_blockers"].split(";"))))
    return status,out,methodology

def save(out,status,stocks,methods):
    out.mkdir(parents=True,exist_ok=True)
    for fname,cols,rows in (
        ("entry_readiness_v613_all.csv",FIELDS,stocks),
        ("entry_readiness_v613_methods.csv",METHOD_FIELDS,methods)):
        with (out/fname).open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=cols,extrasaction="ignore")
            w.writeheader();w.writerows(rows)
    status["artifact_file_sha256"]={
        fn:digest((out/fn).read_bytes()) for fn in (
            "entry_readiness_v613_all.csv","entry_readiness_v613_methods.csv")}
    (out/"entry_readiness_v613_status.json").write_text(
        json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# v6.13 실제 매수 데이터 준비도", "",
      f"**{status['asof']} 완료 일봉 기준 / CASH / 매수 승인 0**",
      "첫 연구 기회는 다음 실제 완료된 정규장 일봉에서 재평가합니다.",
      "정기 원본 수집은 평일 20:15 KST이며 공식 응답이 늦으면 다음 평일 08:50 재검사합니다.",
      "기존 v6.12 발굴점수는 최종 80점 매수점수도 상승확률도 아닙니다.",
      "### 1차 2R만 통과하면 2차 대체 지정가를 강제하지 않는 개선",
      f"총 {status['method_evaluations']}개 방법 검사; 실제 종가 확정 신호 "+
      f"{status['confirmed_technical_method_count']}개; 비용반영 독립 1차 2R "+
      f"{status['confirmed_first_cost_2r_reference_method_count']}개; "+
      f"2차 없이 1차만 충족 {status['first_valid_without_optional_second_count']}개.",
      "", "## 위험선별 Top5: 내일 무엇을 확인하나",
      "| 종목 | 당시 종가(원) | 당시 일봉 고가(관찰) | 20일 고가(관찰) | 기술신호 | 1차 2R |",
      "|---|---:|---:|---:|---|---|"]
    for s in stocks:
        if not s["risk_watch_top5"]:continue
        lines.append(f"| {s['name']} ({s['ticker']}) | {s['asof_close']:,.0f} | "+
          f"{s['prior_day_high_observation']:,.0f} | "+
          f"{s['previous20_day_high_observation']:,.0f} | "+
          f"{s['confirmed_trigger_methods']}개 | "+
          f"{s['first_independent_cost_2R_structure_count']}개 |")
    lines+=["","표의 전일 고가와 20일 고가는 **다음 날 관찰할 역사적 기준**이지 돌파만 하면 사라는 주문가격이 아닙니다.",
      "정규장 15:30 확정 시세·실제 공시재무·최종 매수점수·구조손절·계좌잔고 미검증 상태에서는 어떤 연구가도 주문으로 승인하지 않습니다.",
      "10월 23일 기준 5거래일 전진 성과는 10월 26~30일이 실제로 완료돼야 사후 평가 가능합니다. 당일 10월 26일에 승률이 인증되는 것은 아닙니다.",
      "", "## Required Next Data",
      "다음 정규장 15:30 종가의 독립 증빙, 120일 정규장 가격 검증, 당시 공개된 연결/별도 분기 재무원문, 현재 주문가능현금/포지션/수량, 구조손절과 가격별 2R 재검증."]
    (out/"entry_readiness_v613_mobile.md").write_text(
        "\n".join(lines)+"\n",encoding="utf-8")

def main():
    p=argparse.ArgumentParser()
    for x in ("--top","--issuer","--v18","--outdir"):
        p.add_argument(x,type=Path,required=True)
    a=p.parse_args()
    result,stocks,methods=calculate(a.top,a.issuer,a.v18)
    save(a.outdir,result,stocks,methods)
    print("V613_FIRST_LIMIT_READY_DATE_GATES",json.dumps({
      k:result[k] for k in ("asof","asof_top20_count","asof_risk_screened_top5_count",
      "confirmed_technical_method_count","confirmed_first_cost_2r_reference_method_count",
      "first_valid_without_optional_second_count","decision")},ensure_ascii=False))
if __name__=="__main__":main()
