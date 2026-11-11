"""Research-only fail-closed certification gate. No order generation or PnL."""
from __future__ import annotations
import datetime as dt
from typing import Mapping

REQUIRED_CORPORATE = ("ticker", "event_date", "source_url", "source_sha256",
                      "official_effective_date", "official_reference_price",
                      "raw_price_basis", "adjustment_method", "retrieved_at")
REQUIRED_FINANCIAL = ("ticker", "selection_date", "receipt_date", "original_filing_id",
                      "original_sha256", "revenue", "operating_profit", "debt",
                      "equity", "previous_year_revenue", "is_latest_correction_asof")
REQUIRED_FILL = ("ticker", "signal_date", "entry_low", "entry_high",
                 "structural_stop", "resistance", "expiration_sessions",
                 "execution_timestamp", "execution_price", "execution_source_sha256")

def _date(value):
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None

def certify_corporate_action(record: Mapping) -> dict:
    missing = [k for k in REQUIRED_CORPORATE if record.get(k) in (None, "")]
    if missing:
        return {"status": "BLOCKED_MISSING_PRIMARY_PROOF", "missing": missing}
    event, effective = _date(record["event_date"]), _date(record["official_effective_date"])
    if event is None or effective is None:
        return {"status": "BLOCKED_INVALID_DATES"}
    if record["raw_price_basis"] not in ("UNADJUSTED", "ADJUSTED_VERIFIED"):
        return {"status": "BLOCKED_PRICE_BASIS"}
    if record["adjustment_method"] not in ("OFFICIAL_REFERENCE_REBASE", "OFFICIAL_ADJUSTED_SERIES"):
        return {"status": "BLOCKED_ADJUSTMENT_UNVERIFIED"}
    if not isinstance(record["official_reference_price"], (int, float)) or record["official_reference_price"] <= 0:
        return {"status": "BLOCKED_REFERENCE_PRICE"}
    if not str(record["source_url"]).startswith(("https://kind.krx.co.kr/", "https://dart.fss.or.kr/")):
        return {"status": "BLOCKED_UNTRUSTED_ORIGIN"}
    return {"status": "PRIMARY_PROOF_FIELDS_PRESENT_REQUIRES_MANUAL_SOURCE_AUDIT"}

def certify_financial(record: Mapping) -> dict:
    missing = [k for k in REQUIRED_FINANCIAL if record.get(k) in (None, "")]
    if missing:
        return {"status": "BLOCKED_NO_ORIGINAL_NUMERIC_PIT", "missing": missing}
    signal, receipt = _date(record["selection_date"]), _date(record["receipt_date"])
    if signal is None or receipt is None or receipt >= signal:
        return {"status": "BLOCKED_FUTURE_OR_SAME_DAY_FILING"}
    if record["is_latest_correction_asof"] is not True:
        return {"status": "BLOCKED_CORRECTION_LINEAGE"}
    if not all(isinstance(record[k], (int, float)) for k in
               ("revenue", "operating_profit", "debt", "equity", "previous_year_revenue")):
        return {"status": "BLOCKED_NON_NUMERIC_FINANCIAL"}
    if record["equity"] <= 0 or record["previous_year_revenue"] == 0:
        return {"status": "BLOCKED_UNDEFINED_RATIOS"}
    return {"status": "PRIMARY_PIT_FIELDS_PRESENT_REQUIRES_ORIGINAL_REPLAY",
            "operating_margin_pct": 100 * record["operating_profit"] / record["revenue"]
            if record["revenue"] else None,
            "revenue_yoy_pct": 100 * (record["revenue"] / record["previous_year_revenue"] - 1),
            "debt_to_equity_pct": 100 * record["debt"] / record["equity"]}

def classify_entry(record: Mapping) -> dict:
    missing = [k for k in REQUIRED_FILL if record.get(k) in (None, "")]
    if missing:
        return {"status": "UNCONFIRMED_DAILY_OVERLAP_NOT_FILL", "missing": missing}
    if record["execution_timestamp"] <= record["signal_date"]:
        return {"status": "BLOCKED_EXECUTION_TIME"}
    price = record["execution_price"]
    if not isinstance(price, (int, float)) or not record["entry_low"] <= price <= record["entry_high"]:
        return {"status": "BLOCKED_EXECUTION_OUTSIDE_BAND"}
    if not record["structural_stop"] < price < record["resistance"]:
        return {"status": "BLOCKED_ENTRY_GEOMETRY"}
    if record["expiration_sessions"] not in (1, 2, 3):
        return {"status": "BLOCKED_EXPIRATION"}
    return {"status": "EXECUTION_FIELDS_PRESENT_REQUIRES_BROKER_OR_INTRADAY_AUDIT"}
