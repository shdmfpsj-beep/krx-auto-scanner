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

def historical_pattern_review(series, horizon=5):
    """Non-overlapping research observations with forward 5-session close returns.

    Signals use only bars through signal day. Final horizon bars are excluded;
    no intraday fill, costs, stops, or execution assumptions are implied.
    """
    out={k:[] for k in ("BREAKOUT_20D","RISING_SMA20_PULLBACK","RECLAIM_10D_HIGH")}
    if len(series)<31 or any(v[2] is None or v[3] is None for _,v in series):
        return {k:{"count":0,"mean_forward_5d_pct":"","positive_count":0,
                   "mean_mae_5d_pct":"","mean_mfe_5d_pct":"",
                   "hypothetical_10d_low_breach_count":0}
                for k in out}
    closes=[v[0] for _,v in series]
    highs=[v[3] for _,v in series]
    lows=[v[2] for _,v in series]
    ma=[None]*len(series)
    for i in range(19,len(series)):
        ma[i]=sum(closes[i-19:i+1])/20
    last_used={k:-horizon-1 for k in out}
    for i in range(25,len(series)-horizon):
        signals={
            "BREAKOUT_20D":closes[i]>max(highs[i-20:i]),
            "RISING_SMA20_PULLBACK":(
                ma[i]>ma[i-5] and closes[i-1]>1.03*ma[i-1]
                and .98*ma[i]<=lows[i]<=1.02*ma[i] and closes[i]>=ma[i]),
            "RECLAIM_10D_HIGH":(
                closes[i]>max(highs[i-10:i]) and
                closes[i-1]<=max(highs[i-11:i-1]) and
                min(closes[i-5:i])<ma[i-1])
        }
        for name,matched in signals.items():
            if matched and i-last_used[name]>horizon:
                entry=closes[i]
                future=series[i+1:i+horizon+1]
                # The signal-day 10-bar low is a research-only risk reference,
                # NOT an executable structural stop or an intraday fill.
                reference_low=min(lows[i-9:i+1])
                out[name].append((
                    100*(closes[i+horizon]/entry-1),
                    100*(min(v[2] for _,v in future)/entry-1),
                    100*(max(v[3] for _,v in future)/entry-1),
                    any(v[2]<reference_low for _,v in future)))
                last_used[name]=i
    return {k:{"count":len(v),
               "mean_forward_5d_pct":round(sum(x[0] for x in v)/len(v),3) if v else "",
               "positive_count":sum(x[0]>0 for x in v),
               "mean_mae_5d_pct":round(sum(x[1] for x in v)/len(v),3) if v else "",
               "mean_mfe_5d_pct":round(sum(x[2] for x in v)/len(v),3) if v else "",
               "hypothetical_10d_low_breach_count":sum(x[3] for x in v)}
            for k,v in out.items()}


def stock_market_metrics(root,watch,asof):
    """As-of daily bars and five-session investor flows, research only."""
    from collections import defaultdict
    from datetime import date,timedelta
    if not watch or not asof:
        return []
    tickers={r["ticker"] for r in watch}
    start=(date.fromisoformat(asof)-timedelta(days=110)).isoformat()
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
                        low=number(r,"Low")
                        high=number(r,"High")
                        valid_ohlc=(low is not None and high is not None and
                                    0<low<=close<=high)
                        if close is not None and close>0 and turnover is not None and turnover>=0:
                            bars[t][r["Date"]]=(close,turnover,low if valid_ohlc else None,
                                                 high if valid_ohlc else None)
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
        distance=100*(last/sma20-1) if last and sma20 else None
        recent_high=max(v[0] for _,v in series[-20:]) if len(series)>=20 else None
        # These are screening warnings, not validated buy/sell thresholds.
        extension=[]
        if change is not None and change>=10:
            extension.append("FIVE_DAY_RALLY_GE_10PCT")
        if distance is not None and distance>=15:
            extension.append("DISTANCE_ABOVE_SMA20_GE_15PCT")
        # Daily OHLC lows permit a second independent observation of support.
        # Missing high/low must not be backfilled with closing prices.
        # Intraday lows alone still do not establish a validated stop.
        low_series=sorted((d,v[2]) for d,v in bars[t].items()
                          if len(v)>2 and v[2] is not None)
        low_pivots=[]
        if len(low_series)>=30 and low_series[-1][0]==asof:
            for i in range(2,len(low_series)-2):
                v=low_series[i][1]
                if v<min(x[1] for x in low_series[i-2:i]) and v<=min(
                        x[1] for x in low_series[i+1:i+3]):
                    low_pivots.append((low_series[i][0],v))
        valid_low_pivots=[p for p in low_pivots if last and p[1]<last]
        low_pivot_date,low_pivot_price=(valid_low_pivots[-1]
                                       if valid_low_pivots else ("",None))
        # Review whether a completed low pivot has held on subsequent closes.
        # A historical hold is NOT proof of a fresh breakout-retest setup.
        low_pivot_review="NO_LOW_PIVOT"
        post_pivot_min_close=""
        if low_pivot_price is not None:
            subsequent=[v[0] for d,v in series if d>low_pivot_date]
            if subsequent:
                post_pivot_min_close=min(subsequent)
                low_pivot_review=("CLOSE_BROKE_PIVOT_LOW" if
                                  post_pivot_min_close<low_pivot_price else
                                  "PIVOT_HELD_ON_SUBSEQUENT_CLOSES")
        # Evaluate ALL historical breakout candidates, not just the latest one.
        # Select the freshest still-held retest; no look-ahead or trade approval.
        breakout_date=""
        breakout_level=""
        retest_date=""
        retest_low=""
        breakout_review="NO_OBSERVED_20D_BREAKOUT"
        breakout_candidates_count=0
        valid_retests=[]
        last_broken=False
        if len(series)>=30 and series[-1][0]==asof and all(
                v[2] is not None and v[3] is not None for _,v in series):
            for i in range(20,len(series)-1):
                level=max(v[3] for _,v in series[i-20:i])
                if series[i][1][0]<=level:
                    continue
                breakout_candidates_count+=1
                retests=[(j,series[j][1][2]) for j in range(i+1,len(series))
                         if .98*level<=series[j][1][2]<=1.02*level
                         and series[j][1][0]>=level]
                for j,low in retests:
                    if all(v[0]>=level for _,v in series[j+1:]):
                        valid_retests.append((j,i,level,low))
                if not valid_retests and any(v[0]<level for _,v in series[i+1:]):
                    last_broken=True
            if valid_retests:
                j,i,level,low=max(valid_retests,key=lambda x:(x[0],x[1]))
                breakout_date=series[i][0]
                breakout_level=level
                retest_date=series[j][0]
                retest_low=low
                age=len(series)-1-j
                breakout_review=("RECENT_RETEST_HELD_TO_ASOF" if age<=10 else
                                 "STALE_RETEST_HELD_TO_ASOF")
            elif breakout_candidates_count:
                breakout_review=("NO_VALID_HELD_RETEST" if last_broken else
                                 "BREAKOUT_NO_RETEST_OBSERVED")
        # Alternative: rising 20-session mean, first pullback into the mean
        # following a prior close >3% above it; observational only.
        pullback_review="NO_RISING_SMA20_PULLBACK"
        pullback_date=""
        if len(series)>=30 and series[-1][0]==asof:
            closes=[v[0] for _,v in series]
            ma=[None]*len(series)
            for i in range(19,len(series)):
                ma[i]=sum(closes[i-19:i+1])/20
            for i in range(25,len(series)):
                if (ma[i] is not None and ma[i-5] is not None
                    and ma[i]>ma[i-5]
                    and closes[i-1]>1.03*ma[i-1]
                    and series[i][1][2] is not None
                    and .98*ma[i]<=series[i][1][2]<=1.02*ma[i]
                    and closes[i]>=ma[i]):
                    pullback_date=series[i][0]
                    age=len(series)-1-i
                    pullback_review=("RECENT_RISING_SMA20_PULLBACK" if age<=10
                                     else "STALE_RISING_SMA20_PULLBACK")
        pattern_history=historical_pattern_review(series)
        # No pattern is an executable entry without independent validation.
        # Closing-price pivots are preliminary structure observations only.
        # Require at least 30 daily observations and an as-of latest bar.
        pivot_lows=[]
        if len(series)>=30 and series[-1][0]==asof:
            closes=[v[0] for _,v in series]
            for i in range(2,len(closes)-2):
                if (closes[i]<min(closes[i-2:i]) and
                    closes[i]<=min(closes[i+1:i+3])):
                    pivot_lows.append((series[i][0],closes[i]))
        supports=[p for p in pivot_lows if last is not None and p[1]<last]
        support_date,support_price=supports[-1] if supports else ("",None)
        risk_pct=100*(last-support_price)/last if last and support_price else None
        # A structural stop must be below entry, but close-only pivots cannot
        # establish intraday support, a confirmed retest, or execution costs.
        if support_price is None:
            pivot_review="NO_CONFIRMED_CLOSE_PIVOT"
        elif risk_pct is not None and risk_pct>12:
            pivot_review="PIVOT_TOO_DISTANT_FOR_INITIAL_REVIEW"
        elif risk_pct is not None and risk_pct<2:
            pivot_review="PIVOT_TOO_CLOSE_FOR_INITIAL_REVIEW"
        else:
            pivot_review="PIVOT_REQUIRES_LOW_AND_RETEST_VALIDATION"
        # No stop price is authorized: intraday lows, retests and invalidation
        # of the setup are not validated by this close-only pivot.
        result=dict(row)
        result.update({"close":last if last is not None else "",
                       "return_5d_pct":round(change,3) if change is not None else "",
                       "sma20":round(sma20,2) if sma20 is not None else "",
                       "avg_turnover_5d_krw":round(avg_turnover) if avg_turnover is not None else "",
                       "foreign_net_5d_krw":round(flows[t]["외국인"]) if not reasons else "",
                       "institution_net_5d_krw":round(flows[t]["기관합계"]) if not reasons else "",
                       "price_flow_ready":"YES" if not reasons else "NO",
                       "distance_sma20_pct":round(distance,3) if distance is not None else "",
                       "recent_close_high_20d":recent_high if recent_high is not None else "",
                       "extension_warning":";".join(extension),
                       "entry_setup_verified":"NO",
                       "structure_stop_verified":"NO",
                       "preliminary_pivot_low_date":support_date,
                       "preliminary_pivot_close":support_price if support_price is not None else "",
                       "preliminary_pivot_distance_pct":round(risk_pct,2) if risk_pct is not None else "",
                       "pivot_is_stop_price":"NO",
                       "pivot_review_status":pivot_review,
                       "preliminary_ohlc_pivot_low_date":low_pivot_date,
                       "preliminary_ohlc_pivot_low":low_pivot_price if low_pivot_price is not None else "",
                       "ohlc_low_history_complete":"YES" if len(low_series)>=30 and low_series[-1][0]==asof else "NO",
                       "ohlc_valid_bar_count":len(low_series),
                       "daily_close_bar_count":len(series),
                       "ohlc_pivot_is_stop_price":"NO",
                       "ohlc_pivot_review_status":low_pivot_review,
                       "post_pivot_min_close":post_pivot_min_close,
                       "breakout_retest_verified":"NO",
                       "breakout_20d_date":breakout_date,
                       "breakout_20d_level":breakout_level,
                       "retest_observed_date":retest_date,
                       "retest_observed_low":retest_low,
                       "breakout_retest_review_status":breakout_review,
                       "breakout_candidates_count":breakout_candidates_count,
                       "rising_sma20_pullback_review":pullback_review,
                       "rising_sma20_pullback_date":pullback_date,
                       "pattern_history_breakout_count":pattern_history["BREAKOUT_20D"]["count"],
                       "pattern_history_breakout_mean_5d_pct":pattern_history["BREAKOUT_20D"]["mean_forward_5d_pct"],
                       "pattern_history_breakout_mean_mae_5d_pct":pattern_history["BREAKOUT_20D"]["mean_mae_5d_pct"],
                       "pattern_history_breakout_mean_mfe_5d_pct":pattern_history["BREAKOUT_20D"]["mean_mfe_5d_pct"],
                       "pattern_history_breakout_10d_low_breach_count":pattern_history["BREAKOUT_20D"]["hypothetical_10d_low_breach_count"],
                       "pattern_history_pullback_count":pattern_history["RISING_SMA20_PULLBACK"]["count"],
                       "pattern_history_pullback_mean_5d_pct":pattern_history["RISING_SMA20_PULLBACK"]["mean_forward_5d_pct"],
                       "pattern_history_pullback_mean_mae_5d_pct":pattern_history["RISING_SMA20_PULLBACK"]["mean_mae_5d_pct"],
                       "pattern_history_pullback_mean_mfe_5d_pct":pattern_history["RISING_SMA20_PULLBACK"]["mean_mfe_5d_pct"],
                       "pattern_history_pullback_10d_low_breach_count":pattern_history["RISING_SMA20_PULLBACK"]["hypothetical_10d_low_breach_count"],
                       "pattern_history_reclaim_count":pattern_history["RECLAIM_10D_HIGH"]["count"],
                       "pattern_history_reclaim_mean_5d_pct":pattern_history["RECLAIM_10D_HIGH"]["mean_forward_5d_pct"],
                       "pattern_history_reclaim_mean_mae_5d_pct":pattern_history["RECLAIM_10D_HIGH"]["mean_mae_5d_pct"],
                       "pattern_history_reclaim_mean_mfe_5d_pct":pattern_history["RECLAIM_10D_HIGH"]["mean_mfe_5d_pct"],
                       "pattern_history_reclaim_10d_low_breach_count":pattern_history["RECLAIM_10D_HIGH"]["hypothetical_10d_low_breach_count"],
                       "historical_pattern_trade_verified":"NO",
                       "entry_risk_reward_verified":"NO",
                       "data_warnings":";".join(reasons),
                       "trade_approval":"NO"})
        results.append(result)
    return results

def rank_stock_research(rows):
    """Transparent relative ranking; never a 100-point trade score."""
    eligible=[r for r in rows if r.get("price_flow_ready")=="YES"]
    # Each component is independently ranked. A rank is not a probability.
    def order(key,reverse=True):
        return {r["ticker"]:i for i,r in enumerate(sorted(
            eligible,key=lambda x:((number(x,key) if number(x,key) is not None else -1e30)
                                    *(1 if reverse else -1),x["ticker"]),reverse=True))}
    ret=order("return_5d_pct")
    turnover=order("avg_turnover_5d_krw")
    flow=sorted(eligible,key=lambda r:(
        -(number(r,"foreign_net_5d_krw") or 0)-(number(r,"institution_net_5d_krw") or 0),
        r["ticker"]))
    flow_rank={r["ticker"]:i for i,r in enumerate(flow)}
    trend=sorted(eligible,key=lambda r:(
        -(number(r,"close") or 0)/(number(r,"sma20") or float("inf")),r["ticker"]))
    trend_rank={r["ticker"]:i for i,r in enumerate(trend)}
    result=[]
    for r in eligible:
        t=r["ticker"]
        # Relative percentile rank: price trend 35%, net flows 35%,
        # five-session return 20%, turnover 10%.
        n=max(len(eligible)-1,1)
        proxy=100*(1-(.35*trend_rank[t]+.35*flow_rank[t]+
                      .20*ret[t]+.10*turnover[t])/n)
        result.append({**r,"research_proxy_index":round(proxy,2),
                       "research_rank":"","rank_basis":"RELATIVE_PRICE_FLOW_ONLY",
                       "final_stock_score":"","entry_price":"","stop_price":"",
                       "trade_approval":"NO"})
    # Preserve the original relative score but put extended names into a
    # separate observation queue, never silently treating momentum as entry.
    for r in result:
        r["entry_review_status"]=(
            "WAIT_FOR_PULLBACK_OR_RECLAIM" if r["extension_warning"]
            else "STRUCTURE_AND_RISK_REVIEW_REQUIRED")
    result.sort(key=lambda r:(bool(r["extension_warning"]),-r["research_proxy_index"],r["ticker"]))
    for i,r in enumerate(result,1):
        r["research_rank"]=i
    return result

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
    research=rank_stock_research(enriched)
    summary["research_ranked_stocks"]=len(research)
    summary["research_top5_tickers"]=[r["ticker"] for r in research[:5]]
    summary["research_top5_not_trade_approved"]=True
    summary["extension_warning_count"]=sum(bool(r["extension_warning"]) for r in enriched)
    summary["entry_setup_verified_count"]=0
    summary["structure_stop_verified_count"]=0
    summary["pivot_review_candidate_count"]=sum(
        r.get("pivot_review_status")=="PIVOT_REQUIRES_LOW_AND_RETEST_VALIDATION"
        for r in enriched)
    summary["entry_risk_reward_verified_count"]=0
    summary["ohlc_history_complete_count"]=sum(
        r.get("ohlc_low_history_complete")=="YES" for r in enriched)
    summary["ohlc_pivot_observed_count"]=sum(
        r.get("preliminary_ohlc_pivot_low")!="" for r in enriched)
    summary["ohlc_pivot_close_hold_count"]=sum(
        r.get("ohlc_pivot_review_status")=="PIVOT_HELD_ON_SUBSEQUENT_CLOSES"
        for r in enriched)
    summary["breakout_retest_verified_count"]=0
    summary["retest_close_hold_observed_count"]=sum(
        r.get("breakout_retest_review_status") in (
            "RECENT_RETEST_HELD_TO_ASOF","STALE_RETEST_HELD_TO_ASOF")
        for r in enriched)
    summary["recent_retest_held_count"]=sum(
        r.get("breakout_retest_review_status")=="RECENT_RETEST_HELD_TO_ASOF"
        for r in enriched)
    summary["recent_rising_sma20_pullback_count"]=sum(
        r.get("rising_sma20_pullback_review")=="RECENT_RISING_SMA20_PULLBACK"
        for r in enriched)
    research_fields=metrics_fields+["distance_sma20_pct","recent_close_high_20d",
                                     "extension_warning","entry_setup_verified",
                                     "structure_stop_verified","entry_review_status",
                                     "preliminary_pivot_low_date","preliminary_pivot_close",
                                     "preliminary_pivot_distance_pct","pivot_is_stop_price",
                                     "pivot_review_status","entry_risk_reward_verified",
                                     "preliminary_ohlc_pivot_low_date","preliminary_ohlc_pivot_low",
                                     "ohlc_low_history_complete","ohlc_pivot_is_stop_price",
                                     "ohlc_valid_bar_count","daily_close_bar_count",
                                     "ohlc_pivot_review_status","post_pivot_min_close",
                                     "breakout_retest_verified",
                                     "breakout_20d_date","breakout_20d_level",
                                     "retest_observed_date","retest_observed_low",
                                     "breakout_retest_review_status",
                                     "breakout_candidates_count",
                                     "rising_sma20_pullback_review",
                                     "rising_sma20_pullback_date",
                                     "pattern_history_breakout_count",
                                     "pattern_history_breakout_mean_5d_pct",
                                     "pattern_history_breakout_mean_mae_5d_pct",
                                     "pattern_history_breakout_mean_mfe_5d_pct",
                                     "pattern_history_breakout_10d_low_breach_count",
                                     "pattern_history_pullback_count",
                                     "pattern_history_pullback_mean_5d_pct",
                                     "pattern_history_pullback_mean_mae_5d_pct",
                                     "pattern_history_pullback_mean_mfe_5d_pct",
                                     "pattern_history_pullback_10d_low_breach_count",
                                     "pattern_history_reclaim_count",
                                     "pattern_history_reclaim_mean_5d_pct",
                                     "pattern_history_reclaim_mean_mae_5d_pct",
                                     "pattern_history_reclaim_mean_mfe_5d_pct",
                                     "pattern_history_reclaim_10d_low_breach_count",
                                     "historical_pattern_trade_verified",
                                     "research_proxy_index","research_rank","rank_basis",
                                     "final_stock_score","entry_price","stop_price"]
    with (out/"sector_stock_research_ranking.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=research_fields,extrasaction="ignore")
        w.writeheader();w.writerows(research)
    fields=["sector_id","sector_name","asof","rs_5d_pp","breadth_up_5d_pct",
            "foreign_net_buy_5d_krw","institution_net_buy_5d_krw",
            "research_eligible","warnings","final_sector_score","trade_approval"]
    with (out/"sector_research_ranking.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(ranked)
    (out/"sector_bridge_status.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
