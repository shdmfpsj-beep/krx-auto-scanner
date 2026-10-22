#!/usr/bin/env python3
"""Sector-first mobile summary of existing v18 research, strictly fail closed.

Never relabel ETF-constituent flow proxies as independently verified entire-sector
money inflows; never use relative research index as final 80-point stock score.
"""
import argparse
import csv
import json
import math
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo
from c3_account_state import load_c3_position, c3_mobile_line
from krx_session_clock import nominal_last_completed_krx_session

def read_rows(path):
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def numeric(value):
    try:
        value=float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None

def iso_day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None

def show(value):
    return str(value) if value not in ("",None) else "미확인"

def safe_markdown(value):
    return str(value or "").replace("|","/").replace("\n"," ").replace("\r"," ")[:90]

def excluded_sector(value):
    v=str(value or "").upper()
    return any(token in v for token in ("HEALTH","BIOTECH","PHARMA","바이오","제약"))

def price_reference(row):
    """Only show historical research levels when their order and 2R can be verified."""
    if row.get("plan_status")!="STRUCTURE_CANDIDATE_REQUIRES_VALIDATION":
        return ("","","","")
    first=numeric(row.get("plan_first_entry"))
    second=numeric(row.get("plan_second_entry"))
    stop=numeric(row.get("plan_stop_reference"))
    rr=numeric(row.get("plan_reward_risk"))
    if not (first and second and stop and stop<second<=first and rr is not None and rr>=2):
        return ("","","","")
    return tuple(round(x,2) for x in (first,second,stop,rr))

def build(summary, sector_rows, stock_rows, today, c3_state=None):
    asof=iso_day(summary.get("asof"))
    scan=iso_day(summary.get("scan_date"))
    blockers=[]
    if summary.get("daily_money_gate")=="MARKET_OHLC_CONFLICT":
        blockers.append("TODAYS_MARKET_OHLC_INVALID")
    if summary.get("daily_money_gate")=="INVALID_STALE_OR_INCOMPLETE":
        blockers.append("DAILY_SECTOR_FLOW_SOURCE_INVALID")
    if asof is None or scan is None or asof!=scan:
        blockers.append("SECTOR_SCAN_DATE_MISMATCH")
    if asof is None or asof!=today:
        blockers.append("NOT_TODAYS_COMPLETE_SECTOR_DATA")
    if not summary.get("core_data_verified"):
        blockers.append("CORE_SECTOR_DATA_NOT_VERIFIED")
    if not summary.get("evidence_scan_dates_aligned"):
        blockers.append("SECTOR_SCAN_NOT_ALIGNED")
    ids=summary.get("research_top3_sector_ids") or []
    if not isinstance(ids,list):
        ids=[]
        blockers.append("INVALID_SECTOR_ID_LIST")
    source={str(r.get("sector_id","")):r for r in sector_rows}
    sectors=[]
    for ident in ids[:3]:
        r=source.get(str(ident))
        if not r or r.get("research_eligible")!="YES" or excluded_sector(
            str(ident)+" "+str(r.get("sector_name",""))):
            continue
        if iso_day(r.get("asof"))!=asof:
            continue
        breadth=numeric(r.get("breadth_up_5d_pct"))
        rs=numeric(r.get("rs_5d_pp"))
        foreign=numeric(r.get("foreign_net_buy_5d_krw"))
        institution=numeric(r.get("institution_net_buy_5d_krw"))
        sectors.append(dict(rank=len(sectors)+1,sector_id=str(ident),
             name=safe_markdown(r.get("sector_name") or ident),
             rs_5d_pp=rs,breadth_up_5d_pct=breadth,
             member_turnover_krw=numeric(r.get("member_turnover_krw")),
             research_priority_index=numeric(r.get("research_priority_index")),
             foreign_net_5d_krw=foreign,institution_net_5d_krw=institution,
             flow_proxy_5d_krw=(foreign+institution if foreign is not None and institution is not None else None),
             day_net_flow_1d_incremental_krw=numeric(r.get("day_net_1d_incremental_krw")),
             day_net_flow_1d_raw_krw=numeric(r.get("day_net_1d_raw_krw")),
             day_breadth_up_pct=numeric(r.get("day_breadth_up_pct")),
             flow_phase=str(r.get("flow_phase") or "FIVE_DAY_RESEARCH_ONLY"),
             catalyst="NOT_VERIFIED",fundamentals="NOT_VERIFIED",
             rank_kind=str(r.get("rank_basis") or "V18_RESEARCH_PROXY_NOT_FINAL_100_SCORE"),
             buy_approval="NO"))
    # A missing member or stale input means there is no *current* TOP3.
    if blockers:
        sectors=[]
    source_pending=bool(blockers)
    if len(sectors)<3 and not source_pending:
        blockers.append("LESS_THAN_3_PROVISIONAL_SECTORS")
    sector_ids={r["sector_id"] for r in sectors}
    stocks=[]
    for r in stock_rows:
        code=str(r.get("ticker","")).strip()
        if str(r.get("sector_id","")) not in sector_ids or not(
              len(code)==6 and code.isdigit()):
            continue
        if excluded_sector(r.get("sector_id")) or excluded_sector(r.get("name")):
            continue
        if iso_day(r.get("asof"))!=asof or r.get("price_flow_ready")!="YES":
            continue
        if r.get("trade_approval") not in ("NO",""):
            continue
        proxy=numeric(r.get("research_proxy_index"))
        if proxy is None:
            continue
        first,second,stop,rr=price_reference(r)
        stocks.append(dict(ticker=code,name=safe_markdown(r.get("name")),
          sector_id=str(r.get("sector_id")),proxy_index=round(proxy,2),
          close=numeric(r.get("close")),first_reference=first,
          second_reference=second,stop_reference=stop,rr_reference=rr,
          final_verified_score=None,buy_approval="NO",
          reference_status="STRUCTURAL_LEVELS_UNVERIFIED" if stop else "NO_ELIGIBLE_ENTRY_REFERENCE"))
    stocks.sort(key=lambda x:(-x["proxy_index"],x["ticker"]))
    # The absolute TOP5 is deliberately NOT force-diversified: artificial
    # inclusion of a weak stock from every sector would overstate quality.
    # Independently show one highest-ranked research WATCH per TOP3 sector.
    leaders=[]
    for ident in ids[:3]:
        match=next((r for r in stocks if r["sector_id"]==ident),None)
        if match:
            leaders.append({**match,"leader_rank_type":"SECTOR_RESEARCH_WATCH_ONLY",
                "not_in_global_top5":False})
    global_top5=stocks[:5]
    counts={ident:sum(x["sector_id"]==ident for x in global_top5)
            for ident in ids[:3]}
    for leader in leaders:
        leader["not_in_global_top5"]=all(
            s["ticker"]!=leader["ticker"] for s in global_top5)
    concentration_warning=bool(global_top5 and
        max(counts.values(),default=0)>=4 and len(ids)>=2)
    stocks=global_top5
    if not stocks and not source_pending:
        blockers.append("NO_SECTOR_CONSTITUENT_WITH_VERIFIED_PRICE_FLOW")
    blockers += ["FRESH_CATALYST_EVIDENCE_MISSING",
                 "STOCK_FINANCIALS_AND_FINAL_80_POINT_SCORE_NOT_VERIFIED",
                 "STRUCTURAL_ENTRY_EXECUTION_NOT_VERIFIED"]
    pre_expansion=sum(x["day_breadth_up_pct"] is not None and
                      x["day_breadth_up_pct"]<60 for x in sectors)
    gate=summary.get("daily_money_gate","UNAVAILABLE")
    # Distinguish missing/corrupt evidence from a fully-verified zero-result scan.
    if source_pending or (not sectors and gate!="VERIFIED_NO_QUALIFYING_SECTOR"):
        selection_outcome="PENDING_DATA_VALIDATION"
    elif not sectors and gate=="VERIFIED_NO_QUALIFYING_SECTOR":
        selection_outcome="VERIFIED_NO_QUALIFYING_SECTOR"
    elif len(sectors)<3:
        selection_outcome="PARTIAL_RESEARCH_CANDIDATES"
    else:
        selection_outcome="RESEARCH_CANDIDATES_AVAILABLE"
    stock_outcome=("PENDING_DATA_VALIDATION" if selection_outcome=="PENDING_DATA_VALIDATION"
                   else "NO_RESEARCH_STOCKS_QUALIFIED" if not stocks
                   else "RESEARCH_CANDIDATES_AVAILABLE")
    research_status=("DATA_VALIDATION_PENDING" if selection_outcome=="PENDING_DATA_VALIDATION"
                     else "VERIFIED_NO_QUALIFYING_SECTOR" if not sectors
                     else "EARLY_FLOW_WATCH_ONLY" if pre_expansion
                     else "PROVISIONAL_RESEARCH_ONLY")
    return dict(version="sector_first_mobile_v1",asof=str(asof) if asof else None,
      report_date=str(today),status=research_status,
      sector_selection_outcome=selection_outcome,
      stock_selection_outcome=stock_outcome,
      verified_sector_count=(len(sectors) if selection_outcome!="PENDING_DATA_VALIDATION" else None),
      verified_stock_research_count=(len(stocks) if stock_outcome!="PENDING_DATA_VALIDATION" else None),
      approved_buy_count=0,
      c3_position_state=c3_state or {"status":"POSITION_UNVERIFIED","user_reported":False},
      pre_expansion_sector_count=pre_expansion,
      expanding_sector_count=len(sectors)-pre_expansion,
      decision="CASH",orders_enabled=False,trade_approved=False,
      sector_top3=sectors,stock_research_top5=stocks,
      sector_leader_watch=leaders,
      stock_top5_sector_counts=counts,
      stock_top5_concentration_warning=concentration_warning,
      sector_watch_is_buy_recommendation=False,
      daily_money_rank_applied=bool(summary.get("daily_money_rank_applied")),
      daily_money_gate=summary.get("daily_money_gate","UNAVAILABLE"),
      market_ohlc_quality_verified=summary.get("market_ohlc_quality_verified"),
      raw_tradable_ohlc_checked=summary.get("raw_tradable_ohlc_checked"),
      raw_ohlc_conflict_count=summary.get("raw_ohlc_conflict_count"),
      raw_ohlc_conflict_pct=summary.get("raw_ohlc_conflict_pct"),
      blockers=list(dict.fromkeys(blockers)),
      source_note="V18 ETF-member flow and breadth are proxies, not confirmed whole-sector inflow.",
      required_next_data=["Dated KRX sector turnover and broad constituent money flow",
        "Fresh positive news/disclosures with source links and event dates",
        "Stock earnings/growth verification and valid daily structural entry levels"])

def hundred_million(value):
    return str(round(value/100000000,1)) if value is not None else "미확인"

def render(report):
    lines=["# C3 · K100 오늘의 주도 섹터 / 종목","",
           "**신규매수: CASH** (최종 종목 점수·호재·실행 타점 미검증)","",
           f"섹터 데이터 기준일: {show(report['asof'])} / 보고일: {report['report_date']}",
           f"섹터 상태: {report['status']}","",
           "원본 자료 확보: "+str((report.get("source_acquisition") or {}).get("status","확인되지 않음")),
           "원본 확보 제한사유: "+", ".join((report.get("source_acquisition") or {}).get("errors",[])),"",
           f"섹터 선정판정: {report['sector_selection_outcome']} / 종목 선정판정: {report['stock_selection_outcome']}",
           "실제 BUY 승인: 0건 (80점·진입구조·실행자료 별도 미검증)","",
           "KRX 원본 OHLC 검증: "+
           ("모순 "+str(report.get("raw_ohlc_conflict_count"))+"/"+
            str(report.get("raw_tradable_ohlc_checked"))+
            " ("+str(report.get("raw_ohlc_conflict_pct"))+"%)"
            if report.get("raw_ohlc_conflict_count") is not None else
            "교차검증 수치 미확보"),"",
           c3_mobile_line(report.get("c3_position_state") or {}),"",
           "## ① 자금 선행 섹터 TOP3 (매수 미승인 연구 후보)","",
           "| 순위 | 섹터 | 1일 중복제거 순매수(억)* | 구성종목 거래대금(억)* | 5일 순매수(억)* | 당일 상승 확산 | 단계 |",
           "|---|---|---:|---:|---:|---:|---|"]
    for r in report["sector_top3"]:
        lines.append(f"| {r['rank']} | {r['name']} | {hundred_million(r['day_net_flow_1d_incremental_krw'])} | "
                     f"{hundred_million(r['member_turnover_krw'])} | "
                     f"{hundred_million(r['flow_proxy_5d_krw'])} | "
                     f"{show(r['day_breadth_up_pct'])}% | {r['flow_phase']} |")
    if not report["sector_top3"]:
        label=("판정 보류 (자료 정합성 미충족)"
               if report["sector_selection_outcome"]=="PENDING_DATA_VALIDATION"
               else "검증 완료: 조건 충족 섹터 0개" if report["sector_selection_outcome"]=="VERIFIED_NO_QUALIFYING_SECTOR"
               else "연구후보 확인 불가")
        lines.append(f"| — | {label} | — | — | — | — | — |")
    lines += ["","*당일 중복제거 순매수는 먼저 선정한 섹터와 겹치는 KRX 구성종목의 순매수를"
              " 다시 합산하지 않은 연구용 대리값입니다. 산업 전체 확정 유입액이 아닙니다.",
              "*5일 합산 수급은 당일 수급과 별도로 표시합니다."
              " 수급이 음수이면 당일 급반등을 중기 추세전환으로 단정하지 않습니다.",
              "상승확산 60%는 관찰 단계 분류용입니다. 0%인 경우 순매수가 있어도 가격 하락이 이어져 위험합니다.",
              "자금유입 관찰 TOP3가 곧 상승 확률 검증이나 매수 승인을 뜻하지 않습니다.",
              "호재와 실적·최종 80점은 별도 미검증입니다.","",
              "## ② 해당 섹터 내부 종목 TOP5 (매수 승인 아님)","",
              "| 종목 | 섹터 | 상대 연구지수† | 1차 참고 | 2차 참고 | 일봉손절 참고 |",
              "|---|---|---:|---:|---:|---:|"]
    for r in report["stock_research_top5"]:
        lines.append(f"| {r['ticker']} {r['name']} | {r['sector_id']} | {r['proxy_index']} | "
                     f"{show(r['first_reference'])} | {show(r['second_reference'])} | "
                     f"{show(r['stop_reference'])} |")
    if not report["stock_research_top5"]:
        stock_label=("최종 산출 보류 (자료 정합성 미충족)"
                     if report["stock_selection_outcome"]=="PENDING_DATA_VALIDATION"
                     else "연구 조건 충족 종목 없음")
        lines.append(f"| {stock_label} | — | — | — | — | — |")
    lines += ["","## ③ TOP3 섹터별 대표 연구후보 (TOP5 강제 분산 아님)","",
              "| 섹터 | 대표 연구종목 | 전체 TOP5 포함 |",
              "|---|---|---|"]
    for sector in report["sector_top3"]:
        leader=next((x for x in report["sector_leader_watch"]
                     if x["sector_id"]==sector["sector_id"]),None)
        lines.append("| "+sector["name"]+" | "+
            (leader["name"]+" ("+leader["ticker"]+")" if leader else "데이터 부족")+
            " | "+("아니요" if leader and leader["not_in_global_top5"]
                  else "예" if leader else "—")+" |")
    if report["stock_top5_concentration_warning"]:
        lines.append("")
        lines.append("**집중 경고:** 절대 TOP5의 4개 이상이 한 섹터입니다. 이는 연구 집중이지"
                     " 분산투자 근거나 매수 신호가 아닙니다.")
    lines += ["","†0~100 상대 연구지수는 최종 80점 합격점수나 5거래일 상승확률이 아닙니다.",
              "표의 가격은 완료 일봉 기준 연구 참고값이며 실시간 매수 주문 가격이 아닙니다.",
              "","## 검증 미충족",", ".join(report["blockers"]),"",
              "## Required Next Data"]
    lines += ["- "+x for x in report["required_next_data"]]
    return "\n".join(lines)+"\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,default=Path("output"))
    p.add_argument("--out",type=Path,default=Path("output"))
    p.add_argument("--today",default=nominal_last_completed_krx_session(datetime.now(ZoneInfo("Asia/Seoul"))))
    p.add_argument("--c3-state",type=Path,default=Path("config/c3_position_state.json"))
    a=p.parse_args()
    status=a.input/"sector_bridge_status.json"
    try:
        summary=json.loads(status.read_text(encoding="utf-8")) if status.is_file() else {}
    except (OSError,ValueError):
        summary={}
    sectors=read_rows(a.input/"sector_research_ranking.csv")
    stocks=read_rows(a.input/"sector_stock_research_ranking.csv")
    report=build(summary,sectors,stocks,date.fromisoformat(a.today),load_c3_position(a.c3_state))
    source_status=a.input/"source_selection_status.json"
    try:
        acquisition=json.loads(source_status.read_text(encoding="utf-8")) if source_status.is_file() else {}
    except (OSError,ValueError):
        acquisition={}
    report["source_acquisition"]=acquisition
    if acquisition.get("ready") is False:
        report["sector_selection_outcome"]="PENDING_DATA_VALIDATION"
        report["stock_selection_outcome"]="PENDING_DATA_VALIDATION"
        report["verified_sector_count"]=None
        report["verified_stock_research_count"]=None
        report["status"]="DATA_VALIDATION_PENDING"
        report["blockers"]=list(dict.fromkeys(
            report["blockers"]+["SOURCE_ACQUISITION_INCOMPLETE"]+
            ["SOURCE:"+str(x) for x in acquisition.get("errors",[])]))
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/"sector_first_daily_status.json").write_text(
         json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    (a.out/"sector_first_daily_mobile.md").write_text(render(report),encoding="utf-8")
    print(json.dumps({"decision":report["decision"],"status":report["status"],
       "sector_count":len(report["sector_top3"]),
       "stock_count":len(report["stock_research_top5"]),
       "blockers":report["blockers"]},ensure_ascii=False))

if __name__=="__main__":
    main()
