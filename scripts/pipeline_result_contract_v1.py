"""Validate completed research outputs without requiring market matches.

Only structural integrity determines execution success. Investment gates and
producer results are unchanged; zero candidates never grant a BUY approval.
This module has no market, network, credential, or order API dependencies.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

SCHEMA = "C3_RESEARCH_OUTPUT_INTEGRITY_V1"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def count(obj, key):
    value = obj.get(key)
    require(type(value) is int and value >= 0, "INVALID_COUNT:" + key)
    return value


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def iso(value):
    require(isinstance(value, str), "INVALID_ASOF")
    result = date.fromisoformat(value)
    require(result.isoformat() == value, "NONCANONICAL_ASOF")
    return result


def check_research(obj):
    require(obj.get("trade_approved") is False and
            obj.get("orders_enabled") is False and
            obj.get("decision") == "CASH", "RESEARCH_APPROVAL_MUTATED")


def table(rows, asof=None):
    keys = [r.get("ticker", "") for r in rows]
    require(all(re.fullmatch(r"[A-Z0-9]{6}", t) for t in keys), "INVALID_TICKER")
    require(len(keys) == len(set(keys)), "DUPLICATE_TICKER")
    for row in rows:
        require(row.get("trade_approved") == "False" and
                row.get("orders_enabled") == "False", "ROW_APPROVAL_MUTATED")
        if asof is not None:
            require(row.get("asof") == asof, "ROW_ASOF_MISMATCH")
    return set(keys)


def common(output, issuer, schema):
    require(output.get("schema") == schema, "WRONG_OUTPUT_SCHEMA")
    require(issuer.get("schema") == "C3_K100_OFFICIAL_ISSUER_ENTRY_V610",
            "WRONG_ISSUER_SCHEMA")
    check_research(output)
    check_research(issuer)
    iso(output.get("asof"))
    require(output["asof"] == issuer.get("asof"), "UPSTREAM_ASOF_MISMATCH")


def validate_broad(output, issuer, rows, audit):
    common(output, issuer, "C3_K100_BROAD_COVERAGE_RISK_FIRST_WATCH_V611")
    total = count(output, "full_market_universe")
    require(total == count(issuer, "full_market_initial_codes") and total > 0,
            "FULL_MARKET_COVERAGE_MISMATCH")
    liquid = count(output, "official_common_120day_50e8_liquid")
    flow = count(output, "official_common_120day_liquid_5d_positive_FI")
    both = count(output, "both_investors_5d_net_buy_positive")
    strong = count(output, "strong_proxy_sector_5d_positive_liquid")
    require(flow <= liquid <= total and both <= flow and strong <= flow,
            "IMPOSSIBLE_COUNT_RELATION")
    ids = table(rows, output["asof"])
    all_ids = table(audit, output["asof"])
    require(len(rows) == flow and len(audit) == total and ids <= all_ids,
            "OUTPUT_TABLE_COVERAGE_MISMATCH")
    require(sum(r.get("two_sided_fi_positive") == "True" for r in rows) == both,
            "BOTH_INVESTORS_COUNT_MISMATCH")
    require(sum(r.get("in_strong_sector_proxy") == "True" for r in rows) == strong,
            "STRONG_SECTOR_COUNT_MISMATCH")
    selected = {r["ticker"] for r in audit if r.get("phase") == "RESEARCH_WATCH"}
    require(selected == ids, "AUDIT_SELECTED_SET_MISMATCH")
    require(output.get("broad_radar_universe_untouched_by_old_52_candidate_filter") is True,
            "FULL_MARKET_SCOPE_MUTATED")
    for key in ["final_80_score_verified", "regular_1530_session_certified",
                "financial_and_catalyst_verified"]:
        require(output.get(key) is False, "UNCERTIFIED_AXIS_MUTATED:" + key)
    for key, observed in output.get("observed_watches", {}).items():
        require(isinstance(observed, list) and len(set(observed)) == len(observed)
                and set(observed) <= ids, "OBSERVED_WATCH_SET_INVALID")
        require(count(output.get("group_counts", {}), key) == len(observed),
                "GROUP_COUNT_MISMATCH")
    for key in ["analyzed_pattern_method_rows", "confirmed_research_trigger_rows",
                "both_limit_alternatives_2R_research_rows"]:
        count(output, key)
    require(output["confirmed_research_trigger_rows"] <= output["analyzed_pattern_method_rows"]
            and output["both_limit_alternatives_2R_research_rows"] <= output["confirmed_research_trigger_rows"],
            "IMPOSSIBLE_METHOD_COUNT")
    return dict(coverage=total, flow_watch=flow, strong_sector_watch=strong,
                empty_market_match_is_valid=True)


def validate_dart(output, issuer, stocks, receipts, issuer_rows):
    common(output, issuer, "C3_K100_DART_DATE_ONLY_DISCLOSURE_V6101")
    expected = count(issuer, "input_v68_candidates")
    require(count(output, "upstream_v610_candidates") == expected,
            "UPSTREAM_CANDIDATE_COUNT_MISMATCH")
    ids = table(stocks, output["asof"])
    issuer_ids = table(issuer_rows, output["asof"])
    require(len(stocks) == expected and ids == issuer_ids, "DART_CANDIDATE_SET_MISMATCH")
    require(output.get("v610_v18_source_run_id") == issuer.get("v68_source_run_id"),
            "DART_ANCESTOR_MISMATCH")
    for key in ["strict_intraday_PIT_publication_time_available", "fundamental_growth_checked",
                "catalyst_effect_and_amount_checked", "score80_final_checked"]:
        require(output.get(key) is False, "DART_UNCERTIFIED_AXIS_MUTATED:" + key)
    require(output.get("title_keywords_are_not_positive_earnings_verification") is True,
            "HEADLINE_POLICY_MUTATED")
    require(output.get("observation_window_days") == 30, "RECEIPT_WINDOW_MUTATED")
    require(len(receipts) == count(output, "strictly_preceding_receipts_captured")
            <= count(output, "date_only_source_receipt_count"), "RECEIPT_COVERAGE_MISMATCH")
    asof = iso(output["asof"])
    numbers = set()
    per_stock = Counter()
    for receipt in receipts:
        number = receipt.get("receipt_no", "")
        require(receipt.get("ticker") in ids and re.fullmatch(r"[0-9]{14}", number)
                and number not in numbers, "INVALID_OR_DUPLICATE_RECEIPT")
        numbers.add(number)
        receipt_date = iso(receipt.get("receipt_date"))
        require(asof-timedelta(days=30) <= receipt_date < asof,
                "SAME_DAY_FUTURE_OR_STALE_RECEIPT")
        require(receipt.get("trade_approved") == "False" and
                receipt.get("orders_enabled") == "False" and
                receipt.get("report_content_verified") == "False", "RECEIPT_APPROVAL_MUTATED")
        per_stock[receipt["ticker"]] += 1
    for stock in stocks:
        require(stock.get("actual_earnings_direction_verified") == "False",
                "EARNINGS_VERIFICATION_MUTATED")
        require(str(per_stock[stock["ticker"]]) == stock.get("prior_30_calendar_day_receipts"),
                "PER_STOCK_RECEIPT_COUNT_MISMATCH")
    require(count(output, "stocks_with_strict_prior_receipt") == len(per_stock),
            "RECEIPT_STOCK_COUNT_MISMATCH")
    return dict(coverage=expected, prior_receipts=len(receipts),
                empty_market_match_is_valid=True)


def review(kind, outdir, issuerdir):
    outdir, issuerdir = Path(outdir), Path(issuerdir)
    issuer = load_json(issuerdir / "issuer_entry_v610_status.json")
    if kind == "broad":
        output = load_json(outdir / "broad_watch_v611_status.json")
        # The producer seals these CSVs. Check bytes before parsing.
        for name in ["broad_watch_v611_all.csv", "broad_watch_v611_full_audit.csv"]:
            require(output.get("artifact_file_sha256", {}).get(name) ==
                    hashlib.sha256((outdir/name).read_bytes()).hexdigest(), "OUTPUT_FILE_HASH_MISMATCH")
        facts = validate_broad(output, issuer,
            load_csv(outdir/"broad_watch_v611_all.csv"), load_csv(outdir/"broad_watch_v611_full_audit.csv"))
    else:
        require(kind == "dart", "UNKNOWN_CONTRACT_KIND")
        output = load_json(outdir / "dart_date_only_v610_status.json")
        facts = validate_dart(output, issuer,
            load_csv(outdir/"dart_date_only_v610_all.csv"),
            load_csv(outdir/"dart_date_only_v610_prior_receipts.csv"),
            load_csv(issuerdir/"issuer_entry_v610_all.csv"))
    return dict(schema=SCHEMA, kind=kind, asof=output["asof"],
                execution_status="COMPLETED_VALID_RESEARCH_OUTPUT", facts=facts,
                investment_approval=False, decision="CASH", orders_enabled=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["broad", "dart"], required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--issuer", type=Path, required=True)
    args = parser.parse_args()
    result = review(args.kind, args.outdir, args.issuer)
    (args.outdir/"result_contract_v1.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("C3_RESEARCH_OUTPUT_INTEGRITY", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
