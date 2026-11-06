"""Three preregistered execution packages on the unchanged v6 B selections.

Reuse the validated v4 stop/fill/cash engine. Never promote a historical winner.
No orders, notifications, paid model calls, or live-rule changes.
"""
import argparse,csv,gzip,json,math,statistics
from collections import Counter,defaultdict
from pathlib import Path

from c3_competition_v2 import load_official
from c3_daily_top2_v4 import features,make_plan,atr14,replay,quote,tick,BUY,SELL,SLIP
from c3_selection_factors_v6 import full_session_path,paper_metrics,load_indices
from c3_selection_diagnostic_v5 import outcome
from c3_selection_scope_v5 import digest,write_csv

ENTRIES=("A_SUPPORT_LIMIT","B_CONFIRMED_PULLBACK","C_LIMITED_BREAKOUT")


def first_reclaim(past):
    if len(past)<25:return None
    last=past[-1]
    if not last["close"]>last["open"] or not last["close"]>past[-2]["close"]:return None
    for n in (20,10,5):
        ma=statistics.mean(b["close"] for b in past[-n:])
        if not last["low"]<=ma<=last["close"]:continue
        touched=False
        for i in range(len(past)-6,len(past)-1):
            prior_ma=statistics.mean(b["close"] for b in past[i-n+1:i+1])
            touched=touched or past[i]["low"]<=prior_ma<=past[i]["close"]
        if not touched:return dict(line="MA"+str(n),price=ma)
    return None


def costed_r1_cap(resistance):
    if resistance is None:return None
    cap=resistance*(1-SELL)*(1-SLIP)/((1+BUY)*(1+SLIP));rounded=quote(cap)
    if rounded*(1+BUY)*(1+SLIP)>=resistance*(1-SELL)*(1-SLIP):rounded-=tick(rounded)
    return rounded


def entry_plan(ticker,past,f,variant,market_regime):
    if variant=="A_SUPPORT_LIMIT":
        p,reason=make_plan(ticker,past,f,"PULLBACK",market_regime)
        if p:p.update(signal_rule=variant,execution_model="ONE_SESSION_LIMIT")
        return p,reason
    if variant=="C_LIMITED_BREAKOUT":
        p,reason=make_plan(ticker,past,f,"BREAKOUT",market_regime)
        if p is None:return None,reason
    elif variant=="B_CONFIRMED_PULLBACK":
        reclaim=first_reclaim(past)
        if reclaim is None:return None,"FIRST_PULLBACK_NOT_CONFIRMED"
        s=f["structure"];p=dict(ticker=ticker,decision_date=past[-1]["date"],signal_key=ticker+":"+s["pivot_date"],
            segment=past[-1]["segment"],stop=s["stop"],support=s["support"],support_date=s["pivot_date"],known_on=s["confirmed_on"],
            atr=s["atr"],reference_close=past[-1]["close"],resistance=f["geometry"]["first_resistance"],resistance2=f["geometry"]["second_resistance"],
            rank_turnover=f["turnover20"],rs20=f["rs20"],regime=market_regime,confirmation=reclaim,
            low=quote(max(s["support"],s["stop"]+tick(s["stop"])),True))
        # In the existing engine BREAKOUT names the budgeted next-open fill
        # branch. signal_rule below records this different pullback setup.
        p["method"]="BREAKOUT"
    else:raise ValueError("UNREGISTERED_ENTRY_PACKAGE")
    current_atr=atr14(past);p["high"]=quote(past[-1]["close"]+.5*current_atr)
    cap=costed_r1_cap(p["resistance"])
    if cap is not None:p["high"]=min(p["high"],cap)
    if not 0<p["stop"]<p["low"]<=p["high"]:return None,"NO_VOLATILITY_AND_R1_PRICE_BUDGET"
    cost=p["high"]*(1+BUY)*(1+SLIP);risk=cost-p["stop"]*(1-SELL)*(1-SLIP)
    p.update(signal_rule=variant,execution_model="NEXT_OPEN_WITHIN_FROZEN_BUDGET",current_atr=current_atr,
        net_r1_rr=(p["resistance"]*(1-SELL)*(1-SLIP)-cost)/risk if p["resistance"] is not None else None,
        risk_pct=100*(p["high"]-p["stop"])/p["high"],r1_unknown=p["resistance"] is None)
    return p,None


def prepare(decisions,panel,sessions,variant):
    candidates=[];cells=[]
    for r in decisions:
        past=[b for b in panel[r["ticker"]] if b["date"]<=r["decision_date"] and b["segment"]==r["segment"] and b["tradable"] and not b["invalid_data"]]
        f,reason=features(past,r["legacy_market_return20"]);p=None
        if f is not None:p,reason=entry_plan(r["ticker"],past,f,variant,r["market_regime"])
        cell=dict(ticker=r["ticker"],decision_date=r["decision_date"],status=reason or "PLAN_READY",plan=p)
        if p:
            c=dict(plan=p,fold=r["fold"],paths={str(h):full_session_path(p,panel[r["ticker"]],sessions,h) for h in (5,10,20)})
            candidates.append(c);cell["paths"]=c["paths"]
        cells.append(cell)
    return candidates,cells


def opportunity(cells,panel,sessions,indices,markets,horizon,fold):
    dates=[d for d in sessions if d<="2026-03-31"] if fold=="DEVELOPMENT" else sessions
    grid={d:i for i,d in enumerate(dates)};counts=Counter();values=[];entries=[];details=[];missed=Counter()
    for cell in cells:
        t=cell["ticker"];d=cell["decision_date"];i=grid[d]
        if i+horizon+1>=len(dates):counts["INCOMPLETE_COMMON_CLOCK"]+=1;continue
        reference=outcome(t,d,panel[t],dates,horizon,indices[markets[t]])
        if reference["status"]!="COMPLETE" or reference["reference_net_pct"] is None:counts["DATA_OR_EXECUTION_REFERENCE_UNRESOLVED"]+=1;continue
        label=cell["status"];net=None
        if cell["plan"] is None:net=0.;label="NO_CONFIRMED_SETUP_OR_BUDGET"
        else:
            path=cell["paths"][str(horizon)];e=path["entry"]
            if e["status"]!="MODEL_ENTRY":
                label=e["status"]
                if label in ("DATA_UNUSABLE","REFERENCE_OR_HISTORY_RESET","PENDING_NEXT_SESSION"):counts[label]+=1;continue
                net=0.
            elif path["censor_date"] or not path["exit"] or path["exit"]["date"]>dates[-1]:counts["EXIT_OR_ACTION_UNRESOLVED"]+=1;continue
            else:label="MODEL_ENTRY";net=path["exit"]["net_pct"];entries.append(net)
        counts[label]+=1;values.append(net)
        if reference["reference_net_pct"]>0 and label!="MODEL_ENTRY":missed["no_setup" if cell["plan"] is None else "not_filled"]+=1
        details.append(dict(ticker=t,decision_date=d,status=label,net_pct=net,reference_next_open_net_pct=reference["reference_net_pct"]))
    avg=lambda v:round(statistics.mean(v),6) if v else None
    return dict(selected=len(cells),common_clock_completed=len(values),counts=dict(counts),equal_opportunity_net_pct=avg(values),
        model_entry_mean_net_pct=avg(entries),model_entry_count=len(entries),profitable_reference_no_setup=missed["no_setup"],
        profitable_reference_unfilled=missed["not_filled"],cash_zeros_are_only_known_no_setup_or_no_fill=True,
        not_capital_constrained_portfolio=True),details


def selection_context(archive,markets):
    summary={}
    for h in (5,10,20):
        rows=[r for r in archive["outcomes"] if r["variant"] in ("A","B") and r["cadence"]=="DAILY" and r["fold"]=="HOLDOUT" and r["horizon"]==h and r["status"]=="COMPLETE"]
        avg=lambda v:round(statistics.mean(v),6) if v else None
        unpaired={v:{reg:dict(n=len(xs:=[r for r in rows if r["variant"]==v and r["market_regime"]==reg]),
            mean_excess_pct=avg([r["excess_pct"] for r in xs]),mean_price_move_pct=avg([r["price_move_pct"] for r in xs]),
            mean_net_reference_pct=avg([r["reference_net_pct"] for r in xs if r["reference_net_pct"] is not None])) for reg in ("UP","SIDEWAYS","DOWN")} for v in ("A","B")}
        grouped={v:defaultdict(list) for v in ("A","B")}
        for r in rows:grouped[r["variant"]][(r["decision_date"],markets[r["ticker"]])].append(r)
        paired=defaultdict(list)
        for key in sorted(set(grouped["A"])&set(grouped["B"])):
            a,b=grouped["A"][key],grouped["B"][key];regs={r["market_regime"] for r in a+b}
            if len(regs)!=1:raise ValueError("INCONSISTENT_MARKET_REGIME_ON_SAME_BOARD_DAY")
            paired[next(iter(regs))].append(statistics.mean(r["excess_pct"] for r in b)-statistics.mean(r["excess_pct"] for r in a))
        summary[str(h)]=dict(unpaired=unpaired,paired_same_day_and_market={reg:dict(n=len(paired[reg]),mean_B_minus_A_excess_pct=avg(paired[reg])) for reg in ("UP","SIDEWAYS","DOWN")},
            same_date_different_market_not_paired=True,small_samples_not_proof=True)
    return summary


def run(panel_path,audit_path,archive_path,index_dir,protocol_path,outdir):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    protocol=json.loads(Path(protocol_path).read_text())
    if tuple(protocol["entry_variants"])!=ENTRIES:raise ValueError("ENTRY_PROTOCOL_CHANGED")
    archive=json.load(gzip.open(archive_path,"rt"));all_panel,sessions,audit=load_official(panel_path,audit_path,"reports/v68_investment_sector_members.csv","reports/c3_work2_20261105/source_validation_cases.json")
    panel={t:b for t,b in all_panel.items() if t in audit["confirmation_tickers"]};markets={};turns={}
    with gzip.open(panel_path,"rt") as f:
        for r in csv.DictReader(f):
            if r["ticker"] in panel:markets[r["ticker"]]=r["market"];turns[(r["ticker"],r["date"])]=float(r["turnover_krw"])
    for t,bars in panel.items():
        for b in bars:b["turnover_krw"]=turns[(t,b["date"])]
    indices,index_meta=load_indices(index_dir,sessions);table=[];metrics={};ledgers={};opp={};example=None
    for variant in ENTRIES:
        metrics[variant]={};ledgers[variant]={};opp[variant]={}
        for fold in ("DEVELOPMENT","HOLDOUT"):
            decisions=archive["selections"]["B"]["DAILY"][fold];candidates,cells=prepare(decisions,panel,sessions,variant)
            metrics[variant][fold]={};ledgers[variant][fold]={};opp[variant][fold]={}
            if candidates and example is None:example=candidates[0]["plan"]
            for h in (5,10,20):
                result=replay(candidates,panel,sessions,h,fold,"DAILY");m=paper_metrics(result,candidates,h,panel,sessions,indices,markets,fold)
                opportunity_metrics,detail=opportunity(cells,panel,sessions,indices,markets,h,fold)
                m["opportunity"]=opportunity_metrics;m["no_setup_reasons"]=dict(Counter(c["status"] for c in cells if c["plan"] is None))
                metrics[variant][fold][str(h)]=m;ledgers[variant][fold][str(h)]=result;opp[variant][fold][str(h)]=detail
                table.append(dict(entry=variant,fold=fold,horizon=h,selected=len(decisions),orders=m["orders"],entries=m["model_entries"],completed=m["completed"],
                    fill_rate=m["fill_rate_pct"],mean_net=m["mean_net_pct"],opportunity_mean=opportunity_metrics["equal_opportunity_net_pct"],
                    missed_profitable=opportunity_metrics["profitable_reference_unfilled"],no_setup_profitable=opportunity_metrics["profitable_reference_no_setup"],
                    stop_rate=m["stop_rate_pct"],mdd=m["max_drawdown_close_pct"],portfolio=m["portfolio_return_pct"]))
    # Exact A replay is checked against the archived study, not a new baseline fit.
    for fold in ("DEVELOPMENT","HOLDOUT"):
        for h in (5,10,20):
            before=archive["papers"]["B_DAILY_PULLBACK"][fold][str(h)]["metrics"];after=metrics["A_SUPPORT_LIMIT"][fold][str(h)]
            for key in ("orders","model_entries","completed","mean_net_pct","fill_rate_pct","portfolio_return_pct","max_drawdown_close_pct"):
                if before[key]!=after[key]:raise ValueError("ARCHIVED_SUPPORT_CONTROL_DIVERGED:"+key)
    write_csv(root/"entry_comparison.csv",table)
    report=dict(schema="C3_ENTRY_PRACTICAL_V7",selection_context=selection_context(archive,markets),entry_metrics=metrics,historical_cohort=len(panel),
        frozen_B_decisions_reused=True,support_control_exactly_reproduced=True,current_scope_not_backtested=1983,
        new_unseen_completed={str(h):0 for h in (5,10,20)},ai_C_status="NO_GENUINE_MODEL_REVIEW_NO_PERFORMANCE_CLAIM",current_action="CASH",new_model_adopted=False,
        sources=dict(panel=digest(panel_path),audit=digest(audit_path),frozen_ledger=digest(archive_path),protocol=digest(protocol_path),code=digest(__file__)),
        orders_enabled=False,notifications_or_schedules_changed=False)
    (root/"entry_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    with gzip.open(root/"entry_ledger.json.gz","wt") as f:json.dump(dict(papers=ledgers,opportunities=opp,chart_example=example),f,separators=(",",":"))
    print(json.dumps([r for r in table if r["fold"]=="HOLDOUT"]));return report


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for k in ("panel","audit","archive","indices","protocol","outdir"):p.add_argument("--"+k,required=True)
    a=p.parse_args();run(a.panel,a.audit,a.archive,a.indices,a.protocol,a.outdir)
