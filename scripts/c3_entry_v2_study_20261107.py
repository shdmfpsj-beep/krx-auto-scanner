#!/usr/bin/env python3
"""C3 V2 retrospective execution comparison, with NO change to C3 signals.

1. Frozen 2026-11-05 published research preview vs 2026-11-06 original KRX
   research market: reproduce prospective *price-rule* test without claiming
   the historical late-published preview was available pre-open.
2. Separately evaluate ORIGINAL v6 B/DAILY research decisions and v7 frozen
   A_SUPPORT_LIMIT plans on the same retrospective 95-name panel, strictly
   across paired common 5/10/20-session clocks. This is NOT point-in-time
   whole-market validation and cannot prove profitability.

All outputs are aggregate/derived; licensed raw panel and encrypted secrets
remain excluded from artifacts, research ledger and console logs.
"""
import csv, gzip, hashlib, json, math, os, statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from c3_entry_v2_preopen import entry,exit_model,direct_case,stats
from c3_bootstrap_cache_v13 import restore
from c3_competition_v2 import load_official,market_proxy
from c3_selection_factors_v6 import load_indices,build_pool,choose,nonoverlap
from c3_entry_practical_v7 import prepare
from c3_forward_ledger_v8 import read_record
from c3_daily_top2_v4 import model_path

BASE=Path("/tmp/c3-entry-v2-research")
STATE=Path("state/reports/c3_forward_v8")
LANE=STATE/"lanes/krx_unadjusted_v12"
PREVIEW=Path("preview/reports/c3_forward_v8/latest.json")
HORIZONS=(5,10,20)
METHODS=("LEGACY_GAP_VETO","RESTING_ONE","RESTING_TWO")
ORIGINAL_ENGINE="077113ac2f5e93fecc4c47850b36e5eda2173e3d"


def require(ok,code):
    if not ok:raise ValueError(code)


def jsonout(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")



def dated_index_grid(sessions):
    """Reconcile archived reference index files to the historical panel dates.

    Only the exact published prefix that matches the entire original market
    calendar is allowed. This is NOT a new index series or a data repair.
    """
    dest=BASE/"dated_indices";dest.mkdir(parents=True,exist_ok=True)
    sources=("reports/c3_work6_20261105/sources",
             "reports/c3_work7_20261105/sources")
    audit={};meta=dict(series={})
    for market in ("KOSPI","KOSDAQ"):
        choices=[]
        for folder in sources:
            root=Path(folder)
            manifest=json.loads((root/"index_manifest.json").read_text())
            original=root/(market+"_index.csv")
            original_sha=hashlib.sha256(original.read_bytes()).hexdigest()
            require(original_sha==manifest["series"][market]["csv_sha256"],
                    "ORIGINAL_BENCHMARK_CSV_SHA_MISMATCH")
            with original.open(newline="") as f:rows=list(csv.DictReader(f))
            # Never insert or extrapolate dates, not even over holidays.
            if len(rows)>=len(sessions) and [r["date"] for r in rows[:len(sessions)]]==sessions:
                choices.append((len(rows)-len(sessions),folder,rows,manifest,original_sha))
        require(choices,"NO_HASH_VERIFIED_MATCHING_HISTORICAL_INDEX_GRID_"+market)
        _,folder,original_rows,source_manifest,source_sha=min(choices,key=lambda z:z[0])
        rows=original_rows[:len(sessions)]
        output=dest/(market+"_index.csv")
        with output.open("w",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=["date","market","open","high","low","close"],lineterminator="\n")
            writer.writeheader();writer.writerows(rows)
        updated=dict(source_manifest["series"][market],rows=len(rows),last=rows[-1]["date"],
                     last_close=float(rows[-1]["close"]),
                     csv_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
        meta["series"][market]=updated
        audit[market]=dict(original_ref=folder,original_sha256=source_sha,
                           source_rows=len(original_rows),matched_historical_rows=len(rows),
                           future_rows_trimmed=len(original_rows)-len(rows),
                           last_match=rows[-1]["date"])
    jsonout(dest/"index_manifest.json",meta)
    load_indices(dest,sessions) # independent re-validation of content and calendar
    return dest,audit

def load_historical():
    require(bool(os.environ.get("KRX_AUTH_KEY")),"ORIGINAL_PRIVATE_ARCHIVE_READER_KEY_MISSING")
    require(STATE.is_dir(),"IMMUTABLE_PRICE_STATE_MISSING")
    os.environ["C3_KEY_ENVELOPES_DIR"]=str((STATE/"key_envelopes").resolve())
    provenance=restore("reports/c3_work8_20261105/inputs.json",BASE/"inputs",STATE,
                       BASE/"bootstrap_manifest_receipts.json")
    require(len(provenance)==3,"BOOTSTRAP_HASH_RESTORE_FAILED")
    panel=BASE/"inputs/panel/official_panel.csv.gz"
    qa=BASE/"inputs/panel/quality_audit.json"
    panel_all,sessions,audit=load_official(panel,qa,
        "reports/v68_investment_sector_members.csv",
        "reports/c3_work2_20261105/source_validation_cases.json")
    selected={t:b for t,b in panel_all.items() if t in audit["confirmation_tickers"]}
    # The same original v7 historical 95-name cohort, no future universe added.
    require(len(selected)==95,"HISTORICAL_FROZEN_COHORT_DIFFERS")
    markets={};turnover={}
    with gzip.open(panel,"rt",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["ticker"] in selected:
                markets[r["ticker"]]=r["market"]
                turnover[r["ticker"],r["date"]]=float(r["turnover_krw"])
    for ticker,bars in selected.items():
        for b in bars:
            b["turnover_krw"]=turnover[ticker,b["date"]]
    index_dir,index_audit=dated_index_grid(sessions)
    indices,_=load_indices(index_dir,sessions)
    proxy=market_proxy(panel_all,sessions)
    pool=build_pool(selected,sessions,indices,turnover,markets,proxy)
    return selected,sessions,pool,dict(
        original_panel_rows=audit["raw_source_rows"],
        index_grid_reconciliation=index_audit,
        selected_cohort_names=len(selected),
        input_basis=audit["source_basis"],
        source_end=audit["effective_end"],
        point_in_time_universe_verified=audit["point_in_time_sector_membership_verified"],
        survivorship_bias_removed=audit["survivorship_bias_removed"],
        official_regular_only_certified=audit["regular_only_certified"],
        source_encrypted_bootstrap_hashes=[z["sha256"] for z in provenance])


def nov5_preview_nov6_market():
    old=json.loads(PREVIEW.read_text(encoding="utf-8"))
    require(old["source_price_asof"]=="2026-11-05","PREVIEW_NOT_11_05")
    require(old.get("research_top2_registered_for_source_session") is False,
            "HISTORICAL_PREVIEW_MUST_NOT_BECOME_FORWARD_REGISTERED_SIGNAL")
    require(old["report_day_kst"]=="2026-11-06","PREVIEW_REPORT_DAY_CHANGED")
    # The published report has a recorded time AFTER next-day 09:00 KST.
    created=datetime.fromisoformat(old["generated_at"].replace("Z","+00:00"))
    opening=datetime.fromisoformat("2026-11-06T09:00:00+09:00")
    require(created>opening,"EXPECTED_LATE_RESEARCH_PREVIEW_PUBLICATION_NOT_REPRODUCED")
    market=read_record(LANE/"markets/2026-11-06.json.gz")
    require(market["asof"]=="2026-11-06" and len(market["rows"])==2769,
            "DATED_IMMUTABLE_MARKET_SOURCE_DIFFERENCE")
    require(market["source"].get("regular_only_certified") is False,
            "INCORRECT_SESSION_CERTIFICATION")
    results=[]
    for r in old["research_top2"]:
        ticker=r["ticker"]
        require(ticker in ("028050","030530"),"UNEXPECTED_FROZEN_REFERENCE_TICKER")
        plan=r["entry_plans"]["A_SUPPORT_LIMIT"]["plan"]
        require(plan is not None,"HISTORICAL_PLAN_NOT_PRESENT")
        obs=market["rows"][ticker]
        obs=dict(obs,date="2026-11-06")
        result=direct_case(plan,obs)
        results.append(dict(**result,name=r["name"],
            frozen_prior_close=plan["reference_close"],
            source_day="2026-11-05",
            preview_generated_at=old["generated_at"],
            actually_preopen_publication_verified=False,
            original_order_expiry="NEXT_SESSION_ONLY"))
    return dict(observed="2026-11-06",reference="2026-11-05",
                preopen_publication_verified=False,entries=results,
                data_session_regular_only_certified=False,
                no_new_historical_trade_registration=True)


def evaluate_histories(panel,sessions,pool,fold):
    decisions=choose(pool,sessions,"B","DAILY",fold)
    if fold=="HOLDOUT":require(len(decisions)==150,"ORIGINAL_HOLDOUT_B_SELECTION_COUNT_CHANGED")
    all_cases={}
    decision_by_key={(r["ticker"],r["decision_date"]):r for r in decisions}
    for study_group,orders in (("ALL_REPEATED",decisions),("NONOVERLAP_20",nonoverlap(decisions,sessions,20))):
        _,cells=prepare(orders,panel,sessions,"A_SUPPORT_LIMIT")
        date_index={d:i for i,d in enumerate(sessions)}
        group_report={"decision_count":len(orders),"valid_plans":sum(c["plan"] is not None for c in cells),
                      "no_plan_reasons":dict(Counter(c["status"] for c in cells if c["plan"] is None)),
                      "horizons":{}}
        for horizon in HORIZONS:
            store={m:[] for m in METHODS}
            full_clock_n=0
            entry_reasons={m:Counter() for m in METHODS}
            mechanical_unsafe={m:0 for m in METHODS}
            legacy_cancel_but_resting_fills=0
            close_stop_touch={m:0 for m in METHODS}
            paired_diff=[]
            recovered_cases=[]
            unsafe_open_cases=[]
            legacy_exit_parity_checked=0
            for cell in cells:
                plan=cell["plan"];key=(cell["ticker"],cell["decision_date"])
                if plan is None:continue
                require(key in decision_by_key,"ORIGINAL_B_DECISION_IDENTITY_MISMATCH")
                i=date_index[cell["decision_date"]]
                # One entry session + 5/10/20 observed closes + one exit open.
                if i+horizon+2>=len(sessions):continue
                dates=sessions[i+1:i+horizon+3]
                by={b["date"]:b for b in panel[cell["ticker"]]}
                # Require complete validated common clock for EACH variant.
                if any(d not in by or not by[d].get("tradable") or by[d].get("invalid_data")
                       or by[d].get("action_boundary") for d in dates):continue
                full_clock_n+=1
                entry_day=dates[0]
                outcomes={}
                for method in METHODS:
                    ent=entry(plan,by[entry_day],method)
                    entry_reasons[method][ent["status"]]+=1
                    mechanical_unsafe[method]+=int(bool(ent.get("open_at_or_below_stop")))
                    close_stop_touch[method]+=int(bool(ent.get("same_day_low_touched_stop")))
                    outcome=exit_model(plan,entry_day,ent,by,sessions,horizon,
                        include_unsafe_mechanical=True)
                    require(outcome["status"] in ("COMPLETE","NO_ENTRY"),"SHARED_CLOCK_EXITS_UNRESOLVED")
                    outcomes[method]=outcome
                    if method=="LEGACY_GAP_VETO":
                        frozen_baseline=model_path(plan,panel[cell["ticker"]],sessions,horizon)
                        historical_entry=frozen_baseline["entry"]
                        require(historical_entry["status"]==("MODEL_ENTRY" if ent.get("filled") else ent["status"]),
                                "BASELINE_ENTRY_REPLAY_STATUS_DIVERGED")
                        if outcome["status"]=="COMPLETE":
                            old_exit=frozen_baseline["exit"]
                            require(old_exit is not None and old_exit["date"]==outcome["exit_date"],
                                    "BASELINE_EXIT_REPLAY_DATE_DIVERGED")
                            require(abs(old_exit["net_pct"]-outcome["net_pct"])<0.000002,
                                    "BASELINE_EXIT_REPLAY_COST_DIVERGED")
                            legacy_exit_parity_checked+=1
                    if outcome["status"]=="COMPLETE":
                        store[method].append(dict(outcome,filled=True,unsafe=ent.get("open_at_or_below_stop",False)))
                    else:
                        store[method].append(dict(status="NO_ENTRY",filled=False,
                            cash_adjusted_pct=0.,entry_status=ent["status"]))
                if outcomes["LEGACY_GAP_VETO"]["status"]=="NO_ENTRY" and outcomes["RESTING_ONE"]["status"]=="COMPLETE":
                    legacy_cancel_but_resting_fills+=1
                    recovered_cases.append(dict(
                        ticker=cell["ticker"],decision_date=cell["decision_date"],entry_date=entry_day,
                        original_gap_veto=entry(plan,by[entry_day],"LEGACY_GAP_VETO")["status"],
                        prior_close=plan["reference_close"],low=plan["low"],high=plan["high"],
                        structural_stop=plan["stop"],open=by[entry_day]["open"],
                        net_pct=outcomes["RESTING_ONE"]["net_pct"],
                        exit_date=outcomes["RESTING_ONE"]["exit_date"],
                        exit_reason=outcomes["RESTING_ONE"]["exit_reason"],
                        drawdown_pct=outcomes["RESTING_ONE"]["mae_pct"],
                        non_pit_historical_panel=True))
                if any(x.get("unsafe_unconditional_preopen_fill") for x in outcomes.values()):
                    unsafe_open_cases.append(dict(
                        ticker=cell["ticker"],decision_date=cell["decision_date"],
                        open=by[entry_day]["open"],stop=plan["stop"],
                        resting_one_net_pct=outcomes["RESTING_ONE"].get("net_pct")))
                def val(o):
                    return o.get("opportunity_cash_adjusted_pct",0.) if o["status"]=="COMPLETE" else 0.
                paired_diff.append(val(outcomes["RESTING_ONE"])-val(outcomes["LEGACY_GAP_VETO"]))
            method_summaries={}
            for method,outs in store.items():
                done=[x for x in outs if x["status"]=="COMPLETE"]
                n=len(outs)
                rets=[x["net_pct"] for x in done]
                opportunity=[x["opportunity_cash_adjusted_pct"] if x["status"]=="COMPLETE" else 0. for x in outs]
                method_summaries[method]=dict(
                    common_clock_plans=n,filled=len(done),
                    fill_rate_pct=round(100*len(done)/n,3) if n else None,
                    completed_trade_mean_net_pct=round(statistics.mean(rets),5) if rets else None,
                    opportunity_mean_with_cash_pct=round(statistics.mean(opportunity),5) if opportunity else None,
                    opportunity_median_with_cash_pct=round(statistics.median(opportunity),5) if opportunity else None,
                    completed_win_rate_pct=round(100*sum(v>0 for v in rets)/len(rets),3) if rets else None,
                    exit_stop_count=sum(x.get("exit_reason")=="CLOSE_BELOW_FROZEN_STOP_NEXT_OPEN" for x in done),
                    unsafe_open_at_or_below_stop_count=mechanical_unsafe[method],
                    same_day_low_touched_stop_count=close_stop_touch[method],
                    entry_status_counts=dict(entry_reasons[method]),
                    unconditional_resting_orders_not_automatically_cancelable=True if method.startswith("RESTING_") else False)
            group_report["horizons"][str(horizon)]=dict(
                common_clock_plans=full_clock_n,
                legacy_cancel_but_resting_filled=legacy_cancel_but_resting_fills,
                paired_resting_minus_legacy_mean_cash_pct=round(statistics.mean(paired_diff),5) if paired_diff else None,
                legacy_exit_parity_checked=legacy_exit_parity_checked,
                gap_veto_recovered_outcomes=recovered_cases,
                unprotected_open_at_or_below_stop_cases=unsafe_open_cases,
                variants=method_summaries)
        all_cases[study_group]=group_report
    return dict(raw_selected_decisions=len(decisions),comparison=all_cases)


def main():
    BASE.mkdir(parents=True,exist_ok=True)
    os.environ["C3_KEY_ENVELOPES_DIR"]=str((STATE/"key_envelopes").resolve())
    nov=nov5_preview_nov6_market()
    panel,sessions,pool,provenance=load_historical()
    results={fold:evaluate_histories(panel,sessions,pool,fold) for fold in ("DEVELOPMENT","HOLDOUT")}
    result=dict(schema="C3_V2_PREOPEN_GAP_ENTRY_RESEARCH_V1",
                original_engine_ref=ORIGINAL_ENGINE,
                data_provenance=provenance,
                nov5_to_nov6=nov,
                historical_cohort=results,
                critical_limitations=[
                    "2026-11-05 research preview was generated on Nov 6 AFTER 09:00. Price-rule replay is not a real ex-ante forward signal.",
                    "The user-reported actual preopen mock executions are not a verified broker audit and are not stored as research ledger trades.",
                    "The 95-name historic cohort was retrospectively selected; sector membership and full market sampling are not point-in-time certified.",
                    "Resting preopen orders can fill at or below the stop; cannot undo the opening auction fill with knowledge of the opening price.",
                    "Daily OHLCV does not prove queue fills from touching a limit, intraday rebound confirmation or intraday stop/target ordering.",
                    "Outcome exit uses the frozen structural stop when closing price breaks it, exit at NEXT open; costs use frozen research fee+slippage assumptions.",
                    "ALL_REPEATED observations are serially correlated. NONOVERLAP_20 is small. NO engine promotion or profit claim.",
                    "No performance is included for real forward signals until actually matured after their registered source date.",
                ],
                original_decision_ledger_mutations=0,telegram_sends=0,
                trade_orders=0,model_promotion=False)
    out=BASE/"entry_v2_audit.json"
    jsonout(out,result)
    small=dict(status="PASS",historical_cohort_provenance=provenance,
        preopen_case=[dict(ticker=x["ticker"],name=x["name"],frozen_plan=x["frozen_plan"],
                           bar=x["observed_bar"],
                           variants={m:dict(status=v["status"],price=v.get("price"),fills=v.get("fill_count"),
                                            allocation=v.get("allocations_filled"))
                                     for m,v in x["variants"].items()})
                     for x in nov["entries"]],
        metric_summary={fold:{g:{h:{
            "n":z["common_clock_plans"],
            "gap_cancellations_recovered":z["legacy_cancel_but_resting_filled"],
            "legacy_exit_parity_checked":z["legacy_exit_parity_checked"],
            "gap_veto_recovered_outcomes":z["gap_veto_recovered_outcomes"],
            "unsafe_open_cases":z["unprotected_open_at_or_below_stop_cases"],
            "variants":{method:{k:v for k,v in metric.items() if k in
                ("filled","completed_trade_mean_net_pct","opportunity_mean_with_cash_pct",
                 "exit_stop_count","unsafe_open_at_or_below_stop_count")}
                for method,metric in z["variants"].items()}}
            for h,z in details["horizons"].items()}
            for g,details in data["comparison"].items()}
            for fold,data in results.items()},
        original_forward_model_unchanged=True,telegram_sends=0)
    print("C3_ENTRY_V2_RESEARCH="+json.dumps(small,ensure_ascii=False,allow_nan=False),flush=True)


if __name__=="__main__": main()
