#!/usr/bin/env python3
"""18:30 KST C3/K100 regular-only investment status, no trade approvals."""
import argparse,json
from datetime import datetime,timedelta,time
from pathlib import Path
from zoneinfo import ZoneInfo
from regular_only_policy import evaluate

KST=ZoneInfo("Asia/Seoul")

def last_regular_close_date(now):
    now=now.astimezone(KST)
    day=now.date()
    if now.weekday()>=5 or now.time()<time(15,35):
        day-=timedelta(days=1)
    while day.weekday()>=5:day-=timedelta(days=1)
    return day.isoformat()

def read(path):
    try:
        result=json.loads(Path(path).read_text(encoding="utf-8"))
        return result if isinstance(result,dict) else {}
    except (OSError,ValueError,TypeError):
        return {}

def generate(snapshot,asof,account=None):
    data=evaluate(snapshot,asof)
    data["market_scope"]="KRX_REGULAR_ONLY"
    data["regular_market_hours_kst"]="09:00-15:30"
    data["extended_market_included"]=False
    data["research_source_method"]="REGULAR_ONLY_MARKET_OBSERVATION_NOT_CERTIFIED_RANK"
    data["c3_position_state"]=account or {}
    data["flow_scope_status"]="REGULAR_FLOW_NOT_VERIFIED"
    data["last_65_bars_scope"]="REGULAR_HISTORICAL_BARS_NOT_VERIFIED"
    data["blockers"]=list(dict.fromkeys(
        data["blockers"]+["REGULAR_FLOW_NOT_VERIFIED",
          "REGULAR_HISTORICAL_BARS_NOT_VERIFIED",
          "FINAL_80_POINT_ENTRY_CAPITAL_GATE_UNVERIFIED"]))
    data["source_observation_verified"]=False if data["blockers"] else data["source_observation_verified"]
    data["final_research_candidate_count"]=None
    data["approved_buy_count"]=0
    data["decision"]="CASH"
    data["trade_approved"]=False
    return data

def render(report):
    a=report.get("c3_position_state") or {}
    exited=a.get("closed_ticker")=="004490" and a.get("closed_shares_remaining")==0
    return "\n".join([
      "# C3·K100 정규장 전용 최종 리포트",
      f"**KRX 정규장 기준일:** {report['target_asof']} · 09:00~15:30 KST",
      "**최종 판정: CASH / BUY 승인 0건**",
      "**시장 범위:** KRX_REGULAR_ONLY · 애프터마켓·NXT 시간외 시세 분석 제외",
      "**원본 상태:** "+("세션·OHLC 검증 완료" if report["session_provenance_verified"] else "정규장 전용 가격출처 완전검증 미완료"),
      f"**원본 관찰 건수:** {report.get('source_coverage') if report.get('source_coverage') is not None else '미확보'}",
      f"**원본 가격 모순:** {report.get('invalid_bars') if report.get('invalid_bars') is not None else '미확보'}",
      "**섹터 TOP3:** 최종 판정 보류 (정규장 외국인·기관 수급/세션 증명 부족)",
      "**종목 TOP5:** 최종 판정 보류 (65개 정규장 일봉·기업·구조손절 및 자금 미검증)",
      "**C3:** "+("세방전지(004490) 전량 매도·기존 관점 폐기 / 신규 보유 미확인(CASH)"
                   if exited else "사용자 최신 체결·실제 주문가능현금 별도 확인"),
      "**K100:** 기존 Core 관리, 추가 주문 승인 없음",
      "**자료 보류 근거:** "+", ".join(report["blockers"]),
      "",
      "정규장 확정 출처·정규장 65일 연속 일봉·종목별 정규장 수급·비용후 R:R≥2·80점 및 실제 주문가능현금 미확인 시 가격/손절 임의 생성하지 않습니다.",
      "※ GitHub 작업 성공은 주식 추천/수익성 검증이 아닙니다."
    ])+"\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--snapshot",type=Path,default=Path("inputs/regular/snapshot.json"))
    p.add_argument("--account",type=Path,default=Path("config/c3_position_state.json"))
    p.add_argument("--out",type=Path,default=Path("output/regular_final"))
    p.add_argument("--asof",default="")
    args=p.parse_args()
    date=args.asof or last_regular_close_date(datetime.now(KST))
    report=generate(read(args.snapshot),date,read(args.account))
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/"regular_final_status.json").write_text(
      json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (args.out/"regular_final_mobile.md").write_text(render(report),encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("market_scope","target_asof","decision",
        "approved_buy_count","session_provenance_verified","blockers")},ensure_ascii=False))

if __name__=="__main__":main()
