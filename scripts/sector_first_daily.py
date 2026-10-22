#!/usr/bin/env python3
"""Sector-first mobile summary of existing v18 research, strictly fail closed.

Never relabel ETF-constituent flow proxies as independently verified entire-sector
money inflows; never use relative research index as final 85-point stock score.
"""
import argparse
import csv
import json
import math
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

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

def build(summary, sector_rows, stock_rows, today):
    asof=iso_day(summary.get("asof"))
    scan=iso_day(summary.get("scan_date"))
    blockers=[]
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
             catalyst="NOT_VERIFIED",fundamentals="NOT_VERIFIED",
             rank_kind=str(r.get("rank_basis") or "V18_RESEARCH_PROXY_NOT_FINAL_100_SCORE"),
             buy_approval="NO"))
    # A missing member or stale input means there is no *current* TOP3.
    if blockers:
        sectors=[]
    if len(sectors)<3:
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
    stocks=stocks[:5]
    if not stocks:
        blockers.append("NO_SECTOR_CONSTITUENT_WITH_VERIFIED_PRICE_FLOW")
    blockers += ["FRESH_CATALYST_EVIDENCE_MISSING",
                 "STOCK_FINANCIALS_AND_FINAL_85_POINT_SCORE_NOT_VERIFIED",
                 "STRUCTURAL_ENTRY_EXECUTION_NOT_VERIFIED"]
    return dict(version="sector_first_mobile_v1",asof=str(asof) if asof else None,
      report_date=str(today),status="PROVISIONAL_RESEARCH_ONLY" if sectors else "NO_VERIFIED_TOP3",
      decision="CASH",orders_enabled=False,trade_approved=False,
      sector_top3=sectors,stock_research_top5=stocks,
      daily_money_rank_applied=bool(summary.get("daily_money_rank_applied")),
      daily_money_gate=summary.get("daily_money_gate","UNAVAILABLE"),
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
           "## ① 주도 섹터 TOP3 (검증된 순위가 아닌 잠정 연구 후보)","",
           "| 순위 | 섹터 | 1일 중복제거 순매수(억)* | 구성종목 거래대금(억)* | 5일 순매수(억)* | 당일 상승 확산 |",
           "|---|---|---:|---:|---:|---:|"]
    for r in report["sector_top3"]:
        lines.append(f"| {r['rank']} | {r['name']} | {hundred_million(r['day_net_flow_1d_incremental_krw'])} | "
                     f"{hundred_million(r['member_turnover_krw'])} | "
                     f"{hundred_million(r['flow_proxy_5d_krw'])} | "
                     f"{show(r['day_breadth_up_pct'])} |")
    if not report["sector_top3"]:
        lines.append("| — | 오늘 확정할 섹터 없음 | — | — | — | — |")
    lines += ["","*당일 중복제거 순매수는 먼저 선정한 섹터와 겹치는 KRX 구성종목의 순매수를"
              " 다시 합산하지 않은 연구용 대리값입니다. 산업 전체 확정 유입액이 아닙니다.",
              "*5일 합산 수급은 당일 수급과 별도로 표시합니다."
              " 수급이 음수이면 당일 급반등을 중기 추세전환으로 단정하지 않습니다.",
              "호재와 실적·최종 85점은 별도 미검증입니다.","",
              "## ② 해당 섹터 내부 종목 TOP5 (매수 승인 아님)","",
              "| 종목 | 섹터 | 상대 연구지수† | 1차 참고 | 2차 참고 | 일봉손절 참고 |",
              "|---|---|---:|---:|---:|---:|"]
    for r in report["stock_research_top5"]:
        lines.append(f"| {r['ticker']} {r['name']} | {r['sector_id']} | {r['proxy_index']} | "
                     f"{show(r['first_reference'])} | {show(r['second_reference'])} | "
                     f"{show(r['stop_reference'])} |")
    if not report["stock_research_top5"]:
        lines.append("| 해당 없음 | — | — | — | — | — |")
    lines += ["","†0~100 상대 연구지수는 최종 85점 합격점수나 5거래일 상승확률이 아닙니다.",
              "표의 가격은 완료 일봉 기준 연구 참고값이며 실시간 매수 주문 가격이 아닙니다.",
              "","## 검증 미충족",", ".join(report["blockers"]),"",
              "## Required Next Data"]
    lines += ["- "+x for x in report["required_next_data"]]
    return "\n".join(lines)+"\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,default=Path("output"))
    p.add_argument("--out",type=Path,default=Path("output"))
    p.add_argument("--today",default=datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat())
    a=p.parse_args()
    status=a.input/"sector_bridge_status.json"
    try:
        summary=json.loads(status.read_text(encoding="utf-8")) if status.is_file() else {}
    except (OSError,ValueError):
        summary={}
    sectors=read_rows(a.input/"sector_research_ranking.csv")
    stocks=read_rows(a.input/"sector_stock_research_ranking.csv")
    report=build(summary,sectors,stocks,date.fromisoformat(a.today))
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
