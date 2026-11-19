#!/usr/bin/env python3
"""Fail-closed, read-only C3 TOP5 -> existing OpenDART research adapter.

Run on the SAME Korea calendar date as the price as-of. Historical replays
cannot query today's restated financial statements as if they were PIT data.
This produces research evidence, never trading authorization.
"""
import argparse
import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from dart_financial_screen import collect

def bridge(receipt, key, today=None, collector=collect):
    today = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    asof = str(receipt.get("asof", ""))
    candidates = receipt.get("candidates", [])
    result = {"schema": "C3_TOP5_DART_BRIDGE_V1", "asof": asof,
              "status": "UNVERIFIED", "decision": "CASH",
              "trade_approved": False, "financial_verified": False,
              "researched": [], "excluded": []}
    if not re.fullmatch(r"\d{8}", asof):
        result["status"] = "INVALID_ASOF"
        return result
    try:
        day = date.fromisoformat(f"{asof[:4]}-{asof[4:6]}-{asof[6:]}")
    except ValueError:
        result["status"] = "INVALID_ASOF"
        return result
    # Next-day reports may examine yesterday's signal, but today's OpenDART
    # snapshot must never be represented as yesterday's PIT data.
    if day != today and not (day == today - timedelta(days=1) and day.weekday() < 5):
        result["status"] = "HISTORICAL_REPLAY_NO_RETROACTIVE_FINANCIALS"
        return result
    result["financial_observed_on"] = today.isoformat()
    result["signal_date"] = asof
    result["point_in_time_snapshot_verified"] = (day == today)
    if not isinstance(candidates, list) or not candidates:
        result["status"] = "NO_CANDIDATES"
        return result
    if not key:
        result["status"] = "MISSING_DART_KEY"
        return result
    stocks = []
    seen = set()
    for c in candidates:
        if not isinstance(c, dict):
            result["status"] = "INVALID_CANDIDATE"
            return result
        ticker = str(c.get("code", ""))
        if not re.fullmatch(r"\d{6}", ticker):
            result["status"] = "INVALID_TICKER"
            return result
        if ticker in seen:
            result["status"] = "DUPLICATE_TICKER"
            return result
        seen.add(ticker)
        stocks.append({"ticker": ticker, "name": str(c.get("name", "")),
                       "sector_id": "UNKNOWN", "research_proxy_index": ""})
    research = collector(today, stocks, key, today=today)
    if not isinstance(research, dict):
        result["status"] = "INVALID_DART_RESPONSE"
        return result
    result["source_status"] = research.get("status", "UNKNOWN")
    returned = set()
    for r in research.get("researched", []):
        if r.get("ticker") not in seen or r.get("ticker") in returned:
            result["status"] = "INVALID_FINANCIAL_COVERAGE"
            result["researched"] = []
            result["excluded"] = []
            return result
        returned.add(r["ticker"])
        annual = r.get("status") == "DATED_ANNUAL_RESEARCH_ONLY"
        interim = r.get("interim_research") or {}
        pass_ = bool(annual and r.get("financial_screen_pass") and
                     r.get("annual_plus_interim_growth_pass") and
                     not r.get("recent_financial_weakening_veto") and
                     interim.get("status") == "DATED_INTERIM_YTD_RESEARCH_ONLY" and
                     bool(r.get("receipt_date")) and
                     str(r.get("receipt_date")) <= day.isoformat() and
                     bool(interim.get("filing", {}).get("receipt_date")) and
                     str(interim["filing"]["receipt_date"]) <= day.isoformat())
        item = {"ticker": r["ticker"], "name": r.get("name"),
                "annual_status": r.get("status"),
                "interim_status": interim.get("status"),
                "financial_quality": r.get("financial_quality"),
                "filing_date": r.get("receipt_date"),
                "financial_screen_pass": pass_}
        (result["researched"] if pass_ else result["excluded"]).append(item)
    if day != today:
        result["status"] = "NEXT_DAY_FINANCIAL_RESEARCH_NOT_PIT_CERTIFIED"
        result["financial_verified"] = False
        return result
    if len(result["researched"]) + len(result["excluded"]) != len(stocks):
        result["status"] = "INCOMPLETE_FINANCIAL_COVERAGE"
    elif result["excluded"]:
        result["status"] = "PARTIAL_OR_FAILED_FINANCIAL_GATE"
    else:
        result["status"] = "FINANCIAL_RESEARCH_GATE_PASSED"
        result["financial_verified"] = True
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    key = (os.environ.get("OPENDART_API_KEY") or
           os.environ.get("OPEN_DART_API_KEY") or os.environ.get("DART_API_KEY"))
    result = bridge(receipt, key)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print("C3_TOP5_FINANCIAL_GATE", json.dumps({
        "status": result["status"], "verified": result["financial_verified"],
        "researched": len(result["researched"]),
        "excluded": len(result["excluded"]), "decision": "CASH"}))

if __name__ == "__main__":
    main()
