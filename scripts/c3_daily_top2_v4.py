"""Four fixed experiments: daily/fixed-26 x pullback/confirmed breakout.

Research only. No production imports or order/notification side effects.
Prices are causal; retrospective cohort classification is NOT certified PIT.
"""
import argparse,csv,gzip,hashlib,json,math,statistics
from collections import Counter,defaultdict,deque
from datetime import datetime,timezone
from pathlib import Path

from c3_competition_v2 import load_official,market_proxy,observe,cluster_ci
from c3_entry_geometry_v23 import geometry
from c3_entry_benchmark_v1 import net_return
from c3_practical_top2_v3 import quote,tick,BUY,SELL,SLIP,INITIAL_CASH,mean,pct

METHODS=("PULLBACK","BREAKOUT")
CADENCES=("FIXED26","DAILY")
REUSED_END="2026-11-04"
UNSEEN_START="2026-11-06"


def fingerprint(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atr14(bars):
    if len(bars)<15:return None
    return statistics.mean(max(bars[i]["high"]-bars[i]["low"],
        abs(bars[i]["high"]-bars[i-1]["close"]),abs(bars[i]["low"]-bars[i-1]["close"])) for i in range(len(bars)-14,len(bars)))


def structure(past):
    """Last low confirmed by two later closed bars; buffer frozen at confirmation."""
    found=[]
    for i in range(max(14,len(past)-22),len(past)-2):
        if past[i]["low"]<=min(past[j]["low"] for j in range(i-2,i+3)):found.append(i)
    if not found:return None
    i=found[-1];confirmed=i+2;atr=atr14(past[:confirmed+1])
    raw_stop=past[i]["low"]-.5*atr
    if raw_stop<=0:return None
    stop=quote(raw_stop)
    if stop<=0 or any(b["close"]<stop for b in past[confirmed+1:]):return None
    return dict(pivot_date=past[i]["date"],confirmed_on=past[confirmed]["date"],
                support=past[i]["low"],atr=atr,stop=stop)


def features(past,market_return20):
    if len(past)<65:return None,"HISTORY_LT_65"
    g=geometry(past)
    if g.get("status")!="RESEARCH_GEOMETRY_ONLY" or g["trend_state"]!="UPTREND":return None,"NO_UPTREND"
    rs=100*(past[-1]["close"]/past[-21]["close"]-1)-market_return20
    if rs<=0:return None,"RS_NOT_POSITIVE"
    s=structure(past)
    if s is None:return None,"NO_VALID_CONFIRMED_STRUCTURE"
    volume=statistics.mean(b["volume"] for b in past[-21:-1])
    return dict(structure=s,geometry=g,rs20=rs,
        turnover20=statistics.mean(b["turnover_krw"] for b in past[-20:]),
        volume20=volume,prior_high20=max(b["high"] for b in past[-21:-1])),None


def make_plan(ticker,past,f,method,regime):
    s=f["structure"];atr=s["atr"];close=past[-1]["close"];level=f["prior_high20"]
    if method=="BREAKOUT":
        if not (close>level and past[-2]["close"]<=level and close>past[-1]["open"]
                and f["volume20"]>0 and past[-1]["volume"]>=1.2*f["volume20"]):return None,"BREAKOUT_NOT_CONFIRMED"
        low=quote(max(s["stop"]+tick(s["stop"]),level-.25*atr),True)
        high=quote(close+.5*atr)
    elif method=="PULLBACK":
        low=quote(s["support"]+.25*atr,True);high=quote(s["support"]+atr)
    else:raise ValueError("UNKNOWN_ENTRY_METHOD")
    r1=f["geometry"]["first_resistance"];r2=f["geometry"]["second_resistance"]
    if r1 is not None:high=min(high,quote(r1-tick(r1)))
    if not 0<s["stop"]<low<=high:return None,"NO_USABLE_PRICE_BAND"
    cost=high*(1+BUY)*(1+SLIP);risk=cost-s["stop"]*(1-SELL)*(1-SLIP)
    return dict(ticker=ticker,decision_date=past[-1]["date"],method=method,
        signal_key=ticker+":"+s["pivot_date"],segment=past[-1]["segment"],low=low,high=high,
        stop=s["stop"],support=s["support"],support_date=s["pivot_date"],known_on=s["confirmed_on"],atr=atr,
        reference_close=close,resistance=r1,resistance2=r2,breakout_level=level,
        net_r1_rr=(r1*(1-SELL)*(1-SLIP)-cost)/risk if r1 is not None else None,
        risk_pct=100*(high-s["stop"])/high,rank_turnover=f["turnover20"],rs20=f["rs20"],regime=regime),None


def next_day_entry(p,rows,sessions):
    future=[d for d in sessions if d>p["decision_date"]]
    if not future:return dict(status="PENDING_NEXT_SESSION",terminal=None,touches=[])
    day=future[0];b=next((b for b in rows if b["date"]==day),None)
    base=dict(terminal=day,touches=[])
    if b is None or b.get("invalid_data"):return dict(base,status="DATA_UNUSABLE")
    if b["action_boundary"] or b["segment"]!=p["segment"]:return dict(base,status="REFERENCE_OR_HISTORY_RESET")
    if not b["tradable"]:return dict(base,status="UNTRADABLE_DAY")
    if b["open"]<=p["stop"] or b["open"]<p["low"]:return dict(base,status="OPEN_BELOW_BUDGET")
    if p["method"]=="BREAKOUT":
        if b["open"]>p["high"]:return dict(base,status="OPEN_ABOVE_FROZEN_BUDGET")
        return dict(base,status="MODEL_ENTRY",date=day,price=b["open"],at_open=True,
                    order_unknown=False,actual_fill_verified=False,touches=[day])
    touch=b["low"]<=p["high"] and b["high"]>=p["low"]
    if touch:
        base["touches"]=[day];at_open=b["open"]<=p["high"]
        if at_open or b["low"]<=p["high"]-tick(p["high"]):
            return dict(base,status="MODEL_ENTRY",date=day,price=min(b["open"],p["high"]),
                at_open=at_open,order_unknown=b["low"]<=p["stop"],actual_fill_verified=False)
    return dict(base,status="TOUCH_WITHOUT_TRADE_THROUGH" if touch else "DAY_EXPIRED_NO_TOUCH")


def model_path(p,rows,sessions,horizon):
    entry=next_day_entry(p,rows,sessions)
    out=dict(entry=entry,exit=None,censor_date=None,maturity_date=None,observations=None)
    if entry["status"]!="MODEL_ENTRY":return out
    e=sessions.index(entry["date"])
    if e+horizon+1<len(sessions):out["maturity_date"]=sessions[e+horizon+1]
    out["observations"]=observe(dict(structure_stop=p["stop"],stop=p["stop"],resistance=p["resistance"]),entry,rows,sessions,horizon)
    by={b["date"]:b for b in rows};pending=None
    for j in range(e,len(sessions)):
        day=sessions[j];b=by.get(day)
        if b is None or b.get("invalid_data") or b["action_boundary"]:
            out.update(censor_date=day,censor_reason="UNPRICED_SECURITY_OR_ACTION");break
        if not b["tradable"]:
            if j-e>=horizon:pending=pending or "TIME_NEXT_OPEN"
            continue
        if pending:
            out["exit"]=dict(date=day,price=b["open"],reason=pending,
                net_pct=net_return(entry["price"]*(1+SLIP),b["open"]*(1-SLIP)))
            break
        if b["close"]<p["stop"]:pending="CLOSE_STOP_NEXT_OPEN"
        if j-e>=horizon:pending=pending or "TIME_NEXT_OPEN"
    return out


def replay(candidates,panel,sessions,horizon,fold,cadence):
    start="2025-05-02" if fold=="DEVELOPMENT" else UNSEEN_START if fold=="UNSEEN" else "2026-05-01"
    end="2026-03-31" if fold=="DEVELOPMENT" else sessions[-1] if fold=="UNSEEN" else min(sessions[-1],REUSED_END)
    days=[d for d in sessions if start<=d<=end];by={t:{b["date"]:b for b in rows} for t,rows in panel.items()}
    pool=defaultdict(list)
    for c in candidates:
        if c["fold"]==fold:pool[c["plan"]["decision_date"]].append(c)
    cash=float(INITIAL_CASH);slots=[];orders=[];closed=[];curve=[];used=set();next_allowed={};blocked=None;stats=Counter()
    for day in days:
        remove=[]
        for slot in slots:
            c=slot["c"];p=c["paths"][str(horizon)];entry=p["entry"]
            if slot["qty"]==0 and entry["status"]=="MODEL_ENTRY" and entry["date"]==day:
                unit=entry["price"]*(1+BUY)*(1+SLIP);qty=int(slot["budget"]//unit)
                if not qty:slot["order"]["status"]="UNAFFORDABLE";remove.append(slot);continue
                cash-=qty*unit;slot.update(qty=qty,buy_cost=qty*unit);used.add(c["plan"]["signal_key"])
                slot["order"].update(status="MODEL_ENTRY",qty=qty,entry_date=day,entry_price=entry["price"])
            if slot["qty"]:
                if p["censor_date"]==day:blocked=dict(date=day,ticker=c["plan"]["ticker"],reason=p["censor_reason"]);break
                if p["exit"] and p["exit"]["date"]==day:
                    x=p["exit"];proceeds=slot["qty"]*x["price"]*(1-SELL)*(1-SLIP);cash+=proceeds
                    closed.append(dict(ticker=c["plan"]["ticker"],signal_key=c["plan"]["signal_key"],
                        decision_date=c["plan"]["decision_date"],entry_date=entry["date"],exit_date=day,
                        net_pct=100*(proceeds/slot["buy_cost"]-1),reason=x["reason"],regime=c["plan"]["regime"],
                        mature=bool(p["maturity_date"] and p["maturity_date"]<=end),observations=p["observations"],
                        entry_order_unknown=entry["order_unknown"]))
                    remove.append(slot)
            elif entry["status"]!="MODEL_ENTRY" and entry.get("terminal")==day:
                slot["order"]["status"]=entry["status"];remove.append(slot)
        if blocked:break
        slots=[s for s in slots if s not in remove];nav=cash
        for slot in slots:
            if slot["qty"]:
                b=by[slot["c"]["plan"]["ticker"]].get(day)
                if b is None or not b["close"]:blocked=dict(date=day,reason="UNPRICED_NAV");break
                stats["untradable_marks"]+=int(not b["tradable"])
                nav+=slot["qty"]*b["close"]*(1-SELL)*(1-SLIP)
        if blocked:break
        if cash<-.001:raise ValueError("NEGATIVE_UNLEVERED_CASH")
        curve.append(dict(date=day,equity=nav,cash=cash,positions=sum(s["qty"]>0 for s in slots),reserved=sum(s["qty"]==0 for s in slots)))
        free=cash-math.fsum(s["budget"] for s in slots if not s["qty"]);eligible=[];index=sessions.index(day)
        for c in pool[day]:
            p=c["plan"];t=p["ticker"];stats["raw_plans"]+=1
            if p["signal_key"] in used:stats["already_entered_structure"]+=1;continue
            if cadence=="FIXED26":
                if index<next_allowed.get(t,0):stats["fixed_clock_suppressed"]+=1;continue
                next_allowed[t]=index+26 # As in the old experiment, even a nonselected proposal reserves its clock.
            if t in {s["c"]["plan"]["ticker"] for s in slots}:stats["already_reserved_ticker"]+=1;continue
            eligible.append(c)
        for c in sorted(eligible,key=lambda c:(-c["plan"]["rank_turnover"],-c["plan"]["rs20"],c["plan"]["ticker"]))[:max(0,2-len(slots))]:
            budget=min(free,nav/2)
            if budget<=0:break
            order=dict(plan=c["plan"],budget=budget,status="RESERVED")
            orders.append(order);slots.append(dict(c=c,budget=budget,qty=0,order=order));free-=budget
        if len(slots)>2:raise ValueError("TOP2_SLOT_OVERFLOW")
    complete=[t for t in closed if t["mature"]];values=[t["net_pct"] for t in complete];win=[v for v in values if v>0];loss=[v for v in values if v<0]
    peak=INITIAL_CASH;dd=0.
    for r in curve:peak=max(peak,r["equity"]);dd=min(dd,100*(r["equity"]/peak-1))
    lookup={(c["plan"]["ticker"],c["plan"]["decision_date"]):c for c in candidates};entries=[o for o in orders if o["status"]=="MODEL_ENTRY"]
    touch=sum(bool(lookup[(o["plan"]["ticker"],o["plan"]["decision_date"])]["paths"][str(horizon)]["entry"]["touches"]) for o in orders)
    obs=[t["observations"] for t in complete if t["observations"] and t["observations"]["complete"]]
    metrics=dict(completed=len(values),model_entries=len(entries),orders=len(orders),mean_net_pct=mean(values),
        win_rate_pct=pct([v>0 for v in values]),mean_win_pct=mean(win),mean_loss_pct=mean(loss),
        profit_factor=round(math.fsum(win)/abs(math.fsum(loss)),6) if loss else None,
        stop_rate_pct=pct(["STOP" in t["reason"] for t in complete]),
        touch_rate_pct=100*touch/len(orders) if orders else None,fill_rate_pct=100*len(entries)/len(orders) if orders else None,
        mean_mfe_pct=mean([o["mfe_pct"] for o in obs]),mean_mae_pct=mean([o["mae_pct"] for o in obs]),
        ci95_month_clusters=cluster_ci([(t["decision_date"][:7],t["net_pct"]) for t in complete]),
        portfolio_return_pct=round(100*(curve[-1]["equity"]/INITIAL_CASH-1),6) if curve and not blocked else None,
        max_drawdown_close_pct=round(dd,6) if curve and not blocked else None,censored=blocked,
        open_at_end=sum(s["qty"]>0 for s in slots),pending_at_end=sum(s["qty"]==0 for s in slots),counts=dict(stats),
        market_regimes={reg:dict(n=sum(t["regime"]==reg for t in complete),mean_net_pct=mean([t["net_pct"] for t in complete if t["regime"]==reg])) for reg in ("UP","DOWN","SIDEWAYS")},
        actual_fills_verified=False,intraday_mdd_verified=False)
    return dict(metrics=metrics,orders=orders,trades=closed,equity=curve)


def prepare(panel,sessions,audit,source):
    selected={t:rows for t,rows in panel.items() if t in set(audit["confirmation_tickers"])}
    with gzip.open(source,"rt") as f:
        turns={(r["ticker"],r["date"]):float(r["turnover_krw"]) for r in csv.DictReader(f) if r["ticker"] in selected}
    for t,rows in selected.items():
        for b in rows:b["turnover_krw"]=turns[(t,b["date"]) ]
    proxy=market_proxy(panel,sessions);market={}
    for i,d in enumerate(sessions):
        levels=[proxy[x] for x in sessions[:i+1]]
        if len(levels)<65:continue
        m20=statistics.mean(levels[-20:]);m60=statistics.mean(levels[-60:])
        market[d]=dict(rs_base=100*(levels[-1]/levels[-21]-1),regime="UP" if levels[-1]>m20>m60 else "DOWN" if levels[-1]<m20<m60 else "SIDEWAYS")
    candidates={m:[] for m in METHODS};counts=Counter()
    for t,rows in sorted(selected.items()):
        groups=defaultdict(list)
        for b in rows:
            if b["tradable"] and b["ohlc_valid"]:groups[b["segment"]].append(b)
        for bars in groups.values():
            for i in range(64,len(bars)):
                day=bars[i]["date"];index=sessions.index(day)
                if day<="2026-03-31":
                    if index+22>=len(sessions) or sessions[index+22]>"2026-03-31":continue
                    fold="DEVELOPMENT"
                elif day>=UNSEEN_START:fold="UNSEEN"
                elif "2026-05-01"<=day<=REUSED_END:fold="HOLDOUT"
                else:continue
                if day not in market or market[day]["regime"]=="DOWN":counts["MARKET_DOWN_OR_UNKNOWN"]+=1;continue
                past=bars[:i+1];f,reason=features(past,market[day]["rs_base"])
                if f is None:counts[reason]+=1;continue
                for method in METHODS:
                    p,reason=make_plan(t,past,f,method,market[day]["regime"])
                    if p is None:counts[method+":"+reason]+=1;continue
                    candidates[method].append(dict(plan=p,fold=fold,paths={str(h):model_path(p,rows,sessions,h) for h in (5,10,20)}))
        print(json.dumps(dict(ticker=t,prepared=sum(c["plan"]["ticker"]==t for c in candidates["PULLBACK"]))),flush=True)
    return selected,candidates,dict(counts)


def run(panel,sessions,audit,source,outdir):
    selected,candidates,counts=prepare(panel,sessions,audit,source);results={};table=[]
    for method in METHODS:
        for cadence in CADENCES:
            key=cadence+"_"+method
            results[key]={fold:{str(h):replay(candidates[method],selected,sessions,h,fold,cadence) for h in (5,10,20)} for fold in ("DEVELOPMENT","HOLDOUT","UNSEEN")}
            stats=results[key]["HOLDOUT"]
            table.append(dict(model=key,n5=stats["5"]["metrics"]["completed"],mean5=stats["5"]["metrics"]["mean_net_pct"],
                n10=stats["10"]["metrics"]["completed"],mean10=stats["10"]["metrics"]["mean_net_pct"],
                n20=stats["20"]["metrics"]["completed"],mean20=stats["20"]["metrics"]["mean_net_pct"],
                mdd20=stats["20"]["metrics"]["max_drawdown_close_pct"],portfolio20=stats["20"]["metrics"]["portfolio_return_pct"],
                fill_rate20=stats["20"]["metrics"]["fill_rate_pct"],state="REUSED_PERIOD_EXPLORATORY_NOT_ADOPTED"))
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    with gzip.open(root/"daily_ledger.json.gz","wt") as f:json.dump(results,f,separators=(",",":"))
    report=dict(schema="C3_DAILY_TOP2_V4",audit=audit,cohort_used=len(selected),candidate_counts={m:len(c) for m,c in candidates.items()},rejections=counts,
        metrics={k:{fold:{h:r["metrics"] for h,r in f.items()} for fold,f in folds.items()} for k,folds in results.items()},
        protocol=dict(buy_cost=BUY,sell_cost=SELL,slippage_each_side=SLIP,initial_cash=INITIAL_CASH,slots=2,
            order_validity_next_session_only=True,fixed26_clock_starts_at_proposal_even_if_not_selected=True,
            rank="UPTREND_AND_POSITIVE_RS_THEN_TURNOVER20",market_down_new_entries=False,
            pivot_left_right=2,structure_window_sessions=20,atr_buffer=.5,atr_frozen_at_pivot_confirmation=True,
            fixed_stop_percentage=False,hard_first_resistance_rr_filter=False,one_fill_per_structure=True,
            daily_uses_only_closed_bars=True,signal_close_is_not_a_fill=True,code_sha256=fingerprint(__file__),
            full_market_historical_biotech_classification_verified=False,old_comparison_period_already_seen=True),
        unseen=dict(first_decision_not_before=UNSEEN_START,
            completed_by_model={k:{h:r["metrics"]["completed"] for h,r in folds["UNSEEN"].items()} for k,folds in results.items()},
            status="FORWARD_WINDOWS_NOT_AVAILABLE_NO_PERFORMANCE_CLAIM" if sessions[-1]<UNSEEN_START else "FORWARD_DATA_PRESENT_NOT_AUTOMATIC_APPROVAL",schedules_created=False),
        current_action="CASH",adopted_model=None,orders_enabled=False)
    (root/"daily_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    with (root/"daily_comparison.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]),lineterminator="\n");w.writeheader();w.writerows(table)
    print(json.dumps(table),flush=True);return report


def main():
    p=argparse.ArgumentParser()
    for name in ("panel","audit","outdir"):p.add_argument("--"+name,required=True)
    p.add_argument("--members",default="reports/v68_investment_sector_members.csv")
    p.add_argument("--exploratory",default="reports/c3_work2_20261105/source_validation_cases.json");a=p.parse_args()
    panel,sessions,audit=load_official(a.panel,a.audit,a.members,a.exploratory)
    run(panel,sessions,audit,a.panel,a.outdir)


if __name__=="__main__":main()
