"""Read-only C3 5/10/20 session observation, not simulated fills.

Anchor is the registered source close. A horizon return is a benchmark
observation, NOT a strategy or executable return.
"""
import argparse
import csv
import json
from pathlib import Path
from c3_price_concordance_v1 import read_rows
from c3_entry_geometry_research_v1 import review

HORIZONS=(5,10,20)

def evaluate(plan,prices):
    g=review(plan)
    series=sorted((day,bar) for (code,day),bar in prices.items()
                  if code==plan["ticker"] and day>plan["registered_day"])
    anchor=g["source_close"]
    stop=g["structure_stop"]
    target=g["first_target"]
    rows=[]
    for n in HORIZONS:
        observed=series[:n]
        complete=len(observed)==n
        both=[day for day,bar in observed if bar["low"]<=stop and bar["high"]>=target]
        rows.append(dict(horizon_sessions=n,observed_sessions=len(observed),
                         complete=complete,
                         horizon_date=observed[-1][0] if complete else None,
                         source_close_to_horizon_close_pct=(
                             round(100*(observed[-1][1]["close"]/anchor-1),2)
                             if complete else None),
                         stop_touched_days=sum(bar["low"]<=stop for _,bar in observed),
                         target1_touched_days=sum(bar["high"]>=target for _,bar in observed),
                         same_day_stop_target_ambiguous=both,
                         strategy_return_pct=None,
                         verified_entry=False,verified_exit=False))
    return dict(plan_id=plan["plan_id"],ticker=plan["ticker"],
                source_close=anchor,registration_day=plan["registered_day"],
                horizons=rows,trade_approved=False,orders_enabled=False,
                scope="SOURCE_CLOSE_BENCHMARK_ONLY_NOT_TRADING_PNL")

def build(plans,prices):
    items=list(plans)
    if len(items)!=2 or len({p["plan_id"] for p in items})!=2:
        raise ValueError("EXPECTED_TWO_UNIQUE_PLANS")
    return dict(schema="C3_FORWARD_HORIZON_OBSERVATION_V1",
                independent_regular_only_verified=False,
                trade_approved=False,orders_enabled=False,
                plans=[evaluate(p,prices) for p in items])

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True)
    p.add_argument("--prices",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    with Path(a.plans).open(encoding="utf-8-sig",newline="") as f:
        result=build(csv.DictReader(f),read_rows(a.prices))
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
