"""Exact Nov5 frozen *late-published* preview vs Nov6 price-rule V4 sensitivity.

This is NOT a true forward result: preview itself was written Nov6 at 11:15 KST
after Nov6 pre-open auction; user-reported mock orders were independently placed
earlier, with their own limits, not these mechanically reconstructed V4 limits.
"""
import json,os
from datetime import datetime
from pathlib import Path
from c3_entry_v4_geometry import VARIANTS,executable_cap,model_entry
from c3_forward_ledger_v8 import read_record
from c3_entry_v2_study_20261107 import STATE,PREVIEW,jsonout,require

OUT=Path("/tmp/c3-v4-entry-geometry/v4_nov6_scenario_only.json")
def run():
    os.environ["C3_KEY_ENVELOPES_DIR"]=str((STATE/"key_envelopes").resolve())
    preview=json.loads(PREVIEW.read_text(encoding="utf-8"))
    market=read_record(STATE/"lanes/krx_unadjusted_v12/markets/2026-11-06.json.gz")
    require(preview["source_price_asof"]=="2026-11-05","NOV5_PREVIEW_DATE_MISMATCH")
    require(preview["research_top2_registered_for_source_session"] is False,
            "LATE_PREVIEW_NOT_ACTUALLY_REGISTERED")
    created=datetime.fromisoformat(preview["generated_at"].replace("Z","+00:00"))
    opening=datetime.fromisoformat("2026-11-06T09:00:00+09:00")
    require(created>opening,"NOV5_PREVIEW_LATE_TIMESTAMP_INVARIANT_CHANGED")
    require(len(market["rows"])==2769,"FROZEN_MARKET_ROW_COUNT_CHANGED")
    results=[]
    for r in preview["research_top2"]:
        ticker=r["ticker"]
        require(ticker in ("028050","030530"),"FROZEN_CANDIDATE_SET_CHANGED")
        plan=r["entry_plans"]["A_SUPPORT_LIMIT"]["plan"]
        require(plan and plan["decision_date"]=="2026-11-05",
                "NOV5_FROZEN_ENTRY_PLAN_INVALID")
        bar=dict(market["rows"][ticker],date="2026-11-06")
        outcomes={}
        for variant in VARIANTS:
            result,cap=model_entry(plan,bar,variant)
            outcomes[variant]=dict(
                preopen_limit=cap.get("limit"),
                preclose_gate=cap["status"],
                model_price=result.get("price"),
                model_filled=result.get("filled",False),
                model_status=result["status"],
                no_broker_fill_verification=True)
        results.append(dict(ticker=ticker,name=r["name"],
            decision_date=plan["decision_date"],
            original_high=plan["high"],original_low=plan["low"],
            structural_stop=plan["stop"],first_resistance=plan.get("resistance"),
            actual_saved_nextday_ohlc={k:bar[k] for k in
                ("date","open","high","low","close")},
            variants=outcomes))
    obj=dict(schema="C3_V4_NOV5_LATE_PREVIEW_SENSITIVITY_V1",
        price_asof="2026-11-06",
        plan_basis="2026-11-05",
        preview_generated_at=preview["generated_at"],
        preview_available_preopen=False,
        no_preopen_signal_from_archive=True,
        original_user_mock_broker_execution_not_accessed=True,
        registered_forward_signals_created=0,
        independent_regular_only_price_verified=False,
        scenarios=results,
        not_prospective_evidence=True,
        default_live_action="CASH")
    jsonout(OUT,obj)
    print("C3_V4_NOV6_CASE="+json.dumps({
        "status":"PASS","preview_preopen_available":False,
        "scenarios":[{"ticker":r["ticker"],"open":r["actual_saved_nextday_ohlc"]["open"],
            "variants":{v:dict(limit=x["preopen_limit"],filled=x["model_filled"],
                              status=x["model_status"]) for v,x in r["variants"].items()}}
            for r in results],
        "no_orders":True},ensure_ascii=False),flush=True)
    return obj

if __name__=="__main__":run()
