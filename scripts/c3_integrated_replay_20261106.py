#!/usr/bin/env python3
"""C3 November 6, 2026 integrated read-only audit.

Combines archived entire-market data, sealed A/B decisions, dated 11/05
(retrospective) levels, user's stated pre-open mock limit orders,
V2 execution, V3 pending exits, original two-photo hash receipts and schedule
time order. Refuses to certify an unverified regular-only KRX price session.

No signal registration, no brokerage API, no sendMediaGroup, no new receipts,
no retroactive forward ledger writes, no prospective trade recommendations.
"""
from __future__ import annotations

import collections
import copy
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path

from PIL import Image

from c3_data_quality_v17 import classify_bar
from c3_forward_ledger_v8 import read_record, signal_id, hash_value
from c3_entry_v2_preopen import entry
from c3_exit_v3_close_confirmed import exit_strategy, POLICIES
from c3_classic_theme import create_cards, validate_bars
from c3_report_context import attach_context, publication_ok
from c3_telegram_notify import ReceiptStore, delivery_key, validate_photos

DAY="2026-11-06"
EXPECTED={"028050":("삼성E&A",60500,59600,62300,58300),
          "030530":("원익홀딩스",28300,23450,29200,23450)}
OUT=Path("/tmp/c3-integrated-20261106")
LANE=Path("state/reports/c3_forward_v8/lanes/krx_unadjusted_v12")
INPUT=Path("state/reports/c3_forward_v8/latest.json")
PREVIEW=Path("preview/reports/c3_forward_v8/latest.json")
OPERATIONS=Path("reports/c3_operations_v18_20261107/execution_evidence.json")
DELIVERY=Path("delivery/receipts")
KEY="final/2026-11-06-0289a5f01e43a4ed"
CARD_NAMES={"028050":"028050_integrated.png","030530":"030530_integrated.png"}
ORDER_SPECS=[
    dict(ticker="028050",limit=63500,budget=2500000),
    dict(ticker="028050",limit=60700,budget=2500000),
    dict(ticker="030530",limit=23500,budget=2500000),
]


def require(condition,reason):
    if not condition:raise ValueError(reason)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+"\n",
                    encoding="utf-8")


def iso(s):
    d=datetime.fromisoformat(s.replace("Z","+00:00"))
    require(d.tzinfo is not None,"NAIVE_SOURCE_TIME")
    return d


def at_kst(s):
    from zoneinfo import ZoneInfo
    return iso(s).astimezone(ZoneInfo("Asia/Seoul")).isoformat()


class OfflineReceiptGithub:
    """Read-only fake of GitHub's file path accessor; no write methods."""
    def file(self,path,ref,missing_ok=False):
        require(ref=="delivery/c3-top2-telegram","WRONG_RECEIPT_REF")
        p=Path("delivery")/path
        if not p.is_file():
            if missing_ok:return None
            raise ValueError("MISSING_DELIVERY_RECEIPT")
        return p.read_bytes()
    def api(self,path,missing_ok=False):
        require(path=="git/ref/heads/delivery/c3-top2-telegram" and
                (DELIVERY/"STORE_V1.json").is_file(),
                "RECEIPT_STORE_BRANCH_MISSING")
        return {"ref":"refs/heads/delivery/c3-top2-telegram"}


def previous_research_preview():
    p=read_json(PREVIEW)
    require(p.get("source_price_asof")=="2026-11-05","WRONG_PREVIEW_SOURCE_DAY")
    require(p.get("research_top2_registered_for_source_session") is False,
            "RETROSPECTIVE_PREVIEW_MISCLASSIFIED_REGISTERED")
    require([r["ticker"] for r in p["research_top2"]]==list(EXPECTED),
            "PREVIEW_SELECTION_CHANGED")
    open_time=iso("2026-11-06T09:00:00+09:00")
    publication=iso(p["generated_at"])
    require(publication>open_time,"RETROSPECTIVE_PUBLICATION_TIMESTAMP_CHANGED")
    return p, dict(
        study_source_day="2026-11-05",
        study_publication_kst=at_kst(p["generated_at"]),
        next_market_open_kst="2026-11-06T09:00:00+09:00",
        published_before_open=False,
        user_reported_preopen_mock_order=True,
        independent_broker_order_timestamp_available=False,
        eligible_as_automatically_registered_forward_signal=False,
        label="RETROSPECTIVE_PRICE_RULE_TEST_NOT_CERTIFIED_EX_ANTE")


def immutable_source(original):
    require(bool(os.environ.get("KRX_AUTH_KEY")),
            "OWNER_ENCRYPTED_RECORD_READ_ACCESS_MISSING")
    os.environ["C3_KEY_ENVELOPES_DIR"]=str(
        Path("state/reports/c3_forward_v8/key_envelopes").resolve())
    record=read_record(LANE/"markets/2026-11-06.json.gz")
    decision=read_record(LANE/"decisions/2026-11-06.json")
    require(record["asof"]==DAY and len(record["rows"])==2769,
            "ENCRYPTED_FULL_MARKET_DAY_OR_COUNT_MISMATCH")
    require(len(record["indices"])==2 and
            set(record["indices"])=={"KOSPI","KOSDAQ"},"MISSING_BENCHMARK")
    require(record["source"]["price_basis"]=="UNADJUSTED_AS_TRADED",
            "FROZEN_PRICE_UNIT_NOT_UNADJUSTED")
    if record["source"].get("provider")!="FINANCEDATA_KRX_CACHE":
        print("C3_SOURCE_PROVENANCE_DIAGNOSTIC="+json.dumps({
            "encrypted_market_provider":record["source"].get("provider"),
            "report_provider":original["source_provider"],
            "source_meta_fieldnames":sorted(record["source"]),
            "source_scope":record["source"].get("source_scope"),
            "underlying_provider":record["source"].get("underlying_provider"),
            "price_basis":record["source"].get("price_basis"),
            "source_asof":record["asof"],
        },ensure_ascii=False),flush=True)
    # The immutable market records the collection wrapper as provider and
    # its finance-data/KRX origin as underlying_provider. The mobile report
    # shows the latter; never compare the two at the same provenance layer.
    require(record["source"]["provider"]=="C3_KRX_UNADJUSTED_SUPPLY_V12" and
            record["source"].get("underlying_provider")==original["source_provider"],
            "FROZEN_WRAPPER_OR_UNDERLYING_PROVIDER_DIFFERENCE")
    require(original["source_price_asof"]==DAY and
            original["source_provider"]=="FINANCEDATA_KRX_CACHE",
            "REPORT_SOURCE_DISAGREES_WITH_MARKET")
    require(original["source_regular_only_certified"] is False,
            "INVALID_CLAIM_OF_REGULAR_ONLY_CERTIFICATION")
    qualities=collections.Counter(classify_bar(x) for x in record["rows"].values())
    require(qualities=={"VALID_TRADED_BAR":2659,"NO_TRADES_OBSERVED":110},
            "PRICE_FIELD_INTEGRITY_OR_BAR_COUNTS_DIFFER")
    board=collections.Counter(p["market"] for p in record["rows"].values())
    require(board=={"KOSPI":938,"KOSDAQ":1831},
            "ORIGINAL_KOSPI_KOSDAQ_COVERAGE_DIFFER")
    require(len(set(record["rows"]))==2769,"DUPLICATE_TICKERS_IN_UNIQUE_PRICE_MAP")
    require(all(x["date"]==DAY for x in record["rows"].values()),
            "MIXED_PRICE_SOURCE_DATES")
    require(sum(board.values())==original["current_scope"]["price_rows"],
            "PUBLISHED_SCOPE_ROWS_NOT_MATCHING_IMMUTABLE_MARKET")
    require(original["current_scope"]["analysis_eligible"]==1986,
            "ANALYSIS_ELIGIBLE_COUNT_CHANGED")
    require(original["current_scope"]["a_candidates"]==100 and
            original["current_scope"]["b_candidates"]==93,
            "NOV6_RESEARCH_POOLS_CHANGED")
    models=decision["models"]
    require(set(models)=={"A","B"} and
            len(models["A"])==len(models["B"])==2,
            "NOV6_EXPECTED_A_B_FOUR_RECORDS")
    require(decision["price_asof"]==DAY,"WRONG_REGISTERED_DECISION_SESSION")
    require(original["performance"]["registered_signals"]==4 and
            original["performance"]["unique_registered_tickers"]==2,
            "FROZEN_FORWARD_SIGNAL_COUNT_CHANGED")
    require(original["new_registered_signals"]==0 and
            original["research_top2_registered_for_source_session"] is True,
            "LATER_REPORT_REQUIRES_NO_NEW_REGISTRATION")
    require(original["orders_enabled"] is False and
            original["current_action"]=="CASH",
            "UNEXPECTED_REAL_TRADE_AUTHORIZATION")
    require([x["ticker"] for x in models["B"]]==list(EXPECTED),
            "REGISTERED_B_SELECTION_DIFFERENCE")
    matched={}
    for model,items in models.items():
        for position,pick in enumerate(items,1):
            ticker=pick["ticker"]
            require(pick["signal_id"]==signal_id(DAY,model,ticker),
                    "IMMUTABLE_SIGNAL_ID_NOT_REPRODUCED")
            require(pick["model"]==model and pick["rank"]==position,
                    "IMMUTABLE_RANK_OR_MODEL_DIFFERENCE")
            if model=="B":
                published=next((x for x in original["research_top2"]
                                if x["ticker"]==ticker),None)
                require(published is not None and
                        all(pick.get(k)==published.get(k) for k in
                            ("ticker","signal_id","rank","reference_close","entry_plans")),
                        "LATEST_REPORT_AND_REGISTERED_B_DECISION_DIFFER")
                raw=record["rows"][ticker]
                name,close,op,hi,lo=EXPECTED[ticker]
                require(pick["name"]==name and
                        (raw["open"],raw["high"],raw["low"],raw["close"])==
                        (op,hi,lo,close),"TICKER_DATED_OHLC_PRICE_MISMATCH")
                chart=validate_bars(pick["chart_bars"],DAY,close)
                require(len(chart)>=60,"LESS_THAN_60_ACTUAL_CHART_SESSIONS")
                require(all(b["date"]<=DAY for b in chart),"CHART_HAS_FUTURE_BAR")
                require(chart[-1]["date"]==DAY and
                        chart[-1]["close"]==raw["close"] and
                        chart[-1]["open"]==raw["open"],"CHART_AND_PRICE_DIVERGED")
                matched[ticker]=dict(ticker=ticker,name=name,close=close,
                    open=op,high=hi,low=lo,chart_bars=len(chart),
                    moving_averages={
                        str(n):float(sum((Decimal(str(b["close"]))
                            for b in chart[-n:]),Decimal(0))/Decimal(n))
                        for n in (5,20,60)})
    return record,decision,matched,dict(
        market_count=len(record["rows"]),
        market_counts=dict(board),
        bar_quality_counts=dict(qualities),
        quality_gate=original["source_quality_gate"]["status"],
        validated_ohlc_field_counts=True,
        source_price_basis=record["source"]["price_basis"],
        original_market_received_kst=at_kst(record["source"]["received_at"]),
        immutable_decision_fingerprint=hash_value(decision),
        official_regular_only_session_certified=False,
        completeness_of_independent_listing_census_certified=False,
        original_signals_replayed_exactly=4,
        no_signal_registration_attempted=True,
        screen_status="RESEARCH_VALIDATED_NOT_EXECUTION_CERTIFIED")


def verify_external_limitations(ops,market):
    fact=ops["actual_data"]
    require(fact["asof"]==DAY and fact["quality"]["status"]=="QUALITY_GATE_PASSED",
            "OPERATIONS_AUDIT_SOURCE_DATE_OR_STATUS_CHANGED")
    require(fact["bar_states"]=={"VALID_TRADED_BAR":2659,
                                    "NO_TRADES_OBSERVED":110},
            "OPERATIONS_AUDIT_NOT_MATCHING_RAW_SOURCE")
    require(fact["original_session_contract"]["regular_input_allowed"] is False,
            "UNEXPECTED_REGULAR_ONLY_APPROVAL")
    require(fact["official_status"]=="OFFICIAL_MARKETS_NOT_COMPLETE",
            "OFFICIAL_STATUS_CHANGED_NEEDS_REVIEW")
    require(fact["full_current_listing_census_independently_verified"] is False,
            "UNEXPECTED_CERTIFIED_CENSUS")
    nov6=[d for d in fact["official_response_diagnostics"] if d["asof"]==DAY]
    require(len(nov6)==2 and all(x["http_status"]==200 and
                                 x["outblock_rows"]==0 for x in nov6),
            "NOV6_DIRECT_KRX_RESPONSES_DIFFER")
    require(fact["earlier_official_control"]["rows"]==2769 and
            fact["earlier_official_control"]["asof"]=="2026-11-05",
            "NOV5_OFFICIAL_CONTROL_CHANGED")
    return dict(official_nov6_response_rows={x["market"]:x["outblock_rows"]
            for x in nov6},nov5_official_control_rows=2769,
            original_snapshot_sha256=fact["original_snapshot_sha256"],
            documented_source=record_string(fact["original_session_contract"]["source_table"]),
            regular_only_price_volume_turnover_verified=False,
            official_2026_11_06_listing_census_verified=False,
            alternative_source_substituted=False,
            overall_price_approval="RESEARCH_FIELDS_PASS_BUT_REGULAR_ONLY_AND_LISTING_CENSUS_FAIL")


def record_string(s):
    require(isinstance(s,str) and bool(s),"EMPTY_SOURCE_DOCUMENTATION")
    return s


def order_replay(preview,market):
    by_ticker={r["ticker"]:r for r in preview["research_top2"]}
    row_results={}
    expected_qty=[39,41,106]
    orders=[]
    for index,spec in enumerate(ORDER_SPECS):
        ticker=spec["ticker"]
        ref=by_ticker[ticker]
        plan=ref["entry_plans"]["A_SUPPORT_LIMIT"]["plan"]
        require(plan and plan["decision_date"]=="2026-11-05",
                "FROZEN_NEXT_SESSION_PLAN_NOT_2026_11_05")
        require(plan["low"]<=spec["limit"]<=plan["high"],
                "USER_LIMIT_OUTSIDE_RESEARCH_PLAN")
        raw=market["rows"][ticker]
        nextday=dict(raw,date=DAY)
        model=entry(plan,nextday,"RESTING_ONE")
        require(model["filled"] and
                model["individual_fills"][0]["price"]==raw["open"] and
                raw["open"]<=spec["limit"],"PREOPEN_LIMIT_MODEL_NOT_OPEN_FILL")
        n=int(Decimal(spec["budget"])/Decimal(spec["limit"]))
        require(n==expected_qty[index],"ORDER_QUANTITY_FROM_LIMIT_NOT_REPRODUCED")
        notional=n*int(model["price"])
        require(n*spec["limit"]<=spec["budget"],
                "LIMIT_ORDER_SPENDS_MORE_THAN_BUDGET")
        orders.append(dict(ticker=ticker,method="PREOPEN_ONE_SESSION_BUY_LIMIT",
                user_reported_limit=spec["limit"],budget_krw=spec["budget"],
                max_whole_shares_at_order_limit=n,model_open_fill=model["price"],
                gross_paid_if_filled_krw=notional,
                fill_status="MECHANICAL_MODEL_FILL_NOT_A_BROKER_EXECUTION_PROOF",
                buy_order_timestamp_source="USER_REPORTED_PRE_OPEN_UNVERIFIED"))
        row_results.setdefault(ticker,[]).append((n,model))
    require([q[0] for q in row_results["028050"]]==[39,41] and
            row_results["030530"][0][0]==106,"USER_POSITION_QUANTITIES_DO_NOT_RECONCILE")
    total_qty={"028050":80,"030530":106}
    notional_by={t:sum(n*m["price"] for n,m in rows)
        for t,rows in row_results.items()}
    require(notional_by=={"028050":4768000,"030530":2485700},
            "GROSS_COSTS_DISAGREE_WITH_USER_SCREENSHOT")
    sum_n=sum(notional_by.values())
    require(sum_n==7253700,"ORIGINAL_COST_7253700_NOT_REPRODUCED")
    require(10000000-sum_n==2746300,"AVAILABLE_CASH_NOT_REPRODUCED")
    source_valuation={t:total_qty[t]*market["rows"][t]["close"]
            for t in total_qty}
    require(sum(source_valuation.values())==7839800,
            "CACHED_SOURCE_CLOSING_VALUE_NOT_REPRODUCED")
    source_pnl=sum(source_valuation.values())-sum_n
    require(source_pnl==586100,"CACHED_SOURCE_GROSS_PNL_NOT_REPRODUCED")
    screenshot_current={"028050":61300,"030530":28800}
    screenshot_value=sum(total_qty[t]*screenshot_current[t] for t in total_qty)
    require(screenshot_value==7956800,"USER_SCREENSHOT_VALUATION_NOT_REPRODUCED")
    shown_net=633977
    implied_difference=screenshot_value-sum_n-shown_net
    require(implied_difference==69123,"SCREENSHOT_IMPLIED_COST_BRIDGE_DIFFERENCE")
    variant_diagnostics={}
    for ticker in EXPECTED:
        p=by_ticker[ticker]["entry_plans"]["A_SUPPORT_LIMIT"]["plan"]
        today=dict(market["rows"][ticker],date=DAY)
        variants={v:entry(p,today,v) for v in
                    ("LEGACY_GAP_VETO","RESTING_ONE","RESTING_TWO","POST_OPEN_REVIEW")}
        if ticker=="028050":
            require(not variants["LEGACY_GAP_VETO"]["filled"] and
                    variants["LEGACY_GAP_VETO"]["status"]=="OPEN_BELOW_BUDGET",
                    "LEGACY_GAP_VETO_SAMSUNG_NOT_REPRODUCED")
            require(variants["RESTING_TWO"]["fill_count"]==2 and
                    variants["RESTING_TWO"]["price"]==59600,
                    "SAMSUNG_SAME_OPEN_TWO_LIMIT_FILLS_NOT_REPRODUCED")
        else:
            require(variants["LEGACY_GAP_VETO"]["filled"] and
                    variants["RESTING_TWO"]["fill_count"]==1,
                    "WONIK_ONLY_UPPER_LIMIT_FILLED_DIFFERENCE")
        require(variants["POST_OPEN_REVIEW"]["status"]==
                "INTRADAY_SEQUENCE_UNOBSERVED",
                "INTRADAY_CONFIRMATION_WRONGLY_INFERRED_FROM_OHLC")
        variant_diagnostics[ticker]={
            v:dict(status=z["status"],filled=z["filled"],
                   hypothetical_fill_price=z.get("price"),
                   limit_orders_model_filled=z.get("fill_count"))
            for v,z in variants.items()}
    return dict(
        initial_capital_krw=10000000,
        user_reported_three_buy_limits=orders,
        quantity_by_ticker=total_qty,
        hypothetical_gross_paid_by_ticker_krw=notional_by,
        hypothetical_total_gross_cost_krw=sum_n,
        hypothetical_cash_left_krw=2746300,
        cached_source_last_price_val_krw=source_valuation,
        cached_source_gross_pnl_krw=source_pnl,
        cached_source_gross_pnl_as_pct_of_initial_cash=round(source_pnl/10000000*100,4),
        cached_source_close_regular_only_certified=False,
        user_reported_screen_price_krw=screenshot_current,
        user_reported_screen_total_market_value_krw=screenshot_value,
        user_reported_screen_net_pnl_krw=shown_net,
        user_reported_screen_net_pnl_pct_initial=round(shown_net/10000000*100,5),
        fee_and_valuation_bridge_implied_krw=implied_difference,
        exact_broker_fees_verified=False,
        broker_fills_not_independently_verified=True,
        preopen_publication_not_verified=True,
        engine_entry_variants=variant_diagnostics,
        all_orders_good_until="NOV6_ONLY",
        reusing_plan_on_nov9_without_refreezing=False,
        order_routing_executed=False)


def forward_and_exit_assessment(latest,preview,market):
    # Nov 6's registered B-signal is a distinct thing from the 11/05
    # unregistered plan whose Nov 6 opening execution is reconstructed above.
    counts={}
    for model in ("A","B"):
        for h in ("5","10","20"):
            performance=latest["performance"]["selection"][model][h]
            require(performance["completed_nonoverlap"]==0,
                    "FORWARD_SELECTION_NOT_MATURED_AS_OF_NOV6")
            counts[f"{model}_{h}"]=performance["completed_nonoverlap"]
    require(latest["performance"]["actual_broker_fills"]==0,
            "LIVE_LEDGER_HAS_BROKER_FILLS")
    require(latest["performance"]["paper"]["B"]["A_SUPPORT_LIMIT"]["5"]
            ["status_counts"].get("PENDING_NEXT_SESSION")==2,
            "ORIGINAL_NOV6_B_NEXT_SESSION_NOT_PENDING")
    previews={}
    by={x["ticker"]:x for x in preview["research_top2"]}
    for ticker in EXPECTED:
        p=by[ticker]["entry_plans"]["A_SUPPORT_LIMIT"]["plan"]
        b=market["rows"][ticker]
        ent=entry(p,dict(b,date=DAY),"RESTING_ONE")
        variants={v:exit_strategy(p,DAY,ent,{DAY:b},[DAY],5,v)
                  for v in POLICIES}
        require(all(x["status"]=="WINDOW_NOT_MATURED" for x in variants.values()),
                "NOV6_LACKING_FUTURE_SESSIONS_WAS_INVENTED")
        previews[ticker]=dict(v3_policies=list(variants),
              known_11_06_sessions=1,matured_forward_sessions=0,
              no_5_10_20_return_can_be_attributed=True)
    return dict(A_B_registered_signals=4,
                completed_forward_sessions_for_registered_signals=counts,
                distinct_preopen_price_rule_study=previews,
                settlement_action="CASH_UNTIL_PROSPECTIVE_DATA_AVAILABLE",
                v2_v3_models_not_retroactively_promoted=True)


def render_and_delivery(latest,decision,clock):
    repo=copy.deepcopy(latest)
    top={r["ticker"]:r for r in decision["models"]["B"]}
    for r in repo["research_top2"]:
        r["chart_bars"]=top[r["ticker"]]["chart_bars"]
        r["chart_price_basis"]="KRX_UNADJUSTED_AS_TRADED"
    report=attach_context(repo,OUT,client=None)
    images=create_cards(report,OUT)
    require(len(images)==2,"INTEGRATED_RENDER_NOT_EXACTLY_TWO_IMAGES")
    checked=validate_photos(images)
    require([p.name for p in images]==[CARD_NAMES[t] for t in EXPECTED],
            "CARD_FILE_NAME_OR_ORDER_DIFFERENCE")
    claim=read_json(DELIVERY/"claims"/(KEY+".json"))
    outcome=read_json(DELIVERY/"outcomes"/(KEY+".json"))
    require(claim["card_sha256"]==checked,
            "REPLAY_CARDS_NOT_BYTE_IDENTICAL_TO_ORIGINAL_SENT_PHOTOS")
    require(claim["source_date"]==DAY and claim["source_run_id"]=="42233092127",
            "ORIGINAL_TELEGRAM_CLAIM_WRONG_SESSION")
    require(claim["automatic_resend_allowed"] is False and
            outcome["source_date"]==DAY and outcome["status"]=="DELIVERED" and
            outcome["send_attempts"]==1 and outcome["photos"]==2 and
            outcome["message_ids"]==[30,31],
            "SOURCE_TELEGRAM_DELIVERY_OUTCOME_CHANGED")
    require(outcome["captions_present"] is False and
            outcome["text_present"] is False,
            "ORIGINAL_DELIVERY_WAS_NOT_PHOTO_ONLY")
    reader=OfflineReceiptGithub()
    store=ReceiptStore(reader)
    store.initialize()
    require(store.exists(KEY) and
            delivery_key(DAY,KEY.split("-")[-1],"live")==KEY,
            "EXISTING_DELIVERY_RECEIPT_DUPLICATE_NOT_BLOCKED")
    require(clock["orig_telegram_delivered"]==outcome["recorded_at"][:19]+
            outcome["recorded_at"][19:] or
            iso(clock["orig_telegram_delivered"]).replace(microsecond=0)==
            iso(outcome["recorded_at"]).replace(microsecond=0),
            "OPS_DELIVERY_CLOCK_CONFLICT")
    return dict(photo_count=len(images),pixel_sizes=[list(Image.open(p).size) for p in images],
        render_sha256=checked,hashes_identical_to_original_send=True,
        original_outcome_status=outcome["status"],original_sent_photo_ids=outcome["message_ids"],
        captions_present=False,text_messages_sent=False,
        original_claim_is_durable=True,duplicate_resend_would_be_blocked=True,
        simulated_send_attempts=0,actual_send_attempts_this_run=0,
        chat_credentials_supplied=False,original_telegram_delivery_kst=outcome["recorded_at"])


def clock_audit(op,preview,delivered):
    d=op["schedules"]
    require(d["prior_chatgpt_started"]=="2026-11-06T22:29:07+09:00",
            "SCHEDULE_SOURCE_CHANGED")
    prior=iso(d["prior_chatgpt_started"])
    original_start=iso(d["prior_research_actual_start"])
    original_end=iso(d["prior_research_actual_end"])
    sent=iso(d["prior_telegram_delivered"])
    require(prior<original_start<original_end<sent,
            "ACTUAL_REPORT_AND_DELIVERY_ORDER_INCORRECT")
    require(iso(preview["generated_at"])>
            iso("2026-11-06T09:00:00+09:00"),
            "NOV5_REPORT_UNEXPECTEDLY_PREOPEN")
    require(d["chatgpt_delivery_status"]=="unknown",
            "UNVERIFIED_CHATGPT_DELIVERY_STATUS_CHANGED")
    return dict(chatgpt_report_started=d["prior_chatgpt_started"],
        original_c3_research_started=d["prior_research_actual_start"],
        original_c3_research_completed=d["prior_research_actual_end"],
        telegram_sent=delivered["original_telegram_delivery_kst"],
        original_chatgpt_status_at_22_30="NO_REGISTERED_SIGNALS_AVAILABLE_THEN",
        original_C3_nov6_registered_research_available_after="23:21 KST",
        chatgpt_integration_problem="REPORT_AT_22_30_BEFORE_C3_DECISION_AT_23_21",
        no_claim_chatgpt_delivered_correctly=True)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    latest=read_json(INPUT)
    preview,availability=previous_research_preview()
    op=read_json(OPERATIONS)
    market,decision,cards,price_integrity=immutable_source(latest)
    official=verify_external_limitations(op,market)
    orders=order_replay(preview,market)
    forward=forward_and_exit_assessment(latest,preview,market)
    delivered=render_and_delivery(latest,decision,
           {"orig_telegram_delivered":op["schedules"]["prior_telegram_delivered"]})
    timing=clock_audit(op,preview,delivered)
    final=dict(schema="C3_2026_11_06_FULL_INTEGRATION_READ_ONLY_V1",
      asof=DAY,
      source_snapshot_git_ref=os.environ.get("C3_FROZEN_SOURCE_REF"),
      model_hashes=dict(
        v2_entry_ref="ffb9ee44c73800adcbb6ee3bdf7067f61a35cd69",
        v3_exit_ref="433ce30b087ab7b4866a8d1622fa5f656ec051fa",
        original_engine_ref="077113ac2f5e93fecc4c47850b36e5eda2173e3d"),
      source_integrity=price_integrity,
      price_session_verification=official,
      registered_top2=cards,
      nov5_price_plan_availability=availability,
      nov6_user_mock_order_reconciliation=orders,
      v2_v3_forward_not_matured=forward,
      telegram_receipt_dry_run_only=delivered,
      report_clock=timing,
      summary_status={
         "price_ohlcv_raw_rows":"PASS",
         "official_regular_only_price_and_listing":"UNVERIFIED",
         "historical_four_A_B_registration_integrity":"PASS",
         "nov5_plan_ex_ante_publication":"FAIL_AFTER_OPEN",
         "nov6_user_mock_order_price_model":"PASS_RECONCILED_NOT_BROKER_VERIFIED",
         "v3_forward_five_ten_twenty":"NOT_MATURED",
         "two_rendered_images_match_telegram_exact":"PASS",
         "duplicate_photo_and_text_send":"NO_SEND_PROVEN",
         "chatgpt_22_30_report_clock":"FAIL_DELIVERY_BEFORE_MODEL_COMPLETE",
         "overall":"RESEARCH_REPRODUCIBLE_NOT_EXECUTION_CERTIFIED"
      },
      actions=dict(new_signals=0,original_ledger_writes=0,telegram_calls=0,
                   broker_calls=0,existing_telegram_receipts_rewritten=0,
                   main_branch_edits=0,live_policy_promoted=False),
      research_gate=dict(next_session_buy_authorized=False,
           regular_session_certified=False,
           forward_trades_completed=0,
           recommended_action="CASH"))
    write_json(OUT/"integrated_20261106_result.json",final)
    print("C3_20261106_INTEGRATED="+json.dumps({
        "status":final["summary_status"]["overall"],
        "market":final["source_integrity"]["market_count"],
        "bar_quality":final["source_integrity"]["bar_quality_counts"],
        "AB_registered":4,
        "listed":list(cards),
        "user_order_shares":orders["quantity_by_ticker"],
        "total_gross_cost":orders["hypothetical_total_gross_cost_krw"],
        "market_gross_cache_pnl":orders["cached_source_gross_pnl_krw"],
        "11_05_study_signal_preopen_available":False,
        "official_regular_only_certified":False,
        "nov6_forward_matured":0,
        "photo_hash_match":delivered["hashes_identical_to_original_send"],
        "telegram_send":0,
        "report_clock_22_30_before_decision_23_21":True,
        "files":[str(OUT/"integrated_20261106_result.json"),
                 str(OUT/"028050_integrated.png"),str(OUT/"030530_integrated.png")]
    },ensure_ascii=False),flush=True)


if __name__=="__main__":main()
