"""Prospective, read-only C3 watch-band opportunity accounting.

Daily OHLC cannot establish within-day ordering of stop, target and entry.
Never interprets a touched band as an actual fill or broker order.
"""
import argparse
import csv
import json
from pathlib import Path

from c3_price_concordance_v1 import read_rows
from c3_entry_geometry_research_v1 import review

def evaluate(plan, bars):
    geometry=review(plan)
    ticker=plan["ticker"]
    registered=plan["registered_day"]
    selected=sorted((date, ohlc) for (code,date),ohlc in bars.items()
                    if code==ticker and date>registered)
    horizon=int(plan.get("expires_after_sessions") or 5)
    if horizon<=0:
        raise ValueError("INVALID_HORIZON")
    window=selected[:horizon]
    low=geometry["watch_low"]
    high=geometry["watch_high"]
    source_close=geometry["source_close"]
    touched=[day for day,bar in window
             if bar["low"]<=high and bar["high"]>=low]
    # A session gap through the watch band is not a guaranteed execution.
    confirmed_fill=False
    missed=[day for day,bar in window
            if bar["high"]>source_close and day not in touched]
    return dict(plan_id=plan["plan_id"],ticker=ticker,name=plan["name"],
                registered_day=registered,window_sessions=len(window),
                expected_sessions=horizon,
                observation_complete=len(window)>=horizon,
                first_band_touch_day=touched[0] if touched else None,
                band_touch_sessions=len(touched),
                no_touch_higher_high_sessions=len(missed),
                highest_observed_high=max((b["high"] for _,b in window),default=None),
                source_close=source_close,
                band_touch_is_fill=False,confirmed_fill=confirmed_fill,
                actual_broker_fill=False,trade_approved=False,
                result_scope="OHLC_OPPORTUNITY_ONLY_NOT_EXECUTION")

def build(plans,bars):
    items=list(plans)
    if len(items)!=2:
        raise ValueError("EXPECTED_EXACTLY_TWO_PLANS")
    return dict(schema="C3_TOP2_NO_FILL_OPPORTUNITY_V1",
                source_regular_only_certified=False,
                trade_approved=False,orders_enabled=False,
                plans=[evaluate(plan,bars) for plan in items])

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True)
    p.add_argument("--prices",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    with Path(a.plans).open(encoding="utf-8-sig",newline="") as f:
        plans=list(csv.DictReader(f))
    result=build(plans,read_rows(a.prices))
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
