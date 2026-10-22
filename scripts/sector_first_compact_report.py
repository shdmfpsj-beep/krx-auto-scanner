#!/usr/bin/env python3
"""Short phone-first sector TOP3 -> price-qualified TOP5 research report.

No invented score or BUY prices. Show independently calculated daily-stop
references even for non-buyable setups and distinguish price from execution.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from c3_account_state import c3_mobile_line

STATE_NAMES={
 "HISTORICAL_DAILY_REFERENCE_ONLY":"일봉 손절 참고가 계산됨; 실제 진입조건 별도",
 "NOT_IN_FOCUS_WATCHLIST":"해당 종목 최신 일봉 별도 재수집 미수행",
 "FOCUS_DATE_MISMATCH":"일봉 기준일 불일치",
 "DATA_MISSING":"무료 가격 이력 수집 실패",
 "INVALID_DAILY_SERIES":"무료 일봉 OHLC 검증 실패",
 "NO_HELD_CONFIRMED_PIVOT":"확정·유지된 일봉 구조저점 부재",
 "STOP_DISTANCE_UNSUITABLE":"손절거리가 진입 적합 범위 밖",
 "LOW_FORWARD_REWARD_RISK":"전고점 대비 손익비 부족",
 "SECOND_SUPPORT_NOT_CONFIRMED":"2차 지지 미확인",
}
def txt(v,fallback="—"):
    s=str(v or "").replace("|","/").replace("\n"," ").replace("\r"," ")
    return s[:90] if s else fallback

def krw(v):
    if v in (None,""):return "—"
    try:
        return f"{int(round(float(v))):,}원"
    except (ValueError,TypeError,OverflowError):
        return txt(v)

def safe_link(url):
    try:
        p=urlsplit(str(url))
    except ValueError:
        return None
    if p.scheme!="https" or not p.hostname:
        return None
    if any(char in str(url) for char in " \r\n[]()<>"):
        return None
    return str(url)

def first_reference(s):
    return txt(s.get("independent_first_entry_reference") or s.get("first_reference"))

def second_reference(s):
    return txt(s.get("independent_second_entry_reference") or s.get("second_reference"))

def stop_reference(s):
    v=s.get("independently_collected_daily_stop_reference")
    return krw(v) if v not in ("",None) else krw(s.get("stop_reference"))

def format_summary(data):
    sectors=data.get("sector_top3") or []
    stocks=data.get("stock_research_top5") or []
    sector_outcome=data.get("sector_selection_outcome","PENDING_DATA_VALIDATION")
    stock_outcome=data.get("stock_selection_outcome","PENDING_DATA_VALIDATION")
    lines=["# C3·K100 일일 섹터·가격 요약","",
           "**신규매수: CASH** — 전체 80점 검증·당일 진입 조건 완료 전",
           "",f"일봉·섹터 기준일: {txt(data.get('asof'),'미확보')}",
           "이하 모든 가격은 해당일 완료된 일봉 연구 참고가격이며 실시간 주문호가가 아닙니다.",
           "데이터 판정: "+txt(sector_outcome)+" / 종목 판정: "+txt(stock_outcome),
           ("원본 확보 실패: "+", ".join(str(x) for x in
            (data.get("source_acquisition") or {}).get("errors",[]))
            if (data.get("source_acquisition") or {}).get("ready") is False
            else "원본 출처: 최신 가격 근거 별도 확인"),
           "최종 BUY 승인 0건 · 데이터 오류 때문에 후보가 공란인 것과 검증 후 후보 0개는 다릅니다.","",
           ("**시장 OHLC 오류:** "+txt(data.get("raw_ohlc_conflict_count"))+"/"+
            txt(data.get("raw_tradable_ohlc_checked"))+"개 ("+
            txt(data.get("raw_ohlc_conflict_pct"))+"%) · 수집기 성공과 품질 보증은 별개입니다."
            if data.get("raw_ohlc_conflict_count") is not None else
            "**시장 OHLC 오류 수량:** 최종 자료에 미포함 — 정상 판정 불가"),"",
           c3_mobile_line(data.get("c3_position_state") or {}),"",
           "## ① 자금 선행 섹터 TOP3 (매수 미승인 관찰 순위)","",
           "| 섹터 | 중복 제거 1일 순매수(억)* | 5일 순매수(억)* | 거래대금(억)* | 상승확산 | 단계 |",
           "|---|---:|---:|---:|---:|---|"]
    for s in sectors[:3]:
        flow=s.get("flow_proxy_5d_krw")
        turnover=s.get("member_turnover_krw")
        def hundred_million(v):
            try:return f"{float(v)/1e8:,.1f}"
            except (TypeError,ValueError,OverflowError):return "—"
        lines.append("| "+txt(s.get("name"))+" | "+
          hundred_million(s.get("day_net_flow_1d_incremental_krw"))+" | "+
          hundred_million(flow)+" | "+hundred_million(turnover)+" | "+
          (txt(s.get("day_breadth_up_pct"))+"%" if s.get("day_breadth_up_pct") is not None else "—")+" | "+
          txt(s.get("flow_phase"),"연구용") +" |")
    if not sectors:
        sector_label=("최종 판정 보류 (데이터 정합성 미충족)"
                      if sector_outcome=="PENDING_DATA_VALIDATION"
                      else "검증 완료: 적격 섹터 0개" if sector_outcome=="VERIFIED_NO_QUALIFYING_SECTOR"
                      else "유효 연구 섹터 없음")
        lines.append("| "+sector_label+" | — | — | — | — | — |")
    lines+=["","*ETF 구성종목 기준 표본 수급·거래대금이며 전체 산업 섹터의 확정 유입금액은 아닙니다.",
       "당일 외국인·기관 순매수와 5일 합산 수급을 분리했습니다."
       " ETF 겹친 주식 순매수는 당일 수치에서 중복 제거하지만,"
       " 이는 전체 산업 자금 유입이나 확정된 최종 100점 점수가 아닙니다.",
       "상승확산 60% 미만도 연구 후보이며 매수 승인과 무관합니다."
       " 상승 종목 0%일 때의 순매수는 하락 흡수 위험이 있어 별도 주의합니다.","",
       "## ② 섹터 내 연구 종목 TOP5 — 산정 가능한 가격은 숫자로 표시","",
       "| 종목 | 1차 일봉 연구 | 2차 지지 연구 | 구조손절 참고 |",
       "|---|---|---|---|"]
    conflicted=set(str(x) for x in data.get("focus_close_conflict_tickers") or [])
    for x in stocks[:5]:
        status=str(x.get("independent_stop_status") or "")
        if (str(x.get("ticker","")) in conflicted or
            status in ("CROSS_SOURCE_CLOSE_CONFLICT","FOCUS_DATE_MISMATCH")):
            # The old sector research may still carry numerically plausible
            # prices. Never display them as usable after quote/date conflict.
            first=second=stop="—"
        else:
            first=first_reference(x)
            second=second_reference(x)
            stop=stop_reference(x)
        lines.append("| "+txt(x.get("name"))+" | "+first+" | "+
                     second+" | "+stop+" |")
    if not stocks:
        stock_label=("TOP5 최종 산출 보류 (검증 미완료)"
                     if stock_outcome=="PENDING_DATA_VALIDATION"
                     else "검증 조건 충족 연구종목 없음")
        lines.append("| "+stock_label+" | — | — | — |")
    leaders=data.get("sector_leader_watch") or []
    lines+=["","### 섹터별 대표 연구 관찰 (절대 TOP5와 별도)",""]
    for sector in sectors[:3]:
        item=next((x for x in leaders if x.get("sector_id")==sector.get("sector_id")),None)
        if item:
            lines.append("- "+txt(sector.get("name"))+": "+txt(item.get("name"))+
                " ("+txt(item.get("ticker"))+")"+
                (" — TOP5 밖 연구 후보" if item.get("not_in_global_top5") else " — TOP5 포함"))
        else:
            lines.append("- "+txt(sector.get("name"))+": 유효 종목 데이터 부족")
    if data.get("stock_top5_concentration_warning"):
        lines+=["","**섹터 편중 주의:** 전체 TOP5의 4개 이상이 한 섹터입니다."
                 " 다른 섹터의 약한 종목을 억지로 매수 후보로 승격하지 않습니다."]
    if data.get("focus_close_conflict_tickers"):
        lines+=["","**시세 출처 충돌:** "+", ".join(
            str(x) for x in data["focus_close_conflict_tickers"])+
            " — 손절·매수 참고가격 및 신규 모의매매 생성 차단."]

    lines+=["","### 왜 실제 신규매수를 승인하지 않았는가?",""]
    for x in stocks[:5]:
        reason=x.get("independent_stop_status") or x.get("reference_status") or "FINAL_SCORE_UNVERIFIED"
        lines.append("- "+txt(x.get("name"))+": "+txt(STATE_NAMES.get(reason,reason))+
           "; 최종 80점·당일 지지/수급/손익비 검증 전")
    if not stocks:
        if sector_outcome=="PENDING_DATA_VALIDATION":
            lines.append("- 서로 다른 기준일 또는 데이터 무결성 문제로 TOP3·TOP5 **최종 산출 보류**. BUY 승인만 0건으로 확정.")
        elif data.get("daily_money_gate")=="VERIFIED_NO_QUALIFYING_SECTOR":
            lines.append("- 당일 KRX 자료가 검증됐으나 완전한 가격·수급 표본에서 플러스 순매수인 섹터가 없어 TOP3·TOP5 연구후보 0건입니다. 신규매수는 CASH입니다.")
        else:
            lines.append("- 섹터 또는 투자자 수급·가격 자료가 해당일 완결되지 않아 종목 선정 자체가 제한됨")
    lines+=["","## ③ 해외에서 먼저 관찰된 뉴스 (원문 근거 목록)",""]
    count=0
    for s in sectors[:3]:
        for a in (s.get("global_news_observations") or [])[:1]:
            url=safe_link(a.get("url"))
            if not url:continue
            title=txt(a.get("title"))
            lines.append("- "+txt(s.get("name"))+": ["+title+"]("+url+")")
            count+=1
    for x in (data.get("global_early_watch_outside_top3") or [])[:2]:
        for a in x.get("sources",[])[:1]:
            url=safe_link(a.get("url"))
            if url:
                lines.append("- 해외 선행 관찰 "+txt(x.get("sector_id"))+": ["+
                            txt(a.get("title"))+"]("+url+")")
                count+=1
    if not count:lines.append("- 수집된 해외 원문 출처 없음 / 수집 실패와 무호재를 동일시하지 않음")
    lines+=["","## 다음 분석에서 자동 확인할 자료","",
       "- 최신 확정 일봉, 구조저점·ATR, 1차·2차 지지와 전고점 대비 손익비",
       "- 외국인/기관 실제 순매수와 종목별 거래대금·상승 확산",
       "- 해외 호재 원문·한국 상장사 실질 수혜·재무 실적 연결",
       "- 진입 당일 가격·확정 80점 이상 여부와 보유계좌 실행 조건","",
       "**종목 가격을 계산했다는 사실이 매수 신호를 뜻하지 않습니다.**",""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("output"))
    a=p.parse_args()
    source=a.root/"sector_first_with_prices.json"
    if source.is_file():
        data=json.loads(source.read_text(encoding="utf-8"))
        mode="PRICE_RESEARCH_AVAILABLE"
    else:
        # Fail closed: a missing price report is acceptable ONLY when upstream
        # source acquisition explicitly reported a blocked market and the
        # research-only daily report independently confirms zero BUY approvals.
        meta=a.root/"source_selection_status.json"
        fallback=a.root/"sector_first_daily_status.json"
        try:
            acq=json.loads(meta.read_text(encoding="utf-8"))
            data=json.loads(fallback.read_text(encoding="utf-8"))
        except (OSError,TypeError,ValueError):
            raise SystemExit("MISSING_FINAL_SECTOR_PRICE_REPORT")
        if (acq.get("schema")!="sector_source_acquisition_v1"
            or acq.get("ready") is not False
            or acq.get("status")!="PENDING_DATA_VALIDATION"
            or acq.get("trade_approved") is not False
            or data.get("sector_selection_outcome")!="PENDING_DATA_VALIDATION"
            or data.get("stock_selection_outcome")!="PENDING_DATA_VALIDATION"
            or data.get("decision")!="CASH"
            or data.get("trade_approved") is not False
            or data.get("approved_buy_count")!=0
            or data.get("sector_top3")
            or data.get("stock_research_top5")):
            raise SystemExit("MISSING_FINAL_SECTOR_PRICE_REPORT")
        data["source_acquisition"]=acq
        mode="SOURCE_QUALITY_PENDING_NO_PRICE_REPORT"
    a.root.mkdir(parents=True,exist_ok=True)
    (a.root/"sector_first_compact_mobile.md").write_text(
        format_summary(data),encoding="utf-8")
    print(json.dumps({"sector_research_count":len(data.get("sector_top3",[])),
       "stock_research_count":len(data.get("stock_research_top5",[])),
       "trade_approved":False,"decision":"CASH","report_mode":mode},ensure_ascii=False))

if __name__=="__main__":
    main()
