"""Independent third-party XKRX calendar cross-check; NOT an official KRX certification."""
import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path

# KRX closure announced 2026-05-20; source:
# https://www.yna.co.kr/amp/view/AKR20260520064251008
DOCUMENTED_KRX_CLOSURES={"2026-07-17":"CONSTITUTION_DAY_KRX_2026"}
def compare(plans, prices, start, end, sessions):
    raw_expected=set(sessions)
    overrides={d:DOCUMENTED_KRX_CLOSURES[d] for d in raw_expected if d in DOCUMENTED_KRX_CLOSURES}
    expected=raw_expected-set(DOCUMENTED_KRX_CLOSURES)
    if not expected:
        raise ValueError("EMPTY_THIRD_PARTY_SESSION_CALENDAR")
    if len(expected)!=len(sessions):
        raise ValueError("DUPLICATE_THIRD_PARTY_SESSION_DATE")
    observed={p["ticker"]:set() for p in plans}
    if len(observed)!=2 or len(plans)!=2:
        raise ValueError("EXPECTED_TWO_UNIQUE_PLANS")
    seen=set()
    for row in prices:
        ticker,day=row["ticker"],row["date"]
        if ticker not in observed:
            raise ValueError("UNEXPECTED_PRICE_TICKER")
        key=(ticker,day)
        if key in seen:
            raise ValueError("DUPLICATE_PRICE_TICKER_DATE")
        seen.add(key)
        observed[ticker].add(day)
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
                documented_calendar_overrides=overrides,
                third_party_calendar_unpatched=True,
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
    for ticker,info in result["results"].items():
        print("C3_XKRX_DATE_DIAGNOSTICS="+json.dumps(dict(
            ticker=ticker,
            missing_expected_dates=info["missing_expected_dates"][:30],
            unexpected_observed_dates=info["unexpected_observed_dates"][:30],
            missing_count=len(info["missing_expected_dates"]),
            unexpected_count=len(info["unexpected_observed_dates"])),ensure_ascii=False))
    raise SystemExit(2 if result["discrepancies_found"] else 0)

if __name__=="__main__":
    main()
