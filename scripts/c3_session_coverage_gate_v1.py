"""Fail-closed TOP2 price input coverage gate.

Verifies exact registered tickers, ISO dates, session ordering and missing
calendar gaps only when an explicit exchange session calendar is supplied.
A row count alone does not establish consecutive trading sessions.
"""
import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from c3_price_concordance_v1 import read_rows

def validate(plans,prices,session_dates):
    items=list(plans)
    errors=[]
    if len(items)!=2 or len({p["ticker"] for p in items})!=2:
        errors.append("EXPECTED_TWO_UNIQUE_TICKERS")
    if not session_dates:
        errors.append("SESSION_CALENDAR_REQUIRED")
    if len(set(session_dates))!=len(session_dates):
        errors.append("DUPLICATE_CALENDAR_DAY")
    try:
        for d in session_dates:
            dt.date.fromisoformat(d)
        if session_dates!=sorted(session_dates):
            errors.append("CALENDAR_NOT_SORTED")
        for code,day in prices:
            dt.date.fromisoformat(day)
            if len(code)!=6 or not code.isdigit():
                errors.append("INVALID_TICKER")
    except ValueError:
        errors.append("INVALID_DATE")
    expected={p["ticker"] for p in items}
    unexpected=sorted({code for code,_ in prices}-expected)
    if unexpected:
        errors.append("UNEXPECTED_TICKERS")
    coverage={}
    for p in items:
        code=p["ticker"]
        reg=p["registered_day"]
        try:
            dt.date.fromisoformat(reg)
        except ValueError:
            errors.append("INVALID_REGISTRATION_DATE")
            continue
        dates=[d for d in session_dates if d>reg][:20]
        observed=[d for d in dates if (code,d) in prices]
        missing=[d for d in dates if (code,d) not in prices]
        outside=[d for (ticker,d) in prices if ticker==code and d>reg and d not in session_dates]
        if outside:
            errors.append("PRICE_DAY_NOT_IN_SESSION_CALENDAR")
        coverage[code]=dict(expected_session_days=len(dates),
                            observed_session_days=len(observed),
                            missing_session_dates=missing,
                            five_complete=len(dates)>=5 and not any(d in missing for d in dates[:5]),
                            ten_complete=len(dates)>=10 and not any(d in missing for d in dates[:10]),
                            twenty_complete=len(dates)>=20 and not missing)
    if any(v["missing_session_dates"] for v in coverage.values()):
        errors.append("MISSING_EXPECTED_SESSION_ROWS")
    errors=sorted(set(errors))
    return dict(schema="C3_TOP2_SESSION_COVERAGE_GATE_V1",
                calendar_source_verified=False,
                input_complete=not errors,
                data_certified=False,trade_approved=False,orders_enabled=False,
                errors=errors,coverage=coverage)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True)
    p.add_argument("--prices",required=True)
    p.add_argument("--sessions",required=True,help="CSV with date column, exchange session days")
    p.add_argument("--output",required=True)
    a=p.parse_args()
    with Path(a.plans).open(encoding="utf-8-sig",newline="") as f:
        plans=list(csv.DictReader(f))
    with Path(a.sessions).open(encoding="utf-8-sig",newline="") as f:
        days=[r["date"] for r in csv.DictReader(f)]
    result=validate(plans,read_rows(a.prices),days)
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result["input_complete"] else 2)

if __name__=="__main__":
    main()
