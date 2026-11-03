"""Read-only C3 paper-ledger integrity audit. No trading, writes, or invented fills."""
import argparse
import csv
import json
from pathlib import Path

def audit(plans_path, ledger_path):
    with open(plans_path, encoding="utf-8", newline="") as f:
        plans = list(csv.DictReader(f))
    with open(ledger_path, encoding="utf-8") as f:
        ledger = json.load(f)
    errors = []
    ids = [p["plan_id"] for p in plans]
    if len(ids) != len(set(ids)):
        errors.append("DUPLICATE_PLAN_ID")
    positions = ledger.get("positions", {})
    for plan in plans:
        pid = plan["plan_id"]
        pos = positions.get(pid)
        if pos is None:
            errors.append(f"{pid}:MISSING_POSITION")
            continue
        frozen = pos.get("plan", {})
        for key, value in plan.items():
            if str(frozen.get(key)) != str(value):
                errors.append(f"{pid}:PLAN_MISMATCH:{key}")
        if pos.get("trade_approved") is not False or pos.get("orders_enabled") is not False:
            errors.append(f"{pid}:TRADING_SAFETY_FLAG")
        if pos.get("source_regular_only_certified") is not False:
            errors.append(f"{pid}:UNSUPPORTED_REGULAR_CERTIFICATION")
        entry = pos.get("entry_date")
        if entry and entry <= plan["registered_day"]:
            errors.append(f"{pid}:RETROACTIVE_ENTRY")
        if pos.get("status") == "OPEN" and not entry:
            errors.append(f"{pid}:OPEN_WITHOUT_ENTRY")
        if pos.get("last_mark_date") and pos.get("last_observed_date"):
            if pos["last_mark_date"] > pos["last_observed_date"]:
                errors.append(f"{pid}:FUTURE_MARK")
        for horizon in (5, 10, 20):
            key = f"net_return_after_{horizon}_sessions_pct"
            if pos.get(key) is not None and pos.get("held_sessions", 0) < horizon:
                errors.append(f"{pid}:PREMATURE_{horizon}_SESSION_RESULT")
    for pid in positions:
        if pid not in ids:
            errors.append(f"{pid}:UNREGISTERED_POSITION")
    events = ledger.get("events", [])
    keys = [e.get("event_key") for e in events]
    if len(keys) != len(set(keys)):
        errors.append("DUPLICATE_EVENT_KEY")
    for event in events:
        pid = event.get("plan_id")
        if pid not in positions:
            errors.append(f"{pid}:EVENT_WITHOUT_POSITION")
        if event.get("actual_broker_fill") is True:
            errors.append(f"{pid}:BROKER_FILL_CLAIM")
        if pid in positions and event.get("source_session"):
            if event["source_session"] <= positions[pid]["plan"]["registered_day"]:
                errors.append(f"{pid}:RETROACTIVE_EVENT")
    if ledger.get("real_broker_orders") is not False:
        errors.append("REAL_ORDERS_FLAG")
    if ledger.get("authoritative_regular_scope") is not False:
        errors.append("REGULAR_SCOPE_FLAG")
    return {"ok": not errors, "errors": errors, "registered": len(plans),
            "positions": len(positions), "events": len(events),
            "last_observed_dates": {pid: p.get("last_observed_date")
                                    for pid, p in positions.items()}}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plans", default="config/c3_paper_top2_plans.csv")
    parser.add_argument("--ledger", default="reports/c3_paper/paper_ledger.json")
    args = parser.parse_args()
    result = audit(Path(args.plans), Path(args.ledger))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)

if __name__ == "__main__":
    main()
