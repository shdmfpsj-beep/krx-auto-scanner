#!/usr/bin/env python3
"""Free, fail-closed v8.4 close-price diagnostic; never a trade approval.

Checks internal scanner/preliminary consistency and dated archived manual
cross-checks. Matching two derivatives of the same feed is NOT independent
price confirmation, and date-only OHLC cannot certify the KRX regular session.
"""
import argparse
import csv
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def rows(path):
    path = Path(path)
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))
    except (OSError, UnicodeError, csv.Error):
        return None


def expected_session(now=None):
    """Conservative weekday target; holidays remain unverified, not invented."""
    now = now or datetime.now(ZoneInfo("Asia/Seoul"))
    local = now.astimezone(ZoneInfo("Asia/Seoul"))
    day = local.date()
    if local.hour < 16:
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()


def inspect(outdir, reference_file, expected_asof, max_price_drift_pct):
    outdir = Path(outdir)
    candidate = rows(outdir / "candidates.csv")
    prelim_names = ("c3_preliminary.csv", "k100_preliminary.csv")
    pre = {name: rows(outdir / name) for name in prelim_names}
    problems = []
    internal_conflicts = []
    dated_crosscheck_conflicts = []
    comparisons = 0
    candidate_prices = {}
    dates = set()

    if not candidate:
        problems.append("CANDIDATES_MISSING_OR_EMPTY")
    else:
        for item in candidate:
            d = str(item.get("latest_date", ""))
            dates.add(d)
            ticker = str(item.get("ticker", "")).strip()
            close = number(item.get("close"))
            if len(ticker) != 6 or not ticker.isdigit() or close is None:
                problems.append("CANDIDATE_BAD_TICKER_OR_CLOSE")
                continue
            if ticker in candidate_prices:
                problems.append("DUPLICATE_CANDIDATE_TICKER")
                continue
            candidate_prices[ticker] = close
    if dates != {expected_asof}:
        problems.append("ASOF_MISMATCH")

    for filename, items in pre.items():
        if not items:
            problems.append(filename.upper().replace(".", "_") + "_MISSING_OR_EMPTY")
            continue
        for item in items:
            if str(item.get("latest_date", "")) != expected_asof:
                problems.append("PRELIMINARY_ASOF_MISMATCH")
                continue
            ticker = str(item.get("ticker", "")).strip()
            close = number(item.get("close_reference"))
            if item.get("trade_approval") not in ("NO", "", None):
                problems.append("UNEXPECTED_TRADE_APPROVAL_FLAG")
            if ticker not in candidate_prices:
                continue
            comparisons += 1
            if close is None:
                problems.append("PRELIMINARY_BAD_CLOSE")
            else:
                drift = abs(close / candidate_prices[ticker] - 1) * 100
                if drift > max_price_drift_pct:
                    internal_conflicts.append({
                        "ticker": ticker, "preliminary_file": filename,
                        "candidate_close": candidate_prices[ticker],
                        "preliminary_close": close,
                        "drift_pct": round(drift, 4),
                    })
    if comparisons == 0:
        problems.append("NO_PRELIMINARY_PRICE_OVERLAP")

    manual_references = {}
    try:
        references = json.loads(Path(reference_file).read_text(encoding="utf-8"))
        if isinstance(references, dict):
            manual_references = references.get(expected_asof, {})
            if not isinstance(manual_references, dict):
                manual_references = {}
    except (OSError, ValueError, TypeError):
        pass
    checked = 0
    for ticker, quoted in manual_references.items():
        if ticker not in candidate_prices or not isinstance(quoted, dict):
            continue
        target = number(quoted.get("close"))
        if target is None:
            continue
        checked += 1
        drift = abs(candidate_prices[ticker] / target - 1) * 100
        if drift > max_price_drift_pct:
            dated_crosscheck_conflicts.append({
                "ticker": ticker, "candidate_close": candidate_prices[ticker],
                "manual_reference_close": target, "drift_pct": round(drift, 4),
                "reference_urls": quoted.get("sources", [])[:3],
            })
    problems = sorted(set(problems))
    if internal_conflicts:
        status = "INTERNAL_CLOSE_CONFLICT"
    elif dated_crosscheck_conflicts:
        status = "DATED_REFERENCE_CLOSE_CONFLICT"
    elif problems:
        status = "DATA_MISSING_OR_ASOF_UNVERIFIED"
    else:
        status = "INTERNAL_CONSISTENT_EXTERNAL_UNVERIFIED"

    return {
        "schema": "krx_v84_free_price_integrity_v1",
        "expected_asof": expected_asof,
        "candidate_dates": sorted(dates),
        "candidate_stock_count": len(candidate_prices),
        "internal_comparisons": comparisons,
        "manually_archived_reference_comparisons": checked,
        "max_price_drift_pct": max_price_drift_pct,
        "status": status,
        "data_errors": problems,
        "internal_close_conflict_count": len(internal_conflicts),
        "dated_reference_conflict_count": len(dated_crosscheck_conflicts),
        "internal_examples": internal_conflicts[:15],
        "manual_reference_examples": dated_crosscheck_conflicts[:15],
        "independent_price_provider_verified": False,
        "regular_session_scope_verified": False,
        "sector_top3_verified": False,
        "final_80_point_stock_score_verified": False,
        "order_execution_enabled": False,
        "trade_approved": False,
        "decision": "CASH",
        "note": "Internal feed agreement and archived manual references do not prove a regular-only certified session.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", type=Path, default=Path("reports"))
    parser.add_argument("--reference-file", type=Path, default=Path("config/krx_close_crosscheck_20261021.json"))
    parser.add_argument("--expected-asof", default="")
    parser.add_argument("--max-price-drift-pct", type=float, default=0.5)
    args = parser.parse_args()
    if not math.isfinite(args.max_price_drift_pct) or not 0 <= args.max_price_drift_pct <= 5:
        raise SystemExit("INVALID_DRIFT_THRESHOLD")
    target = args.expected_asof or expected_session()
    try:
        datetime.strptime(target, "%Y-%m-%d")
    except ValueError:
        raise SystemExit("INVALID_EXPECTED_ASOF")
    result = inspect(args.outdir, args.reference_file, target, args.max_price_drift_pct)
    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir / "v84_price_integrity_audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in
        ("expected_asof", "status", "candidate_stock_count",
         "internal_close_conflict_count", "dated_reference_conflict_count",
         "trade_approved", "decision")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
