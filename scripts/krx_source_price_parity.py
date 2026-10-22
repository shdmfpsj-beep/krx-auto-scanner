#!/usr/bin/env python3
"""Diagnose KRX recovery vs v18 daily prices for matched constituent tickers.

This is a READ-ONLY cross-source comparison. Even equal prices may share a
common upstream provider and are NOT independent market-data certification.
Different regular vs after-market session definitions must not be spliced.
"""
import argparse,csv,json,math
from pathlib import Path

def value(raw):
    try:
        x=float(raw)
        return x if math.isfinite(x) and x>0 else None
    except (TypeError,ValueError):
        return None

def source_file(root,relative):
    # Sparse GitHub artifact extraction differs by uploader directory prefix.
    # Refuse ambiguous duplicate files instead of silently picking one.
    root=Path(root)
    opts=[root/relative,root/"reports"/relative,
          root/"sector_evidence_v18"/relative,
          root/"reports"/"sector_evidence_v18"/relative]
    matches=[p for p in opts if p.is_file()]
    return matches[0] if len(matches)==1 else None

def csv_rows(path):
    if not path or not path.is_file():return []
    with path.open(newline="",encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))

def run(scan_root,evidence_root,asof):
    history=source_file(scan_root,"candidate_daily_history_v52.csv")
    if not history:
        return dict(status="RECOVERY_CANDIDATE_HISTORY_MISSING_OR_AMBIGUOUS",asof=asof)
    past={}
    bad=0
    for row in csv_rows(history):
        ticker=str(row.get("ticker","")).strip()
        if row.get("date")!=asof or len(ticker)!=6 or not ticker.isdecimal():continue
        close=value(row.get("close"))
        if close is None or ticker in past:
            bad+=1
            continue
        op=value(row.get("open"));high=value(row.get("high"));low=value(row.get("low"))
        if None in (op,high,low) or not(low<=min(op,close)<=max(op,close)<=high):
            bad+=1
            continue
        past[ticker]=(close,high,low,row.get("data_source","UNKNOWN"))
    v18={}
    market_missing=[]
    for market in ("KOSPI","KOSDAQ"):
        path=source_file(evidence_root,f"market/daily_prices/{market}/{asof}.csv")
        if not path:
            market_missing.append(market)
            continue
        for row in csv_rows(path):
            ticker=str(row.get("ticker","")).strip()
            if len(ticker)!=6 or not ticker.isdecimal():continue
            close=value(row.get("Close"));op=value(row.get("Open"))
            high=value(row.get("High"));low=value(row.get("Low"))
            if None in (close,op,high,low) or not(
                  low<=min(op,close)<=max(op,close)<=high):continue
            if ticker in v18:
                return dict(status="DUPLICATE_V18_TICKER",asof=asof,
                            decision="CASH",trade_approved=False)
            v18[ticker]=(close,high,low,market)
    matched=sorted(set(past)&set(v18))
    differences=[];exact=0;changed_close_unchanged_range=0
    for ticker in matched:
        c,h,l,_=past[ticker]
        other,hi,lo,market=v18[ticker]
        if c==other:
            exact+=1
            continue
        if h==hi and l==lo:changed_close_unchanged_range+=1
        differences.append(dict(ticker=ticker,market=market,
            recovery_close=c,v18_close=other,
            recovery_high=h,recovery_low=l,
            v18_high=hi,v18_low=lo,
            absolute_close_difference=round(other-c,2),
            relative_close_difference_pct=round(100*(other-c)/c,4)))
    if market_missing:status="V18_DAILY_MARKET_SOURCE_MISSING"
    elif not matched:status="NO_OVERLAPPING_VALID_DAILY_BARS"
    elif differences:status="CROSS_SOURCE_CLOSE_CONFLICT"
    else:status="CANDIDATE_CLOSES_MATCH_RESEARCH_ONLY"
    return dict(schema="krx_candidate_daily_source_comparison_v1",
        asof=asof,status=status,market_files_missing=market_missing,
        recovery_eligible_candidate_tickers=len(past),
        recovery_invalid_candidate_bars=bad,
        v18_valid_tickers=len(v18),overlap_tickers=len(matched),
        exact_close_matches=exact,close_mismatches=len(differences),
        close_match_pct=round(100*exact/len(matched),2) if matched else None,
        changed_close_unchanged_highlow_count=changed_close_unchanged_range,
        mismatch_examples=differences[:15],
        same_date_is_not_same_market_session=True,
        independent_provider_verified=False,
        trade_approved=False,decision="CASH")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--recovery",type=Path,required=True)
    a.add_argument("--v18",type=Path,required=True)
    a.add_argument("--asof",required=True)
    a.add_argument("--out",type=Path,default=Path("output/source_price_parity.json"))
    x=a.parse_args()
    report=run(x.recovery,x.v18,x.asof)
    x.out.parent.mkdir(parents=True,exist_ok=True)
    x.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="mismatch_examples"},ensure_ascii=False))

if __name__=="__main__":main()
