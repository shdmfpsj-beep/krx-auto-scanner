#!/usr/bin/env python3
"""v6.18 research-only global/US + dated domestic v6.17 + watch-five fusion.

Only a snapshot integration. Frozen October23 archives are NOT a substitute
for the next KRX regular-session scan or broker order. No automatic trades.
"""
from __future__ import annotations
import argparse,csv,json
from datetime import date,datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from forward_ledger_v63 import digest,read_csv
from global_macro_risk_v618 import SCHEMA as GSCHEMA
KST=ZoneInfo("Asia/Seoul")
SCHEMA="C3_K100_V618_WORLD_KRX_READ_ONLY_FUSION"

def previous_weekday(today):
    day=today-timedelta(days=1)
    while day.weekday()>=5:day-=timedelta(days=1)
    return day

def expected_domestic_session(now):
    day=now.date()
    if day.weekday()>=5 or now.hour<15 or (now.hour==15 and now.minute<30):
        return previous_weekday(day)
    return day

def fuse(global_report,domestic_rows,candidates,now):
    if now.tzinfo is None:raise ValueError("V618_FUSION_KST_REQUIRED")
    local=now.astimezone(KST)
    if (global_report.get("schema")!=GSCHEMA or
        global_report.get("trade_approved") is not False or
        global_report.get("orders_enabled") is not False or
        global_report.get("krx_session_data_included") is not False):
        raise ValueError("V618_NO_TRADE_MACRO_PARENT_REQUIRED")
    latest=max(domestic_rows,key=lambda r:r["asof"]) if domestic_rows else None
    domestic_day=date.fromisoformat(latest["asof"]) if latest else None
    expect=expected_domestic_session(local)
    domestic_ready=domestic_day==expect
    # Holidays require a certified exchange calendar; this weekday-only
    # expectation can incorrectly flag a holiday as stale. It NEVER promotes BUY.
    domestic_status=latest["risk_mode"] if domestic_ready else "DOMESTIC_ARCHIVE_STALE_OR_UNAVAILABLE"
    usday=global_report.get("us_last_session")
    usdate=date.fromisoformat(usday) if usday else None
    global_ready=bool(usdate and usdate<=local.date() and (local.date()-usdate).days<=5)
    global_regime=global_report["regime"] if global_ready else "GLOBAL_MISSING_OR_STALE"
    priority=("CASH_DOMESTIC_RISK" if domestic_ready and domestic_status.startswith("RED")
        else "CASH_DOMESTIC_SOURCE_PENDING" if not domestic_ready
        else "CASH_GLOBAL_RISK" if global_regime=="GLOBAL_RISK_OFF_RESEARCH_ONLY"
        else "CASH_GLOBAL_SOURCE_PENDING" if not global_ready or "INCOMPLETE" in global_regime
        else "CASH_DURING_CAUTION_RESEARCH_ONLY" if "CAUTION" in global_regime
        else "CASH_FINAL_GATES_UNVERIFIED")
    unique=[];seen=set()
    if domestic_ready:
        for r in candidates:
            if r["asof"]!=latest["asof"] or r["ticker"] in seen:continue
            if r["trade_approved"]!="False" or r["orders_enabled"]!="False":
                raise ValueError("V618_CANDIDATE_FALSE_BUY_POLICY_VIOLATED")
            seen.add(r["ticker"])
            unique.append(dict(ticker=r["ticker"],name=r["name"],
                asof=r["asof"],research_method=r["method"],
                research_tier=r["classification"],
                last_research_score_not_final80=r["discovery_index_only"],
                study_entry_not_a_order=r["first_limit_study"],
                study_pivot_stop_not_live_order=r["structure_stop_study"],
                action="NO_ORDER_RESEARCH_ONLY"))
            if len(unique)==5:break
    return dict(schema=SCHEMA,assessment_at_kst=local.isoformat(timespec="seconds"),
        expected_regular_day_no_holiday_attestation=expect.isoformat(),
        domestic_source_date=domestic_day.isoformat() if domestic_day else None,
        domestic_source_same_expected_date=domestic_ready,
        domestic_risk=domestic_status,
        US_macro_source_date=usday,US_macro_source_fresh_for_research=global_ready,
        US_macro_regime=global_regime,
        global_group_breakdown=global_report.get("group_classifications",{}),
        foreign_institution_flow_required_for_buys=False,
        research_watch5=unique,
        observed_approval_count=0,
        no_aftermarket_mixing=True,account_cash_verified=False,
        regular_only_PIT_verified=False,final_stock_80_verified=False,
        fee_adjusted_two_R_verified=False,brokers_orders_placed=False,
        recommendation=priority,trade_approved=False,orders_enabled=False)

def render(r):
    lines=["# C3·K100 미국증시·글로벌 매크로 + 국내 위험 통합 의사결정","",
           "**최종: "+r["recommendation"]+" / 신규주문 0건**","",
       "- 국내 정규장 연구 최신일: "+str(r["domestic_source_date"]),
       "- 미국 ETF/매크로 완료일: "+str(r["US_macro_source_date"]),
       "- 국내 시장 위험: **"+r["domestic_risk"]+"**",
       "- 미국·세계 거시 위험: **"+r["US_macro_regime"]+"**",
       "- 개별 KRX 정규장 09:00~15:30 가격·과거 65봉·최종 점수/계좌는 별도 인증 필요",
       "","## 연구 Top5 (기술 감시이며 매수신호 아님)","",
       "| 종목 | 방법 | 등급 | 참고 진입가 | 일봉 손절참조 |",
       "|---|---|---|---:|---:|"]
    for z in r["research_watch5"]:
        lines.append("| {} ({}) | {} | {} | {} | {} |".format(
          z["name"],z["ticker"],z["research_method"],z["research_tier"],
          z["study_entry_not_a_order"],z["study_pivot_stop_not_live_order"]))
    if not r["research_watch5"]:lines.append("| 최신일 연구후보 미확보 | — | — | — | — |")
    lines+=["","**중요:** C등급 연구 참고 가격은 증권사 지정가/손절가로 사용 불가; 공식 호가단위·정규장 출처 확인 전 소수점 가격도 그대로 출력된 미검증 연구값입니다.",
      "기존 제약/바이오 제외, C3 1종목 원칙·물타기 금지, K100 Core/Tactical 분리 유지.",
      "**Required Next Data:** 최근 정규장 15:30 독립 검증, 국가별 최신 공개 환율/금리 최초 발표시각, 실제 매수가능 현금/보유·최종 종목 80점."]
    return "\n".join(lines)+"\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--macro",type=Path,required=True)
    p.add_argument("--domestic",type=Path,required=True)
    p.add_argument("--watch",type=Path,required=True)
    p.add_argument("--at-kst",required=True)
    p.add_argument("--outdir",type=Path,required=True)
    a=p.parse_args()
    m=json.loads(a.macro.read_text(encoding="utf-8"))
    domestic=read_csv(a.domestic);watch=read_csv(a.watch)
    out=fuse(m,domestic,watch,datetime.fromisoformat(a.at_kst))
    a.outdir.mkdir(parents=True,exist_ok=True)
    (a.outdir/"v618_world_krx_fusion_status.json").write_text(
        json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (a.outdir/"v618_world_krx_fusion_mobile.md").write_text(render(out),encoding="utf-8")
    print("V618_WORLD_KRX_FUSION",json.dumps({
       k:out[k] for k in ("domestic_risk","US_macro_regime","recommendation","domestic_source_date","trade_approved")},ensure_ascii=False))
if __name__=="__main__":main()
