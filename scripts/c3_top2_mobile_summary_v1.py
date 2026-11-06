"""Make a compact, mobile-friendly provisional TOP2 report.

The report is intentionally observation-only; no executable buy signal.
"""
import argparse
import json
from pathlib import Path

def render(payload, calendar_check=None):
    coverage=payload.get("coverage",{})
    manifest=payload.get("collector_manifest",{})
    errors=payload.get("provenance",{}).get("errors",[])
    lines=["# C3 TOP2 잠정 관측 보고서","",
           "**상태: CASH / 신규 매수 판단 보류**",
           "",
           "- 실제 독립 정규장 시세 검증: 미완료",
           "- 공식 거래소 영업일 달력 대조: 미완료",
           "- 중간 누락 거래일 여부: 검증 불가",
           "- 실제 체결 검증: 미완료",
           "- 전략 수익성 검증: 미완료",
           "- 실계좌 주문: 비활성",
           f"- 관측 종료일: {manifest.get('end','미확인')}",
           f"- 수집 일봉 수: {manifest.get('rows','미확인')}",
           f"- 수집 실패: {json.dumps(manifest.get('failures',{}),ensure_ascii=False)}",
           f"- 출처 검사 경고: {', '.join(errors) if errors else '메타데이터 일치만 확인'}",
           "",
           "| 종목코드 | 관측 행 | 5행 | 10행 | 20행 |",
           "|---|---:|:---:|:---:|:---:|"]
    for code,rec in sorted(coverage.items()):
        flag=lambda key:"관측" if rec.get(key) else "미완료"
        lines.append(f"| {code} | {rec.get('observed_sessions',0)} | {flag('five_session_complete')} | {flag('ten_session_complete')} | {flag('twenty_session_complete')} |")
    dates=manifest.get("ticker_date_coverage",{})
    if dates:
        lines+=["","**종목별 마지막 수집일 (공식 거래일 검증 아님)**"]
        for code,rec in sorted(dates.items()):
            lines.append(f"- {code}: {rec.get('last_observed_date') or '미수집'} / 종료일까지 달력상 {rec.get('calendar_days_from_last_to_end')}일")
        lines.append(f"- 두 종목의 마지막 관측일 일치: {'예' if manifest.get('latest_observed_dates_aligned') else '아니요'}")
    if calendar_check is not None:
        clean=not calendar_check.get("discrepancies_found",True)
        lines += ["", "**제3자 XKRX 달력 대조 (공식 인증 아님)**",
                  f"- 날짜 대조: {'불일치 미발견' if clean else '불일치 발견 / 검토 필요'}",
                  f"- 대조 범위: {calendar_check.get('start','?')} ~ {calendar_check.get('end','?')}",
                  "- 공식 한국거래소 거래일 인증: 미완료"]
    lines+=["","**주의:** 5·10·20행 충족은 실제 연속 거래일 수집을 보장하지 않습니다. 제3자 달력과 일치하더라도 공식 거래일·독립 가격 검증 및 수익성 검증은 미완료입니다.",
            "매수구간·구조손절·목표가는 과거 등록된 연구 계획 그대로 유지하며 이 보고서에서 새 주문을 생성하지 않습니다.",""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--calendar-check",help="Optional third-party XKRX check JSON")
    a=p.parse_args()
    payload=json.loads(Path(a.input).read_text(encoding="utf-8"))
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    calendar_check=json.loads(Path(a.calendar_check).read_text(encoding="utf-8")) if a.calendar_check else None
    out.write_text(render(payload,calendar_check),encoding="utf-8")
    print(str(out))

if __name__=="__main__":
    main()
