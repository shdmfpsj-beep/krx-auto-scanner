"""Classify free daily C3 data readiness from source evidence, without trading."""
import argparse,json
from pathlib import Path
def diagnose(ledger,source_status=None,scan_status=None,report_date=None,report_phase="POST_CLOSE",source_run_id=None):
    positions=ledger.get("positions",{})
    states=(source_status or {}).get("ticker_states",{})
    scan=scan_status or {}
    rows=[]
    for p in positions.values():
        ticker=p.get("plan",{}).get("ticker","")
        source=states.get(ticker,{})
        capture=source.get("capture_status","NOT_REPORTED")
        observed=int(p.get("sessions_observed") or 0)
        if report_date and p.get("last_observed_date") and p.get("last_observed_date")>report_date:
            reason="LEDGER_DATE_IN_FUTURE"
        elif report_date and source.get("last_session") and source.get("last_session")>report_date:
            reason="SOURCE_DATE_IN_FUTURE"
        elif capture=="FAILED_OR_SUSPENDED_NO_PAPER_TRADE":
            reason="PRICE_PROVIDER_FAILED_OR_SUSPENDED"
        elif report_phase=="PRE_CLOSE" and report_date and source.get("last_session") and source.get("last_session")<report_date:
            reason="AWAIT_TODAY_CLOSE_PRICE"
        elif report_date and source.get("last_session") and source.get("last_session")<report_date and observed==0 and p.get("plan",{}).get("registered_day","")<report_date:
            reason="NO_CURRENT_REPORT_DATE_PRICE"
        elif capture=="NOT_REPORTED":
            reason="CAPTURE_ARTIFACT_NOT_AVAILABLE"
        elif not scan.get("scan_complete",False):
            reason="FULL_MARKET_SCAN_NOT_VERIFIED"
        elif not scan.get("market_data_date"):
            reason="SCAN_DATE_MISSING"
        elif source.get("last_session")!=scan.get("market_data_date"):
            reason="SOURCE_DATES_MISMATCH"
        elif source.get("last_session") and p.get("plan",{}).get("registered_day") and source.get("last_session")<=p["plan"]["registered_day"]:
            reason="NO_POST_REGISTRATION_SESSION_YET"
        elif observed==0:
            reason="CHECK_REGISTRATION_AND_FORWARD_ELIGIBILITY"
        else:
            reason="FORWARD_OBSERVATIONS_PRESENT"
        if observed>0 and report_date and source.get("last_session") and source.get("last_session")<report_date and reason in ("AWAIT_TODAY_CLOSE_PRICE","NO_CURRENT_REPORT_DATE_PRICE","FORWARD_OBSERVATIONS_PRESENT"):
            reason="HISTORICAL_OBSERVATIONS_ONLY"
        rows.append({"ticker":ticker,"name":p.get("plan",{}).get("name"),
            "paper_status":p.get("status"),"observed_sessions":observed,
            "source_capture_status":capture,"source_last_session":source.get("last_session"),
            "scan_date":scan.get("market_data_date"),"last_observed_date":p.get("last_observed_date"),"reason":reason,
            "actual_order":False,"verified_regular_only":False})
    return {"schema":"C3_FREE_SOURCE_DIAGNOSTIC_V1",
        "positions":rows,"source_available":source_status is not None,
        "scan_available":scan_status is not None,"report_date":report_date,"report_phase":report_phase,"source_run_id":source_run_id,"orders_enabled":False,
        "readiness_not_profitability":True}
def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path and Path(path).exists() else None
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",required=True);p.add_argument("--source");p.add_argument("--scan");p.add_argument("--out");p.add_argument("--report-date");p.add_argument("--source-run-id");p.add_argument("--report-phase",choices=("PRE_CLOSE","POST_CLOSE"),default="POST_CLOSE")
    a=p.parse_args();ledger=read(a.ledger)
    if ledger is None:raise SystemExit("LEDGER_MISSING")
    result=diagnose(ledger,read(a.source),read(a.scan),a.report_date,a.report_phase,a.source_run_id)
    output=json.dumps(result,ensure_ascii=False,indent=2)
    if a.out:
        out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(output+"\n",encoding="utf-8")
    print(output)
