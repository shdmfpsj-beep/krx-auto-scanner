"""Render source diagnostic to a mobile-friendly, no-order Markdown report."""
import argparse,json
from pathlib import Path
LABELS={"AWAIT_TODAY_CLOSE_PRICE":"장 마감 전: 오늘 종가 수집 대기","SOURCE_DATE_IN_FUTURE":"보고일 이후의 미래 날짜 데이터(검증 필요)",
"NO_CURRENT_REPORT_DATE_PRICE":"보고일 기준 최신 가격 없음(이전 거래일 자료)","PRICE_PROVIDER_FAILED_OR_SUSPENDED":"가격 공급원 실패·거래정지 여부 확인",
"CAPTURE_ARTIFACT_NOT_AVAILABLE":"가격 수집 결과 파일 없음",
"FULL_MARKET_SCAN_NOT_VERIFIED":"전 종목 스캔 완료 확인 불가",
"SCAN_DATE_MISSING":"전 종목 스캔 기준일 없음",
"SOURCE_DATES_MISMATCH":"가격 수집일과 스캔일 불일치",
"CHECK_REGISTRATION_AND_FORWARD_ELIGIBILITY":"등록일·관찰 가능 거래일 검토 필요",
"NO_POST_REGISTRATION_SESSION_YET":"계획 등록 이후 거래일 자료 없음(정상 대기)",
"FORWARD_OBSERVATIONS_PRESENT":"후속 관찰 기록 존재"}
def render(d):
    lines=["# C3 TOP2 무료 데이터 점검","",
      "**실제 매수·주문 없음 / 관찰 자료는 실거래 수익률이 아님**","",
      "| 종목 | 상태 | 관찰 세션 | 데이터 판정 |",
      "|---|---|---:|---|"]
    for p in d.get("positions",[]):
        name=str(p.get("name") or p.get("ticker") or "미확인").replace("|","/")
        ticker=str(p.get("ticker") or "")
        reason=LABELS.get(p.get("reason"),"추가 확인 필요")
        status=str(p.get("paper_status") or "미확인")
        lines.append(f"| {name} ({ticker}) | {status} | {int(p.get('observed_sessions') or 0)} | {reason} |")
    lines.extend(["","**운영 판단:** 수집 근거가 불완전한 경우 신규매수 판단 보류(CASH).",
       "정규장 시세 인증·실제 체결·수익성 검증은 이 보고서로 입증되지 않습니다.",""])
    return "\n".join(lines)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--diagnostic",required=True);p.add_argument("--out",required=True)
    a=p.parse_args()
    result=json.loads(Path(a.diagnostic).read_text(encoding="utf-8"))
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(render(result),encoding="utf-8")
    print("MOBILE_DIAGNOSTIC_WRITTEN",str(out))
