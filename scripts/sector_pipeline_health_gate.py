#!/usr/bin/env python3
"""Pure source-quality assessment for the daily read-only KRX health audit.

Workflow success means software ran, not that bars are coherent or tradable.
A failed collector may publish useful diagnostics. Never promote that
diagnostic artifact into a verified sector rank or a BUY instruction.
"""
from datetime import date

REQUIRED=("prices","price_ohlc_integrity","flows","etf_prices","holdings","normalization")
VALID_OVERALL={"EVIDENCE_PARTIAL_CATALYST_PIT_PENDING"}

def judge_collection(status,expected_asof,workflow_conclusion):
    if not isinstance(status,dict) or not status:
        return dict(status="NOT_VERIFIED",reason="SOURCE_STATUS_ARTIFACT_UNAVAILABLE",
                    asof=None,datasets={},missing_gates=list(REQUIRED),
                    source_verified=False,source_diagnostic_available=False,
                    prices_api_ok=False,price_integrity_ok=False,
                    trade_approved=False)
    datasets=status.get("datasets")
    if not isinstance(datasets,dict):datasets={}
    names={k:v.get("status","MISSING") if isinstance(v,dict) else "MISSING"
           for k,v in datasets.items()}
    checks=[k for k in REQUIRED if names.get(k)!="OK"]
    price=names.get("price_ohlc_integrity","MISSING")
    price_row=datasets.get("price_ohlc_integrity") if isinstance(datasets.get("price_ohlc_integrity"),dict) else {}
    asof=status.get("asof")
    fresh=asof==expected_asof
    source_verified=(workflow_conclusion=="success" and fresh
                     and status.get("overall_status") in VALID_OVERALL
                     and not checks
                     and status.get("orders_enabled") is False)
    if price=="MISSING":
        reason="SOURCE_OHLC_INTEGRITY_GATE_NOT_RECORDED"
    elif price!="OK":
        reason="SOURCE_OHLC_INTEGRITY_FAILED"
    elif checks:
        reason="SOURCE_CORE_DATASET_MISSING_OR_UNVERIFIED"
    elif workflow_conclusion!="success":
        reason="SOURCE_WORKFLOW_FAILED_EVEN_IF_ARTIFACT_EXISTS"
    elif not fresh:
        reason="SOURCE_ASOF_MISMATCH"
    elif status.get("overall_status") not in VALID_OVERALL:
        reason="SOURCE_OVERALL_STATUS_UNVERIFIED"
    elif status.get("orders_enabled") is not False:
        reason="SOURCE_ORDER_FLAG_NOT_READ_ONLY"
    else:
        reason="PRICE_SOURCE_QUALITY_VERIFIED_RESEARCH_ONLY"
    return dict(status=status.get("overall_status","UNKNOWN"),reason=reason,
                asof=asof,fresh_for_today=fresh,workflow_conclusion=workflow_conclusion,
                datasets=names,missing_gates=checks,
                prices_api_ok=names.get("prices")=="OK",
                price_integrity_ok=(price=="OK"),
                price_checked=price_row.get("checked"),
                price_invalid=price_row.get("invalid"),
                price_invalid_pct=price_row.get("invalid_pct"),
                source_diagnostic_available=True,
                source_verified=bool(source_verified),
                orders_enabled=status.get("orders_enabled"),
                trade_approved=False)

if __name__=="__main__":
    raise SystemExit("LIBRARY_ONLY_RUN_OFFLINE_TESTS")
