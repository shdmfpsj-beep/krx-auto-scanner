#!/usr/bin/env python3
"""Read-only C3 B TOP2 watch/entry lifecycle overlay; never an order or BUY gate.

This deliberately does not import/modify the immutable V8 selection, market,
decision, or paper ledgers. It only derives dated status from the *published*
B TOP2 and separately archived daily snapshots. Missing dates fail closed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


SCHEMA = "C3_TOP2_LIFECYCLE_OVERLAY_V1"


class EvidenceError(ValueError):
    pass


def fingerprint(obj):
    return hashlib.sha256(json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def as_day(value):
    from datetime import date
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise EvidenceError("INVALID_SOURCE_DATE") from exc


def load_history(path):
    if path is None:
        return []
    p = Path(path)
    if not p.exists():
        raise EvidenceError("HISTORY_PATH_MISSING")
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    dates = [as_day(r.get("source_date")) for r in rows]
    if dates != sorted(set(dates)):
        raise EvidenceError("HISTORY_DUPLICATED_OR_UNSORTED")
    for row in rows:
        if row.get("schema") != "C3_TOP2_OBSERVED_RANK_V1":
            raise EvidenceError("HISTORY_SCHEMA_INVALID")
        items = row.get("pairs")
        if not isinstance(items, list) or len(items) != 2:
            raise EvidenceError("HISTORY_MISSING_TWO_PICKS")
        if len({x.get("ticker") for x in items}) != 2:
            raise EvidenceError("HISTORY_DUPLICATED_TICKER")
        digest = fingerprint({"source_date": row["source_date"], "pairs": items})
        if row.get("fingerprint") != digest:
            raise EvidenceError("HISTORY_FINGERPRINT_MISMATCH")
    return rows


def validate_calendar(calendar):
    if not isinstance(calendar, dict) or not isinstance(calendar.get("dates"), list):
        raise EvidenceError("CALENDAR_MISSING")
    dates = [as_day(x) for x in calendar["dates"]]
    if not dates or dates != sorted(set(dates)):
        raise EvidenceError("CALENDAR_UNSORTED_OR_DUPLICATED")
    return dates


def snapshot(source_date, rows):
    pairs = []
    for row in sorted(rows, key=lambda x: x["rank"]):
        p = (row.get("entry_plans") or {}).get("A_SUPPORT_LIMIT") or {}
        plan = p.get("plan")
        pairs.append({
            "ticker": row["ticker"],
            "signal_id": row["signal_id"],
            "signal_key": plan.get("signal_key") if isinstance(plan, dict) else None,
            "rank": row["rank"],
            "plan_hash": fingerprint(row.get("entry_plans")),
        })
    out = {"schema": "C3_TOP2_OBSERVED_RANK_V1", "source_date": source_date, "pairs": pairs}
    out["fingerprint"] = fingerprint({"source_date": source_date, "pairs": pairs})
    return out


def watch_age(ticker, current_index, dates, by_date):
    """Return consecutive previously observed TOP2 sessions (lower bound).

    A missing preceding session is not interpreted as a no-selection day.
    Never backfill or infer missing sessions from weekends or wall time.
    """
    age = 0
    for index in range(current_index - 1, -1, -1):
        previous = by_date.get(dates[index])
        if previous is None:
            return (None, "MISSING_PRIOR_SESSION")
        if ticker not in {x["ticker"] for x in previous["pairs"]}:
            return (age, "CONTINUITY_CONFIRMED")
        age += 1
    return (age, "EARLIEST_RECORDED_SESSION_REACHED")


def evaluate(latest, calendar, history):
    dates = validate_calendar(calendar)
    source = as_day(latest.get("source_price_asof")) if latest.get("source_price_asof") else None
    preview = latest.get("preview_price_asof")
    base = {
        "schema": SCHEMA, "source_date": source,
        "source_regular_only_certified": False,
        "status": "DATA_PENDING", "buy_approved": False,
        "orders_enabled": False, "current_action": "CASH",
        "calendar_scope": "REFERENCE_SESSIONS_NOT_INDEPENDENT_KRX_CERTIFICATION",
        "read_only": True, "top2": [], "out_of_top2": [],
        "snapshot": None, "history": history[:],
    }
    if (source != dates[-1] or preview != source or
        latest.get("errors") or
        not latest.get("research_top2_registered_for_source_session") or
        latest.get("research_preview_only")):
        base["reason"] = "SOURCE_DATE_OR_REGISTRATION_NOT_READY"
        return base
    if source not in dates:
        base["reason"] = "SOURCE_NOT_IN_COMPLETED_REFERENCE_CALENDAR"
        return base
    if latest.get("current_action") != "CASH" or latest.get("orders_enabled") is not False:
        raise EvidenceError("UPSTREAM_TRADE_POLICY_CHANGED")
    rows = latest.get("research_top2")
    if not isinstance(rows, list) or len(rows) != 2:
        raise EvidenceError("REGISTERED_B_TOP2_MISSING")
    if (sorted(r.get("rank") for r in rows) != [1, 2] or
        len({r.get("ticker") for r in rows}) != 2):
        raise EvidenceError("B_TOP2_RANK_OR_ID_INVALID")
    for row in rows:
        if (row.get("model") != "B" or row.get("source_price_asof") != source or
            row.get("buy_approved") is not False or row.get("live_action") != "CASH" or
            not row.get("signal_id") or
            not isinstance(row.get("ticker"), str) or len(row["ticker"]) != 6 or
            not row["ticker"].isdigit() or
            int(row.get("order_validity_sessions", -1)) != 1):
            raise EvidenceError("B_TOP2_IMMUTABLE_CONTRACT_INVALID")

    index = dates.index(source)
    by_date = {x["source_date"]: x for x in history}
    if any(x not in dates or dates.index(x) > index for x in by_date):
        raise EvidenceError("HISTORY_FUTURE_OR_OFF_CALENDAR")
    current = snapshot(source, rows)
    if source in by_date:
        if current["fingerprint"] != by_date[source]["fingerprint"]:
            raise EvidenceError("SAME_DATE_REPLAY_CONFLICT")
        # Idempotent re-read: no duplicate daily observation.
        augmented = history[:]
    else:
        augmented = history + [current]
    last = by_date.get(dates[index - 1]) if index > 0 else None
    old_names = {x["ticker"] for x in last["pairs"]} if last else set()
    present = {r["ticker"] for r in rows}
    if last:
        base["out_of_top2"] = sorted(old_names - present)

    top2 = []
    for row in sorted(rows, key=lambda r: r["rank"]):
        age, coverage = watch_age(row["ticker"], index, dates, by_date)
        if age is None:
            watch = "HISTORY_GAP_REVIEW"
        elif age >= 5:
            watch = "OLD_WATCH_ARCHIVE_REVIEW"  # Current fresh TOP2 ranking is NOT revoked.
        elif age >= 3:
            watch = "WATCH_REEVALUATE"
        elif age == 0:
            watch = "FIRST_OBSERVED_TOP2"
        else:
            watch = "WATCH_CONTINUES"
        entry_item = (row.get("entry_plans") or {}).get("A_SUPPORT_LIMIT") or {}
        plan = entry_item.get("plan")
        band = None
        diagnostics = []
        if isinstance(plan, dict):
            low, high, close, stop = (
                plan.get("low"), plan.get("high"), row.get("close"), plan.get("stop"))
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (low, high, close, stop)):
                raise EvidenceError("ENTRY_PLAN_NONNUMERIC")
            if not 0 < stop < low <= high or close <= 0:
                raise EvidenceError("ENTRY_PLAN_BAD_GEOMETRY")
            gap_pct = round(100 * (close / high - 1), 2)
            risk_pct = round(100 * (high - stop) / high, 2)
            rr = plan.get("net_r1_rr")
            if gap_pct > 10:
                diagnostics.append("LIMIT_OVER_10PCT_BELOW_CLOSE_DIAGNOSTIC")
            if risk_pct > 12:
                diagnostics.append("STOP_OVER_12PCT_DIAGNOSTIC")
            if rr is None or rr < 1:
                diagnostics.append("R1_RR_BELOW_1_OR_UNKNOWN_DIAGNOSTIC")
            band = {
                "low": low, "high": high, "structure_stop": stop,
                "reference_close": close, "gap_close_vs_upper_pct": gap_pct,
                "stop_distance_from_upper_pct": risk_pct, "net_r1_rr": rr,
            }
        else:
            diagnostics.append("NO_A_SUPPORT_PLAN")
        if not latest.get("source_regular_only_certified", False):
            diagnostics.append("REGULAR_ONLY_UNCERTIFIED")
        if row.get("market_regime") == "DOWN":
            diagnostics.append("MARKET_DOWN")
        top2.append({
            "rank": row["rank"], "ticker": row["ticker"], "name": row.get("name", ""),
            "signal_id": row["signal_id"], "watch_status": watch,
            "consecutive_prior_sessions_lower_bound": age,
            "watch_history_quality": coverage,
            "original_plan_validity": "NEXT_ONE_TRADING_SESSION_ONLY",
            "plan_status_at_source_close": "NOT_AN_ACTIVE_ORDER",
            "band": band, "diagnostics": diagnostics,
            "buy_approved": False, "action": "CASH",
        })
    return {
        **base, "status": "RESEARCH_STATUS_ONLY", "reason": "NO_NEW_TRADE_APPROVAL",
        "top2": top2, "snapshot": current,
        "history": augmented,
    }


def run(latest_path, calendar_path, history_path, outdir):
    latest = json.loads(Path(latest_path).read_text(encoding="utf-8"))
    calendar = json.loads(Path(calendar_path).read_text(encoding="utf-8"))
    history = load_history(history_path)
    result = evaluate(latest, calendar, history)
    folder = Path(outdir)
    folder.mkdir(parents=True, exist_ok=True)
    exported = {k: v for k, v in result.items() if k not in ("history", "snapshot")}
    (folder / "c3_top2_lifecycle_status.json").write_text(
        json.dumps(exported, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Derived observations only: this never modifies the original C3 ledger.
    if result["snapshot"] is not None:
        (folder / "c3_top2_observed_history.jsonl").write_text(
            "".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n"
                    for x in result["history"]), encoding="utf-8")
    lines = [
        "# C3 TOP2 매수기회·관찰상태 (읽기 전용)",
        f"- 원본 거래일: {result['source_date'] or '미확인'} / 상태: {result['status']}",
        "- **실전 매수승인 없음: CASH**. 종목 선정은 매수 추천이나 실제 체결 확인이 아닙니다.",
        "- 지정가의 유효기간은 기존 1거래일 그대로입니다. 3/5거래일은 종목 관찰 재검토용이며 자동 주문·자동 종목삭제가 아닙니다.",
        "",
        "| 순위/종목 | 관찰상태 | 매수 관찰 상단 | 매수승인 |",
        "|---|---|---:|---|",
    ]
    for p in result["top2"]:
        high = p["band"]["high"] if p["band"] else "-"
        lines.append(f"| {p['rank']} {p['name']}({p['ticker']}) | {p['watch_status']} | {high} | NO |")
    if result["out_of_top2"]:
        lines.append("- 이전 TOP2 중 당일 제외: " + ", ".join(result["out_of_top2"]))
    (folder / "c3_top2_lifecycle_mobile.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--latest", required=True)
    p.add_argument("--calendar", required=True)
    p.add_argument("--history", default=None)
    p.add_argument("--outdir", required=True)
    a = p.parse_args()
    value = run(a.latest, a.calendar, a.history, a.outdir)
    print(json.dumps({"source_date": value["source_date"], "status": value["status"],
                      "top2": len(value["top2"]), "orders_enabled": False}))


if __name__ == "__main__":
    main()
