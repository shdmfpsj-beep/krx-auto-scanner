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
from c3_top5_financial_selection import finite

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
    if day > today:
        result["status"] = "FUTURE_ASOF_NOT_ALLOWED"
        return result
    result["financial_observed_on"] = today.isoformat()
    result["signal_date"] = asof
    # Observation on the same date is not proof of an immutable PIT snapshot.
    result["point_in_time_snapshot_verified"] = False
    result["historical_disclosure_date_filter_only"] = (day < today)
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
        if not re.fullmatch(r"[0-9A-Z]{6}", ticker):
            result["status"] = "INVALID_TICKER"
            return result
        if ticker in seen:
            result["status"] = "DUPLICATE_TICKER"
            return result
        seen.add(ticker)
        stocks.append({"ticker": ticker, "name": str(c.get("name", "")),
                       "sector_id": "UNKNOWN", "research_proxy_index": ""})
    try:
        research = collector(today, stocks, key, today=today)
    except Exception as exc:
        result["status"] = "DART_COLLECTION_FAILED_" + type(exc).__name__
        return result
    if not isinstance(research, dict):
        result["status"] = "INVALID_DART_RESPONSE"
        return result
    result["source_status"] = research.get("status", "UNKNOWN")
    returned = set()
    evidence_failed = False
    for r in research.get("researched", []):
        if r.get("ticker") not in seen or r.get("ticker") in returned:
            result["status"] = "INVALID_FINANCIAL_COVERAGE"
            result["researched"] = []
            result["excluded"] = []
            return result
        returned.add(r["ticker"])
        annual = r.get("status") == "DATED_ANNUAL_RESEARCH_ONLY"
        interim = r.get("interim_research") or {}
        annual_receipt = r.get("receipt_date")
        interim_receipt = interim.get("filing", {}).get("receipt_date")
        comparable = bool(r.get("latest_periodic_division_comparable"))
        # Hard risk gate: verified statements, positive equity and annual operating
        # profit, and no excessive balance-sheet leverage. Sales/profit slowdown
        # is scored, not an automatic veto. No missing metric is assumed safe.
        equity = r.get("equity_krw")
        liabilities = r.get("liabilities_krw")
        operating_profit = r.get("operating_profit_krw")
        leverage_ok = (finite(equity) and equity>0 and
                       finite(liabilities) and liabilities>=0 and
                       liabilities/equity<=3.0)
        profitable = finite(operating_profit) and operating_profit>0
        evidence_ok = bool(annual and
            all(finite(v) for v in (equity, liabilities, operating_profit)) and
            interim.get("status")=="DATED_INTERIM_YTD_RESEARCH_ONLY" and
            comparable and annual_receipt and interim_receipt and
            str(annual_receipt)<=day.isoformat() and
            str(interim_receipt)<=day.isoformat())
        evidence_failed = evidence_failed or not evidence_ok
        pass_ = bool(evidence_ok and leverage_ok and profitable and
            r.get("financial_quality")!="FINANCIAL_SECTOR_SPECIAL_MODEL_REQUIRED")
        reasons = []
        if not annual: reasons.append("ANNUAL_REPORT_NOT_VERIFIED")
        if interim.get("status")!="DATED_INTERIM_YTD_RESEARCH_ONLY": reasons.append("INTERIM_NOT_VERIFIED")
        if not comparable: reasons.append("STATEMENT_DIVISION_NOT_COMPARABLE")
        if not annual_receipt or str(annual_receipt)>day.isoformat(): reasons.append("ANNUAL_RECEIPT_AFTER_SIGNAL_OR_MISSING")
        if not interim_receipt or str(interim_receipt)>day.isoformat(): reasons.append("INTERIM_RECEIPT_AFTER_SIGNAL_OR_MISSING")
        if not leverage_ok: reasons.append("BALANCE_SHEET_LEVERAGE_OR_EQUITY_RISK")
        if not profitable: reasons.append("ANNUAL_OPERATING_LOSS_OR_UNKNOWN")
        if r.get("financial_quality")=="FINANCIAL_SECTOR_SPECIAL_MODEL_REQUIRED": reasons.append("SECTOR_MODEL_REQUIRED")
        slowdown = bool(r.get("recent_financial_weakening_veto"))
        item = {"ticker": r["ticker"], "name": r.get("name"),
                "financial_evidence_complete": evidence_ok,
                "annual_status": r.get("status"),
                "interim_status": interim.get("status"),
                "financial_quality": r.get("financial_quality"),
                "filing_date": r.get("receipt_date"),
                "financial_screen_pass": pass_,
                "financial_risk_gate_pass": pass_,
                "recent_slowdown_flag": slowdown,
                "liabilities_to_equity_pct": round(liabilities/equity*100,2) if leverage_ok else None,
                "annual_quality_screen_pass": bool(r.get("financial_screen_pass")),
                "annual_plus_interim_growth_pass": bool(r.get("annual_plus_interim_growth_pass")),
                "interim_quality": interim.get("quality"),
                "interim_filing_date": interim.get("filing", {}).get("receipt_date"),
                "exclusion_reasons": reasons if not pass_ else []}
        (result["researched"] if pass_ else result["excluded"]).append(item)
    if len(result["researched"]) + len(result["excluded"]) != len(stocks):
        result["status"] = "INCOMPLETE_FINANCIAL_COVERAGE"
    elif evidence_failed:
        # Missing/API-failed evidence is an operational failure, not a finding
        # that every company is financially unsuitable and normal CASH.
        result["status"] = "FAILED_FINANCIAL_EVIDENCE"
    elif day < today:
        result["status"] = "HISTORICAL_DISCLOSURE_DATE_FILTERED_RESEARCH_ONLY"
        result["financial_verified"] = False
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
