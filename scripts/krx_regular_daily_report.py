#!/usr/bin/env python3
"""Create 18:00 read-only phone report from REGULAR observation only.

This cannot certify a session from an unscoped date-only provider, even if
its captured clock time lies between 15:33 and 15:40. No after-market input.
"""
import argparse,json
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from krx_regular_after_layers import assess_capture,REGULAR

def nominal_regular_day(now):
    local=now.astimezone(ZoneInfo("Asia/Seoul"))
    d=local.date()
    if d.weekday()>=5 or (local.hour,local.minute)<(15,33):
        d-=timedelta(days=1)
    while d.weekday()>=5:d-=timedelta(days=1)
    return d.isoformat()

def report(snapshot,day):
    snap=snapshot if isinstance(snapshot,dict) else {}
    blockers=assess_capture(snap) if snap else ["SNAPSHOT_MISSING"]
    if snap.get("asof")!=day:blockers.append("REGULAR_SOURCE_ASOF_MISMATCH")
    if snap.get("trade_session")!=REGULAR or snap.get("phase")!="regular":
        blockers.append("REGULAR_SESSION_REQUIRED")
    if snap.get("regular_strategy_eligible") is not True:blockers.append("REGULAR_ONLY_SOURCE_NOT_CERTIFIED")
    if snap.get("trade_approved") is not False:blockers.append("READ_ONLY_ORDER_SAFETY_UNKNOWN")
    if snap.get("orders_enabled") is not False:blockers.append("READ_ONLY_ORDER_SAFETY_UNKNOWN")
    # Price-source integrity and session investor-flow integrity are distinct.
    # The current PyKRX date-only source does not certify regular-only flow.
    blockers.append("REGULAR_ONLY_FOREIGN_INSTITUTION_FLOW_NOT_VERIFIED")
    blockers=list(dict.fromkeys(blockers))
    return dict(schema="krx_regular_only_daily_v1",target_asof=day,
        regular_snapshot_asof=snap.get("asof"),
        mode="KRX_REGULAR_ONLY_0900_1530",
        after_market_excluded=True,
        market_source_status="PENDING_DATA_VALIDATION" if blockers else "REGULAR_ONLY_SOURCE_VERIFIED",
        source_capture_window=snap.get("capture_window"),
        regular_snapshot_available=bool(snap.get("stocks")),
        provider_session_scope_verified=snap.get("provider_session_scope_verified") is True,
        regular_quality=snap.get("quality") or {},
        sector_top3=[],stock_research_top5=[],
        sector_selection_outcome="PENDING_DATA_VALIDATION",
        stock_selection_outcome="PENDING_DATA_VALIDATION",
        verified_sector_count=None,verified_stock_count=None,
        blockers=blockers,
        approved_buy_count=0,trade_approved=False,
        decision="CASH")
def markdown(r):
    q=r["regular_quality"]
    lines=[
      "# C3·K100 정규장 전용 최종 리포트",
      "",
      f"**KRX 정규장 대상일:** {r['target_asof']} (09:00~15:30)",
      "**애프터마켓 자료:** 분석·매수/손절가 산정 제외",
      "**최종 신규매수:** CASH (BUY 승인 0건)",
      "",
      "| 점검 | 판정 |",
      "|---|---|",
      f"| 정규장 관찰 파일 | {'확보' if r['regular_snapshot_available'] else '미확보'} |",
      f"| 가격 수집 시간대 | {r['source_capture_window'] or '미확인'} |",
      f"| OHLC 유효성 확인 | {q.get('checked','미확인')}건 검사 / 오류 {q.get('invalid','미확인')}건 |",
      f"| 제공자 정규장 구간 보증 | {'확인' if r['provider_session_scope_verified'] else '미검증'} |",
      "| 외국인·기관 정규장 수급 | 별도 검증 필요 |",
      "| 섹터 TOP3 | 최종 판정 보류 |",
      "| 종목 TOP5 | 최종 판정 보류 |",
      "",
      "**보류 사유:** "+", ".join(r["blockers"]),
      "",
      "정규장 종가 확인 시점에 수집한 자료라도 데이터 공급원이 정규장 구간만 포함했는지는 별도 입증해야 합니다.",
      "애프터마켓 체결가·고저가·누적거래량을 정규장 값으로 수정·대체하지 않습니다.",
      "",
      "**Required Next Data:** 공급원 정규장 전용 시세 검증, 정규장 구간 외국인·기관 수급, 유효 일봉 65개 및 가격 구조.",
    ]
    return "\n".join(lines)+"\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--regular",required=True)
    p.add_argument("--date",default="")
    p.add_argument("--out",default="output")
    a=p.parse_args()
    src=Path(a.regular)
    try:snap=json.loads(src.read_text(encoding="utf-8"))
    except (OSError,TypeError,ValueError):snap={}
    day=a.date or nominal_regular_day(datetime.now(ZoneInfo("Asia/Seoul")))
    r=report(snap,day)
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    (out/"regular_only_final_status.json").write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out/"regular_only_final_mobile.md").write_text(markdown(r),encoding="utf-8")
    print(json.dumps({"asof":day,"status":r["market_source_status"],
        "capture":r["regular_snapshot_available"],"buy":0,"decision":"CASH"},
        ensure_ascii=False))

if __name__=="__main__":main()
