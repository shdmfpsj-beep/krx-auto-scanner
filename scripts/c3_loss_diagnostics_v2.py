"""Explain the frozen legacy losses without relabeling post-entry outcomes as predictors."""
import argparse
import csv
import json
import statistics
from pathlib import Path

from c3_entry_benchmark_v1 import load_archived_panel,read_bars,run_benchmark


def preconditions(plan,rows):
    past=[b for b in rows if b["date"]<=plan["decision_date"]]
    if not past or past[-1]["date"]!=plan["decision_date"]:
        raise ValueError("DECISION_BAR_MISSING")
    g=plan["geometry"];high=plan["watch_high"];stop=plan["structure_stop"]
    resistance=plan["resistance1"]
    risk=100*(high-stop)/high
    cost_risk=high*1.0015-stop*.995
    net_rr=(resistance*.995-high*1.0015)/cost_risk if resistance and cost_risk>0 else None
    prior=past[:-1];pivots=[]
    for i in range(2,len(prior)-2):
        if (prior[i]["low"]==g["support"]
                and prior[i]["low"]<=min(prior[k]["low"] for k in range(i-2,i+3))):
            pivots.append(i)
    age=len(past)-1-pivots[-1] if pivots else None
    volume=statistics.mean(b["volume"] for b in past[-21:-1])
    atr_pct=100*plan["atr14"]/past[-1]["close"]
    gap=(past[-1]["close"]-g["ma20"])/plan["atr14"]
    return dict(planned_risk_pct=risk,net_first_resistance_rr=net_rr,
                support_age_sessions=age,atr_pct=atr_pct,ma20_gap_atr=gap,
                flags={"STRUCTURAL_RISK_ABOVE_8PCT":risk>8,
                       "FIRST_RESISTANCE_NET_RR_BELOW_1":net_rr<1 if net_rr is not None else None,
                       "FIRST_RESISTANCE_MISSING":resistance is None,
                       "DECISION_CLOSE_ABOVE_MA20_BY_2ATR":gap>2,
                       "ATR_ABOVE_5PCT":atr_pct>5,
                       "SUPPORT_OLDER_THAN_20_SESSIONS":age>20 if age is not None else None,
                       "DECISION_VOLUME_BELOW_70PCT_PRIOR20":past[-1]["volume"]<.7*volume if volume>0 else None,
                       "MARKET_DOWNTREND":plan["context"]["market_regime"]=="DOWN" if plan["context"]["market_regime"]!="UNAVAILABLE" else None,
                       "SECTOR_RELATIVE_STRENGTH_WEAK":None})


def decompose_stop(record,rows):
    exit=record["exits"]["20"]["CLOSE_HOLD"]
    entry=record["entry"]["price"]
    gross=100*(exit["exit_price"]/entry-1)
    cost=exit["hypothetical_net_pct"]-gross
    if exit["exit_reason"]!="CLOSE_STOP_NEXT_OPEN":
        return dict(structural_distance=None,close_breach_overshoot=None,next_open_gap=None,
                    costs=cost,gross_return=gross,net_return=exit["hypothetical_net_pct"])
    before=[b for b in rows if b["date"]<exit["exit_date"]]
    if not before:
        raise ValueError("STOP_TRIGGER_CLOSE_MISSING")
    close=before[-1]["close"];stop=record["structure_stop"]
    components=dict(structural_distance=100*(stop/entry-1),
                    close_breach_overshoot=100*(close-stop)/entry,
                    next_open_gap=100*(exit["exit_price"]-close)/entry,costs=cost)
    if abs(sum(components.values())-exit["hypothetical_net_pct"])>1e-7:
        raise ValueError("STOP_PNL_COMPONENTS_DO_NOT_RECONCILE")
    components.update(gross_return=gross,net_return=exit["hypothetical_net_pct"])
    return components


def diagnose(panel,ledger):
    plans={p["plan_id"]:p for p in ledger["decisions"]}
    cases=[]
    for r in ledger["records"]["C3_BASELINE"]:
        if (r["fold"]!="HOLDOUT" or r["entry"]["status"]!="MODEL_ENTRY"
                or not r["exits"]["20"]["CLOSE_HOLD"]["complete"]):
            continue
        p=plans[r["plan_id"]];rows=panel[r["ticker"]]
        after=[b for b in rows if b["date"]>r["entry"]["date"]]
        pre=preconditions(p,rows)
        before=[b for b in rows if b["date"]<=p["decision_date"]]
        prior_vol=statistics.mean(b["volume"] for b in before[-21:-1])
        net=r["exits"]["20"]["CLOSE_HOLD"]["hypothetical_net_pct"]
        post=dict(first_next_close_return_pct=100*(after[0]["close"]/r["entry"]["price"]-1),
                  CLOSE_DROP_3PCT_FIRST_NEXT_SESSION=after[0]["close"]<r["entry"]["price"]*.97,
                  STRUCTURE_LOST_IN_FIRST_THREE_SESSIONS=any(b["close"]<r["structure_stop"] for b in after[:3]),
                  BREAKOUT_FAILED_WITHIN_THREE_SESSIONS=(any(b["close"]<p["geometry"]["prior_high20"] for b in after[:3]) if p["geometry"]["breakout_watch"] else None),
                  VOLUME_CONTRACTED_AFTER_ENTRY=(statistics.mean(b["volume"] for b in after[:3])<.7*prior_vol if prior_vol>0 else None))
        cases.append(dict(plan_id=r["plan_id"],ticker=r["ticker"],decision_date=p["decision_date"],
                          entry_date=r["entry"]["date"],entry_price=r["entry"]["price"],
                          structure_stop=r["structure_stop"],first_resistance=r["resistance1"],
                          exit_date=r["exits"]["20"]["CLOSE_HOLD"]["exit_date"],
                          net_pct=net,loss=net<0,before_decision=pre,after_entry_only=post,
                          accounting=decompose_stop(r,rows)))
    if not cases:
        raise ValueError("NO_LEGACY_COMPLETE_CASES")
    factors=[]
    for key in cases[0]["before_decision"]["flags"]:
        known=[c for c in cases if c["before_decision"]["flags"][key] is not None]
        selected=[c for c in known if c["before_decision"]["flags"][key]]
        losses=[c for c in selected if c["loss"]]
        factors.append(dict(hypothesis=key,known_cases=len(known),flagged_cases=len(selected),
                            flagged_losses=len(losses),negative_pnl_covered_pct_points=sum(c["net_pct"] for c in losses),
                            subgroup_mean_net_pct=statistics.mean(c["net_pct"] for c in selected) if selected else None,
                            winners_also_rejected=sum(not c["loss"] for c in selected),
                            causal_effect_established=False))
    ranked=sorted((f for f in factors if f["known_cases"]),key=lambda f:f["negative_pnl_covered_pct_points"])
    accounting={k:sum(c["accounting"][k] for c in cases if c["loss"] and c["accounting"][k] is not None)
                for k in ("structural_distance","close_breach_overshoot","next_open_gap","costs")}
    return dict(schema="C3_LEGACY_LOSS_DIAGNOSTICS_V2",cases=cases,factors=factors,top5_hypotheses=ranked[:5],
                losses=sum(c["loss"] for c in cases),completed_cases=len(cases),
                mean_net_pct=statistics.mean(c["net_pct"] for c in cases),
                additive_loss_accounting_pct_points=accounting,
                factor_coverage_overlaps_and_must_not_be_added=True,
                post_entry_flags_are_not_ex_ante_predictors=True,
                old_16_tickers_reserved_as_exploratory_not_confirmation=sorted(panel),
                price_basis="LEGACY_ADJUSTED_UNCERTIFIED",regular_only_certified=False,
                strategy_improvement_verified=False,orders_enabled=False,decision="CASH")


def write_report(result,outdir):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    (root/"legacy_loss_diagnostics.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    flat=[]
    for c in result["cases"]:
        r={k:v for k,v in c.items() if not isinstance(v,dict)}
        r.update({"pre_"+k:v for k,v in c["before_decision"].items() if k!="flags"})
        r.update({"account_"+k:v for k,v in c["accounting"].items()})
        flat.append(r)
    with (root/"legacy_loss_cases.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]),lineterminator="\n");w.writeheader();w.writerows(flat)
    (root/"source_validation_cases.json").write_text(json.dumps(dict(tickers=result["old_16_tickers_reserved_as_exploratory_not_confirmation"],
        dates=sorted({d for c in result["cases"] for d in (c["decision_date"],c["entry_date"],c["exit_date"])})),indent=2)+"\n")


def main():
    p=argparse.ArgumentParser();p.add_argument("--ledger");p.add_argument("--outdir",required=True)
    a=p.parse_args()
    panel,sessions,audit=load_archived_panel('reports/c3_premove_history_v1.csv.gz','reports/c3_premove_observation_status_v1.json',
        'reports/c3_reference_calendar_v1.json','reports/v68_investment_sector_members.csv','config/c3_screening_evidence/basic_20261023')
    ledger=json.loads(Path(a.ledger).read_text()) if a.ledger else run_benchmark(panel,sessions,read_bars('reports/c3_work_20261104/inputs/market_reference.csv'))
    result=diagnose(panel,ledger);write_report(result,a.outdir)
    print(json.dumps(dict(cases=result["completed_cases"],losses=result["losses"],mean_net_pct=result["mean_net_pct"])))


if __name__=="__main__":main()
