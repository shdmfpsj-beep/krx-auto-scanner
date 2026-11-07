#!/usr/bin/env python3
"""V6 original frozen B cohort missed-fill causal audit (READ ONLY).

Only this summary is persisted. Original encrypted panel, issuer lists,
signals, Telegram receipts and simulated account state are never written.
The diagnostic does not claim observed broker fills or new optimized trades.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

from c3_v5_continuation_entry import POLICIES, simulate
from c3_v5_continuation_study_20261107 import (
    _rows, market_map, indexed_benchmark, SOURCE_LAST, HORIZONS
)
from c3_v6_fill_attribution import explain, summarize
from c3_entry_v2_study_20261107 import STATE, load_historical, require, jsonout
from c3_selection_factors_v6 import choose, nonoverlap
from c3_entry_practical_v7 import prepare

OUT=Path("/tmp/c3-v6-missed-fill")
FOLDS=("DEVELOPMENT","HOLDOUT")
GROUPS=("ALL_REPEATED","NONOVERLAP_20")

def audit_rows(panel, sessions, selection, fold, horizon, index, markets):
    rows,exclusions,base=_rows(panel,sessions,selection,fold,horizon,index,markets)
    orig_cells=prepare(selection,panel,sessions,"A_SUPPORT_LIMIT")[1]
    by_cell={(c["ticker"],c["decision_date"]):c for c in orig_cells}
    by_prior={(c["ticker"],c["decision_date"]):c for c in selection}
    require(len(by_cell)==len(orig_cells),"V6_DUPLICATE_PREDECISION_PLAN_KEY")
    require(len(by_prior)==len(selection),"V6_DUPLICATE_FROZEN_DECISION_KEY")
    by_bar={t:{b["date"]:b for b in bs} for t,bs in panel.items()}
    attributed=[]
    errors=Counter()
    for row in rows:
        ticker=row["ticker"]
        decision_date=row["decision_date"]
        key=(ticker,decision_date)
        require(key in by_cell and key in by_prior,
                "V6_RECONSTRUCTED_PLAN_KEY_MISSING")
        plan=by_cell[key]["plan"]
        frozen_prior=by_prior[key]
        next_bar=by_bar[ticker][row["entry_date"]]
        require(bool(plan is not None)==row["source_plan_present"],
                "V6_RESEARCH_PLAN_PRESENT_CHANGED")
        outcomes={}
        for policy in POLICIES:
            expected=row["output"][policy]
            frozen,e=simulate(plan,frozen_prior,next_bar,policy)
            require(expected["submitted"]==frozen["submitted"],
                    "V6_FROZEN_PREOPEN_SUBMISSION_DRIFT")
            require(expected["prior_status"]==frozen["status"],
                    "V6_PREOPEN_STATUS_DRIFT")
            require(expected["limit"]==frozen.get("limit"),
                    "V6_PREOPEN_LIMIT_DRIFT")
            require(expected["filled"]==e["filled"],
                    "V6_FROZEN_EXECUTION_DRIFT")
            require(expected["entry_status"]==e["status"],
                    "V6_ENTRY_STATUS_DRIFT")
            item=explain(plan,frozen,e,next_bar,
                         expected_ticker=ticker,
                         expected_decision_date=decision_date)
            require(item["filled"]==expected["filled"],
                    "V6_ATTRIBUTED_FILL_DRIFT")
            outcomes[policy]=item
        attributed.append(dict(
            ticker=ticker, decision_date=decision_date,
            next_open_reference_net_pct=row["independent_next_open_reference_net_pct"],
            causes=outcomes))
    return dict(
        source_baseline=base,strict_full_clock_exclusions=exclusions,
        original_selection_count=len(selection),
        evaluated_causal_pairs=len(attributed),
        cause_attribution=summarize(attributed),
        unused_future_values_for_entry_decision=True,
        source_rows_persisted=False,
    )

def main():
    os.environ["C3_KEY_ENVELOPES_DIR"]=str((STATE/"key_envelopes").resolve())
    panel,sessions,pool,provenance=load_historical()
    require(provenance["source_end"]==SOURCE_LAST,
            "V6_ORIGINAL_HISTORICAL_END_CHANGED")
    indices=indexed_benchmark(sessions)
    markets=market_map(panel)
    result={}
    for fold in FOLDS:
        original=choose(pool,sessions,"B","DAILY",fold)
        if fold=="HOLDOUT":
            require(len(original)==150,"V6_B_DAILY_HOLDOUT_COUNT_CHANGED")
        result[fold]={}
        for group in GROUPS:
            selected=(original if group=="ALL_REPEATED"
                      else nonoverlap(original,sessions,20))
            result[fold][group]={}
            for horizon in HORIZONS:
                result[fold][group][str(horizon)]=audit_rows(
                    panel,sessions,selected,fold,horizon,indices,markets)
    payload=dict(
        schema="C3_V6_FROZEN_MISSED_FILL_ATTRIBUTION_20261107_V1",
        source_end=SOURCE_LAST,
        fixed_preexisting_policies=list(POLICIES),
        exact_original_prior_close_selections=True,
        original_source=provenance,
        results=result,
        limitations=[
            "Historical 95-name selected research cohort, not point-in-time whole-market data.",
            "Five, ten, twenty-session results share signals: not independent trials.",
            "An intraday one-tick trade-through remains a model fill, not a broker-executed receipt.",
            "A touched resting limit without trade-through is queue-uncertain, NOT filled.",
            "No intraday timing order can be reconstructed from OHLCV.",
            "No real independent 09:00-15:30-only KRX OHLCV/turnover attestation.",
            "Profit reference assumes hypothetical next-open purchase; it is ex-post ONLY.",
            "Nov5 preopen order examples were not an original preregistered C3 morning signal.",
            "Original trading ledger, charts, Telegram, alerts, orders and main not modified.",
        ],
        new_entry_policy_count=0,live_trade_authorized=False,
        real_forward_5_10_20_matured=0,
        strategy_promotion_authorized=False,default_action="CASH")
    OUT.mkdir(parents=True,exist_ok=True)
    jsonout(OUT/"v6_cause_attribution_summary.json",payload)
    short={fold:{grp:{h:{
        "n":d["evaluated_causal_pairs"],
        "V2":d["cause_attribution"]["policy_causes"]["V2_HIGH"],
        "V4":d["cause_attribution"]["policy_causes"]["V4_MIDPOINT"],
    }for h,d in groups.items()}
        for grp,groups in folds.items()}
        for fold,folds in result.items()}
    print("C3_V6_ATTRIBUTION="+json.dumps(dict(
        status="PASS",source_end=SOURCE_LAST,
        diagnostic=short,
        original_ledger_writes=0,telegram_sends=0,
        live_orders=0,model_promotion=False),
        ensure_ascii=False,allow_nan=False),flush=True)

if __name__=="__main__":
    main()
