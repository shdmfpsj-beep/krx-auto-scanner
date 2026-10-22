"""Read-only, fail-closed KRX source pair admission. Date agreement is not OHLC equivalence."""
import json

REQUIRED_V18=("prices","price_ohlc_integrity","flows","etf_prices","holdings","normalization")

def read_status(archive,kind):
    names=[]
    for name in archive.namelist():
        clean=name.lstrip("./")
        if kind=="recovery" and clean in ("status.json","reports/status.json"):
            names.append(name)
        elif kind=="v18" and (clean=="diagnostics/collection_status.json" or
             clean in ("sector_evidence_v18/diagnostics/collection_status.json",
                       "reports/sector_evidence_v18/diagnostics/collection_status.json")):
            names.append(name)
    if len(names)!=1:return {}
    try:
        value=json.loads(archive.read(names[0]).decode("utf-8-sig"))
        return value if isinstance(value,dict) else {}
    except (KeyError,ValueError,UnicodeError,TypeError):
        return {}

def validate(kind,status,target):
    if not isinstance(status,dict) or not status:
        return ["MISSING_"+kind.upper()+"_STATUS"]
    errors=[]
    if kind=="recovery":
        if status.get("market_data_date")!=target:errors.append("RECOVERY_ASOF_MISMATCH")
        if status.get("scan_complete") is not True:errors.append("RECOVERY_SCAN_INCOMPLETE")
        if status.get("data_date_verified") is not True:errors.append("RECOVERY_PRICE_DATE_UNVERIFIED")
        ratio=status.get("coverage_ratio")
        if isinstance(ratio,bool) or not isinstance(ratio,(int,float)) or not 0.95<=ratio<=1:
            errors.append("RECOVERY_COVERAGE_UNVERIFIED")
        count=status.get("valid_ohlcv")
        if not isinstance(count,int) or isinstance(count,bool) or count<100:
            errors.append("RECOVERY_PRICE_SAMPLE_UNVERIFIED")
    elif kind=="v18":
        if status.get("asof")!=target:errors.append("V18_ASOF_MISMATCH")
        if status.get("mode")!="backfill":errors.append("V18_NOT_BACKFILL")
        if status.get("overall_status")!="EVIDENCE_PARTIAL_CATALYST_PIT_PENDING":
            errors.append("V18_STATUS_UNVERIFIED")
        if status.get("orders_enabled") is not False:errors.append("V18_NOT_READ_ONLY")
        ds=status.get("datasets") or {}
        for k in REQUIRED_V18:
            if not isinstance(ds.get(k),dict) or ds[k].get("status")!="OK":
                errors.append("V18_GATE_UNVERIFIED_"+k.upper())
    else:raise ValueError("UNKNOWN_SOURCE_KIND")
    return errors

def assess(recovery,v18,target):
    errors=validate("recovery",recovery,target)+validate("v18",v18,target)
    return dict(schema="krx_cross_source_gate_v1",target_asof=target,
                recovery_asof=(recovery or {}).get("market_data_date"),
                v18_asof=(v18 or {}).get("asof"),ready=not errors,
                errors=errors,same_exchange_date=bool(
                    recovery and v18 and recovery.get("market_data_date")==target==v18.get("asof")),
                independent_price_equivalence_verified=False,
                trade_approved=False,decision="CASH")
