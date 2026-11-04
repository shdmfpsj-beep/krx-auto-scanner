"""Make a compact, mobile-friendly provisional TOP2 report.

The report is intentionally observation-only; no executable buy signal.
"""
import argparse
import json
from pathlib import Path

def render(payload):
    coverage=payload.get("coverage",{})
    manifest=payload.get("collector_manifest",{})
    errors=payload.get("provenance",{}).get("errors",[])
    lines=["# C3 TOP2 잠정 관측 보고서","",
           "**상태: CASH / 신규 매수 판단 보류**",
           "",
           "- 실제 독립 정규장 시세 검증: 미완료",
           "- 실제 체결 검증: 미완료",
           "- 전략 수익성 검증: 미완료",
           "- 실계좌 주문: 비활성",
           f"- 관측 종료일: {manifest.get('end','미확인')}",
           f"- 수집 일봉 수: {manifest.get('rows','미확인')}",
           f"- 수집 실패: {json.dumps(manifest.get('failures',{}),ensure_ascii=False)}",
           f"- 출처 검사 경고: {', '.join(errors) if errors else '메타데이터 일치만 확인'}",
           "",
           "| 종목코드 | 관측 행 | 5일 | 10일 | 20일 |",
           "|---|---:|:---:|:---:|:---:|"]
    for code,rec in sorted(coverage.items()):
        flag=lambda key:"관측" if rec.get(key) else "미완료"
        lines.append(f"| {code} | {rec.get('observed_sessions',0)} | {flag('five_session_complete')} | {flag('ten_session_complete')} | {flag('twenty_session_complete')} |")
    lines+=["","**주의:** '관측'은 가격 행 개수 기준이며 공식 거래소 영업일 달력과 대조된 완결성을 의미하지 않습니다.",
            "매수구간·구조손절·목표가는 과거 등록된 연구 계획 그대로 유지하며 이 보고서에서 새 주문을 생성하지 않습니다.",""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    payload=json.loads(Path(a.input).read_text(encoding="utf-8"))
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(render(payload),encoding="utf-8")
    print(str(out))

if __name__=="__main__":
    main()
