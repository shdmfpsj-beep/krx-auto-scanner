"""Conservative same-session evidence gate for C3/K100 mobile reporting.

Reads unmodified GitHub Actions output from independent workflows.
Never upgrades technical research into a final trade recommendation.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def evaluate(day: str, recovery: dict, focus: dict, sector: dict, money: dict) -> dict:
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
    if focus.get("orders_enabled") is not False or focus.get("trade_approved") is not False:
        reasons.append("FOCUS_RESEARCH_ORDER_FLAG_NOT_SAFE")
    if sector.get("orders_enabled") is not False or sector.get("trade_approved") is not False:
        reasons.append("SECTOR_RESEARCH_ORDER_FLAG_NOT_SAFE")
    if not sector.get("sector_top3") or not sector.get("stock_research_top5"):
        reasons.append("INDEPENDENT_SECTOR_OR_STOCK_EVIDENCE_INCOMPLETE")
    # Research-only evidence, even if every source's calendar date agrees.
    # Final 85pt trade-score, live entry trigger, cash and existing holdings
    # are not independently verified by these free end-of-day files.
    reasons.append("FINAL_85_LIVE_ENTRY_CASH_HOLDINGS_NOT_VERIFIED")
    names = {
        "NOT_TODAY": "자료 기준일 불일치",
        "FINAL_85": "최종점수·실시간 타점·계좌 검증 누락",
    }
    return {
        "schema": "c3_k100_today_asof_gate_v1",
        "target_kst_date": day,
        "source_dates": dates,
        "recovery_universe": universe,
        "recovery_valid_ohlcv": valid,
        "recovery_coverage_ratio": ratio,
        "recovery_research_geometry_pass": recovery.get("geometry_pass_count"),
        "recovery_research_watch_tickers": recovery.get("c3_research_top5", [])[:5],
        "focus_research_count": focus.get("research_count"),
        "focus_stop_reference_count": focus.get("stop_reference_count"),
        "sector_research_top3_count": len(sector.get("sector_top3") or []),
        "sector_research_top5_count": len(sector.get("stock_research_top5") or []),
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
    return f"""# 📅 {data['target_kst_date']} C3·K100 실제 데이터 교차검증

🚦 **신규매수: CASH (0건 승인)**

🎯 오늘 할 일: 종목 연구가격과 매수 승인 구분. 날짜 불일치가 해소되고 85점·실행가격·자금이 검증되기 전 신규 주문 보류.

| 독립 자료 | 실제 자료 기준일 | 오늘 날짜 일치 |
|---|---|---|
| KRX 전종목 종가/기술스크리닝 | {fmt(src['recovery_krx_price'])} | {'확인' if src['recovery_krx_price']==data['target_kst_date'] else '불일치'} |
| 관심종목 일봉 구조가격 | {fmt(src['focus_price'])} | {'확인' if src['focus_price']==data['target_kst_date'] else '불일치'} |
| 섹터 TOP3 선정 | {fmt(src['sector_ranking'])} | {'확인' if src['sector_ranking']==data['target_kst_date'] else '불일치'} |
| 섹터 구성종목 수급 | {fmt(src['sector_constituent_flow'])} | {'확인' if src['sector_constituent_flow']==data['target_kst_date'] else '불일치'} |

**KRX 데이터 커버리지:** {fmt(data['recovery_valid_ohlcv'])}/{fmt(data['recovery_universe'])} ({pct})
**일봉 연구 구조 통과:** {fmt(data['recovery_research_geometry_pass'])}건 · 연구 티커 {watch}
**최종 검증 85점·매수승인:** 0건 (독립 검증 미완료)

## 이번 실행의 매수 차단 사유
{reason_lines}

**기존 보유주:** C3와 K100 별도 관리, 이 파일만으로 매도·손절·추가매수를 지시하지 않음.

**Required Next Data:** 당일 완료 섹터·기관/외국인 수급, 공식 기업 호재·실적, 실시간 진입 트리거·실제 주문가능현금.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--focus", type=Path, required=True)
    parser.add_argument("--sector", type=Path, required=True)
    parser.add_argument("--money", type=Path, required=True)
    parser.add_argument("--date", default=None)
    parser.add_argument("--out", type=Path, default=Path("output"))
    args = parser.parse_args()
    target_day = args.date or datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    result = evaluate(target_day, load_json(args.recovery), load_json(args.focus),
                      load_json(args.sector), load_json(args.money))
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
