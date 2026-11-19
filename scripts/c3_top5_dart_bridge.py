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
from datetime import date, datetime
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
    day = date.fromisoformat(f"{asof[:4]}-{asof[4:6]}-{asof[6:]}")
    if day != today:
        result["status"] = "HISTORICAL_REPLAY_NO_RETROACTIVE_FINANCIALS"
        return result
    if not isinstance(candidates, list) or not candidates:
        result["status"] = "NO_CANDIDATES"
        return result
    stocks = []
    for c in candidates:
        ticker = str(c.get("code", ""))
        if not re.fullmatch(r"\d{6}", ticker):
            result["status"] = "INVALID_TICKER"
            return result
        stocks.append({"ticker": ticker, "name": str(c.get("name", "")),
                       "sector_id": "UNKNOWN", "research_proxy_index": ""})
    research = collector(day, stocks, key, today=today)
    result["source_status"] = research.get("status", "UNKNOWN")
    for r in research.get("researched", []):
        annual = r.get("status") == "DATED_ANNUAL_RESEARCH_ONLY"
        interim = r.get("interim_research") or {}
        pass_ = bool(annual and r.get("financial_screen_pass") and
                     r.get("annual_plus_interim_growth_pass") and
                     not r.get("recent_financial_weakening_veto") and
                     interim.get("status") == "DATED_INTERIM_YTD_RESEARCH_ONLY" and
                     str(r.get("receipt_date", "")) <= day.isoformat())
        item = {"ticker": r["ticker"], "name": r.get("name"),
                "annual_status": r.get("status"),
                "interim_status": interim.get("status"),
                "financial_quality": r.get("financial_quality"),
                "filing_date": r.get("receipt_date"),
                "financial_screen_pass": pass_}
        (result["researched"] if pass_ else result["excluded"]).append(item)
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
