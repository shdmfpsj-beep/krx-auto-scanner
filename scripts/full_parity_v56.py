#!/usr/bin/env python3
"""Dated, complete candidate-vs-v18 price provenance audit (research-only).

This audit compares every matched candidate, not just 15 examples.
Agreement between two PyKRX-derived files never certifies KRX REGULAR prices.
No BUY/order path. Neither file can silently replace the other as an authority.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from krx_source_price_parity import source_file, csv_rows, value, run as legacy_run

SCHEMA = "free_krx_full_parity_v56"


def valid_ohlc(row, keys):
    nums = [value(row.get(k)) for k in keys]
    if any(x is None for x in nums):
        return None
    op, high, low, close = nums
    if not low <= min(op, close) <= max(op, close) <= high:
        return None
    return dict(open=op, high=high, low=low, close=close)


def inspect(recovery_root: Path, v18_root: Path, asof: str):
    base = dict(schema=SCHEMA, asof=asof, source_status="MISSING",
                mismatch_tickers_complete=False, overlap_tickers=0,
                close_mismatches=None, exact_close_matches=0,
                comparison_rows=[], mismatch_tickers=[], unpaired_recovery_tickers=[],
                missing_market_files=[], invalid_rows=0, duplicate_tickers=[],
                independent_provider_verified=False,
                regular_only_session_certified=False, trade_approved=False,
                orders_enabled=False, decision="CASH")
    history = source_file(recovery_root, "candidate_daily_history_v52.csv")
    paths = {market: source_file(v18_root,
             f"market/daily_prices/{market}/{asof}.csv")
             for market in ("KOSPI", "KOSDAQ")}
    missing = [market for market, p in paths.items() if p is None]
    base["missing_market_files"] = missing
    if history is None or missing:
        base["source_status"] = ("RECOVERY_HISTORY_MISSING_OR_AMBIGUOUS"
                                 if history is None else "V18_MARKET_FILE_MISSING_OR_AMBIGUOUS")
        return base

    recovery, v18, duplicate, invalid = {}, {}, set(), 0
    for row in csv_rows(history):
        if row.get("date") != asof:
            continue
        ticker = str(row.get("ticker", "")).strip()
        price = valid_ohlc(row, ("open", "high", "low", "close"))
        if len(ticker) != 6 or not ticker.isdecimal() or price is None:
            invalid += 1
            continue
        if ticker in recovery:
            duplicate.add(ticker)
            continue
        recovery[ticker] = price
    for market, p in paths.items():
        for row in csv_rows(p):
            ticker = str(row.get("ticker", "")).strip()
            if len(ticker) != 6 or not ticker.isdecimal():
                continue
            # Date is a required provenance field even if the file is named asof.
            if row.get("Date") != asof:
                invalid += 1
                continue
            price = valid_ohlc(row, ("Open", "High", "Low", "Close"))
            if price is None:
                invalid += 1
                continue
            if ticker in v18:
                duplicate.add(ticker)
                continue
            v18[ticker] = dict(**price, market=market)
    base["invalid_rows"] = invalid
    base["duplicate_tickers"] = sorted(duplicate)
    base["recovery_valid_tickers"] = len(recovery)
    base["v18_valid_tickers"] = len(v18)
    if duplicate:
        base["source_status"] = "DUPLICATE_DATED_TICKER"
        return base

    common = sorted(set(recovery) & set(v18))
    base["unpaired_recovery_tickers"] = sorted(set(recovery) - set(v18))
    comparisons = []
    mismatched = []
    for ticker in common:
        r, e = recovery[ticker], v18[ticker]
        matches = r["close"] == e["close"]
        comparisons.append(dict(
            ticker=ticker, market=e["market"],
            recovery_close=r["close"], v18_close=e["close"],
            close_equal=matches,
            recovery_ohlc=[r[k] for k in ("open", "high", "low", "close")],
            v18_ohlc=[e[k] for k in ("open", "high", "low", "close")],
            close_relative_drift_pct=round((e["close"]/r["close"]-1)*100, 5),
            same_high_low=(r["high"] == e["high"] and r["low"] == e["low"]),
            trade_approved=False))
        if not matches:
            mismatched.append(ticker)
    base.update(comparison_rows=comparisons, mismatch_tickers=mismatched,
                overlap_tickers=len(common),
                close_mismatches=len(mismatched),
                exact_close_matches=len(common)-len(mismatched))
    if not common:
        base["source_status"] = "NO_VALID_OVERLAP"
        return base

    # Cross-check against the original analysis so a change in parsing rules
    # cannot quietly promote a different count to the same "certified" output.
    legacy = legacy_run(recovery_root, v18_root, asof)
    if (legacy.get("overlap_tickers") != len(common)
            or legacy.get("close_mismatches") != len(mismatched)):
        base["source_status"] = "V55_SOURCE_PARSER_DISAGREEMENT"
        return base
    base["mismatch_tickers_complete"] = True
    base["source_status"] = ("CROSS_SOURCE_CLOSE_CONFLICT" if mismatched
                             else "CANDIDATE_CLOSES_MATCH_RESEARCH_ONLY")
    return base


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--v18", type=Path, required=True)
    parser.add_argument("--asof", required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    from datetime import date
    try:
        assert date.fromisoformat(args.asof).isoformat() == args.asof
    except (ValueError, AssertionError):
        raise SystemExit("ASOF_INVALID")
    data = inspect(args.recovery, args.v18, args.asof)
    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir/"source_price_parity.json").write_text(
        json.dumps({**data, "status": data["source_status"]},
                   indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    with (args.outdir/"complete_price_parity_v56.csv").open(
            "w", encoding="utf-8-sig", newline="") as out:
        columns = ("ticker","market","recovery_close","v18_close",
                   "close_equal","close_relative_drift_pct","same_high_low",
                   "trade_approved")
        writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data["comparison_rows"])
    lines = ["# 2026-10-23 free full-dated price provenance v5.6", "",
             f"Target: {args.asof}",
             f"Result: {data['source_status']}",
             f"Overlap: {data['overlap_tickers']} / mismatches: {data['close_mismatches']}",
             f"All mismatches enumerated: {data['mismatch_tickers_complete']}",
             f"Unpaired candidate tickers: {', '.join(data['unpaired_recovery_tickers']) or 'none'}",
             "",
             "Matching date/close values is not independent KRX regular-session verification.",
             "**CASH / zero BUY approvals / no executed orders.**"]
    (args.outdir/"full_parity_v56_mobile.md").write_text(
        "\n".join(lines)+"\n", encoding="utf-8")
    print(json.dumps({k:data[k] for k in
        ("asof","source_status","overlap_tickers","close_mismatches",
         "mismatch_tickers_complete","unpaired_recovery_tickers","decision")},
        ensure_ascii=False))


if __name__ == "__main__":
    main()
