#!/usr/bin/env python3
"""Read ONLY the frozen 2026-11-06 archive; produce non-trading V8 audit."""
from __future__ import annotations
import json
from pathlib import Path
from c3_v8_prospective_contract import evidence_snapshot,review_gate

COMMIT="7bad1564f2d017e6bd0481758d0f6e0f8aa0c289"
SOURCE=Path("frozen/reports/c3_forward_v8/latest.json")
OUT=Path("/tmp/c3-v8-prospective-audit")
MONDAY_OPEN="2026-11-09T09:00:00+09:00"

def main():
    source=json.loads(SOURCE.read_text(encoding="utf-8"))
    before=evidence_snapshot(source,check_at="2026-11-06T22:30:00+09:00",
                             next_session_open=MONDAY_OPEN,source_commit=COMMIT)
    after=evidence_snapshot(source,check_at="2026-11-07T08:30:00+09:00",
                            next_session_open=MONDAY_OPEN,source_commit=COMMIT)
    assert before["status"]=="ARCHIVED_REPORT_NOT_AVAILABLE_AS_OF_CHECK"
    assert before["selected_count"] is None
    assert after["status"]=="TOP2_REGISTERED_BUT_SOURCE_UNCERTIFIED"
    assert after["selected_count"]==2
    assert [x["ticker"] for x in after["selected"]]==["028050","030530"]
    assert all(x["buy_recommendation"]=="NOT_AUTHORIZED"
               for x in after["selected"])
    assert all(v=="FUTURE_OUTCOME_UNMATURED_OR_NOT_READ"
               for v in after["evaluation_windows"].values())
    # No prospective cohort was provided in this pinned archive.
    # This MUST not silently become zero backfilled returns or fabricated
    # forward decisions. Actual future observations require independent
    # publication and source certification on their own dates.
    review=review_gate([])
    assert review["unique_valid_independent_signals"]==0
    assert not review["process_review_ready"]
    result=dict(
        schema="C3_V8_REAL_ARCHIVE_READONLY_AUDIT_V1",
        pinned_commit=COMMIT,
        actual_original_report_source_asof=source["source_price_asof"],
        report_generated_at=source["generated_at"],
        asof_2026_11_06_2230=before,
        asof_2026_11_07_0830=after,
        true_new_independent_forward_20d_samples_in_this_audit=0,
        starting_prospective_review_gate=review,
        no_new_trading_rule=True,
        no_broker_order=True,no_notification=True,
        no_existing_signal_or_ledger_write=True,
        audit_pass=True,
    )
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"v8_archive_audit.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n",
        encoding="utf-8")
    concise=dict(
        status="PASS",source_asof=source["source_price_asof"],
        original_top2_count=after["selected_count"],
        at_2230_state=before["status"],
        at_nov7_0830_state=after["status"],
        per_ticker=[dict(name=x["name"],ticker=x["ticker"],
          rank=x["rank"],
          primary=x["entry_plan_diagnostics"]["A_SUPPORT_LIMIT"],
          secondary=x["entry_plan_diagnostics"]["B_CONFIRMED_PULLBACK"])
          for x in after["selected"]],
        source_regular_only_certified=False,
        forward_evidence_matured=0,
        no_buy_approval=True,untouched_operational_main=True)
    print("C3_V8_ARCHIVE_CHECK="+json.dumps(concise,ensure_ascii=False,allow_nan=False),
          flush=True)

if __name__=="__main__":
    main()
