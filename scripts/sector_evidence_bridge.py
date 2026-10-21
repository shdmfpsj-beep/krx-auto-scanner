#!/usr/bin/env python3
"""Conservative sector evidence bridge: research ranking, never a trade signal."""
import argparse,csv,json,math
from pathlib import Path

EXCLUDE={"HEALTH"}
REQUIRED=("prices","flows","etf_prices","holdings","normalization")

def number(row,key):
    try:
        value=float(row.get(key,""))
        return value if math.isfinite(value) else None
    except (ValueError,TypeError):
        return None

def build(status,rows,scan_date):
    asof=status.get("asof")
    datasets=status.get("datasets",{})
    valid=bool(asof and asof==scan_date and
               all(datasets.get(k,{}).get("status")=="OK" for k in REQUIRED))
    result=[]
    for r in rows:
        if r.get("sector_id") in EXCLUDE: continue
        reasons=[]
        if not valid: reasons.append("CORE_DATA_OR_DATE_UNVERIFIED")
        if r.get("date")!=asof: reasons.append("SECTOR_DATE_MISMATCH")
        if str(r.get("price_flow_proxy_ready","")).lower() not in ("true","1","yes"):
            reasons.append("PRICE_FLOW_PROXY_UNREADY")
        if str(r.get("live_selection_authorized","")).lower() in ("true","1","yes"):
            reasons.append("UNEXPECTED_LIVE_AUTHORIZATION")
        rs=number(r,"rs_5d_pp")
        breadth=number(r,"breadth_up_5d_pct")
        flow=number(r,"foreign_net_buy_5d_krw")
        inst=number(r,"institution_net_buy_5d_krw")
        if any(v is None for v in (rs,breadth,flow,inst)):
            reasons.append("RESEARCH_METRIC_MISSING")
        coverage_keys=("breadth_coverage","turnover_coverage",
                       "foreign_5d_coverage","institution_5d_coverage")
        coverages=[number(r,k) for k in coverage_keys]
        if any(v is None for v in coverages):
            reasons.append("COVERAGE_UNVERIFIED")
        elif any(v < 0.95 for v in coverages):
            reasons.append("LOW_METRIC_COVERAGE")
        if flow is not None and inst is not None and flow + inst <= 0:
            reasons.append("NO_POSITIVE_NET_FLOW_PROXY")
        # No 100-point sector score: catalyst PIT and fundamentals not verified.
        result.append({"sector_id":r.get("sector_id",""),
                       "sector_name":r.get("sector_name",""),
                       "asof":asof or "",
                       "rs_5d_pp":"" if rs is None else rs,
                       "breadth_up_5d_pct":"" if breadth is None else breadth,
                       "foreign_net_buy_5d_krw":"" if flow is None else flow,
                       "institution_net_buy_5d_krw":"" if inst is None else inst,
                       "research_eligible":"YES" if not reasons else "NO",
                       "warnings":";".join(reasons),
                       "final_sector_score":"","trade_approval":"NO"})
    eligible=[r for r in result if r["research_eligible"]=="YES"]
    eligible.sort(key=lambda r:(-(r["rs_5d_pp"]),-(r["breadth_up_5d_pct"]),r["sector_id"]))
    return eligible+[r for r in result if r["research_eligible"]!="YES"],{
        "asof":asof,"scan_date":scan_date,"core_data_verified":valid,
        "research_eligible_sectors":len(eligible),
        "research_top3_sector_ids":[r["sector_id"] for r in eligible[:3]],
        "research_top3_not_trade_approved":True,
        "final_sector_top3_verified":False,"trade_approvals":0,
        "decision":"CASH","note":"ETF-member flow proxy is not verified whole-sector capital inflow; catalyst PIT and earnings not scored."}

def stock_watchlist(root,sector_ids,asof,limit=20):
    """ETF membership watchlist only; not a fundamentals or entry ranking."""
    path=root/"market/sector_membership_dated.csv"
    if not path.is_file() or not asof or not sector_ids:
        return [],"MEMBERSHIP_OR_SECTORS_UNAVAILABLE"
    with path.open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    selected=[]
    for sector in sector_ids:
        dated=[r for r in rows if r.get("sector_id")==sector and
               r.get("snapshot_date","")<=asof]
        if not dated: continue
        latest=max(r["snapshot_date"] for r in dated)
        for r in dated:
            if r["snapshot_date"]!=latest: continue
            ticker=r.get("ticker","")
            weight=number(r,"weight_pct")
            if not (len(ticker)==6 and ticker.isdigit() and weight is not None and 0<=weight<=100):
                continue
            selected.append({"sector_id":sector,"ticker":ticker,
                             "name":r.get("name",""),"weight_pct":weight,
                             "snapshot_date":latest,"asof":asof,
                             "point_in_time_status":r.get("point_in_time_status",""),
                             "fundamentals_verified":"NO","chart_entry_verified":"NO",
                             "trade_approval":"NO"})
    # Fair round-robin by sector; exposure is an ordering proxy, NOT alpha.
    # Deduplicate across ETFs, and redistribute unused slots if a sector
    # has fewer eligible members. Never fabricate an empty sector's picks.
    pools={}
    for sector in sector_ids:
        pool=[r for r in selected if r["sector_id"]==sector]
        pools[sector]=sorted(pool,key=lambda r:(-r["weight_pct"],r["ticker"]))
    chosen=[]
    seen=set()
    while len(chosen)<limit:
        progressed=False
        for sector in sector_ids:
            pool=pools[sector]
            while pool and pool[0]["ticker"] in seen:
                pool.pop(0)
            if pool and len(chosen)<limit:
                row=pool.pop(0)
                chosen.append(row)
                seen.add(row["ticker"])
                progressed=True
        if not progressed:
            break
    return chosen,("ETF_MEMBERSHIP_BALANCED_RESEARCH_ONLY" if chosen else "NO_DATED_MEMBERSHIP")

def stock_market_metrics(root,watch,asof):
    """As-of daily bars and five-session investor flows, research only."""
    from collections import defaultdict
    from datetime import date,timedelta
    if not watch or not asof:
        return []
    tickers={r["ticker"] for r in watch}
    start=(date.fromisoformat(asof)-timedelta(days=50)).isoformat()
    bars=defaultdict(dict)
    prices=root/"market/daily_prices"
    for market in ("KOSPI","KOSDAQ"):
        folder=prices/market
        if not folder.is_dir(): continue
        for p in sorted(folder.glob("*.csv")):
            if not (start<=p.stem<=asof): continue
            with p.open(encoding="utf-8-sig",newline="") as f:
                for r in csv.DictReader(f):
                    t=r.get("ticker")
                    if t in tickers:
                        close=number(r,"Close")
                        turnover=number(r,"TurnoverKRW")
                        if close is not None and close>0 and turnover is not None and turnover>=0:
                            bars[t][r["Date"]]=(close,turnover)
    flows=defaultdict(lambda:defaultdict(float))
    flow_days=set()
    for market in ("KOSPI","KOSDAQ"):
        folder=root/"market/daily_flows"/market
        if not folder.is_dir(): continue
        for p in folder.glob("*.csv"):
            d=p.name[:10]
            if start<=d<=asof: flow_days.add(d)
    # The five most recent observed market dates; missing investor files
    # must be flagged rather than silently interpreted as zero flow.
    flow_dates=set(sorted(flow_days)[-5:])
    coverage=defaultdict(set)
    for market in ("KOSPI","KOSDAQ"):
        folder=root/"market/daily_flows"/market
        if not folder.is_dir(): continue
        for p in folder.glob("*.csv"):
            if p.name[:10] not in flow_dates: continue
            with p.open(encoding="utf-8-sig",newline="") as f:
                for r in csv.DictReader(f):
                    t=r.get("ticker")
                    investor=r.get("investor","")
                    value=number(r,"net_buy_krw")
                    if t in tickers and value is not None and investor in ("외국인","기관합계"):
                        flows[t][investor]+=value
                        coverage[t].add((r.get("date"),investor))
    results=[]
    for row in watch:
        t=row["ticker"]
        series=sorted(bars[t].items())
        reasons=[]
        if len(series)<21 or not series or series[-1][0]!=asof:
            reasons.append("INSUFFICIENT_OR_STALE_DAILY_BARS")
        if len(flow_dates)!=5 or len(coverage[t])!=10:
            reasons.append("INCOMPLETE_5D_INVESTOR_FLOW")
        last=series[-1][1][0] if series else None
        previous=series[-6][1][0] if len(series)>=6 else None
        sma20=sum(v[0] for _,v in series[-20:])/20 if len(series)>=20 else None
        avg_turnover=sum(v[1] for _,v in series[-5:])/5 if len(series)>=5 else None
        change=100*(last/previous-1) if last and previous else None
        result=dict(row)
        result.update({"close":last if last is not None else "",
                       "return_5d_pct":round(change,3) if change is not None else "",
                       "sma20":round(sma20,2) if sma20 is not None else "",
                       "avg_turnover_5d_krw":round(avg_turnover) if avg_turnover is not None else "",
                       "foreign_net_5d_krw":round(flows[t]["외국인"]) if not reasons else "",
                       "institution_net_5d_krw":round(flows[t]["기관합계"]) if not reasons else "",
                       "price_flow_ready":"YES" if not reasons else "NO",
                       "data_warnings":";".join(reasons),
                       "trade_approval":"NO"})
        results.append(result)
    return results

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",required=True)
    p.add_argument("--scan-status",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    root=Path(a.evidence)
    status=json.loads((root/"diagnostics/collection_status.json").read_text())
    scan=json.loads(Path(a.scan_status).read_text())
    evidence_csv=root/"research/sector_evidence_latest.csv"
    if evidence_csv.is_file():
        with evidence_csv.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
    else:
        rows=[]
    ranked,summary=build(status,rows,scan.get("market_data_date"))
    if not evidence_csv.is_file():
        summary["missing_evidence"]="research/sector_evidence_latest.csv"
        summary["decision"]="CASH"
        summary["reason"]="Historical baseline-only artifact lacks current sector feature rows"
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    watch,watch_status=stock_watchlist(root,summary["research_top3_sector_ids"],
                                       summary["asof"],20)
    summary["watchlist_count"]=len(watch)
    summary["watchlist_status"]=watch_status
    summary["stock_top5_verified"]=False
    with (out/"sector_stock_watchlist.csv").open("w",encoding="utf-8-sig",newline="") as f:
        stock_fields=["sector_id","ticker","name","weight_pct","snapshot_date","asof",
                      "point_in_time_status","fundamentals_verified","chart_entry_verified","trade_approval"]
        w=csv.DictWriter(f,fieldnames=stock_fields);w.writeheader();w.writerows(watch)
    enriched=stock_market_metrics(root,watch,summary["asof"])
    summary["stock_price_flow_ready_count"]=sum(r["price_flow_ready"]=="YES" for r in enriched)
    metrics_fields=["sector_id","ticker","name","weight_pct","snapshot_date","asof",
                    "close","return_5d_pct","sma20","avg_turnover_5d_krw",
                    "foreign_net_5d_krw","institution_net_5d_krw",
                    "price_flow_ready","data_warnings","point_in_time_status",
                    "fundamentals_verified","chart_entry_verified","trade_approval"]
    with (out/"sector_stock_market_metrics.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=metrics_fields,extrasaction="ignore")
        w.writeheader();w.writerows(enriched)
    fields=["sector_id","sector_name","asof","rs_5d_pp","breadth_up_5d_pct",
            "foreign_net_buy_5d_krw","institution_net_buy_5d_krw",
            "research_eligible","warnings","final_sector_score","trade_approval"]
    with (out/"sector_research_ranking.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(ranked)
    (out/"sector_bridge_status.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
