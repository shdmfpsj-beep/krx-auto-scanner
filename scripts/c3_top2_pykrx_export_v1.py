"""Export provisional TOP2 pykrx research OHLCV and observed-date union.

Not an exchange-verified trading calendar or independent regular-only feed.
Never overwrites frozen plans or places orders.
"""
import argparse
import csv
import json
import hashlib
import inspect
import math
import re
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

def routing_probe(fetch):
    """Inspect the installed adapter without claiming an independent feed."""
    try:
        source=inspect.getsource(fetch)
    except (OSError,TypeError):
        return dict(upstream="PYKRX_UPSTREAM_UNVERIFIED",source_sha256=None)
    naver_adjusted=bool(re.search(r"if adjusted:\s+df\s*=\s*naver\.get_market_ohlcv_by_date",source))
    return dict(upstream="NAVER_VIA_PYKRX_ADJUSTED" if naver_adjusted else "PYKRX_UPSTREAM_UNVERIFIED",
                source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                adjusted_request_routes_to_naver=naver_adjusted,
                inspection_is_not_session_certification=True)

def collect(plans,fetch,start,end):
    tickers=[p["ticker"] for p in plans]
    if len(tickers)!=2 or len(set(tickers))!=2:
        raise ValueError("EXPECTED_TWO_UNIQUE_TICKERS")
    rows=[]
    days=set()
    failures={}
    for code in tickers:
        try:
            ticker_rows=[]
            frame=fetch(start.replace("-",""),end.replace("-",""),code,adjusted=True)
            if frame is None or frame.empty:
                raise ValueError("EMPTY_RESPONSE")
            for idx,r in frame.iterrows():
                day=idx.strftime("%Y-%m-%d")
                vals=[float(r[k]) for k in ("시가","고가","저가","종가","거래량")]
                if not all(math.isfinite(v) for v in vals) or not (0<vals[2]<=min(vals[0],vals[3])<=max(vals[0],vals[3])<=vals[1]) or vals[4]<0:
                    raise ValueError("INVALID_OHLCV")
                if not start<=day<=end:
                    raise ValueError("PRICE_OUTSIDE_REQUESTED_DATES")
                ticker_rows.append(dict(ticker=code,date=day,open=vals[0],high=vals[1],
                                 low=vals[2],close=vals[3],volume=vals[4]))
            rows.extend(ticker_rows)
            days.update(r["date"] for r in ticker_rows)
        except Exception as exc:
            failures[code]=type(exc).__name__+":"+str(exc)[:150]
    rows.sort(key=lambda r:(r["ticker"],r["date"]))
    if len({(r["ticker"],r["date"]) for r in rows})!=len(rows):
        raise ValueError("DUPLICATE_OHLCV")
    return rows,sorted(days),failures

def history_start(plans,lookback_calendar_days=120):
    if lookback_calendar_days<40:
        raise ValueError("INSUFFICIENT_REQUESTED_HISTORY")
    return min(date.fromisoformat(p["selection_date"]) for p in plans)-timedelta(days=lookback_calendar_days)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True)
    p.add_argument("--end",required=True,help="Last completed research date YYYY-MM-DD")
    p.add_argument("--outdir",required=True)
    a=p.parse_args()
    end=date.fromisoformat(a.end)
    kst_today=datetime.now(timezone(timedelta(hours=9))).date()
    if end>=kst_today:
        raise ValueError("END_DATE_MUST_PRECEDE_KST_TODAY")
    with Path(a.plans).open(encoding="utf-8-sig",newline="") as f:
        plans=list(csv.DictReader(f))
    start=history_start(plans,120)
    from pykrx import stock
    probe=routing_probe(stock.get_market_ohlcv_by_date)
    rows,days,failures=collect(plans,stock.get_market_ohlcv_by_date,start.isoformat(),end.isoformat())
    out=Path(a.outdir)
    out.mkdir(parents=True,exist_ok=True)
    with (out/"top2_provisional_ohlcv.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["ticker","date","open","high","low","close","volume"])
        w.writeheader()
        w.writerows(rows)
    with (out/"observed_date_union_NOT_VERIFIED_CALENDAR.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.writer(f)
        w.writerow(["date"])
        w.writerows([[d] for d in days])
    # Date diagnostics are observations only; not an official exchange calendar.
    by_ticker={code:sorted(r["date"] for r in rows if r["ticker"]==code)
               for code in sorted({p["ticker"] for p in plans})}
    ticker_date_coverage={code:dict(observed_rows=len(dates),
                                    first_observed_date=dates[0] if dates else None,
                                    last_observed_date=dates[-1] if dates else None,
                                    calendar_days_from_last_to_end=(end-date.fromisoformat(dates[-1])).days if dates else None)
                          for code,dates in by_ticker.items()}
    last_dates={v["last_observed_date"] for v in ticker_date_coverage.values()}
    latest_observed_dates_aligned=(len(last_dates)==1 and None not in last_dates)
    manifest=dict(schema="C3_TOP2_PYKRX_PROVISIONAL_EXPORT_V1",
                  provider="pykrx",upstream=probe["upstream"],
                  source_routing_probe=probe,
                  price_adjustment="ADJUSTED",market_scope="UNKNOWN",
                  session_calendar_verified=False,
                  observed_dates_are_not_exchange_calendar=True,
                  independent_price_verified=False,regular_only_certified=False,
                  trade_approved=False,orders_enabled=False,
                  history_lookback_calendar_days=120,
                  history_before_selection_requested=True,
                  start=start.isoformat(),end=end.isoformat(),
                  rows=len(rows),tickers=sorted({r["ticker"] for r in rows}),
                  ticker_date_coverage=ticker_date_coverage,
                  latest_observed_dates_aligned=latest_observed_dates_aligned,
                  failures=failures)
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(manifest,ensure_ascii=False))
    if failures or len(manifest["tickers"])!=2:
        raise SystemExit(2)

if __name__=="__main__":
    main()
