"""Classify free daily C3 data readiness from source evidence, without trading."""
import argparse,json
from pathlib import Path
def diagnose(ledger,source_status=None,scan_status=None):
    positions=ledger.get("positions",{})
    states=(source_status or {}).get("ticker_states",{})
    scan=scan_status or {}
    rows=[]
    for p in positions.values():
        ticker=p.get("plan",{}).get("ticker","")
        source=states.get(ticker,{})
        capture=source.get("capture_status","NOT_REPORTED")
        observed=int(p.get("sessions_observed") or 0)
        if capture=="FAILED_OR_SUSPENDED_NO_PAPER_TRADE":
            reason="PRICE_PROVIDER_FAILED_OR_SUSPENDED"
        elif capture=="NOT_REPORTED":
            reason="CAPTURE_ARTIFACT_NOT_AVAILABLE"
        elif not scan.get("scan_complete",False):
            reason="FULL_MARKET_SCAN_NOT_VERIFIED"
        elif not scan.get("market_data_date"):
            reason="SCAN_DATE_MISSING"
        elif source.get("last_session")!=scan.get("market_data_date"):
            reason="SOURCE_DATES_MISMATCH"
        elif observed==0:
            reason="CHECK_REGISTRATION_AND_FORWARD_ELIGIBILITY"
        else:
            reason="FORWARD_OBSERVATIONS_PRESENT"
        rows.append({"ticker":ticker,"name":p.get("plan",{}).get("name"),
            "paper_status":p.get("status"),"observed_sessions":observed,
            "source_capture_status":capture,"source_last_session":source.get("last_session"),
            "scan_date":scan.get("market_data_date"),"reason":reason,
            "actual_order":False,"verified_regular_only":False})
    return {"schema":"C3_FREE_SOURCE_DIAGNOSTIC_V1",
        "positions":rows,"source_available":source_status is not None,
        "scan_available":scan_status is not None,"orders_enabled":False,
        "readiness_not_profitability":True}
def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path and Path(path).exists() else None
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",required=True);p.add_argument("--source");p.add_argument("--scan");p.add_argument("--out")
    a=p.parse_args();ledger=read(a.ledger)
    if ledger is None:raise SystemExit("LEDGER_MISSING")
    result=diagnose(ledger,read(a.source),read(a.scan))
    output=json.dumps(result,ensure_ascii=False,indent=2)
    if a.out:
        out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(output+"\n",encoding="utf-8")
    print(output)
