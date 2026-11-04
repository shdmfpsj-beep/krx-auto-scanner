"""Independent third-party XKRX calendar cross-check; NOT an official KRX certification."""
import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path

def compare(plans, prices, start, end, sessions):
    expected=set(sessions)
    observed={p["ticker"]:set() for p in plans}
    for row in prices:
        if row["ticker"] in observed:
            observed[row["ticker"]].add(row["date"])
    results={}
    for ticker, days in observed.items():
        results[ticker]=dict(missing_expected_dates=sorted(expected-days),
                             unexpected_observed_dates=sorted(days-expected),
                             expected_count=len(expected),
                             observed_count=len(days))
    return dict(schema="C3_XKRX_THIRD_PARTY_CALENDAR_CHECK_V1",
                calendar_provider="exchange_calendars:XKRX",
                official_krx_calendar_verified=False,
                calendar_source_verified=False,
                independent_price_verified=False,
                regular_only_certified=False,
                trade_approved=False,orders_enabled=False,
                start=start,end=end,results=results,
                discrepancies_found=any(v["missing_expected_dates"] or v["unexpected_observed_dates"] for v in results.values()))

def main():
    parser=argparse.ArgumentParser()
    for arg in ("plans","prices","start","end","output"):
        parser.add_argument("--"+arg,required=True)
    args=parser.parse_args()
    import exchange_calendars as xc
    cal=xc.get_calendar("XKRX")
    sessions=[d.strftime("%Y-%m-%d") for d in cal.sessions_in_range(args.start,args.end)]
    with open(args.plans,encoding="utf-8-sig",newline="") as f:
        plans=list(csv.DictReader(f))
    with open(args.prices,encoding="utf-8-sig",newline="") as f:
        prices=list(csv.DictReader(f))
    result=compare(plans,prices,args.start,args.end,sessions)
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="results"},ensure_ascii=False))
    raise SystemExit(2 if result["discrepancies_found"] else 0)

if __name__=="__main__":
    main()
