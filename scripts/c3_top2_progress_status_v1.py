"""C3 research status from existing machine-readable observations; no trade claims."""
import argparse,json,math
from pathlib import Path

def build(entry,impact):
    plans=entry["plans"]
    if len(plans)!=2 or len(impact["results"])!=2:
        raise ValueError("TOP2_COUNT_MISMATCH")
    if len({p["ticker"] for p in plans})!=2 or len({r["ticker"] for r in impact["results"]})!=2:
        raise ValueError("DUPLICATE_TOP2_TICKER")
    impact_by={r["ticker"]:r for r in impact["results"]}
    if set(impact_by)!={p["ticker"] for p in plans}:
        raise ValueError("TICKER_MISMATCH")
    results=[]
    for p in plans:
        ticker=p["ticker"]
        gap=float(impact_by[ticker]["max_provider_close_gap_pct"])
        if not math.isfinite(gap) or gap<0:
            raise ValueError("INVALID_PROVIDER_GAP:"+ticker)
        future=p.get("future_close_observations",{})
        if not isinstance(future,dict):
            raise ValueError("INVALID_FORWARD_OBSERVATIONS:"+ticker)
        for rows in future.values():
            if not isinstance(rows,list) or any(type(row.get("complete")) is not bool for row in rows):
                raise ValueError("INVALID_FORWARD_OBSERVATIONS:"+ticker)
        completed=sum(row["complete"] for rows in future.values() for row in rows)
        total=sum(len(rows) for rows in future.values())
        results.append(dict(ticker=ticker,
            observed_sessions=p["observed_sessions"],
            expected_sessions=p["expected_sessions"],
            observation_complete=p["observation_complete"],
            pullback_opportunities=p["pullback"]["opportunity_days"],
            retest_opportunities=p["breakout_retest"]["opportunity_days"],
            continuation_opportunities=p["breakout_without_pullback"]["opportunity_days"],
            forward_horizons_complete=completed,
            forward_horizons_total=total,
            max_provider_gap_pct=gap,
            price_certified=False))
    return dict(schema="C3_TOP2_PROGRESS_STATUS_V1",
        status="RESEARCH_ONLY",implementation_ci_verified=None,
        price_source_certified=False,official_session_calendar_verified=False,
        strategy_profitability_verified=False,trade_approved=False,orders_enabled=False,
        progress_percentage=None,
        note="PROGRESS_NOT_A_PERFORMANCE_SCORE",
        results=results)

def markdown(report):
    lines=["### C3 TOP2 개발·검증 현황 (자동 생성)",
           "| 종목 | 관찰/계획 | 눌림 | 재시험 | 돌파지속 | 사후기간 완료 | 최대 가격차 |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    for r in report["results"]:
        lines.append("| {} | {}/{} | {} | {} | {} | {}/{} | {:.3f}% |".format(
            r["ticker"],r["observed_sessions"],r["expected_sessions"],
            r["pullback_opportunities"],r["retest_opportunities"],
            r["continuation_opportunities"],r["forward_horizons_complete"],
            r["forward_horizons_total"],r["max_provider_gap_pct"]))
    lines.extend(["","- 구현: 진입기회·사후관찰·공급원 차이 분석",
                  "- 미완료: 공식 거래일·독립 가격 인증·수익성 검증",
                  "- 진행률: 수치 산정 보류 (기능 구현과 실전 신뢰도 분리)",
                  "> CASH / 신규매수 보류. 체결·주문·수익률 인증 아님."])
    return "\n".join(lines)+"\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--entry",required=True);p.add_argument("--impact",required=True)
    p.add_argument("--output",required=True);p.add_argument("--markdown",required=True)
    a=p.parse_args()
    result=build(json.loads(Path(a.entry).read_text(encoding="utf-8")),
                 json.loads(Path(a.impact).read_text(encoding="utf-8")))
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    Path(a.markdown).write_text(markdown(result),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
