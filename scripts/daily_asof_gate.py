"""Conservative same-session evidence gate for C3/K100 mobile reporting.

Reads unmodified GitHub Actions output from independent workflows.
Never upgrades technical research into a final trade recommendation.
"""
from __future__ import annotations

import argparse
import json
import csv
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from trade_approval_policy import BUY_REVIEW_SCORE_MIN, SCORE_MAX, evaluate_review
from c3_account_state import load_c3_position, c3_mobile_line
from krx_session_clock import nominal_last_completed_krx_session



def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def krx_common_tick_floor(value) -> int | None:
    """Research-only tick floor for ordinary KOSPI/KOSDAQ shares.

    Excludes ETFs/ETNs and securities with a different tick convention.
    This does not validate an executable limit order.
    """
    try:
        price = Decimal(str(value))
    except (ValueError, InvalidOperation):
        return None
    if not price.is_finite() or price <= 0:
        return None
    tick = 1
    for lower, size in (
        (2000, 5), (5000, 10), (20000, 50), (50000, 100),
        (200000, 500), (500000, 1000)
    ):
        if price >= lower:
            tick = size
        else:
            break
    return int((price / tick).to_integral_value(rounding=ROUND_FLOOR) * tick)


def research_candidate_from_csv(path: Path, tickers: list, day: str) -> dict:
    """Only a dated technical observation, never an approved trade."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
    except OSError:
        return {}
    for ticker in tickers[:5]:
        for row in rows:
            if (row.get("ticker") == ticker and row.get("snapshot_date") == day
                and row.get("structure_status") == "RESEARCH_GEOMETRY_PASS"
                and row.get("trade_approval") == "NO"):
                candidate = {key: row.get(key) for key in (
                    "ticker", "name", "snapshot_date", "close_reference", "atr14",
                    "entry1_close_reference", "entry2_ma20_proxy",
                    "structural_stop_reference", "no_chase_reference",
                    "prior_60d_resistance", "rr_to_prior_resistance",
                    "c3_preliminary_score", "k100_preliminary_score",
                    "blocking_reasons")}
                aligned = {
                    key + "_tick_floor": krx_common_tick_floor(candidate[key])
                    for key in ("close_reference", "entry1_close_reference",
                                "entry2_ma20_proxy", "structural_stop_reference",
                                "no_chase_reference")
                }
                # A malformed price must not become an apparently precise plan.
                if any(v is None for v in aligned.values()):
                    return {}
                if not (aligned["structural_stop_reference_tick_floor"]
                        < aligned["entry2_ma20_proxy_tick_floor"]
                        <= aligned["entry1_close_reference_tick_floor"]
                        <= aligned["no_chase_reference_tick_floor"]):
                    return {}
                candidate.update(aligned)
                try:
                    atr = Decimal(str(candidate["atr14"]))
                    first = Decimal(aligned["entry1_close_reference_tick_floor"])
                    second = Decimal(aligned["entry2_ma20_proxy_tick_floor"])
                    stop = Decimal(aligned["structural_stop_reference_tick_floor"])
                    if not atr.is_finite() or atr <= 0 or stop >= first:
                        return {}
                    separation = (first - second) / atr
                    stop_dist = (first - stop) / atr
                except (InvalidOperation, ValueError, TypeError):
                    return {}
                candidate["second_entry_spacing_atr"] = round(float(separation), 3)
                candidate["structural_stop_distance_atr"] = round(float(stop_dist), 3)
                # Exploratory only: a 2nd level essentially equal to the 1st
                # is not an independent pullback support. Do not pass it off
                # as a second executable entry. 0.25 ATR is a *diagnostic*
                # heuristic, never a validated profitable trading rule.
                candidate["second_entry_is_distinct_research"] = separation >= Decimal("0.25")
                candidate["second_entry_quality_warning"] = (
                    "SECOND_ENTRY_TOO_NEAR_FIRST_VS_ATR"
                    if separation < Decimal("0.25") else "")
                candidate["swing_stop_atr_warning"] = (
                    "SWING_STOP_WITHIN_ONE_DAILY_ATR"
                    if stop_dist < 1 else "")
                candidate["tick_aligned_research_only"] = True
                candidate["rr_after_tick_and_costs_verified"] = False
                return candidate
    return {}


def evaluate(day: str, recovery: dict, focus: dict, sector: dict, money: dict,
             research_candidate: dict | None = None,
             c3_state: dict | None = None,
             focus_source: str = "INDEPENDENT_WORKFLOW",
             regular: dict | None = None) -> dict:
    dates = {
        "recovery_krx_price": recovery.get("market_data_date"),
        "focus_price": focus.get("asof"),
        "sector_ranking": sector.get("asof"),
        "sector_constituent_flow": money.get("asof"),
    }
    reasons = []
    for key, source_day in dates.items():
        if source_day != day:
            reasons.append(f"{key.upper()}_NOT_TODAY:{source_day or 'MISSING'}")
    ratio = recovery.get("coverage_ratio")
    valid = recovery.get("valid_ohlcv")
    universe = recovery.get("universe")
    if not isinstance(ratio, (float, int)) or ratio < 0.95:
        reasons.append("PRICE_COVERAGE_BELOW_95_PERCENT_OR_MISSING")
    if not isinstance(valid, int) or not isinstance(universe, int) or valid > universe or universe <= 0:
        reasons.append("MARKET_UNIVERSE_COUNTS_MISSING_OR_INVALID")
    if recovery.get("candidate_date_mismatch") not in (False, 0, None):
        reasons.append("KRX_CANDIDATE_DATE_MISMATCH")
    if not focus:
        reasons.append("FOCUS_SOURCE_MISSING")
    elif focus.get("orders_enabled") is not False or focus.get("trade_approved") is not False:
        reasons.append("FOCUS_RESEARCH_ORDER_FLAG_NOT_SAFE")
    if focus_source=="SECTOR_FIRST_EMBEDDED_FALLBACK":
        reasons.append("FOCUS_SINGLE_PIPELINE_NOT_INDEPENDENT")
    if sector.get("orders_enabled") is not False or sector.get("trade_approved") is not False:
        reasons.append("SECTOR_RESEARCH_ORDER_FLAG_NOT_SAFE")
    if (sector.get("sector_selection_outcome")=="PENDING_DATA_VALIDATION" or
        sector.get("stock_selection_outcome")=="PENDING_DATA_VALIDATION"):
        reasons.append("SECTOR_STOCK_FINAL_SELECTION_PENDING_DATA")
    elif not sector.get("sector_top3") or not sector.get("stock_research_top5"):
        reasons.append("INDEPENDENT_SECTOR_OR_STOCK_EVIDENCE_INCOMPLETE")
    if money.get("market_ohlc_quality_verified") is False:
        reasons.append("MARKET_OHLC_SOURCE_CONFLICT")
    # 23 Oct incident: dated streams agreed, but date-only feed prices
    # differed and KRX regular 15:33-15:39 observation was missed.
    # Do not confuse same-day records with independently attested prices.
    regular = regular if isinstance(regular, dict) else {}
    price_parity = sector.get("source_price_parity")
    price_parity = price_parity if isinstance(price_parity, dict) else {}
    parity_status = price_parity.get("status", "NOT_PROVIDED")
    mismatch_count = price_parity.get("close_mismatches")
    overlap_count = price_parity.get("overlap_tickers")
    if not price_parity:
        reasons.append("CROSS_SOURCE_CLOSE_PARITY_NOT_PROVIDED")
    elif price_parity.get("asof") != day:
        reasons.append("CROSS_SOURCE_CLOSE_PARITY_DATE_MISMATCH")
    elif (parity_status != "CANDIDATE_CLOSES_MATCH_RESEARCH_ONLY"
          or mismatch_count != 0 or not isinstance(overlap_count, int)
          or overlap_count <= 0):
        reasons.append("CROSS_SOURCE_DAILY_CLOSE_CONFLICT_OR_UNVERIFIED")
    reg_status = str(regular.get("market_source_status") or "MISSING")
    reg_asof = regular.get("target_asof")
    regular_ok = bool(
        reg_asof == day
        and regular.get("mode") == "KRX_REGULAR_ONLY_0900_1530"
        and regular.get("after_market_excluded") is True
        and regular.get("regular_snapshot_available") is True
        and regular.get("provider_session_scope_verified") is True
        and reg_status == "REGULAR_PRICE_SOURCE_VERIFIED_RESEARCH_ONLY"
        and regular.get("blockers") == []
        and regular.get("trade_approved") is False
        and regular.get("decision") == "CASH"
    )
    if not regular:
        reasons.append("REGULAR_ONLY_REPORT_MISSING")
    elif reg_asof != day:
        reasons.append("REGULAR_ONLY_REPORT_ASOF_MISMATCH")
    elif not regular_ok:
        reasons.append("REGULAR_ONLY_PRICE_SOURCE_NOT_CERTIFIED")
    # Surface research watches without giving them executable prices.
    # The 23 Oct original sector and stock watchlists have missing catalysts,
    # weak breadth and no validated structural entry references.
    def safe_label(value):
        return str(value or "").replace("|", "/").replace("\n", " ").replace("\r", " ")[:48]
    watch_sectors = []
    if sector.get("asof") == day:
        for item in (sector.get("sector_top3") or [])[:3]:
            if not isinstance(item, dict) or item.get("buy_approval") not in ("NO", None):
                continue
            breadth = item.get("day_breadth_up_pct")
            if isinstance(breadth, bool) or not isinstance(breadth, (int, float)):
                breadth = None
            elif not 0 <= breadth <= 100:
                breadth = None
            watch_sectors.append({
                "rank": len(watch_sectors) + 1,
                "sector_id": safe_label(item.get("sector_id")),
                "name": safe_label(item.get("name")),
                "breadth_up_pct": breadth,
                "phase": safe_label(item.get("flow_phase")),
                "scope": "ETF_CONSTITUENT_RESEARCH_ONLY",
                "buy_approval": False,
            })
    watch_stocks = []
    if sector.get("asof") == day:
        for item in (sector.get("stock_research_top5") or [])[:5]:
            if not isinstance(item, dict) or item.get("buy_approval") not in ("NO", None):
                continue
            ticker = str(item.get("ticker") or "")
            if len(ticker) != 6 or not ticker.isdigit():
                continue
            watch_stocks.append({
                "rank": len(watch_stocks) + 1,
                "ticker": ticker, "name": safe_label(item.get("name")),
                "sector_id": safe_label(item.get("sector_id")),
                "final_verified_score": None,
                "structural_order_level_verified": False,
                "trade_approved": False,
            })
    # Research-only evidence, even if every source's calendar date agrees.
    # Final 80pt trade-score, live entry trigger, cash and existing holdings
    # are not independently verified by these free end-of-day files.
    reasons.append("FINAL_80_LIVE_ENTRY_CASH_HOLDINGS_NOT_VERIFIED")
    names = {
        "NOT_TODAY": "자료 기준일 불일치",
        "FINAL_80": "최종점수·실시간 타점·계좌 검증 누락",
    }
    return {
        "schema": "c3_k100_today_asof_gate_v2",
        "score_scale_max": SCORE_MAX,
        "final_score_threshold": BUY_REVIEW_SCORE_MIN,
        "final_score_verified": False,
        "manual_review_gate": evaluate_review(None, {}, cost_adjusted_rr=None),
        "target_kst_date": day,
        "target_session_semantics": "MOST_RECENT_NOMINAL_COMPLETED_KRX_WEEKDAY_NOT_HOLIDAY_VERIFIED",
        "source_dates": dates,
        "recovery_universe": universe,
        "recovery_valid_ohlcv": valid,
        "recovery_coverage_ratio": ratio,
        "recovery_research_geometry_pass": recovery.get("geometry_pass_count"),
        "recovery_research_watch_tickers": recovery.get("c3_research_top5", [])[:5],
        "today_research_candidate": research_candidate or {},
        "focus_research_count": focus.get("research_count"),
        "focus_stop_reference_count": focus.get("stop_reference_count"),
        "focus_source": focus_source,
        "all_independent_sources_verified": bool(
            all(x == day for x in dates.values())
            and focus_source == "INDEPENDENT_WORKFLOW"
            and money.get("market_ohlc_quality_verified") is True
            and regular_ok
            and price_parity.get("independent_provider_verified") is True
            and price_parity.get("close_mismatches") == 0
            and price_parity.get("asof") == day),
        "research_source_dates_aligned": all(x == day for x in dates.values()),
        "regular_only_price_verified": regular_ok,
        "regular_report_asof": reg_asof,
        "regular_source_status": reg_status,
        "regular_source_blockers": regular.get("blockers", []),
        "recovery_vs_sector_price_parity_status": parity_status,
        "price_parity_overlap_count": overlap_count,
        "price_parity_mismatch_count": mismatch_count,
        "price_parity_independent_provider_verified": (
            price_parity.get("independent_provider_verified") is True),
        "sector_research_top3_count": len(sector.get("sector_top3") or []),
        "sector_research_top5_count": len(sector.get("stock_research_top5") or []),
        "sector_research_watch": watch_sectors,
        "stock_research_watch": watch_stocks,
        "sector_watch_breadth_ge_60_count": sum(
            x["breadth_up_pct"] is not None and x["breadth_up_pct"] >= 60
            for x in watch_sectors),
        "sector_selection_outcome": sector.get("sector_selection_outcome","PENDING_DATA_VALIDATION"),
        "stock_selection_outcome": sector.get("stock_selection_outcome","PENDING_DATA_VALIDATION"),
        "c3_position_state": c3_state or {"status":"POSITION_UNVERIFIED","user_reported":False},
        "market_ohlc_quality_verified": money.get("market_ohlc_quality_verified"),
        "market_ohlc_checked": money.get("raw_tradable_ohlc_checked"),
        "market_ohlc_invalid": money.get("raw_ohlc_conflict_count"),
        "market_ohlc_invalid_pct": money.get("raw_ohlc_conflict_pct"),
        "all_source_dates_aligned": all(x == day for x in dates.values()),
        "data_integrity_blockers": reasons,
        "decision": "CASH",
        "trade_approved": False,
        "orders_enabled": False,
        "live_market_order_not_generated": True,
        "note": "Historical research references are not today's executable quotes. No estimated win rate, no backfilled trade.",
    }


def to_markdown(data: dict) -> str:
    src = data["source_dates"]
    ratio = data["recovery_coverage_ratio"]
    pct = f"{100 * ratio:.1f}%" if isinstance(ratio, (int, float)) else "미확인"
    def fmt(value):
        return value if value is not None else "미확인"
    watch = ", ".join(data["recovery_research_watch_tickers"]) or "없음"
    reason_lines = "\n".join(f"- {x}" for x in data["data_integrity_blockers"])
    candidate = data.get("today_research_candidate", {})
    watch_sectors = data.get("sector_research_watch") or []
    watch_stocks = data.get("stock_research_watch") or []
    watch_section = ("\n## 섹터 TOP3 (ETF 구성종목 연구 · 미승인)\n\n"
        "| 순위 | 섹터 | 상승확산 | 분류 |\n|---|---|---:|---|\n")
    for item in watch_sectors:
        breadth = item.get("breadth_up_pct")
        watch_section += (f"| {item['rank']} | {item['name']} | "
             f"{breadth:.1f}% | {item['phase']} |\n"
             if isinstance(breadth, (int, float)) else
             f"| {item['rank']} | {item['name']} | 미확인 | {item['phase']} |\n")
    if not watch_sectors:
        watch_section += "| - | 검증 가능한 연구 목록 없음 | - | - |\n"
    watch_section += (f"\n상승확산 60% 이상: "
        f"{data.get('sector_watch_breadth_ge_60_count', 0)}/{len(watch_sectors)}개."
        " 이는 TOP3 강세 확인이 아닙니다.\n"
        "\n## 종목 TOP5 (연구순위 · 미승인)\n\n"
        "| 순위 | 종목 | 섹터 | 타점 |\n|---|---|---|---|\n")
    for item in watch_stocks:
        watch_section += (f"| {item['rank']} | {item['name']} ({item['ticker']}) | "
             f"{item['sector_id']} | 일봉 구조가격·원본 검증 대기 |\n")
    if not watch_stocks:
        watch_section += "| - | 검증 가능한 연구 목록 없음 | - | - |\n"
    watch_section += ("\n**이 표의 연구순위는 최종 80점이나 5거래일 "
        "상승확률이 아닙니다.** 종가 불일치가 해소되기 전 개별 매매가격은 사용 금지.\n")
    if candidate:
        research_line = (f"**오늘 확인한 기술 연구후보:** {candidate['name']} ({candidate['ticker']}) · "
            f"종가 {candidate['close_reference_tick_floor']:,}원 · 1차 {candidate['entry1_close_reference_tick_floor']:,}원 · "
            f"2차 {'연구 보류(간격 '+str(candidate['second_entry_spacing_atr'])+'ATR)' if not candidate['second_entry_is_distinct_research'] else format(candidate['entry2_ma20_proxy_tick_floor'], ',')+'원(연구)'} · "
            f"구조손절 {candidate['structural_stop_reference_tick_floor']:,}원(진입 대비 {candidate['structural_stop_distance_atr']}ATR; 손절 안정성 미검증) · "
            f"추격금지 {candidate['no_chase_reference_tick_floor']:,}원 · 추격상한 기준 원본 R:R {candidate['rr_to_prior_resistance']} (호가·비용 후 재검증 필요) · "
            f"C3 예비점수 {candidate['c3_preliminary_score']}점(최종80점 승인 아님) · "
            f"차단: {candidate['blocking_reasons']}. 가격은 한국거래소 일반주식 호가단위로 내림한 연구 참고치(매수·손절 주문 미승인)입니다.")
    else:
        research_line = "**오늘 확인한 기술 연구후보:** 검증된 당일 연구 행 없음"
    return f"""# 📅 {data['target_kst_date']} 종가 기준 C3·K100 데이터 교차검증

*장전·주말 실행은 직전 완료 거래일을 대상으로 합니다. 실제 휴장일과 원본 수집 완료 여부는 별도로 검증하며, 일치하지 않으면 매수를 승인하지 않습니다.*

🚦 **신규매수: CASH (0건 승인)**

🎯 오늘 할 일: 종목 연구가격과 매수 승인 구분. 날짜 불일치가 해소되고 80점·실행가격·자금이 검증되기 전 신규 주문 보류.

| 자료 출처 | 실제 자료 기준일 | 대상 완료 거래일 일치 |
|---|---|---|
| KRX 전종목 종가/기술스크리닝 | {fmt(src['recovery_krx_price'])} | {'확인' if src['recovery_krx_price']==data['target_kst_date'] else '불일치'} |
| 관심종목 일봉 구조가격 | {fmt(src['focus_price'])} ({data.get('focus_source','미확인')}) | {'확인' if src['focus_price']==data['target_kst_date'] else '불일치'} |
| 섹터 TOP3 선정 | {fmt(src['sector_ranking'])} | {'확인' if src['sector_ranking']==data['target_kst_date'] else '불일치'} |
| 섹터 구성종목 수급 | {fmt(src['sector_constituent_flow'])} | {'확인' if src['sector_constituent_flow']==data['target_kst_date'] else '불일치'} |

**KRX 데이터 커버리지:** {fmt(data['recovery_valid_ohlcv'])}/{fmt(data['recovery_universe'])} ({pct})
**OHLC 내부 일관성:** {str(data.get('market_ohlc_invalid'))+' / '+str(data.get('market_ohlc_checked'))+'건 ('+str(data.get('market_ohlc_invalid_pct'))+'%)' if data.get('market_ohlc_invalid') is not None else '수치 미확보'} · {'형식 검사 통과(공급원 독립 검증 아님)' if data.get('market_ohlc_quality_verified') is True else '형식 검사 실패/미확인'}
**종목별 일봉 출처 대조:** {fmt(data.get('recovery_vs_sector_price_parity_status'))} · 중복 {fmt(data.get('price_parity_overlap_count'))}종목 중 종가 불일치 {fmt(data.get('price_parity_mismatch_count'))}종목
**정규장 전용 가격 인증:** {'인증 연구 단계' if data.get('regular_only_price_verified') else '미완료'} · 상태 {fmt(data.get('regular_source_status'))} / 기준일 {fmt(data.get('regular_report_asof'))}
**독립 원본 출처 교차확인:** {'완료' if data.get('all_independent_sources_verified') else '미완료 (날짜 일치 및 같은 공급원 내부 일관성은 인증이 아님)'}
**중요:** 수집 워크플로 실행 성공·날짜 일치·OHLC 내부 유효성만으로 정규장 가격을 인증하지 않습니다.
**일봉 연구 구조 통과:** {fmt(data['recovery_research_geometry_pass'])}건 · 연구 티커 {watch}
{research_line}
**TOP3 판정:** {data.get('sector_selection_outcome','PENDING_DATA_VALIDATION')} · **TOP5 판정:** {data.get('stock_selection_outcome','PENDING_DATA_VALIDATION')} (보류와 검증 후 0개를 구분)
{watch_section}
{c3_mobile_line(data.get('c3_position_state') or {})}
**최종 검증 80점·매수승인:** 0건 (독립 검증 미완료)

## 이번 실행의 매수 차단 사유
{reason_lines}

**기존 보유주:** C3와 K100 별도 관리, 이 파일만으로 매도·손절·추가매수를 지시하지 않음.

**Required Next Data:** 공식 정규장 가격/65일 일봉 인증, 당일 섹터 거래대금·상승확산, 공식 기업 호재·실적, 구조손절·실시간 진입 트리거·실제 주문가능현금. 외국인·기관 수급은 선택적 보조 지표.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--recovery-structure", type=Path, required=False)
    parser.add_argument("--recovery-csv", type=Path, required=False)
    parser.add_argument("--focus", type=Path, required=True)
    parser.add_argument("--focus-fallback",type=Path,required=False)
    parser.add_argument("--sector", type=Path, required=True)
    parser.add_argument("--money", type=Path, required=True)
    parser.add_argument("--regular", type=Path, required=False,
                        help="Read-only REGULAR-only final source status")
    parser.add_argument("--date", default=None)
    parser.add_argument("--out", type=Path, default=Path("output"))
    parser.add_argument("--c3-state", type=Path, default=Path("config/c3_position_state.json"))
    args = parser.parse_args()
    target_day = args.date or nominal_last_completed_krx_session(
        datetime.now(ZoneInfo("Asia/Seoul")))
    recovery = load_json(args.recovery)
    structure = load_json(args.recovery_structure) if args.recovery_structure else {}
    for field in ("geometry_pass_count", "c3_research_top5", "k100_research_top5"):
        if field in structure:
            recovery[field] = structure[field]
    candidate = (research_candidate_from_csv(args.recovery_csv,
                 recovery.get("c3_research_top5", []), target_day)
                 if args.recovery_csv else {})
    focus=load_json(args.focus)
    focus_source="INDEPENDENT_WORKFLOW" if focus else "MISSING"
    if not focus and args.focus_fallback:
        embedded=load_json(args.focus_fallback)
        if embedded:
            focus=embedded
            focus_source="SECTOR_FIRST_EMBEDDED_FALLBACK"
    result = evaluate(target_day, recovery, focus,
                      load_json(args.sector), load_json(args.money), candidate,
                      load_c3_position(args.c3_state), focus_source,
                      load_json(args.regular) if args.regular else {})
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "today_asof_gate.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.out / "today_asof_mobile.md").write_text(to_markdown(result), encoding="utf-8")
    print(json.dumps({"date": target_day, "decision": "CASH",
                      "aligned": result["all_source_dates_aligned"],
                      "blocker_count": len(result["data_integrity_blockers"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
