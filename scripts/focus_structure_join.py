#!/usr/bin/env python3
"""Combine free KRX focus-stock structure prices with sector-first phone report.

Completed daily support reference is displayed without claiming a BUY trigger.
Separate market-date checks make stale prices non-actionable.
"""
import argparse,csv,json
from pathlib import Path

def read_rows(path):
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def merge(report,price_rows):
    out=dict(report)
    sector_asof=str(report.get("asof") or "")
    byticker={}
    enriched=[]
    for x in price_rows:
        ticker=str(x.get("ticker",""))
        if not (len(ticker)==6 and ticker.isdigit()):continue
        valid_date=bool(sector_asof and x.get("latest_complete_date")==sector_asof)
        item=dict(x)
        item["matches_sector_data_date"]=valid_date
        item["self_computed_reference_usable"]=(
            valid_date and bool(x.get("historical_stop_reference")) and
            x.get("structure_state") not in ("STALE_DAILY_CLOSE","INVALID_DAILY_SERIES",
                "DATA_MISSING","PIVOT_RISK_INVALID","NO_HELD_CONFIRMED_PIVOT"))
        item["trade_approval"]="NO"
        byticker[ticker]=item
        enriched.append(item)
    selected=[]
    for original in report.get("stock_research_top5",[]):
        r=dict(original)
        ref=byticker.get(str(r.get("ticker","")))
        if ref and ref["self_computed_reference_usable"]:
            r["independently_collected_daily_stop_reference"]=ref["historical_stop_reference"]
            r["independent_stop_support_date"]=ref.get("pivot_date")
            r["independent_stop_source"]=ref.get("data_source")
            r["independent_stop_status"]="HISTORICAL_DAILY_REFERENCE_ONLY"
        else:
            r["independently_collected_daily_stop_reference"]=None
            r["independent_stop_status"]=(
                "FOCUS_DATE_MISMATCH" if ref and not ref["matches_sector_data_date"]
                else ref["structure_state"] if ref else "NOT_IN_FOCUS_WATCHLIST")
        selected.append(r)
    out["stock_research_top5"]=selected
    out["focus_daily_structure_research"]=enriched
    out["focus_daily_price_matched_count"]=sum(x["matches_sector_data_date"] for x in enriched)
    out["focus_independent_stop_reference_count"]=sum(
         x["self_computed_reference_usable"] for x in enriched)
    out["focus_price_is_independent_trade_approval"]=False
    out["decision"]="CASH"
    out["trade_approved"]=False
    out["orders_enabled"]=False
    return out

def render(report,previous):
    lines=["","## ⑤ 주요 관심·보유 종목: 자동 일봉 구조 가격","",
       "여기 표시된 가격은 별도 무료 일봉 수집으로 계산합니다. 섹터 TOP3의 최종 적격 종목 명단이 아니며 자동매수 승인도 아닙니다.","",
       "| 종목 | 자료일 | 기준 종가 | 구조손절 참고 | 1차 연구 | 2차 연구 | 자동검증 결과 |",
       "|---|---|---:|---:|---|---|---|"]
    for item in report.get("focus_daily_structure_research",[]):
        if not item["matches_sector_data_date"]:
            detail="날짜 불일치: 기존자료 비사용"
            price="—";stop="—";first="—";second="—"
        else:
            price=item.get("close") or "—"
            stop=item.get("historical_stop_reference") or "—"
            first=item.get("entry1_research_range") or "—"
            second=item.get("entry2_support_research_range") or "—"
            detail=item.get("structure_state") or "원인 미기록"
        lines.append(f"| {item.get('name','')} | {item.get('latest_complete_date','')} | "
                     f"{price} | {stop} | {first} | {second} | {detail} |")
    if not report.get("focus_daily_structure_research"):
        lines.append("| 가격 파일 없음 | — | — | — | — | — | 무료 수집기 점검 |")
    lines += ["","### 미산정이 발생한 정확한 사유",""]
    for r in report.get("focus_daily_structure_research",[]):
        if not r["matches_sector_data_date"] or not r.get("historical_stop_reference"):
            lines.append("- "+str(r.get("name",""))+": "+str(r.get("structure_state"))+
                   " / "+str(r.get("next_action")))
    lines += ["","* 별도 손절 참고값은 역사적 구조저점에 따른 연구 가격이며, 향후 손절의 성공을 보장하지 않습니다.",
      "시장·섹터·재무·수급 검증 미완료 또는 매매가격 미적합 시 **최종 신규매수: CASH**.",""]
    return previous.rstrip()+"\n"+"\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("output"))
    a=p.parse_args()
    source=a.root/"sector_first_global.json"
    if not source.is_file():source=a.root/"sector_first_with_catalysts.json"
    if not source.is_file():source=a.root/"sector_first_daily_status.json"
    if not source.is_file():raise SystemExit("NO_SECTOR_FIRST_BASE_REPORT")
    base=json.loads(source.read_text(encoding="utf-8"))
    merged=merge(base,read_rows(a.root/"focus_daily_structure_prices.csv"))
    (a.root/"sector_first_with_prices.json").write_text(
        json.dumps(merged,ensure_ascii=False,indent=2),encoding="utf-8")
    old=a.root/"sector_first_global_mobile.md"
    if not old.is_file():old=a.root/"sector_first_with_catalysts_mobile.md"
    if not old.is_file():old=a.root/"sector_first_daily_mobile.md"
    previous=old.read_text(encoding="utf-8") if old.is_file() else "# 섹터 보고서\n"
    (a.root/"sector_first_with_prices_mobile.md").write_text(
        render(merged,previous),encoding="utf-8")
    print(json.dumps({"research_names":len(merged["focus_daily_structure_research"]),
       "matched_dates":merged["focus_daily_price_matched_count"],
       "stop_references":merged["focus_independent_stop_reference_count"],
       "decision":"CASH"},ensure_ascii=False))

if __name__=="__main__":
    main()
