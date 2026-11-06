"""Selection returns without entry filters, plus attribution of archived v4 orders.

No optimization: use the frozen trend/RS/turnover rule and the OLD 95-stock
research cohort. Newly fetched industries are intentionally not accepted here.
Selection price changes are NOT executable trade profits or portfolio returns.
"""
import argparse,csv,gzip,json,math,statistics
from collections import Counter,defaultdict
from pathlib import Path

from c3_competition_v2 import load_official,market_proxy,cluster_ci
from c3_daily_top2_v4 import BUY,SELL,SLIP
from c3_selection_scope_v5 import selection_features,write_csv,digest


def avg(values):return round(statistics.mean(values),6) if values else None


def source_market(panel_path):
    """Dated all-security official returns; a transparent proxy, NOT KOSPI index."""
    changes=defaultdict(list);turns={}
    with gzip.open(panel_path,"rt") as f:
        for r in csv.DictReader(f):
            if r["tradable"]=="True" and r["ohlc_valid"]=="True" and r["change_pct"] not in ("","None"):
                v=float(r["change_pct"])
                if math.isfinite(v):changes[(r["market"],r["date"])].append(v)
            turns[(r["ticker"],r["date"])]=float(r["turnover_krw"]) if r["turnover_krw"] not in ("","None") else None
    levels={};dates=sorted({d for m,d in changes})
    for market in ("KOSPI","KOSDAQ"):
        level=100.;series={}
        for d in dates:
            values=changes[(market,d)]
            if not values:raise ValueError("MISSING_MARKET_BENCHMARK_DAY")
            level*=1+math.fsum(values)/len(values)/100;series[d]=level
        levels[market]=series
    return levels,turns


def outcome(ticker,day,rows,sessions,horizon,market):
    """Exactly H later closing sessions; next-open reference is separate and costed."""
    i=sessions.index(day);by={b["date"]:b for b in rows};out=dict(status="INCOMPLETE_WINDOW",ticker=ticker,decision_date=day,horizon=horizon)
    if i+horizon>=len(sessions):return out
    dates=sessions[i:i+horizon+1];bars=[by.get(d) for d in dates]
    if any(b is None or not b["tradable"] or b.get("invalid_data") or not b["close"] for b in bars):
        return dict(out,status="CENSORED_MISSING_HALT_OR_INVALID")
    if any(b["segment"]!=bars[0]["segment"] for b in bars):return dict(out,status="CENSORED_REFERENCE_OR_HISTORY_RESET")
    if not all(d in market for d in (dates[0],dates[-1])):return dict(out,status="BENCHMARK_MISSING")
    move=100*(bars[-1]["close"]/bars[0]["close"]-1);benchmark=100*(market[dates[-1]]/market[dates[0]]-1)
    out.update(status="COMPLETE",price_move_pct=move,market_proxy_pct=benchmark,excess_pct=move-benchmark,
        evaluation_date=dates[-1],reference_net_pct=None,reference_entry_date=None,reference_exit_date=None)
    # Hold H sessions starting at next open; liquidate at the following open.
    if i+horizon+1<len(sessions):
        extra=by.get(sessions[i+horizon+1]);entry=bars[1]
        if extra and extra["tradable"] and not extra.get("invalid_data") and extra["segment"]==bars[0]["segment"]:
            out.update(reference_net_pct=100*(extra["open"]*(1-SELL)*(1-SLIP)/(entry["open"]*(1+BUY)*(1+SLIP))-1),
                reference_entry_date=entry["date"],reference_exit_date=extra["date"])
    return out


def select_only(panel,sessions,turns,proxy,cadence):
    """Rank with decision-day values only; no pivot/entry/stop eligibility gate."""
    pools=defaultdict(list);clock={};grid={d:i for i,d in enumerate(sessions)}
    for t,bars in sorted(panel.items()):
        groups=defaultdict(list)
        for b in bars:
            if b["tradable"] and not b["invalid_data"]:groups[b["segment"]].append(b)
        for group in groups.values():
            for i in range(64,len(group)):
                past=group[:i+1];d=past[-1]["date"];idx=grid[d]
                if not "2026-05-01"<=d<="2026-11-04":continue
                levels=[proxy[x] for x in sessions[:idx+1]]
                if len(levels)<65:continue
                if levels[-1]<statistics.mean(levels[-20:])<statistics.mean(levels[-60:]):continue
                market20=100*(levels[-1]/levels[-21]-1)
                recent=[turns[(t,b["date"])] for b in past[-20:]]
                if any(v is None or v<=0 for v in recent):continue
                candidate=selection_features([dict(b,turnover_krw=turns[(t,b["date"])]) for b in past],market20)
                if candidate is None:continue
                if cadence=="FIXED26":
                    if idx<clock.get(t,0):continue
                    clock[t]=idx+26
                pools[d].append(dict(ticker=t,name=past[-1]["name"],decision_date=d,**candidate))
    return [r for d,pool in sorted(pools.items()) for r in sorted(pool,key=lambda r:(-r["turnover20"],-r["rs20"],r["ticker"]))[:2]]


def metrics(rows):
    complete=[r for r in rows if r["status"]=="COMPLETE"];costed=[r["reference_net_pct"] for r in complete if r["reference_net_pct"] is not None]
    return dict(selected=len(rows),completed=len(complete),incomplete_or_censored=dict(Counter(r["status"] for r in rows if r["status"]!="COMPLETE")),
        unique_tickers=len({r["ticker"] for r in complete}),unique_decision_dates=len({r["decision_date"] for r in complete}),
        mean_price_move_pct=avg([r["price_move_pct"] for r in complete]),mean_market_proxy_pct=avg([r["market_proxy_pct"] for r in complete]),
        mean_excess_pct=avg([r["excess_pct"] for r in complete]),outperform_rate_pct=100*sum(r["excess_pct"]>0 for r in complete)/len(complete) if complete else None,
        reference_net_completed=len(costed),mean_costed_next_open_reference_pct=avg(costed),
        excess_ci95_month_clusters_descriptive=cluster_ci([(r["decision_date"][:7],r["excess_pct"]) for r in complete]),
        overlapping_labels_not_independent=True,portfolio_mdd_not_inferred=True)


def attribute(orders,trades,reference):
    closed={(t["ticker"],t["decision_date"]):t for t in trades if t["mature"]};counts=Counter();net_by=defaultdict(list);details=[]
    for o in orders:
        p=o["plan"];r=reference(p);x=closed.get((p["ticker"],p["decision_date"]))
        if r["status"]!="COMPLETE":label=r["status"]
        elif r["excess_pct"]<=0:label="SELECTION_DID_NOT_OUTPERFORM"
        elif o["status"]!="MODEL_ENTRY":label="OUTPERFORMER_NOT_FILLED"
        elif x is None:label="OUTPERFORMER_TRADE_NOT_MATURE"
        elif x["net_pct"]<=0:label="OUTPERFORMER_BUT_TRADE_LOST"
        else:label="OUTPERFORMER_AND_PROFITABLE_TRADE"
        counts[label]+=1
        if x:net_by[label].append(x["net_pct"])
        details.append(dict(ticker=p["ticker"],decision_date=p["decision_date"],label=label,
            price_move_pct=r.get("price_move_pct"),excess_pct=r.get("excess_pct"),order_status=o["status"],trade_net_pct=x["net_pct"] if x else None,
            entry_band_upper_to_decision_pct=100*(p["high"]/p["reference_close"]-1),net_r1_rr=p.get("net_r1_rr")))
    return dict(counts=dict(counts),trade_net_sum_by_label={k:round(math.fsum(v),6) for k,v in net_by.items()},
        net_sum_is_not_portfolio_return=True,legacy_v4_exit_window_differs_from_selection_horizon=True,
        r1_costed_reward_nonpositive_orders=sum(p["plan"].get("net_r1_rr") is not None and p["plan"]["net_r1_rr"]<=0 for p in orders)),details


def run(panel_path,audit_path,members,exploratory,archived_ledger,outdir):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    panel,sessions,audit=load_official(panel_path,audit_path,members,exploratory)
    selected={t:rows for t,rows in panel.items() if t in audit["confirmation_tickers"]}
    market,turns=source_market(panel_path);proxy=market_proxy(panel,sessions);markets={}
    with gzip.open(panel_path,"rt") as f:
        for r in csv.DictReader(f):
            if r["ticker"] in selected:markets[r["ticker"]]=r["market"]
    table=[];detail=[];report={}
    for cadence in ("FIXED26","DAILY"):
        decisions=select_only(selected,sessions,turns,proxy,cadence);report[cadence]={}
        for h in (5,10,20):
            rows=[outcome(d["ticker"],d["decision_date"],selected[d["ticker"]],sessions,h,market[markets[d["ticker"]]]) for d in decisions]
            m=metrics(rows);report[cadence][str(h)]=m;table.append(dict(cadence=cadence,horizon=h,**{k:m[k] for k in ("selected","completed","unique_tickers","mean_price_move_pct","mean_market_proxy_pct","mean_excess_pct","outperform_rate_pct","mean_costed_next_open_reference_pct")}))
            detail.extend(dict(cadence=cadence,**r) for r in rows)
    archived=json.load(gzip.open(archived_ledger,"rt"));attribution={};attr_rows=[]
    for model,folds in archived.items():
        attribution[model]={}
        for h,study in folds["HOLDOUT"].items():
            ref=lambda p:outcome(p["ticker"],p["decision_date"],selected[p["ticker"]],sessions,int(h),market[markets[p["ticker"]]])
            m,rows=attribute(study["orders"],study["trades"],ref);attribution[model][h]=m;attr_rows.extend(dict(model=model,horizon=int(h),**r) for r in rows)
    # Fixed schemas keep incomplete outcomes explicit instead of dropping them.
    fields=sorted(set().union(*(r.keys() for r in detail)))
    write_csv(root/"selection_outcomes.csv",[{k:r.get(k) for k in fields} for r in detail]);write_csv(root/"selection_comparison.csv",table)
    write_csv(root/"entry_attribution.csv",attr_rows)
    result=dict(schema="C3_SELECTION_DIAGNOSTIC_V5",cohort_size=len(selected),period=["2026-05-01",sessions[-1]],
        historical_current_industries_used=False,rules_retuned=False,entry_filters_used_in_selector=False,metrics=report,archived_entry_attribution=attribution,
        market_benchmark="DATED_ALL_QUOTED_SECURITY_EQUAL_WEIGHT_OFFICIAL_CHANGE_PROXY_BY_BOARD_NOT_OFFICIAL_INDEX",
        selection_labels="DECISION_CLOSE_TO_EXACT_H_LATER_CLOSE_NOT_A_FILL",costed_reference="NEXT_OPEN_TO_OPEN_AFTER_H_FULL_SESSIONS_NO_STOP_NOT_PORTFOLIO",
        previous_v4_horizon="ENTRY_SESSION_PLUS_H_ADDITIONAL_SESSIONS_THEN_NEXT_OPEN_PRESERVED_NOT_RELABELLED",
        old_cohort_and_comparison_period_already_seen=True,unseen_completed={str(h):0 for h in (5,10,20)},current_action="CASH",
        source_hashes=dict(panel=digest(panel_path),audit=digest(audit_path),archived_ledger=digest(archived_ledger)),orders_enabled=False)
    (root/"selection_diagnostic.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(table));return result


def main():
    p=argparse.ArgumentParser()
    for k in ("panel","audit","archived-ledger","outdir"):p.add_argument("--"+k,required=True)
    p.add_argument("--members",default="reports/v68_investment_sector_members.csv")
    p.add_argument("--exploratory",default="reports/c3_work2_20261105/source_validation_cases.json")
    a=p.parse_args();run(a.panel,a.audit,a.members,a.exploratory,a.archived_ledger,a.outdir)


if __name__=="__main__":main()
