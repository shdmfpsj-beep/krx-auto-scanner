"""C3 prospective entry-style opportunity comparison (read-only research).

Daily OHLC touches are opportunities, never verified fills. Breakout retest
requires a PRIOR completed session above the registered source close.
"""
import argparse
import csv
import json
from pathlib import Path
from c3_price_concordance_v1 import read_rows
from c3_entry_geometry_research_v1 import review

def evaluate(plan, prices):
    g=review(plan)
    code=plan["ticker"]
    dates=sorted((day,b) for (ticker,day),b in prices.items()
                 if ticker==code and day>plan["registered_day"])
    horizon=int(plan.get("expires_after_sessions") or 5)
    if horizon<1:
        raise ValueError("INVALID_HORIZON")
    window=dates[:horizon]
    low,high=g["watch_low"],g["watch_high"]
    breakout_level=g["source_close"]
    pullback=[]
    retest=[]
    breakout_confirmed=False
    breakout_without_pullback=[]
    first_signal_close={}
    prior_close_above=False
    for day,b in window:
        touches=b["low"]<=high and b["high"]>=low
        if touches:
            pullback.append(day)
            first_signal_close.setdefault('pullback',(day,b['close']))
            if breakout_confirmed:
                retest.append(day)
                first_signal_close.setdefault('breakout_retest',(day,b['close']))
        # A prior completed close above the anchor plus a full session above
        # the watch band indicates missed pullback opportunity, not a fill.
        if prior_close_above and b["low"]>high:
            breakout_without_pullback.append(day)
            first_signal_close.setdefault('breakout_without_pullback',(day,b['close']))
        # Confirmation uses completed close; same-day high cannot qualify.
        if b["close"]>breakout_level:
            breakout_confirmed=True
        prior_close_above=b["close"]>breakout_level
    # Same-day OHLC ordering is unknown: use only later completed sessions.
    future_observations={}
    for style,(signal_day,signal_close) in first_signal_close.items():
        subsequent=[(day,bar) for day,bar in dates if day>signal_day]
        future_observations[style]=[]
        for n in (5,10,20):
            complete=len(subsequent)>=n
            future_observations[style].append(dict(
                signal_day=signal_day,signal_close=signal_close,
                horizon_sessions=n,observed_sessions=min(len(subsequent),n),
                horizon_day=subsequent[n-1][0] if complete else None,
                complete=complete,
                observation_close_return_pct=(round(100*(subsequent[n-1][1]["close"]/signal_close-1),4) if complete else None),
                strategy_return_pct=None,verified_fill=False))
    return dict(plan_id=plan["plan_id"],ticker=code,
                observed_sessions=len(window),expected_sessions=horizon,
                observation_complete=len(window)>=horizon,
                pullback=dict(first_opportunity=pullback[0] if pullback else None,
                              opportunity_days=len(pullback),
                              actual_fill_verified=False),
                breakout_retest=dict(first_opportunity=retest[0] if retest else None,
                                     opportunity_days=len(retest),
                                     requires_prior_close_above_source=True,
                                     actual_fill_verified=False),
                breakout_without_pullback=dict(first_opportunity=breakout_without_pullback[0] if breakout_without_pullback else None,
                                               opportunity_days=len(breakout_without_pullback),
                                               requires_prior_completed_close=True,
                                               actual_fill_verified=False),
                future_close_observations=future_observations,
                first_resistance_verified=False,
                trade_approved=False,orders_enabled=False,
                note="OPPORTUNITY_ONLY_NO_EXECUTION_OR_RETURN_CLAIMS")

def build(plans,prices):
    items=list(plans)
    if len(items)!=2:
        raise ValueError("EXPECTED_EXACTLY_TWO_PLANS")
    return dict(schema="C3_ENTRY_STYLE_OPPORTUNITY_COMPARISON_V1",
                plans=[evaluate(p,prices) for p in items],
                independent_price_verified=False,
                trade_approved=False,orders_enabled=False)

def markdown_table(report):
    lines=["### TOP2 진입 방식별 관찰 기회 (체결 아님)",
           "| 종목 | 관찰일 | 눌림목 | 돌파 재시험 | 눌림 없는 돌파 지속 |",
           "|---|---:|---:|---:|---:|"]
    for p in report["plans"]:
        lines.append("| {} | {}/{} | {} | {} | {} |".format(
            p["ticker"],p["observed_sessions"],p["expected_sessions"],
            p["pullback"]["opportunity_days"],p["breakout_retest"]["opportunity_days"],
            p["breakout_without_pullback"]["opportunity_days"]))
    lines.extend(["","### 최초 진입 신호 이후 종가 변화 (수익률 아님)",
                  "| 종목 | 방식 | 신호일 | 5일 | 10일 | 20일 |",
                  "|---|---|---|---:|---:|---:|"])
    names={"pullback":"눌림","breakout_retest":"재시험","breakout_without_pullback":"돌파지속"}
    for p in report["plans"]:
        for style,rows in p["future_close_observations"].items():
            values=[("{:+.2f}%".format(r["observation_close_return_pct"]) if r["complete"] else "대기") for r in rows]
            lines.append("| {} | {} | {} | {} | {} | {} |".format(
                p["ticker"],names[style],rows[0]["signal_day"],*values))
    if not any(p["future_close_observations"] for p in report["plans"]):
        lines.append("| 전체 | 신호 없음 | - | 대기 | 대기 | 대기 |")
    lines.append("")
    lines.append("> 관찰일 이후 완료된 종가만 사용. 매수 체결·실제 수익률 인증 아님. CASH / 주문 비활성.")
    return "\n".join(lines)+"\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True)
    p.add_argument("--prices",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--markdown")
    args=p.parse_args()
    with Path(args.plans).open(encoding="utf-8-sig",newline="") as f:
        plans=list(csv.DictReader(f))
    result=build(plans,read_rows(args.prices))
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if args.markdown: Path(args.markdown).write_text(markdown_table(result),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
