"""Research-only TOP2 reservations, tick-aware entries and causal evidence gates.

Consumes the frozen v2 decision clock, not its future fills for ranking. The
retrospective non-biotech cohort is NOT a historical full-market TOP2 replay.
"""
import argparse,csv,gzip,hashlib,json,math,statistics
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path

from c3_competition_v2 import (load_official,market_proxy,signal_features,entry_cap,observe,cluster_ci)
from c3_entry_benchmark_v1 import net_return

ENTRIES=("C3_STRUCTURE","COSTED_LIMIT","FRESH_COSTED_LIMIT")
RANKS=("TURNOVER20","STOCK_RS20","SECTOR_LEADER")
BUY=.0015;SELL=.005;SLIP=.001
INITIAL_CASH=10_000_000


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def mean(xs):return round(statistics.mean(xs),6) if xs else None
def pct(xs):return round(100*sum(xs)/len(xs),4) if xs else None


def tick(price):
    if not math.isfinite(price) or price<=0:raise ValueError("INVALID_QUOTE")
    for bound,step in ((2000,1),(5000,5),(20000,10),(50000,50),(200000,100),(500000,500)):
        if price<bound:return step
    return 1000


def quote(price,up=False):
    step=tick(price)
    return int((math.ceil(price/step-1e-10) if up else math.floor(price/step+1e-10))*step)


def plan_entry(original,features,method):
    p=deepcopy(original);p["strategy"]=method
    p["resistance2"]=features.get("geometry",{}).get("second_resistance")
    if method=="FRESH_COSTED_LIMIT":
        support=features["fresh_support"]
        if support is None:return None,"NO_RECENT_CONFIRMED_LOW"
        p.update(stop=support-.5*p["atr"],low=support+.25*p["atr"],high=support+p["atr"])
    # Freeze the structural invalidation first. The budget changes entry only.
    p["stop"]=quote(p["stop"])
    if method!="C3_STRUCTURE":
        cap=entry_cap(p["stop"],p["resistance"])
        if cap is None:return None,"FIRST_RESISTANCE_UNKNOWN"
        p["high"]=min(p["high"],cap)
    p["low"]=quote(p["low"],True);p["high"]=quote(p["high"])
    if not 0<p["stop"]<p["low"]<=p["high"]:return None,"NO_COSTED_ENTRY_BAND"
    cost=p["high"]*(1+SLIP)*(1+BUY)
    risk=cost-p["stop"]*(1-SLIP)*(1-SELL)
    p["net_r1_rr"]=(p["resistance"]*(1-SLIP)*(1-SELL)-cost)/risk if p["resistance"] else None
    p["planned_risk_pct"]=100*(p["high"]-p["stop"])/p["high"]
    return p,None


def locate_strict(p,by,sessions):
    days=[d for d in sessions if d>p["decision_date"]][:5];touches=[]
    for d in days:
        b=by.get(d)
        if b is None or b.get("invalid_data"):return dict(status="DATA_UNUSABLE",terminal=d,touches=touches)
        if b["action_boundary"]:return dict(status="REFERENCE_CHANGED",terminal=d,touches=touches)
        if not b["tradable"]:continue
        if b["segment"]!=p["segment"]:return dict(status="SIGNAL_HISTORY_RESET",terminal=d,touches=touches)
        if b["open"]<=p["stop"] or b["open"]<p["low"]:
            return dict(status="GAP_INVALIDATION",terminal=d,touches=touches)
        if b["low"]<=p["high"] and b["high"]>=p["low"]:
            touches.append(d)
            at_open=b["open"]<=p["high"]
            # A single print at the limit does not establish queue execution.
            if at_open or b["low"]<=p["high"]-tick(p["high"]):
                return dict(status="MODEL_ENTRY",date=d,price=min(b["open"],p["high"]),at_open=at_open,
                    order_unknown=b["low"]<=p["stop"],actual_fill_verified=False,touches=touches)
        if b["close"]<p["stop"] or (p["resistance"] and b["high"]>=p["resistance"]):
            return dict(status="WATCH_INVALIDATED",terminal=d,touches=touches)
    return dict(status="NO_TRADE_THROUGH" if len(days)==5 else "INCOMPLETE_WATCH",
                terminal=days[-1] if len(days)==5 else None,touches=touches)


def path_model(p,rows,sessions,horizon,mode="CLOSE"):
    by={b["date"]:b for b in rows};entry=locate_strict(p,by,sessions)
    out=dict(entry=entry,exit=None,censor_date=None,maturity_date=None,observations=None)
    if entry["status"]!="MODEL_ENTRY":return out
    e=sessions.index(entry["date"])
    if e+horizon+1<len(sessions):out["maturity_date"]=sessions[e+horizon+1]
    out["observations"]=observe(p,entry,rows,sessions,horizon)
    pending=None;stop=p["stop"]
    for j in range(e,len(sessions)):
        d=sessions[j];b=by.get(d)
        if b is None or b.get("invalid_data") or b["action_boundary"]:
            out.update(censor_date=d,censor_reason="UNPRICED_SECURITY_OR_ACTION");break
        if not b["tradable"]:
            if j-e>=horizon:pending=pending or "TIME_NEXT_OPEN"
            continue
        price=None;reason=None
        if pending:price=b["open"];reason=pending
        elif mode=="INTRADAY" and (j>e or entry["at_open"]) and b["open"]<=stop:
            price=b["open"];reason="GAP_STOP"
        elif mode=="INTRADAY" and b["low"]<=stop:
            price=stop;reason="INTRADAY_STOP"
        if price is not None:
            out["exit"]=dict(date=d,price=price,reason=reason,
                net_pct=net_return(entry["price"]*(1+SLIP),price*(1-SLIP)))
            break
        if mode!="INTRADAY" and b["close"]<stop:pending="CLOSE_STOP_NEXT_OPEN"
        if j-e>=horizon:pending=pending or "TIME_NEXT_OPEN"
        if mode=="R1_RAISE" and p["resistance"] and b["close"]>p["resistance"]:
            stop=max(stop,quote(entry["price"])) # Applies next day, never retroactively.
    return out


def rank_key(candidate,rule):
    f=candidate["features"]
    if rule=="TURNOVER20":return (-f["turnover20"],candidate["ticker"])
    if rule=="STOCK_RS20":return (-f["stock_rs20"],-f["turnover20"],candidate["ticker"])
    if rule=="SECTOR_LEADER":
        if f["sector_rs20"] is None or f["stock_vs_sector20"] is None:return None
        return (-f["sector_rs20"],-f["stock_vs_sector20"],-f["turnover20"],candidate["ticker"])
    raise ValueError("UNKNOWN_RANK_RULE")


def edge_gate(candidates,day,horizon):
    cutoff=(date.fromisoformat(day)-timedelta(days=120)).isoformat();past=[]
    for c in candidates:
        p=c["paths"][str(horizon)];m=p["maturity_date"];x=p["exit"]
        # Early losing exits wait for the same scheduled maturity as winners.
        if m and cutoff<=m<day and x and x["date"]<day and not p["censor_date"]:
            past.append((c["ticker"],x["net_pct"]))
    values=[v for t,v in past]
    enough=len(values)>=20 and len({t for t,v in past})>=10
    allowed=bool(enough and statistics.mean(values)>0 and statistics.median(values)>=0)
    return dict(allowed=allowed,n=len(values),tickers=len({t for t,v in past}),mean_net_pct=mean(values),
                median_net_pct=statistics.median(values) if values else None,
                reason="PASSED" if allowed else "INSUFFICIENT_MATURED_EVIDENCE" if not enough else "NONPOSITIVE_RECENT_EDGE")


def replay(candidates,panel,sessions,rank,horizon,fold,gated=False,mode="CLOSE"):
    start="2025-05-02" if fold=="DEVELOPMENT" else "2026-05-01"
    end="2026-03-31" if fold=="DEVELOPMENT" else sessions[-1]
    days=[d for d in sessions if start<=d<=end];by={t:{b["date"]:b for b in bars} for t,bars in panel.items()}
    pool=defaultdict(list)
    for c in candidates:
        if c["fold"]==fold:pool[c["decision_date"]].append(c)
    cash=float(INITIAL_CASH);slots=[];orders=[];closed=[];curve=[];decisions=[];blocked=None;stale_marks=0
    for d in days:
        releases=[]
        for s in slots:
            p=s["candidate"]["paths"][str(horizon)];entry=p["entry"]
            if s["qty"]==0 and entry["status"]=="MODEL_ENTRY" and entry["date"]==d:
                unit=entry["price"]*(1+SLIP)*(1+BUY);qty=int(s["budget"]//unit)
                if qty<=0:
                    s["order"]["status"]="UNAFFORDABLE";releases.append(s);continue
                s.update(qty=qty,buy_cost=qty*unit);cash-=qty*unit
                s["order"].update(status="MODEL_ENTRY",qty=qty,entry_date=d,entry_price=entry["price"])
            if s["qty"]:
                if p["censor_date"]==d:blocked=dict(date=d,ticker=s["candidate"]["ticker"],reason=p["censor_reason"]);break
                if p["exit"] and p["exit"]["date"]==d:
                    x=p["exit"];proceeds=s["qty"]*x["price"]*(1-SLIP)*(1-SELL);cash+=proceeds
                    closed.append(dict(ticker=s["candidate"]["ticker"],decision_date=s["candidate"]["decision_date"],
                        entry_date=entry["date"],exit_date=d,net_pct=100*(proceeds/s["buy_cost"]-1),
                        pnl_krw=proceeds-s["buy_cost"],reason=x["reason"],regime=s["candidate"]["features"]["regime"],
                        mature=bool(p["maturity_date"] and p["maturity_date"]<=end),
                        first_resistance_rr=s["candidate"]["plan"]["net_r1_rr"],entry_order_unknown=entry["order_unknown"],
                        observations=p["observations"]))
                    releases.append(s)
            elif entry["status"]!="MODEL_ENTRY" and entry.get("terminal")==d:
                s["order"]["status"]=entry["status"];releases.append(s)
        if blocked:break
        slots=[s for s in slots if s not in releases]
        nav=cash
        for s in slots:
            if s["qty"]:
                b=by[s["candidate"]["ticker"]].get(d)
                if b is None or not b["close"]:blocked=dict(date=d,reason="UNPRICEABLE_NAV");break
                stale_marks+=int(not b["tradable"])
                nav+=s["qty"]*b["close"]*(1-SLIP)*(1-SELL)
        if blocked:break
        if cash<-.001:raise ValueError("NEGATIVE_UNLEVERED_CASH")
        curve.append(dict(date=d,equity=nav,cash=cash,open_positions=sum(s["qty"]>0 for s in slots),
                          reserved_slots=sum(s["qty"]==0 for s in slots)))
        available=cash-sum(s["budget"] for s in slots if s["qty"]==0)
        eligible=[]
        for c in pool[d]:
            if c["ticker"] in {s["candidate"]["ticker"] for s in slots}:continue
            k=rank_key(c,rank)
            if k is not None:eligible.append((k,c))
        gate=edge_gate(candidates,d,horizon) if gated else dict(allowed=True,reason="CONTROL_NO_EDGE_GATE")
        picked=[]
        if gate["allowed"]:
            for k,c in sorted(eligible,key=lambda x:x[0])[:max(0,2-len(slots))]:
                budget=min(available,nav/2)
                if budget<=0:break
                order=dict(ticker=c["ticker"],decision_date=d,budget=budget,status="RESERVED",plan=c["plan"])
                orders.append(order);slots.append(dict(candidate=c,budget=budget,qty=0,order=order));picked.append(c["ticker"])
                available-=budget
        if len(slots)>2:raise ValueError("TOP2_SLOT_OVERFLOW")
        if pool[d]:decisions.append(dict(date=d,ranked_candidates=len(eligible),selected=picked,gate=gate))
    complete=[t for t in closed if t["mature"]];values=[t["net_pct"] for t in complete]
    winners=[v for v in values if v>0];losers=[v for v in values if v<0]
    peak=INITIAL_CASH;dd=0.
    for r in curve:peak=max(peak,r["equity"]);dd=min(dd,100*(r["equity"]/peak-1))
    fills=[o for o in orders if o["status"]=="MODEL_ENTRY"]
    touched=sum(bool(next(c for c in candidates if c["ticker"]==o["ticker"] and c["decision_date"]==o["decision_date"])["paths"][str(horizon)]["entry"]["touches"]) for o in orders)
    obs=[t["observations"] for t in complete if t["observations"] and t["observations"]["complete"]]
    metrics=dict(orders=len(orders),model_entries=len(fills),touch_rate_pct=100*touched/len(orders) if orders else None,
        strict_fill_rate_pct=100*len(fills)/len(orders) if orders else None,
        missed_or_pending_pct=100*(len(orders)-len(fills))/len(orders) if orders else None,
        completed_trades=len(values),mean_net_pct=mean(values),win_rate_pct=pct([v>0 for v in values]),
        mean_win_pct=mean(winners),mean_loss_pct=mean(losers),
        payoff_ratio=statistics.mean(winners)/abs(statistics.mean(losers)) if winners and losers else None,
        profit_factor=sum(winners)/abs(sum(losers)) if losers else None,
        expectancy_pct=mean(values),stop_rate_pct=pct(["STOP" in t["reason"] for t in complete]),
        mean_mfe_pct=mean([o["mfe_pct"] for o in obs]),mean_mae_pct=mean([o["mae_pct"] for o in obs]),
        mean_first_resistance_rr=mean([t["first_resistance_rr"] for t in complete if t["first_resistance_rr"] is not None]),
        mean_ci95_month_clusters=cluster_ci([(t["decision_date"][:7],t["net_pct"]) for t in complete]),
        market_regimes={r:dict(n=sum(t["regime"]==r for t in complete),mean_net_pct=mean([t["net_pct"] for t in complete if t["regime"]==r])) for r in ("UP","DOWN","SIDEWAYS")},
        portfolio_return_pct=100*(curve[-1]["equity"]/INITIAL_CASH-1) if curve and not blocked else None,
        max_drawdown_close_liquidation_pct=dd if not blocked else None,
        prefix_max_drawdown_if_censored=dd if blocked else None,censored=blocked,
        open_positions_at_end=sum(s["qty"]>0 for s in slots),
        pending_orders_at_end=sum(s["qty"]==0 for s in slots),
        signals_not_reservable=sum(len(v) for v in pool.values())-len(orders),
        untradable_close_marks=stale_marks,liquidation_mark_is_not_guaranteed_execution=True,
        intraday_drawdown_verified=False,actual_fills_verified=False)
    return dict(metrics=metrics,orders=orders,trades=closed,equity=curve,decisions=decisions)


def prepare(panel,sessions,audit,ledger_path,panel_path,members_path):
    records=json.load(gzip.open(ledger_path,"rt"))["C3_BASELINE"]
    old=set(audit["excluded_prior_exploratory_tickers"]);records=[r for r in records if r["ticker"] not in old]
    turnovers={}
    with gzip.open(panel_path,"rt") as f:
        for r in csv.DictReader(f):
            if r["ticker"] in panel:turnovers[(r["ticker"],r["date"])]=float(r["turnover_krw"])
    members=defaultdict(set)
    with open(members_path,encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["ticker"] in panel:members[r["ticker"]].add(r["investment_sector"])
    proxy=market_proxy(panel,sessions);days=sorted({r["decision_date"] for r in records});context={}
    for d in days:
        market=[proxy[x] for x in sessions if x<=d];returns={};sectors=defaultdict(dict)
        for t,bars in panel.items():
            past=[b for b in bars if b["date"]<=d and b["tradable"]]
            if len(past)<21 or past[-1]["date"]!=d or past[-21]["segment"]!=past[-1]["segment"]:continue
            ret=100*(past[-1]["close"]/past[-21]["close"]-1);returns[t]=ret
            for sector in members[t]:sectors[sector][t]=ret
        sector_returns={s:statistics.mean(v.values()) for s,v in sectors.items() if len(v)>=3}
        context[d]=(returns,sector_returns,100*(market[-1]/market[-21]-1))
    candidates={m:[] for m in ENTRIES};rejections={m:Counter() for m in ENTRIES}
    for r in records:
        t=r["ticker"];d=r["decision_date"];segment=r["plan"]["segment"]
        past=[b for b in panel[t] if b["date"]<=d and b["segment"]==segment and b["tradable"]]
        f=signal_features(past,{},proxy,sessions)
        if f is None:raise ValueError("FROZEN_DECISION_CANNOT_BE_RECONSTRUCTED")
        returns,sectors,mret=context[d];known=[sectors[s] for s in sorted(members[t]) if s in sectors]
        # Do not retrospectively choose whichever of several themes did best.
        sector_ret=statistics.mean(known) if known else None
        features=dict(turnover20=statistics.mean(turnovers[(t,b["date"])] for b in past[-20:]),
            stock_rs20=returns[t]-mret,sector_rs20=sector_ret-mret if sector_ret is not None else None,
            stock_vs_sector20=returns[t]-sector_ret if sector_ret is not None else None,
            heat_atr=(past[-1]["close"]-f["ma"][20])/r["plan"]["atr"],regime=f["regime"],
            sector_membership_is_retrospective=True,flows=None,earnings=None,news=None)
        for method in ENTRIES:
            p,reason=plan_entry(r["plan"],f,method)
            if p is None:rejections[method][reason]+=1;continue
            c=dict(ticker=t,decision_date=d,fold=r["fold"],plan=p,features=features,
                paths={str(h):path_model(p,panel[t],sessions,h) for h in (5,10,20)})
            candidates[method].append(c)
    return candidates,{k:dict(v) for k,v in rejections.items()}


def opportunity_comparison(candidates,sessions,fold,horizon):
    """One shared fully observed clock; no-fill is cash, unknown exits are not zero."""
    end="2026-03-31" if fold=="DEVELOPMENT" else sessions[-1]
    lookup={method:{(c["ticker"],c["decision_date"]):c for c in rows if c["fold"]==fold}
            for method,rows in candidates.items()}
    keys=[]
    for key in lookup["C3_STRUCTURE"]:
        i=sessions.index(key[1]);m=i+5+horizon+1
        if m<len(sessions) and sessions[m]<=end:keys.append(key)
    totals={method:[] for method in ENTRIES};statuses={method:Counter() for method in ENTRIES};censored=0;missed=Counter()
    for key in keys:
        values={};filled={}
        for method in ENTRIES:
            c=lookup[method].get(key)
            if c is None:values[method]=0.;filled[method]=False;statuses[method]["FILTERED_AT_DECISION"]+=1;continue
            p=c["paths"][str(horizon)];e=p["entry"]
            statuses[method][e["status"]]+=1;filled[method]=e["status"]=="MODEL_ENTRY"
            if not filled[method]:values[method]=0.
            elif p["exit"] and p["exit"]["date"]<=end:values[method]=p["exit"]["net_pct"]
            else:values[method]=None
        if any(v is None for v in values.values()):censored+=1;continue
        for method,v in values.items():
            totals[method].append(v)
            if method!="C3_STRUCTURE" and values["C3_STRUCTURE"]>0 and not filled[method]:missed[method]+=1
    return dict(shared_fully_observed_anchors=len(keys),common_censored_anchors=censored,
        methods={m:dict(mean_net_per_anchor_including_cash=mean(v),evaluated_anchors=len(v),
                        entry_statuses=dict(statuses[m]),baseline_winners_missed=missed[m]) for m,v in totals.items()},
        not_a_capital_weighted_portfolio=True)


def run(panel,sessions,audit,ledger_path,panel_path,members_path,outdir):
    candidates,rejections=prepare(panel,sessions,audit,ledger_path,panel_path,members_path)
    results={};summary=[]
    for method in ENTRIES:
        for rank in RANKS:
            key=method+"__"+rank;results[key]={}
            for fold in ("DEVELOPMENT","HOLDOUT"):
                results[key][fold]={str(h):replay(candidates[method],panel,sessions,rank,h,fold) for h in (5,10,20)}
    primary="FRESH_COSTED_LIMIT__SECTOR_LEADER"
    key=primary+"__CAUSAL_EDGE_GATE";results[key]={fold:{str(h):replay(candidates["FRESH_COSTED_LIMIT"],panel,sessions,"SECTOR_LEADER",h,fold,True) for h in (5,10,20)} for fold in ("DEVELOPMENT","HOLDOUT")}
    for key,folds in results.items():
        stats=folds["HOLDOUT"]
        summary.append(dict(model=key,n5=stats["5"]["metrics"]["completed_trades"],mean5=stats["5"]["metrics"]["mean_net_pct"],
            n10=stats["10"]["metrics"]["completed_trades"],mean10=stats["10"]["metrics"]["mean_net_pct"],
            n20=stats["20"]["metrics"]["completed_trades"],mean20=stats["20"]["metrics"]["mean_net_pct"],
            portfolio_return20=stats["20"]["metrics"]["portfolio_return_pct"],mdd20=stats["20"]["metrics"]["max_drawdown_close_liquidation_pct"],
            strict_fill_rate20=stats["20"]["metrics"]["strict_fill_rate_pct"],validation="EXPLORATORY_NOT_ADOPTED"))
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    with gzip.open(root/"top2_replay_ledger.json.gz","wt") as f:json.dump(results,f,separators=(",",":"))
    report=dict(schema="C3_PRACTICAL_TOP2_V3",audit=audit,rejections=rejections,
        opportunity_comparison={fold:{str(h):opportunity_comparison(candidates,sessions,fold,h) for h in (5,10,20)} for fold in ("DEVELOPMENT","HOLDOUT")},
        metrics={k:{fold:{h:r["metrics"] for h,r in f.items()} for fold,f in folds.items()} for k,folds in results.items()},
        protocol=dict(shared_frozen_decisions=True,baseline_is_geometry_not_historical_live_ranking=True,
            limit_rule="AT_OPEN_OR_ONE_TICK_TRADE_THROUGH",slot_count=2,initial_cash=INITIAL_CASH,
            quote_units_source="https://regulation.krx.co.kr/contents/RGL/03/03010100/RGL03010100T3.jsp",
            integer_shares=True,buy_cost=BUY,sell_cost=SELL,slippage_each_side=SLIP,
            primary_hypothesis=primary,edge_gate_window_days=120,edge_gate_min_n=20,edge_gate_min_tickers=10,
            full_scheduled_maturity_required_for_edge_evidence=True,future_fill_cannot_free_slots_early=True,
            current_sector_mapping_not_pit=True,prior_holdout_already_seen=True,
            fundamental_news_and_investor_flows_not_scored_without_pit_history=True,
            stop_is_structural_not_fixed_pct=True,code_sha256=sha(__file__)),
        decision="CASH",live_strategy_adopted=None,orders_enabled=False)
    (root/"top2_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    with (root/"top2_comparison.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]),lineterminator="\n");w.writeheader();w.writerows(summary)
    print(json.dumps(summary),flush=True);return report


def main():
    p=argparse.ArgumentParser()
    for name in ("panel","audit","ledger","outdir"):p.add_argument("--"+name,required=True)
    p.add_argument("--members",default="reports/v68_investment_sector_members.csv")
    p.add_argument("--exploratory",default="reports/c3_work2_20261105/source_validation_cases.json");a=p.parse_args()
    panel,sessions,audit=load_official(a.panel,a.audit,a.members,a.exploratory)
    run(panel,sessions,audit,a.ledger,a.panel,a.members,a.outdir)


if __name__=="__main__":main()
