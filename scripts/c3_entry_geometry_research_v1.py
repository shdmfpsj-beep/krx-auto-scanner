"""Read-only C3 entry geometry review of pre-registered plans.

This module never creates orders, fills, signals, or price forecasts.
"""
import argparse
import csv
import json
import math
from pathlib import Path

def number(row, key):
    x = float(row[key])
    if not math.isfinite(x) or x <= 0:
        raise ValueError(f"INVALID_{key.upper()}")
    return x

def review(plan):
    stop = number(plan, "structure_stop")
    low = number(plan, "watch_low")
    high = number(plan, "watch_high")
    source_close = number(plan, "source_close")
    target1 = number(plan, "target1")
    target2 = number(plan, "target2")
    if not (stop < low <= high < target1 <= target2):
        raise ValueError("INVALID_PRICE_GEOMETRY")
    # Reward/risk is computed at BOTH ends, not only at a convenient midpoint.
    def metrics(entry):
        risk = entry - stop
        return dict(entry=entry, risk_pct=round(100 * risk / entry, 2),
                    reward_to_first_target=round((target1-entry)/risk, 2),
                    reward_to_second_target=round((target2-entry)/risk, 2))
    lower = metrics(low)
    upper = metrics(high)
    return dict(plan_id=plan["plan_id"], ticker=plan["ticker"],
                name=plan["name"], source_session=plan["selection_date"],
                registered_day=plan["registered_day"],
                source_close=source_close, structure_stop=stop,
                watch_low=low, watch_high=high,
                first_target=target1, second_target=target2,
                lower_entry=lower, upper_entry=upper,
                first_resistance_verified=False,
                entry_trigger_verified=False,
                independent_price_verified=False,
                trade_approved=False, orders_enabled=False,
                assessment="RESEARCH_GEOMETRY_ONLY_NO_BUY_SIGNAL")

def build(plans):
    rows = list(plans)
    if len(rows) != 2:
        raise ValueError("EXPECTED_EXACTLY_TWO_FROZEN_TOP2_PLANS")
    ids = [r["plan_id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("DUPLICATE_PLAN_ID")
    return dict(schema="C3_TOP2_ENTRY_GEOMETRY_RESEARCH_V1",
                status="UNVERIFIED_NO_TRADE_APPROVAL",
                plans=[review(row) for row in rows],
                trade_approved=False, orders_enabled=False)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plans", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    with Path(a.plans).open(encoding="utf-8-sig", newline="") as f:
        result = build(csv.DictReader(f))
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.output).write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
