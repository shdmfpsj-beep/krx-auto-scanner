#!/usr/bin/env python3
"""Read-only reproduction of the registered 2026-11-06 C3 TOP2 research cards.

No new selections, decision writes, simulated trades, Telegram requests, or
modification of research receipts. The KRX_AUTH_KEY is used only to read a
previously sealed immutable decision on the research branch.
"""
import hashlib
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from PIL import Image

from c3_classic_theme import create_cards, notes, validate_bars
from c3_report_context import attach_context
from c3_telegram_inputs import GitHub, frozen_live_bars, report_pair

DAY = "2026-11-06"
EXPECTED = {"028050": ("삼성E&A", 60500), "030530": ("원익홀딩스", 28300)}
OUT = Path("/tmp/c3-20261106-historical-replay")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if not os.environ.get("GH_TOKEN") or not os.environ.get("KRX_AUTH_KEY"):
        raise SystemExit("READ_ONLY_SOURCE_ACCESS_NOT_AVAILABLE")

    gh = GitHub(os.environ["GH_TOKEN"])
    latest, summary, revision = report_pair(gh)
    if latest.get("source_price_asof") != DAY:
        raise ValueError("FROZEN_DAY_NOT_2026_11_06")
    if summary.get("source_price_asof") != DAY:
        raise ValueError("FROZEN_SUMMARY_DAY_MISMATCH")
    if summary.get("generated_at") != latest.get("generated_at") or summary.get("source_run_id") != latest.get("source_run_id"):
        raise ValueError("LATEST_SUMMARY_REVISION_MISMATCH")
    if latest.get("data_quality_state") != "RESEARCH_VALIDATED" or latest.get("source_provider") != "FINANCEDATA_KRX_CACHE":
        raise ValueError("HISTORICAL_SOURCE_NOT_RESEARCH_VALIDATED")
    if latest.get("source_regular_only_certified") is not False or latest.get("orders_enabled") is not False:
        raise ValueError("UNAPPROVED_SESSION_CERTIFICATION_OR_TRADE")
    if (latest.get("source_quality_gate") or {}).get("status") != "QUALITY_GATE_PASSED":
        raise ValueError("HISTORICAL_SOURCE_QUALITY_NOT_PASSED")
    if not latest.get("research_top2_registered_for_source_session"):
        raise ValueError("FROZEN_DAY_SIGNALS_NOT_REGISTERED")
    picks = latest.get("research_top2") or []
    if len(picks) != 2 or [r["ticker"] for r in picks] != ["028050", "030530"]:
        raise ValueError("REGISTERED_TOP2_IDENTITY_DIFFERENCE")
    if (latest.get("performance") or {}).get("registered_signals") != 4:
        raise ValueError("EXPECTED_FOUR_MODEL_REGISTRATIONS_NOT_PRESENT")

    # The bridge independently checks each B decision against its sealed source
    # (signal id, reference close, full entry plan, model and rank).
    report = frozen_live_bars(gh, latest, revision)
    provenance = report.get("input_provenance") or {}
    if provenance.get("price_basis") != "UNADJUSTED_AS_TRADED":
        raise ValueError("FROZEN_PRICE_BASIS_INCOMPATIBLE")

    stock_results = []
    for r in report["research_top2"]:
        ticker = r["ticker"]
        name, expected_close = EXPECTED[ticker]
        if r["name"] != name or float(r.get("reference_close",r["close"])) != expected_close:
            raise ValueError("REGISTERED_TOP2_PRICE_OR_NAME_CHANGED")
        bars = validate_bars(r["chart_bars"], DAY, expected_close)
        if not all(z["date"] <= DAY for z in bars):
            raise ValueError("FUTURE_DATE_IN_FROZEN_CANDLES")
        if not all(float(z["volume"]).is_integer() for z in bars):
            raise ValueError("FRACTIONAL_HISTORICAL_VOLUME")
        plan = ((r.get("entry_plans") or {}).get("A_SUPPORT_LIMIT") or {}).get("plan")
        if plan is None or float(plan["stop"]) >= float(plan["low"]):
            raise ValueError("MISSING_OR_INVALID_FROZEN_ENTRY_PLAN")
        independent_ma={}
        for n in (5,20,60):
            expected_ma=sum((Decimal(str(b["close"])) for b in bars[-n:]),Decimal(0))/Decimal(n)
            independent_ma[str(n)]=float(expected_ma)
        stock_results.append({
            "ticker":ticker,"name":name,"close":expected_close,
            "bars":len(bars),"last_five_sessions":[{
                k:z[k] for k in ("date","open","high","low","close","volume","turnover_krw") if k in z
            } for z in bars[-5:]],"ma_5_20_60_independent":independent_ma,
            "first_entry_low":plan["low"],"first_entry_high":plan["high"],
            "stop":plan["stop"],"resistance_1":plan.get("resistance"),
            "resistance_2":plan.get("resistance2"),
            "source_date":bars[-1]["date"]
        })

    # Curated company context is independently publication-date-filtered.
    # No live DART query is used, so no newly published fact can flow backward.
    report = attach_context(report, OUT, client=None)
    context_checks=[]
    for r in report["research_top2"]:
        paragraphs=notes(r,((r.get("entry_plans") or {}).get("A_SUPPORT_LIMIT") or {}).get("plan"))
        if len(paragraphs) != 4 or any(not v.strip() for _,v in paragraphs):
            raise ValueError("EMPTY_OR_INCOMPLETE_COMPANY_CONTEXT")
        context_checks.append({
            "ticker":r["ticker"], "section_labels":[name for name,_ in paragraphs],
            "sections":[value for _,value in paragraphs],
            "external_dart_called":False,
            "context_status":(r.get("company_context") or {}).get("dart_status")
        })

    images = create_cards(report,OUT)
    if len(images)!=2 or {p.stem.split("_")[0] for p in images}!=set(EXPECTED):
        raise ValueError("REPLAY_DID_NOT_RENDER_EXACT_TWO_CARDS")
    render=json.loads((OUT/"render_diagnostics.json").read_text())
    images_checked=[]
    for c in render["cards"]:
        stock=next(x for x in stock_results if x["ticker"]==c["ticker"])
        if c["asof"]!=DAY or c["close"]!=stock["close"]:
            raise ValueError("RENDERED_CARD_SOURCE_DAY_OR_CLOSE_MISMATCH")
        if c["source_rows"]!=stock["bars"] or c["source_rows"]<60:
            raise ValueError("RENDERED_CARD_MISSING_PRICE_HISTORY")
        for n,independent in stock["ma_5_20_60_independent"].items():
            if abs(c["ma_last"][n]-independent)>1e-7:
                raise ValueError("MOVING_AVERAGE_NOT_INDEPENDENTLY_REPRODUCED")
            path=c["geometry"]["paths"][n]
            if not path or path[-1]["date"]!=DAY or path[-1]["x"]!=c["geometry"]["last_candle_x"]:
                raise ValueError("REPLAY_MA_END_POINT_OR_DATE_INVALID")
        if c["geometry"]["endpoint_label_style"]!="STRAIGHT_PRICE_BADGE_NO_LEADER_POLYLINE":
            raise ValueError("REPLAY_HAS_BENT_PRICE_LEADER")
        path=next(p for p in images if p.name.startswith(c["ticker"]+"_"))
        with Image.open(path) as im:
            width,height=im.size
            im.verify()
        if (width,height)!=(1400,2400):
            raise ValueError("RENDERED_CARD_NOT_MOBILE_RESOLUTION")
        if sha(path.read_bytes())!=c["sha256"]:
            raise ValueError("CARD_IMAGE_HASH_MISMATCH")
        images_checked.append({"ticker":c["ticker"],"name":path.name,"sha256":c["sha256"],
                               "pixel_size":[width,height],"last_candle_and_MA_endpoints":"PASS",
                               "independent_5_20_60_MA":"PASS","no_bent_price_leader":"PASS",
                               "notes_sections":len(c["notes"])})
    manifest={
        "schema":"C3_HISTORICAL_READ_ONLY_REPLAY_V1",
        "source_session":DAY,
        "source_git_ref":revision,
        "immutable_decision_sha256":provenance.get("decision_payload_sha256"),
        "source_provider":"FINANCEDATA_KRX_CACHE",
        "source_quality_state":"RESEARCH_VALIDATED",
        "regular_only_independently_certified":False,
        "full_market_coverage_independently_certified":False,
        "latest_report_new_signal_count":latest.get("new_registered_signals"),
        "historical_unique_registered_tickers":2,
        "historical_A_B_model_registered_records":4,
        "stock_results":stock_results,
        "context_review":context_checks,
        "rendered_images":images_checked,
        "trading_actions":0,"telegram_sends":0,
        "outcome":"HISTORICAL_REPLAY_RENDERED_WITH_RESEARCH_ONLY_PROVENANCE",
        "future_5_10_20_return_samples_complete":0
    }
    (OUT/"historical_replay_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    print("C3_HISTORICAL_REPLAY_20261106="+json.dumps({
        "status":"PASS","asof":DAY,"source_rows":(latest.get("current_scope") or {}).get("price_rows"),
        "research_top2":[{"ticker":r["ticker"],"close":r["close"],
                           "ma":r["ma_5_20_60_independent"]} for r in stock_results],
        "images":len(images_checked),"telegram_sends":0,
        "new_signals_registered":0,"source_session_certified":False
    },ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
