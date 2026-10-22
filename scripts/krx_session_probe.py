#!/usr/bin/env python3
"""Read-only KRX regular/after-market provenance probe (no orders).

Do not repair provider prices, infer an exact close, or reuse session-mixed
snapshots as final investment OHLCV. GitHub scheduler latency is recorded.
"""
import argparse
import json
import math
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

KST=ZoneInfo("Asia/Seoul")
FIELDS=("Open","High","Low","Close","Volume","TurnoverKRW")
SOURCE="pykrx_get_market_ohlcv_date_only"

def numeric(x):
    try:
        x=float(x)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):
        return None

def capture_window(phase, now):
    if phase=="regular":
        return "REGULAR_WINDOW" if now.weekday()<5 and now.hour==15 and now.minute>=35 else "MISSED_REGULAR_WINDOW"
    if phase=="after":
        return "AFTER_CLOSE_WINDOW" if now.weekday()<5 and 20<=now.hour<=23 else "MISSED_AFTER_CLOSE_WINDOW"
    raise ValueError("UNKNOWN_PHASE")

def check_bars(stocks):
    checked=invalid=low=high=0
    for ticker,r in stocks.items():
        if not re.fullmatch(r"[0-9]{6}",ticker):
            continue
        op,hi,lo,close,vol=(numeric(r.get(k)) for k in ("Open","High","Low","Close","Volume"))
        if op==hi==lo==0 and close and close>0:continue
        if close is None or close<=0:continue
        checked+=1
        if None in (op,hi,lo,vol) or not (0<lo<=min(op,close)<=max(op,close)<=hi and vol>=0):
            invalid+=1
            if lo is not None and close<lo:low+=1
            elif hi is not None and close>hi:high+=1
    return dict(checked=checked,invalid=invalid,invalid_pct=round(invalid*100/max(checked,1),2),
                below_low=low,above_high=high)

def new_snapshot(phase, now, markets, ended_at=None):
    stocks={}
    market_counts={}
    for market, rows in markets.items():
        market_counts[market]=len(rows)
        for ticker,bar in rows.items():
            if ticker in stocks:
                raise ValueError("DUPLICATE_TICKER_ACROSS_MARKETS")
            stocks[ticker]={"market":market,**{k:numeric(bar.get(k)) for k in FIELDS}}
    end=ended_at or now
    window=capture_window(phase,now)
    if phase=="regular" and capture_window(phase,end)!="REGULAR_WINDOW":
        window="REGULAR_CAPTURE_FINISHED_AFTER_1600"
    return dict(schema="krx_session_probe_v1",phase=phase,asof=now.date().isoformat(),
                started_at_kst=now.isoformat(),captured_at_kst=end.isoformat(),window=window,
                provider_session_scope="DATE_ONLY_UNVERIFIED",
                source=SOURCE,markets=market_counts,quality=check_bars(stocks),
                stocks=stocks,orders_enabled=False,trade_approved=False)

def compare(regular,after):
    state="PAIR_NOT_VERIFIED"
    reasons=[]
    if (regular.get("schema")!="krx_session_probe_v1" or
        after.get("schema")!="krx_session_probe_v1"):
        reasons.append("MISSING_SNAPSHOT")
    else:
        if regular.get("phase")!="regular" or after.get("phase")!="after":
            reasons.append("PHASE_MISMATCH")
        if regular.get("asof")!=after.get("asof"):
            reasons.append("ASOF_MISMATCH")
        if regular.get("window")!="REGULAR_WINDOW":
            reasons.append("REGULAR_CAPTURE_LATE_OR_MISSING")
        if after.get("window")!="AFTER_CLOSE_WINDOW":
            reasons.append("AFTER_CAPTURE_LATE_OR_MISSING")
        if regular.get("source")!=after.get("source") or regular.get("source")!=SOURCE:
            reasons.append("DIFFERENT_PROVIDER")
        if min(regular.get("quality",{}).get("checked",0),
               after.get("quality",{}).get("checked",0))<100:
            reasons.append("INSUFFICIENT_MARKET_COVERAGE")
    matches=0;close_changed=0;same_highlow=0;examples=[]
    if not reasons:
        a=regular.get("stocks") or {}
        b=after.get("stocks") or {}
        for ticker in sorted(set(a)&set(b)):
            first,last=a[ticker],b[ticker]
            if first.get("market")!=last.get("market"):continue
            matches+=1
            c1,c2=numeric(first.get("Close")),numeric(last.get("Close"))
            if c1 is None or c2 is None:continue
            if c1!=c2:
                close_changed+=1
                if all(first.get(k)==last.get(k) for k in ("High","Low")):
                    same_highlow+=1
                if len(examples)<12:
                    examples.append(dict(ticker=ticker,regular_close=c1,after_close=c2,
                        regular_high=first.get("High"),regular_low=first.get("Low"),
                        after_high=last.get("High"),after_low=last.get("Low")))
        if matches<100:
            reasons.append("OVERLAPPING_STOCK_COVERAGE_LOW")
        else:
            state="PAIRED_SOURCE_OBSERVATIONS_READY"
    return dict(schema="krx_session_comparison_v1",
        asof=after.get("asof"),status=state,blockers=reasons,
        matching_tickers=matches,changed_close_count=close_changed,
        changed_close_unchanged_highlow_count=same_highlow,
        early_quality=regular.get("quality"),late_quality=after.get("quality"),
        example_rows=examples,possible_session_mixing_not_proven=True,
        price_correction_permitted=False,
        authorizes_sector_rank=False,trade_approved=False,
        decision="CASH")

def fetch_market(asof):
    from pykrx import stock
    markets={}
    for market in ("KOSPI","KOSDAQ"):
        frame=stock.get_market_ohlcv(asof.replace("-",""),market=market)
        required={"시가":"Open","고가":"High","저가":"Low","종가":"Close",
                  "거래량":"Volume","거래대금":"TurnoverKRW"}
        if not set(required).issubset(frame.columns) or len(frame)<100:
            raise RuntimeError("SOURCE_SCHEMA_OR_COVERAGE_FAILED_"+market)
        rows={}
        for ticker,item in frame.iterrows():
            ticker=str(ticker)
            if not re.fullmatch(r"[0-9]{6}",ticker):continue
            rows[ticker]={v:numeric(item[k]) for k,v in required.items()}
        markets[market]=rows
    return markets

def read(path):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,ValueError,TypeError):return {}

def write(path,payload):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("capture","compare"),required=True)
    p.add_argument("--phase",choices=("regular","after"))
    p.add_argument("--regular",default="")
    p.add_argument("--after",default="")
    p.add_argument("--out",default="output/krx_session_probe.json")
    args=p.parse_args()
    if args.mode=="compare":
        output=compare(read(args.regular),read(args.after))
    else:
        if not args.phase:p.error("--phase required for capture")
        now=datetime.now(KST)
        # No historical extrapolation and no claim of capturing a previous session.
        if now.weekday()>=5:
            output=dict(schema="krx_session_probe_v1",phase=args.phase,
                asof=now.date().isoformat(),captured_at_kst=now.isoformat(),
                window="NON_TRADING_DAY",source=SOURCE,quality={},stocks={},
                orders_enabled=False,trade_approved=False)
        else:
            try:
                markets=fetch_market(now.date().isoformat())
                end=datetime.now(KST)
                output=new_snapshot(args.phase,now,markets,ended_at=end)
            except Exception as exc:
                # No traceback with external tokens; error codes only.
                output=dict(schema="krx_session_probe_v1",phase=args.phase,
                    asof=now.date().isoformat(),captured_at_kst=now.isoformat(),
                    window="SOURCE_UNAVAILABLE",source=SOURCE,
                    provider_session_scope="DATE_ONLY_UNVERIFIED",
                    quality={},stocks={},
                    error="PUBLIC_MARKET_PROVIDER_UNAVAILABLE",
                    orders_enabled=False,trade_approved=False)
    write(args.out,output)
    print(json.dumps({k:v for k,v in output.items() if k!="stocks" and k!="example_rows"},
                     ensure_ascii=False))

if __name__=="__main__":main()
