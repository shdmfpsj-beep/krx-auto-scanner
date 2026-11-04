"""Research-only prior-bar resistance evidence, strictly excluding selection-day and future bars."""
import argparse,csv,json,math
from pathlib import Path
from c3_price_concordance_v1 import read_rows

MIN_PRIOR_SESSIONS=20
def assess(plan,prices):
    ticker=plan["ticker"]
    cutoff=plan["selection_date"]
    target=float(plan["target1"])
    stop=float(plan["structure_stop"])
    entry=float(plan["watch_high"])
    if not all(math.isfinite(v) and v>0 for v in (target,stop,entry)):
        raise ValueError("INVALID_PRICE")
    prior=sorted(((day,bar) for (code,day),bar in prices.items()
                  if code==ticker and day<cutoff),key=lambda x:x[0])
    prior=prior[-60:]
    enough=len(prior)>=MIN_PRIOR_SESSIONS
    resistance_candidates=sorted(set(float(bar["high"]) for _,bar in prior if float(bar["high"])>entry))
    nearest=resistance_candidates[0] if enough and resistance_candidates else None
    # A raw daily high is not a swing resistance. A 2-left/2-right
    # pivot is confirmed using only bars before the frozen selection date.
    highs=[float(bar["high"]) for _,bar in prior]
    pivots=[]
    for i in range(2,len(highs)-2):
        h=highs[i]
        if h>entry and all(h>v for v in highs[i-2:i]) and all(h>=v for v in highs[i+1:i+3]):
            pivots.append((prior[i][0],h))
    nearest_pivot=min(pivots,key=lambda x:x[1]) if enough and pivots else None
    target_above_candidate=bool(nearest is not None and target>nearest)
    target_gap_pct=round(100*(target/nearest-1),3) if nearest else None
    pivot_price=nearest_pivot[1] if nearest_pivot else None
    entry_risk=entry-stop
    pivot_reward_risk=round((pivot_price-entry)/entry_risk,3) if pivot_price is not None and entry_risk>0 else None
    target_reward_risk=round((target-entry)/entry_risk,3) if entry_risk>0 else None
    pivot_before_target=bool(pivot_price is not None and pivot_price<target)
    entry_geometry_valid=bool(stop<entry<target)
    # Informational warning, not a trade gate or statistically validated cutoff.
    swing_rr_warning=("INVALID_ENTRY_GEOMETRY" if not entry_geometry_valid else
                      "NO_PRIOR_SWING_CANDIDATE" if pivot_reward_risk is None else
                      "SWING_REWARD_BELOW_1R" if pivot_reward_risk<1 else
                      "SWING_REWARD_1_TO_1_5R" if pivot_reward_risk<1.5 else
                      "SWING_REWARD_AT_LEAST_1_5R")
    # Conservative research triage, never a live order signal.
    research_triage=("REVIEW_ENTRY_GEOMETRY" if not entry_geometry_valid else
                     "REVIEW_INSUFFICIENT_HISTORY" if not enough else
                     "REVIEW_NO_SWING_EVIDENCE" if pivot_reward_risk is None else
                     "REVIEW_NEAR_RESISTANCE" if pivot_reward_risk<1 else
                     "WATCH_RESEARCH_ONLY")
    return dict(ticker=ticker,selection_date=cutoff,prior_sessions=len(prior),
                minimum_prior_sessions=MIN_PRIOR_SESSIONS,
                sufficient_history=enough,
                prior_only=True,
                nearest_prior_high_above_watch_high=nearest,
                nearest_confirmed_prior_swing_high_date=nearest_pivot[0] if nearest_pivot else None,
                nearest_confirmed_prior_swing_high=nearest_pivot[1] if nearest_pivot else None,
                prior_swing_high_count=len(pivots),
                swing_high_method="2_LEFT_2_RIGHT_PRIOR_BARS_ONLY",
                planned_first_target=target,
                entry_geometry_valid=entry_geometry_valid,
                planned_target_reward_risk_at_watch_high=target_reward_risk,
                prior_swing_reward_risk_at_watch_high=pivot_reward_risk,
                prior_swing_before_planned_target=pivot_before_target,
                pivot_is_confirmed_resistance=False,
                swing_rr_warning=swing_rr_warning,
                research_triage=research_triage,
                warning_threshold_is_research_only=True,
                target_vs_nearest_prior_high_pct=target_gap_pct,
                planned_target_above_nearest_prior_high=target_above_candidate,
                nearest_prior_high_may_limit_target=target_above_candidate,
                prior_swing_high_below_target=bool(nearest_pivot and nearest_pivot[1]<target),
                resistance_confirmed=False,
                status=("INSUFFICIENT_PRIOR_HISTORY" if not enough else
                        "NO_PRIOR_HIGH_ABOVE_ENTRY" if nearest is None else
                        "PRIOR_HIGH_CANDIDATE_ONLY"),
                price_certified=False,trade_approved=False,orders_enabled=False)

def build(plans,prices):
    if len(plans)!=2 or len({p["ticker"] for p in plans})!=2:
        raise ValueError("EXPECTED_UNIQUE_TOP2")
    return dict(schema="C3_PRIOR_RESISTANCE_EVIDENCE_V1",
                methodology="PRIOR_HIGH_CANDIDATES_NOT_CONFIRMED_RESISTANCE",
                price_certified=False,trade_approved=False,orders_enabled=False,
                results=[assess(p,prices) for p in plans])

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True);p.add_argument("--prices",required=True)
    p.add_argument("--output",required=True);p.add_argument("--markdown",required=True)
    a=p.parse_args()
    with open(a.plans,encoding="utf-8-sig",newline="") as f:
        report=build(list(csv.DictReader(f)),read_rows(a.prices))
    Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["### 첫 저항 후보 근거 점검 (선정일 이전 데이터만)",
           "| 종목 | 스윙고점 후보 | 목표가 | 스윙고점 손익비 | 목표가 손익비 | 연구 판정 |",
           "|---|---:|---:|---:|---:|---|"]
    for r in report["results"]:
        nearest=r["nearest_prior_high_above_watch_high"]
        pivot=r["nearest_confirmed_prior_swing_high"]
        lines.append("| {} | {} | {:,.0f} | {} | {} | {} |".format(
            r["ticker"],
            "{:,.0f}".format(pivot) if pivot is not None else "미확인",
            r["planned_first_target"],
            "{:.2f}".format(r["prior_swing_reward_risk_at_watch_high"]) if r["prior_swing_reward_risk_at_watch_high"] is not None else "미확인",
            "{:.2f}".format(r["planned_target_reward_risk_at_watch_high"]) if r["planned_target_reward_risk_at_watch_high"] is not None else "미확인",
            r["research_triage"]))
    lines.extend(["","> 최소 20거래일의 선정일 이전 일봉 필요. 과거 고가 후보는 검증된 저항선이 아니며 데이터 출처도 미인증. 미래 데이터 사용 금지."])
    Path(a.markdown).write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"schema":report["schema"],"results":[{
        "ticker":r["ticker"],"prior_sessions":r["prior_sessions"],
        "prior_swing":r["nearest_confirmed_prior_swing_high"],
        "swing_rr":r["prior_swing_reward_risk_at_watch_high"],
        "target_rr":r["planned_target_reward_risk_at_watch_high"],
        "warning":r["swing_rr_warning"],
        "research_triage":r["research_triage"]} for r in report["results"]],
        "trade_approved":False},ensure_ascii=False))
if __name__=="__main__":main()
