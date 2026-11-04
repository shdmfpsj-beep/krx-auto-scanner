"""Detect asymmetric TOP2 date gaps without claiming an official KRX calendar."""
import argparse
import csv
import json
from pathlib import Path
from c3_price_concordance_v1 import read_rows

def inspect(plans,prices):
    codes=[p["ticker"] for p in plans]
    if len(codes)!=2 or len(set(codes))!=2:
        raise ValueError("EXPECTED_TWO_UNIQUE_TICKERS")
    dates={code:{day for ticker,day in prices if ticker==code} for code in codes}
    union=set.union(*(dates.values()))
    gaps={code:sorted(union-dates[code]) for code in codes}
    return dict(schema="C3_TOP2_CROSS_TICKER_DATE_GAPS_V1",
                tickers=codes,observed_date_union=len(union),
                asymmetric_missing_dates=gaps,
                asymmetric_gap_count=sum(map(len,gaps.values())),
                cross_ticker_dates_aligned=not any(gaps.values()),
                official_exchange_calendar_verified=False,
                common_missing_sessions_detectable=False,
                regular_only_certified=False,
                trade_approved=False,orders_enabled=False)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True)
    p.add_argument("--prices",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    with Path(a.plans).open(encoding="utf-8-sig",newline="") as f:
        plans=list(csv.DictReader(f))
    result=inspect(plans,read_rows(a.prices))
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":
    main()
