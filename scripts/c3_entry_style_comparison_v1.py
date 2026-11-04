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
    prior_close_above=False
    for day,b in window:
        touches=b["low"]<=high and b["high"]>=low
        if touches:
            pullback.append(day)
            if breakout_confirmed:
                retest.append(day)
        # A prior completed close above the anchor plus a full session above
        # the watch band indicates missed pullback opportunity, not a fill.
        if prior_close_above and b["low"]>high:
            breakout_without_pullback.append(day)
        # Confirmation uses completed close; same-day high cannot qualify.
        if b["close"]>breakout_level:
            breakout_confirmed=True
        prior_close_above=b["close"]>breakout_level
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

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True)
    p.add_argument("--prices",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    with Path(args.plans).open(encoding="utf-8-sig",newline="") as f:
        plans=list(csv.DictReader(f))
    result=build(plans,read_rows(args.prices))
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
