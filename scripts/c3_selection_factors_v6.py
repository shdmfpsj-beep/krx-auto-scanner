"""Prespecified selection ablations; old 95-stock cohort, not 1,983-stock proof.

All factors use completed bars. Current industries/news/flows are not backfilled.
Reuse v4 entries, structural stops and two-slot accounting without live changes.
"""
import argparse,csv,gzip,json,math,statistics
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

from c3_competition_v2 import load_official,market_proxy,cluster_ci
from c3_daily_top2_v4 import features,make_plan,model_path,replay,BUY,SELL,SLIP
from c3_selection_scope_v5 import digest,read_csv,write_csv,selection_features,known_by
from c3_selection_diagnostic_v5 import outcome,metrics as selection_metrics

HORIZONS=(5,10,20)
VARIANTS=("A","B","MARKET_UP","OWN_RS","RS_ACCEL","TREND60","HIGH252_AVAILABLE","HIGH252","TURNOVER","VOLUME","HIGHER_LOWS")
FACTORS=("own_rs20","rs_accel5","trend60","high252_ratio","turnover_ratio","volume_ratio","higher_lows","market_regime")


def load_indices(folder,sessions):
    root=Path(folder);meta=json.loads((root/"index_manifest.json").read_text());series={}
    for market in ("KOSPI","KOSDAQ"):
        path=root/(market+"_index.csv")
        if digest(path)!=meta["series"][market]["csv_sha256"]:raise ValueError("INDEX_HASH_MISMATCH")
        rows=read_csv(path)
        if len(rows)!=len(sessions) or [r["date"] for r in rows]!=sessions:raise ValueError("INDEX_DATE_GRID_MISMATCH")
        for r in rows:
            o,h,l,c=[float(r[k]) for k in ("open","high","low","close")]
            if r["market"]!=market or not all(math.isfinite(x) for x in (o,h,l,c)) or not 0<l<=min(o,c)<=max(o,c)<=h:raise ValueError("INDEX_OHLC_INVALID")
        series[market]={r["date"]:float(r["close"]) for r in rows}
    return series,meta


def regime(values):
    if len(values)<60:return "UNKNOWN"
    m20=statistics.mean(values[-20:]);m60=statistics.mean(values[-60:])
    return "UP" if values[-1]>m20>m60 else "DOWN" if values[-1]<m20<m60 else "SIDEWAYS"


def causal_factors(past,index):
    if len(past)<65:raise ValueError("FACTOR_WARMUP_REQUIRED")
    d=past[-1]["date"];d20=past[-21]["date"];d5=past[-6]["date"];d25=past[-26]["date"]
    rs=lambda a,b:100*(a["close"]/b["close"]-1)-100*(index[a["date"]]/index[b["date"]]-1)
    current=rs(past[-1],past[-21]);previous=rs(past[-6],past[-26])
    pivots=[i for i in range(max(2,len(past)-60),len(past)-2)
            if past[i]["low"]<=min(past[j]["low"] for j in range(i-2,i+3))]
    m20=statistics.mean(b["close"] for b in past[-20:]);m60=statistics.mean(b["close"] for b in past[-60:])
    turnover=statistics.mean(b["turnover_krw"] for b in past[-20:]);volume=statistics.mean(b["volume"] for b in past[-20:])
    return dict(own_rs20=current,rs_accel5=current-previous,
        trend60=bool(past[-1]["close"]>m20>m60>statistics.mean(b["close"] for b in past[-65:-5])),
        high252_ratio=past[-1]["close"]/max(b["high"] for b in past[-252:]) if len(past)>=252 else None,
        turnover_ratio=statistics.mean(b["turnover_krw"] for b in past[-5:])/turnover if turnover>0 else None,
        volume_ratio=statistics.mean(b["volume"] for b in past[-5:])/volume if volume>0 else None,
        higher_lows=bool(len(pivots)>=2 and past[pivots[-1]]["low"]>past[pivots[-2]]["low"]))


def factor_pass(row,variant):
    if variant=="A":return True
    if variant=="B":return row["own_rs20"]>0 and row["rs_accel5"]>0
    if variant=="MARKET_UP":return row["market_regime"]=="UP"
    if variant=="OWN_RS":return row["own_rs20"]>0
    if variant=="RS_ACCEL":return row["rs_accel5"]>0
    if variant=="TREND60":return row["trend60"]
    if variant=="HIGH252_AVAILABLE":return row["high252_ratio"] is not None
    if variant=="HIGH252":return row["high252_ratio"] is not None and row["high252_ratio"]>=.8
    if variant=="TURNOVER":return row["turnover_ratio"] is not None and row["turnover_ratio"]>1
    if variant=="VOLUME":return row["volume_ratio"] is not None and row["volume_ratio"]>1
    if variant=="HIGHER_LOWS":return row["higher_lows"]
    raise ValueError("UNREGISTERED_FACTOR_VARIANT")


def choose(pool,sessions,variant,cadence,fold):
    grid={d:i for i,d in enumerate(sessions)};clock={};out=[]
    for day,rows in sorted(pool.items()):
        eligible=[]
        for r in rows:
            if r["fold"]!=fold or r["cohort_regime"]=="DOWN" or not factor_pass(r,variant):continue
            if cadence=="FIXED26":
                if grid[day]<clock.get(r["ticker"],0):continue
                clock[r["ticker"]]=grid[day]+26
            eligible.append(r)
        out+=sorted(eligible,key=lambda r:(-r["turnover20"],-r["legacy_rs20"],r["ticker"]))[:2]
    return out


def nonoverlap(rows,sessions,window=20):
    grid={d:i for i,d in enumerate(sessions)};next_allowed={};out=[]
    for r in sorted(rows,key=lambda r:(r["decision_date"],r["ticker"])):
        idx=grid[r["decision_date"]];t=r["ticker"]
        if idx<next_allowed.get(t,0):continue
        out.append(r);next_allowed[t]=idx+window
    return out


def evaluate(decisions,panel,sessions,horizon,indices,markets,fold):
    fold_sessions=[d for d in sessions if d<="2026-03-31"] if fold=="DEVELOPMENT" else sessions
    out=[]
    for r in decisions:
        x=outcome(r["ticker"],r["decision_date"],panel[r["ticker"]],fold_sessions,horizon,indices[markets[r["ticker"]]])
        out.append(dict(x,market_regime=r["market_regime"]))
    base=selection_metrics(out);values=[r["reference_net_pct"] for r in out if r.get("reference_net_pct") is not None]
    wins=[x for x in values if x>0];loss=[x for x in values if x<0]
    avg=lambda x:round(statistics.mean(x),6) if x else None
    base.update(mean_win_net_pct=avg(wins),mean_loss_net_pct=avg(loss),win_rate_net_pct=round(100*len(wins)/len(values),6) if values else None,
        loss_rate_net_pct=round(100*len(loss)/len(values),6) if values else None,
        payoff_ratio=round(statistics.mean(wins)/abs(statistics.mean(loss)),6) if wins and loss else None,
        overlapping_labels_not_independent=False,remaining_serial_dependence=True,
        market_regimes={reg:dict(n=sum(r["status"]=="COMPLETE" and r["market_regime"]==reg for r in out),
            mean_excess_pct=avg([r["excess_pct"] for r in out if r["status"]=="COMPLETE" and r["market_regime"]==reg])) for reg in ("UP","SIDEWAYS","DOWN")})
    return base,out


def build_pool(panel,sessions,indices,turns,markets,proxy):
    pool=defaultdict(list);grid={d:i for i,d in enumerate(sessions)}
    for t,bars in sorted(panel.items()):
        groups=defaultdict(list)
        for b in bars:
            b["turnover_krw"]=turns[(t,b["date"])]
            if b["tradable"] and not b["invalid_data"]:groups[b["segment"]].append(b)
        for group in groups.values():
            for i in range(64,len(group)):
                past=group[:i+1];d=past[-1]["date"];idx=grid[d]
                fold="DEVELOPMENT" if d<="2026-03-31" else "HOLDOUT" if d>="2026-05-01" else None
                if not fold or any(b["turnover_krw"] is None or b["turnover_krw"]<=0 for b in past[-20:]):continue
                levels=[proxy[x] for x in sessions[:idx+1]];legacy_return=100*(levels[-1]/levels[-21]-1)
                f=selection_features(past,legacy_return)
                if f is None:continue
                market_values=[indices[markets[t]][x] for x in sessions[:idx+1]]
                pool[d].append(dict(ticker=t,name=past[-1]["name"],decision_date=d,fold=fold,segment=group[-1]["segment"],
                    turnover20=f["turnover20"],legacy_rs20=f["rs20"],legacy_market_return20=legacy_return,
                    market_regime=regime(market_values),cohort_regime=regime(levels),**causal_factors(past,indices[markets[t]])))
    return pool


def paper_candidates(decisions,panel,sessions,method):
    out=[];rejected=Counter()
    for r in decisions:
        past=[b for b in panel[r["ticker"]] if b["date"]<=r["decision_date"] and b["segment"]==r["segment"] and b["tradable"] and not b["invalid_data"]]
        f,reason=features(past,r["legacy_market_return20"])
        if f is None:rejected[reason]+=1;continue
        p,reason=make_plan(r["ticker"],past,f,method,r["market_regime"])
        if p is None:rejected[reason]+=1;continue
        # v4's argument counts additional sessions; H-1 keeps exactly H full
        # entry sessions here. Archived v4 statistics retain their old meaning.
        out.append(dict(plan=p,fold=r["fold"],paths={str(h):full_session_path(p,panel[r["ticker"]],sessions,h) for h in HORIZONS}))
    return out,dict(rejected)


def full_session_path(plan,rows,sessions,horizon):
    if horizon not in HORIZONS:raise ValueError("UNREGISTERED_HORIZON")
    return model_path(plan,rows,sessions,horizon-1)


def paper_metrics(result,candidates,horizon,panel,sessions,indices,markets,fold):
    m=dict(result["metrics"]);trades=[t for t in result["trades"] if t["mature"]]
    lookup={(c["plan"]["ticker"],c["plan"]["decision_date"]):c for c in candidates};risk=defaultdict(list);opportunities=Counter()
    for t in trades:
        c=lookup[(t["ticker"],t["decision_date"])];p=c["plan"];price=c["paths"][str(horizon)]["entry"]["price"]
        distance=(price-p["stop"])/p["atr"];bucket="LE_1_ATR" if distance<=1 else "LE_2_ATR" if distance<=2 else "GT_2_ATR"
        risk[bucket].append(dict(net=t["net_pct"],stop="STOP" in t["reason"],distance_pct=100*(price-p["stop"])/price))
    for o in result["orders"]:
        p=o["plan"];dates=[d for d in sessions if d<="2026-03-31"] if fold=="DEVELOPMENT" else sessions
        x=outcome(p["ticker"],p["decision_date"],panel[p["ticker"]],dates,horizon,indices[markets[p["ticker"]]])
        if x["status"]=="COMPLETE" and x["excess_pct"]>0 and o["status"]!="MODEL_ENTRY":opportunities["OUTPERFORMER_UNFILLED"]+=1
    avg=lambda v:round(statistics.mean(v),6) if v else None
    m.update(payoff_ratio=round(m["mean_win_pct"]/abs(m["mean_loss_pct"]),6) if m["mean_win_pct"] is not None and m["mean_loss_pct"] else None,
        risk_buckets={b:dict(n=len(v),mean_net_pct=avg([x["net"] for x in v]),stop_rate_pct=round(100*sum(x["stop"] for x in v)/len(v),6),mean_distance_pct=avg([x["distance_pct"] for x in v])) for b,v in sorted(risk.items())},
        positive_stock_unfilled=opportunities["OUTPERFORMER_UNFILLED"],orders_with_nonpositive_r1_reward=sum(o["plan"].get("net_r1_rr") is not None and o["plan"]["net_r1_rr"]<=0 for o in result["orders"]),
        exact_full_entry_sessions=horizon,unchanged_v4_structural_stop=True)
    return m


def review_packet(row,source_hash,known_at,execution_open_at):
    # Whitelist excludes identities, dates of past events and realized outcomes.
    feature_names=FACTORS+("turnover20","legacy_rs20")
    return dict(schema="C3_BLIND_AI_PACKET_V6",features={k:row[k] for k in feature_names if k in row},source_hash=source_hash,
        known_at=known_at,execution_open_at=execution_open_at,external_data_allowed=False)


def paired_dates(rows):
    grouped={v:defaultdict(list) for v in ("A","B")}
    for r in rows:
        if r["variant"] in grouped and r["status"]=="COMPLETE":grouped[r["variant"]][r["decision_date"]].append(r["excess_pct"])
    dates=sorted(set(grouped["A"])&set(grouped["B"]));diff=[(d,statistics.mean(grouped["B"][d])-statistics.mean(grouped["A"][d])) for d in dates]
    return dict(common_decision_dates=len(dates),only_A_dates=len(set(grouped["A"])-set(grouped["B"])),only_B_dates=len(set(grouped["B"])-set(grouped["A"])),
        mean_B_minus_A_excess_pct=round(statistics.mean(v for d,v in diff),6) if diff else None,
        ci95_month_clusters_descriptive=cluster_ci([(d[:7],v) for d,v in diff]),missing_model_dates_not_assumed_zero=True)


def validate_review(packet,review,recorded_at):
    import hashlib
    expected=hashlib.sha256(json.dumps(packet,sort_keys=True,separators=(",",":" )).encode()).hexdigest()
    if review.get("packet_sha256")!=expected:raise ValueError("AI_PACKET_HASH_MISMATCH")
    if not known_by(packet["known_at"],review["produced_at"]) or not known_by(review["produced_at"],recorded_at):raise ValueError("AI_TIME_PROVENANCE_INVALID")
    if known_by(packet["execution_open_at"],recorded_at):raise ValueError("AI_REVIEW_AFTER_EXECUTION")
    if review.get("external_data_used") is not False or not set(review.get("evidence_keys",[]))<=set(packet["features"]):raise ValueError("AI_UNGROUNDED_EVIDENCE")
    if review.get("decision") not in ("PASS","VETO","ABSTAIN"):raise ValueError("AI_INVALID_REVIEW_DECISION")
    return True


def run(panel_path,audit_path,indices_dir,protocol_path,members,exploratory,outdir):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True);protocol=json.loads(Path(protocol_path).read_text())
    if protocol["models"]["B"]!="SAME_A_POOL_AND_POSITIVE_OWN_MARKET_RS20_AND_RS20_ACCELERATION_5_RANK_UNCHANGED":raise ValueError("PROTOCOL_CHANGED")
    all_panel,sessions,audit=load_official(panel_path,audit_path,members,exploratory);panel={t:b for t,b in all_panel.items() if t in audit["confirmation_tickers"]}
    indices,index_meta=load_indices(indices_dir,sessions);turns={};markets={}
    with gzip.open(panel_path,"rt") as f:
        for r in csv.DictReader(f):
            if r["ticker"] in panel:
                turns[(r["ticker"],r["date"])]=float(r["turnover_krw"]) if r["turnover_krw"] not in ("","None") else None;markets[r["ticker"]]=r["market"]
    proxy=market_proxy(all_panel,sessions);pool=build_pool(panel,sessions,indices,turns,markets,proxy)
    selected={};summaries={};table=[];observations=[];papers={};paper_table=[];paper_summary={};first_example=None
    for variant in VARIANTS:
        selected[variant]={};summaries[variant]={}
        for cadence in ("FIXED26","DAILY"):
            selected[variant][cadence]={};summaries[variant][cadence]={}
            for fold in ("DEVELOPMENT","HOLDOUT"):
                raw=choose(pool,sessions,variant,cadence,fold);unique=nonoverlap(raw,sessions);selected[variant][cadence][fold]=raw;summaries[variant][cadence][fold]={}
                for h in HORIZONS:
                    m,rows=evaluate(unique,panel,sessions,h,indices,markets,fold);m.update(raw_top2_observations=len(raw),suppressed_overlapping_observations=len(raw)-len(unique))
                    summaries[variant][cadence][fold][str(h)]=m
                    table.append(dict(variant=variant,cadence=cadence,fold=fold,horizon=h,raw=len(raw),nonoverlap=len(unique),n=m["completed"],
                        excess=m["mean_excess_pct"],net_reference=m["mean_costed_next_open_reference_pct"],outperform_rate=m["outperform_rate_pct"],loss_rate=m["loss_rate_net_pct"]))
                    observations.extend(dict(variant=variant,cadence=cadence,fold=fold,**r) for r in rows)
    for variant in ("A","B"):
        for cadence in ("FIXED26","DAILY"):
            for method in ("PULLBACK","BREAKOUT"):
                key=variant+"_"+cadence+"_"+method;papers[key]={};paper_summary[key]={}
                for fold in ("DEVELOPMENT","HOLDOUT"):
                    candidates,rejected=paper_candidates(selected[variant][cadence][fold],panel,sessions,method);papers[key][fold]={};paper_summary[key][fold]={}
                    if candidates and first_example is None:first_example=candidates[0]["plan"]
                    for h in HORIZONS:
                        result=replay(candidates,panel,sessions,h,fold,"DAILY");m=paper_metrics(result,candidates,h,panel,sessions,indices,markets,fold)
                        m["no_plan_rejections"]=rejected;paper_summary[key][fold][str(h)]=m;papers[key][fold][str(h)]=result
                        paper_table.append(dict(model=key,fold=fold,horizon=h,n=m["completed"],mean_net=m["mean_net_pct"],mdd=m["max_drawdown_close_pct"],portfolio=m["portfolio_return_pct"],
                            fill=m["fill_rate_pct"],stop=m["stop_rate_pct"],win=m["win_rate_pct"],payoff=m["payoff_ratio"]))
    write_csv(root/"factor_comparison.csv",table);write_csv(root/"paper_comparison.csv",paper_table)
    with gzip.open(root/"ledger.json.gz","wt") as f:json.dump(dict(pool=pool,selections=selected,outcomes=observations,papers=papers,chart_example=first_example),f,separators=(",",":"))
    report=dict(schema="C3_SELECTION_FACTOR_V6",preserved_tests=558,historical_cohort=len(panel),current_analysis_scope_not_backtested=1983,source_audit=audit,index_source=index_meta,
        selection=summaries,paper=paper_summary,paired_AB={c:{f:{str(h):paired_dates([r for r in observations if r["cadence"]==c and r["fold"]==f and r["horizon"]==h]) for h in HORIZONS} for f in ("DEVELOPMENT","HOLDOUT")} for c in ("FIXED26","DAILY")},
        protocol_sha256=digest(protocol_path),selection_nonoverlap_sessions=20,baseline_high252="HIGH252_AVAILABLE",
        full_sector_B_historical_tested=False,as_filed_earnings_or_flows_tested=False,
        ai_C=dict(status="NOT_RUN_NO_GENUINE_TIMELOCKED_AI_REVIEWS",completed_reviews=0,external_paid_api_calls=0,local_model_available=False),
        unseen=dict(start="2026-11-06",completed={str(h):0 for h in HORIZONS},status="NOT_AVAILABLE_NOT_ZERO_RETURN_SUCCESS"),
        current_action="CASH",approved_top2=[],buy_prices=None,structural_stops=None,resistances=None,new_strategy_adopted=False,
        source_hashes=dict(panel=digest(panel_path),audit=digest(audit_path),code=digest(__file__)),orders_enabled=False,notifications_or_schedules_changed=False)
    (root/"factor_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps([r for r in table if r["variant"] in ("A","B") and r["fold"]=="HOLDOUT"]));return report


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for k in ("panel","audit","indices","protocol","outdir"):p.add_argument("--"+k,required=True)
    p.add_argument("--members",default="reports/v68_investment_sector_members.csv");p.add_argument("--exploratory",default="reports/c3_work2_20261105/source_validation_cases.json")
    a=p.parse_args();run(a.panel,a.audit,a.indices,a.protocol,a.members,a.exploratory,a.outdir)
