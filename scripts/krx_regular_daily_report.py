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

def report(snapshot,day,kis_audit=None):
    snap=snapshot if isinstance(snapshot,dict) else {}
    probe=kis_audit if isinstance(kis_audit,dict) else {}
    probe_date=str(probe.get("date",""))
    probe_date_valid=(probe_date==day.replace("-",""))
    probe_results=probe.get("regular_reconstructions") or []
    valid_probes=([r for r in probe_results
                   if isinstance(r,dict)
                   and r.get("asof")==probe_date
                   and r.get("market_code")=="J"
                   and r.get("regular_ohlcv_reconstruction_verified") is True
                   and r.get("trade_approved") is False
                   and isinstance(r.get("regular_ohlcv"),dict)]
                  if probe_date_valid and isinstance(probe_results,list) else [])
    audited=probe.get("audited_tickers") or []
    kis_probe_status=("NOT_CONNECTED" if not probe else
                      "SOURCE_ASOF_MISMATCH" if not probe_date_valid else
                      "REGULAR_MINUTE_PRICE_SUBSET_OBSERVED" if valid_probes else
                      probe.get("data_status","PENDING_MARKET_DATA_VALIDATION"))
    blockers=assess_capture(snap) if snap else ["SNAPSHOT_MISSING"]
    if snap.get("asof")!=day:blockers.append("REGULAR_SOURCE_ASOF_MISMATCH")
    if snap.get("trade_session")!=REGULAR or snap.get("phase")!="regular":
        blockers.append("REGULAR_SESSION_REQUIRED")
    if snap.get("regular_strategy_eligible") is not True:blockers.append("REGULAR_ONLY_SOURCE_NOT_CERTIFIED")
    if snap.get("trade_approved") is not False:blockers.append("READ_ONLY_ORDER_SAFETY_UNKNOWN")
    if snap.get("orders_enabled") is not False:blockers.append("READ_ONLY_ORDER_SAFETY_UNKNOWN")
    # Investor-category net buying is a useful optional confirmation, not
    # a prerequisite for studying strong price/turnover/breadth/entry setups.
    # Never infer foreign/institution buying from volume or increasing price.
    # Separate source price verification from full strategy score validation.
    blockers=list(dict.fromkeys(blockers))
    return dict(schema="krx_regular_only_daily_v1",target_asof=day,
        regular_snapshot_asof=snap.get("asof"),
        mode="KRX_REGULAR_ONLY_0900_1530",
        after_market_excluded=True,
        market_source_status="PENDING_DATA_VALIDATION" if blockers else "REGULAR_PRICE_SOURCE_VERIFIED_RESEARCH_ONLY",
        investor_flow_policy="OPTIONAL_CONFIRMATION_NOT_BUY_GATE",
        investor_flow_data_status="NOT_PROVIDED",
        mandatory_remaining_evidence=["SECTOR_TURNOVER_BREADTH_NOT_VERIFIED",
               "REGULAR_65_DAY_HISTORY_NOT_VERIFIED",
               "STRUCTURAL_ENTRY_AND_FINAL_SCORE_NOT_VERIFIED",
               "ACCOUNT_AND_MARKET_GATES_NOT_VERIFIED"],
        source_capture_window=snap.get("capture_window"),
        regular_snapshot_available=bool(snap.get("stocks")),
        provider_session_scope_verified=snap.get("provider_session_scope_verified") is True,
        regular_quality=snap.get("quality") or {},
        kis_krx_minute_price_probe=dict(status=kis_probe_status,
          asof=probe_date or None,market="J:KRX",audited_tickers=audited,
          verified_subset_count=len(valid_probes),
          ticker_samples=[dict(ticker=r.get("ticker"),
             ohlcv=r.get("regular_ohlcv"),
             minute_count=r.get("minutes_seen")) for r in valid_probes],
          market_wide_validated=False,investor_flow_validated=False,
          strategy_price_source_authorized=False),
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
      "| 외국인·기관 정규장 수급 | **선택적 확인 지표 (미제공 시 감점·추정 금지)** |",
      "| 공식 KIS KRX 분봉 교차검증 | "+str(r.get("kis_krx_minute_price_probe",{}).get("status"))+
        " / 유효 종목 "+str(r.get("kis_krx_minute_price_probe",{}).get("verified_subset_count",0))+"개 |",
      "| 섹터 TOP3 | 최종 판정 보류 |",
      "| 종목 TOP5 | 최종 판정 보류 |",
      "",
      "**가격 원본 보류 사유:** "+(", ".join(r["blockers"]) if r["blockers"] else "없음"),
      "**매매전략 미검증 항목:** "+", ".join(r["mandatory_remaining_evidence"]),
      "",
      "정규장 종가 확인 시점에 수집한 자료라도 데이터 공급원이 정규장 구간만 포함했는지는 별도 입증해야 합니다.",
      "애프터마켓 체결가·고저가·누적거래량을 정규장 값으로 수정·대체하지 않습니다.",
      "KIS 분봉이 있더라도 일부 종목의 정규장 가격 교차검증 용도이며 시장 전체 수급 또는 매수 신호가 아닙니다.",
      "",
      "**Required Next Data:** 정규장 원본 가격 인증, 정규장 거래대금·섹터 확산, 유효 일봉 65개/구조손절/손익비 검증.",
    ]
    return "\n".join(lines)+"\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--regular",required=True)
    p.add_argument("--kis-audit",default="")
    p.add_argument("--date",default="")
    p.add_argument("--out",default="output")
    a=p.parse_args()
    src=Path(a.regular)
    try:snap=json.loads(src.read_text(encoding="utf-8"))
    except (OSError,TypeError,ValueError):snap={}
    day=a.date or nominal_regular_day(datetime.now(ZoneInfo("Asia/Seoul")))
    probe={}
    if a.kis_audit:
        try:probe=json.loads(Path(a.kis_audit).read_text(encoding="utf-8"))
        except (OSError,ValueError,TypeError):pass
    r=report(snap,day,probe)
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    (out/"regular_only_final_status.json").write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out/"regular_only_final_mobile.md").write_text(markdown(r),encoding="utf-8")
    print(json.dumps({"asof":day,"status":r["market_source_status"],
        "capture":r["regular_snapshot_available"],"buy":0,"decision":"CASH"},
        ensure_ascii=False))

if __name__=="__main__":main()
