#!/usr/bin/env python3
"""Short phone-first sector TOP3 -> price-qualified TOP5 research report.

No invented score or BUY prices. Show independently calculated daily-stop
references even for non-buyable setups and distinguish price from execution.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

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
    lines=["# C3·K100 일일 섹터·가격 요약","",
           "**신규매수: CASH** — 전체 85점 검증·당일 진입 조건 완료 전",
           "",f"일봉·섹터 기준일: {txt(data.get('asof'),'미확보')}",
           "이하 모든 가격은 해당일 완료된 일봉 연구 참고가격이며 실시간 주문호가가 아닙니다.","",
           "## ① 국내 자금 중심 섹터 TOP3 (연구 순위)","",
           "| 섹터 | 연구 우선지수 | 관측 순매수(억)* | 거래대금(억)* |",
           "|---|---:|---:|---:|"]
    for s in sectors[:3]:
        flow=s.get("flow_proxy_5d_krw")
        turnover=s.get("member_turnover_krw")
        def hundred_million(v):
            try:return f"{float(v)/1e8:,.1f}"
            except (TypeError,ValueError,OverflowError):return "—"
        lines.append("| "+txt(s.get("name"))+" | "+
          txt(s.get("research_priority_index"))+" | "+
          hundred_million(flow)+" | "+hundred_million(turnover)+" |")
    if not sectors:
        lines.append("| 오늘 확정 자료 미충족 | — | — | — |")
    lines+=["","*ETF 구성종목 기준 표본 수급·거래대금이며 전체 산업 섹터의 확정 유입금액은 아닙니다.",
       "연구 우선지수는 업종 간 상대순위이며 최종 검증 100점 점수가 아닙니다.","",
       "## ② 섹터 내 연구 종목 TOP5 — 산정 가능한 가격은 숫자로 표시","",
       "| 종목 | 1차 일봉 연구 | 2차 지지 연구 | 구조손절 참고 |",
       "|---|---|---|---|"]
    for x in stocks[:5]:
        lines.append("| "+txt(x.get("name"))+" | "+first_reference(x)+" | "+
                     second_reference(x)+" | "+stop_reference(x)+" |")
    if not stocks:
        lines.append("| 최신 섹터 연구 종목 없음 | — | — | — |")
    lines+=["","### 왜 실제 신규매수를 승인하지 않았는가?",""]
    for x in stocks[:5]:
        reason=x.get("independent_stop_status") or x.get("reference_status") or "FINAL_SCORE_UNVERIFIED"
        lines.append("- "+txt(x.get("name"))+": "+txt(STATE_NAMES.get(reason,reason))+
           "; 최종 85점·당일 지지/수급/손익비 검증 전")
    if not stocks:
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
       "- 진입 당일 가격·확정 85점 이상 여부와 보유계좌 실행 조건","",
       "**종목 가격을 계산했다는 사실이 매수 신호를 뜻하지 않습니다.**",""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("output"))
    a=p.parse_args()
    source=a.root/"sector_first_with_prices.json"
    if not source.is_file():
        raise SystemExit("MISSING_FINAL_SECTOR_PRICE_REPORT")
    data=json.loads(source.read_text(encoding="utf-8"))
    a.root.mkdir(parents=True,exist_ok=True)
    (a.root/"sector_first_compact_mobile.md").write_text(
        format_summary(data),encoding="utf-8")
    print(json.dumps({"sector_research_count":len(data.get("sector_top3",[])),
       "stock_research_count":len(data.get("stock_research_top5",[])),
       "trade_approved":False,"decision":"CASH"},ensure_ascii=False))

if __name__=="__main__":
    main()
