#!/usr/bin/env python3
"""C3 report-finality/readiness gate v19: no TOP2='zero' while computation is pending.

This is a derived, read-only report for the existing 22:30 ChatGPT workflow
and late 23:xx C3 result. It does NOT change scheduled alarms, trading logic,
photo delivery, registered signals, or immutable paper ledgers.

A research-validated FINANCEDATA_KRX_CACHE source must NEVER be advertised as
independently certified 09:00-15:30-only price/volume/turnover or BUY_APPROVED.
"""
import argparse
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KST=ZoneInfo("Asia/Seoul")
ACTIVE={"queued","in_progress","waiting","pending","requested"}
WORKFLOWS=("c3_research_daily_caller.yml","c3_daily_research_v8.yml")
VERSION="C3_READY_AND_SOURCE_ATTESTATION_V19"


def parsed(s):
    d=datetime.fromisoformat(str(s).replace("Z","+00:00"))
    if d.tzinfo is None:raise ValueError("TIMEZONE_REQUIRED")
    return d.astimezone(timezone.utc)


def expected_day(clock):
    """Nominal Mon-Fri calendar only; not proof the KRX had a trading session."""
    d=clock.astimezone(KST)
    if d.weekday()>=5:return None
    day=d.date()
    if d.hour<9 or (d.hour==9 and d.minute<30):
        day-=timedelta(days=1)
        while day.weekday()>=5:day-=timedelta(days=1)
    return day.isoformat()


def asof_runs(runs):
    """Workflows can have multiple attempts; one active pending run is enough."""
    active=[]
    for r in runs:
        if r.get("status") in ACTIVE:
            active.append(dict(
                id=r.get("id"),
                workflow=r.get("workflow_name") or r.get("name") or "C3_RESEARCH",
                status=r["status"],
                started_at=r.get("run_started_at") or r.get("created_at")))
    return active


def source_evidence(report,original_audit=None,recheck=None):
    """Market-source provenance: fail closed, never infer price-session scope."""
    audit=(original_audit or {}).get("actual_data") or {}
    original=audit.get("original_session_contract") or {}
    quality=(report or {}).get("source_quality_gate") or {}
    cache=((report or {}).get("source_provider")=="FINANCEDATA_KRX_CACHE")
    date=(report or {}).get("source_price_asof")
    date_matched=(not audit or audit.get("asof")==date)
    official_audit=((audit.get("official_response_diagnostics") or []))
    same_day=[x for x in official_audit if x.get("asof")==date]
    prior=(audit.get("earlier_official_control") or {})
    blockers=[]
    if report.get("source_regular_only_certified") is not True:
        blockers.append("INDEPENDENT_REGULAR_ONLY_ATTESTATION_MISSING")
    # A later official *daily* API being available is not independent minute
    # or session-bounded volume/turnover attestation.
    if cache:
        blockers.extend(("CACHED_DAILY_OHLC_MAY_INCLUDE_AFTERMARKET",
                         "VOLUME_AND_TURNOVER_ARE_NOT_0900_1530_ONLY"))
    if original:
        if original.get("regular_input_allowed") is False:
            blockers.append("ORIGINAL_PROVIDER_CONTRACT_DENIES_REGULAR_ONLY")
    if same_day and any(x.get("outblock_rows",0)==0 for x in same_day):
        blockers.append("OFFICIAL_SAME_DAY_API_RETURNED_EMPTY")
    if not date_matched:
        blockers.append("OFFICIAL_AUDIT_DATE_DOES_NOT_MATCH_SOURCE")
    if (report.get("source_quality_gate") or {}).get("full_current_listing_census_verified") is not True:
        blockers.append("INDEPENDENT_LISTING_CENSUS_UNVERIFIED")
    if audit and audit.get("full_current_listing_census_independently_verified") is not True:
        blockers.append("DATED_LISTING_AND_HALT_STATUS_UNVERIFIED")
    if quality.get("status")!="QUALITY_GATE_PASSED":
        blockers.append("SOURCE_INTERNAL_QUALITY_NOT_PASSED")
    # Even when a newly introduced 'verified' boolean appears in a report,
    # this gate cannot independently authenticate the missing scope. A future
    # approved provider-specific attestation verifier must be introduced first.
    # Date-locked later official rechecks are a separate, newer evidence item.
    # A newly available daily EOD file must not back-certify regular-only scope.
    recent=(recheck or {}) if (recheck or {}).get("requested_asof")==date else {}
    return dict(
        source_session=date,
        latest_official_dated_probe=dict(asof=recent.get("requested_asof"),
            status=recent.get("official_target_status"),
            rows=recent.get("official_target_rows"),
            regular_only_certified=False) if recent else None,
        original_provider=report.get("source_provider"),
        source_contract=original,
        research_quality_passed=quality.get("status")=="QUALITY_GATE_PASSED",
        regular_only_independently_certified=False,
        market_wide_0900_1530_volume_certified=False,
        market_wide_0900_1530_turnover_certified=False,
        independent_listing_census_certified=False,
        provider_claim_is_not_independent_certification=True,
        official_krx_status=audit.get("official_status","NOT_RECHECKED"),
        official_same_day_rows={x.get("market"):x.get("outblock_rows") for x in same_day},
        official_prior_day_control_rows=prior.get("rows"),
        caveats=sorted(set(blockers)),
        buy_approved=False,orders_enabled=False,decision="CASH")


def assess(latest,summary,clock,runs=(),audit=None,day=None,recheck=None):
    """Distinguish not-yet-calculated from genuinely finalized 0 picks.

    Crucial: absence of a *registered* result is NEVER final zero signals.
    Changing the date or looking at a later result must not time-travel.
    """
    clock=clock.astimezone(timezone.utc)
    requested=day or expected_day(clock)
    actives=asof_runs(runs)
    prov=source_evidence(latest,audit,recheck)
    reason=None
    final=False
    requested_day_valid=bool(requested)
    if not requested_day_valid:
        status="NO_NOMINAL_WEEKDAY_SESSION"
        reason="HOLIDAY_CALENDAR_SEPARATELY_UNVERIFIED"
    elif latest.get("source_price_asof")!=requested:
        status="RESEARCH_IN_PROGRESS" if actives else "SOURCE_OR_REPORT_NOT_YET_READY"
        reason="CURRENT_DATE_SOURCE_NOT_AVAILABLE"
    elif summary.get("source_price_asof")!=requested or (latest.get("source_run_id"),
              latest.get("generated_at"))!=(summary.get("source_run_id"),summary.get("generated_at")):
        status="RESEARCH_IN_PROGRESS" if actives else "SOURCE_AND_SUMMARY_REVISION_MISMATCH"
        reason="REPORT_NOT_ATOMICALLY_FINAL"
    else:
        try:
            generated=parsed(latest["generated_at"])
            completed=parsed(latest["analysis_completed_at"])
            received=parsed(latest["source_received_at"])
            close=parsed(requested+"T15:30:00+09:00")
            time_ok=close<=received<=completed<=generated<=clock
        except (KeyError,ValueError,TypeError):
            time_ok=False
        if not time_ok:
            status="RESEARCH_IN_PROGRESS" if actives else "RESEARCH_NOT_YET_AVAILABLE_AT_CHECK_TIME"
            reason="REPORT_NOT_FINAL_OR_FUTURE_AS_OF_CHECK_TIME"
        elif latest.get("errors") or (latest.get("source_quality_gate") or {}).get("status")!="QUALITY_GATE_PASSED":
            status="SOURCE_QUARANTINED"
            reason="RESEARCH_SOURCE_QUALITY_FAILED"
        elif latest.get("research_top2_registered_for_source_session") is not True:
            status="RESEARCH_IN_PROGRESS" if actives else "RESEARCH_NOT_REGISTERED"
            reason="NO_VALID_REGISTERED_DECISION_FOR_EXPECTED_SESSION"
        elif not latest.get("performance") or latest["performance"].get("registered_signals",0)<1:
            status="INCONSISTENT_REGISTERED_LEDGER"
            reason="MISSING_REGISTERED_SIGNAL_PROVENANCE"
        elif len(latest.get("research_top2") or [])==2 and len({
                x.get("ticker") for x in latest["research_top2"]})==2:
            status="FINAL_RESEARCH_TOP2_UNCERTIFIED_SESSION"
            reason=None
            final=True
        else:
            # Never invent "no TOP2" from an absent or incomplete report.
            status="NO_VERIFIABLE_FINAL_TOP2"
            reason="NONEMPTY_REGISTERED_LEDGER_BUT_NO_TWO_PROVEN_CANDIDATES"
    if final and actives:
        # Other active runs do not invalidate an already dated, complete,
        # explicitly committed immutable result. Do not re-label it as zero.
        pass
    picks=[dict(ticker=r["ticker"],name=r["name"],rank=r["rank"],
                reference_close=r.get("reference_close"))
           for r in latest.get("research_top2",[]) if final]
    return dict(schema=VERSION,checked_at_kst=clock.astimezone(KST).isoformat(),
      expected_source_day=requested,
      report_price_asof=latest.get("source_price_asof"),
      report_generation_at=latest.get("generated_at"),
      source_run_id=latest.get("source_run_id"),
      status=status,reason=reason,
      registered_top2_final_at_check_time=final,
      known_top2=picks,
      active_research_runs=actives,
      source_attestation=prov,
      no_candidate_status_not_inferred_from_missing_report=True,
      original_report_registered_signal_count=(latest.get("performance") or {}).get("registered_signals"),
      new_registered_signals_since_latest_report=latest.get("new_registered_signals"),
      recommendation_for_chatgpt=("연구 확정 TOP2는 종목과 가격을 제시할 수 있으나 정규장 독립인증 미완료로 CASH" if final
        else "TOP2 없음으로 확정하지 말고 선정·데이터 검증 미완료로 표시, CASH"),
      orders_enabled=False,trade_approved=False,send_telegram=False,decision="CASH")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--outdir",required=True)
    p.add_argument("--audit",default="reports/c3_operations_v18_20261107/execution_evidence.json")
    p.add_argument("--date",default=None,help="Optional expected source day for read-only dated diagnostic")
    p.add_argument("--recent-official",default=None,help="Optional read-only newer date-locked KRX EOD probe")
    p.add_argument("--at",default=None,help="Observation time ISO8601; default actual current time")
    args=p.parse_args()
    from c3_telegram_inputs import GitHub,report_pair
    gh=GitHub(os.environ.get("GH_TOKEN",""))
    latest,summary,revision=report_pair(gh)
    runs=[]
    for name in WORKFLOWS:
        try:
            data=gh.api("actions/workflows/"+name+"/runs?per_page=15")
            runs.extend([{**r,"workflow_name":name} for r in data.get("workflow_runs",[])])
        except Exception as exc:
            # A transient API failure cannot validate the report as finally
            # absent; the finality check is independently source-based.
            runs.append(dict(status="pending",workflow_name=name,
                             error_type=type(exc).__name__))
    audit=json.loads(Path(args.audit).read_text()) if Path(args.audit).is_file() else {}
    recent=json.loads(Path(args.recent_official).read_text()) if args.recent_official and Path(args.recent_official).is_file() else {}
    output=assess(latest,summary,parsed(args.at) if args.at else
                  datetime.now(timezone.utc),runs,audit,args.date,recent)
    output["research_commit_ref"]=revision
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    (out/"c3_readiness_gate_v19.json").write_text(
        json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print("C3_READINESS_GATE_V19="+json.dumps({
        k:output[k] for k in ("expected_source_day","status",
                              "registered_top2_final_at_check_time",
                              "source_run_id","decision","orders_enabled")},
            ensure_ascii=False),flush=True)


if __name__=="__main__":main()
