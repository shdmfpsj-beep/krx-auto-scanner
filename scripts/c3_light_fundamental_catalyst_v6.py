#!/usr/bin/env python3
"""C3 v6 lightweight financial / catalyst context. NOT a required entry gate.

Purpose: Early price/volume leadership can precede disclosures, so missing news
or financial coverage is NEUTRAL. No investment orders, no forward-price testing,
no use of future publications, no claims that provisional OpenDART snapshots
were independently verified.

Inputs: Oct30 frozen scan zip and v5 price-first ranked CSV (96 cases).
Outputs: human-readable TOP2 context plus full-universe CSV and JSON evidence.
"""
from __future__ import annotations
import argparse, io, json, zipfile, hashlib, csv
from pathlib import Path
from datetime import date
import pandas as pd

SCHEMA = "C3_V6_LIGHT_CONTEXT_NEUTRAL_MISSING_NO_TRADING"
ASOF = "2026-10-30"
FINANCIAL_COVERAGE_FILE = "v91_financial_pit_provisional.csv"
EVENT_FILE = "v95_event_quality_audit.csv"

def read_archive(archive_path):
    with zipfile.ZipFile(archive_path) as z:
        state=json.loads(z.read("status.json"))
        if state.get("market_data_date")!=ASOF or state.get("universe")!=2625:
            raise ValueError("SOURCE_DATE_OR_UNIVERSE_MISMATCH")
        financial=pd.read_csv(io.BytesIO(z.read(FINANCIAL_COVERAGE_FILE)),
                              dtype={"ticker":str,"available_date":str,"filing_date":str})
        events=pd.read_csv(io.BytesIO(z.read(EVENT_FILE)),
                           dtype={"ticker":str,"filing_date":str,"signal_date":str})
    return financial,events

def latest_eligible_financial(data,ticker,asof):
    """Only publicly available by evaluation date. Provisional, not PIT verified."""
    x=data[(data.ticker==ticker)&(data.available_date<=asof)&
           (data.filing_date<=asof)]
    x=x[x.validation_status=="PROVISIONAL_API_SNAPSHOT_NOT_PIT_VERIFIED"]
    if x.empty:
        return dict(financial_status="NO_COVERAGE_NEUTRAL", financial_filing_date=None,
                    financial_available_date=None,
                    revenue_yoy_pct=None, op_profit_yoy_pct=None,
                    op_margin_pct=None,debt_ratio_pct=None,
                    financial_risk_note="NOT_ASSESSED_NO_VERIFIED_RECORD")
    v=x.sort_values(["available_date","filing_date","receipt_no"]).iloc[-1]
    def num(k):
        y=pd.to_numeric(v.get(k),errors="coerce")
        return round(float(y),2) if pd.notna(y) else None
    margin=num("op_margin_pct");debt=num("debt_ratio_pct")
    risk=("PROVISIONAL_POSSIBLE_LOSS_OR_LEVERAGE_NEEDS_REVIEW" if
        (margin is not None and margin< -10) or
        (debt is not None and debt>400) else "PROVISIONAL_NO_FATAL_FLAG_OBSERVED")
    return dict(financial_status="HISTORICAL_OPEN_DART_PROVISIONAL_NEUTRAL",
                financial_filing_date=str(v.filing_date),
                financial_available_date=str(v.available_date),
                revenue_yoy_pct=num("revenue_yoy_pct"),
                op_profit_yoy_pct=num("op_profit_yoy_pct"),
                op_margin_pct=margin,debt_ratio_pct=debt,
                financial_risk_note=risk)

def catalyst_context(data,ticker,asof):
    """Historical title-only audit is NOT treated as a verified live catalyst."""
    x=data[(data.ticker==ticker)&(data.filing_date<=asof)&
           (data.signal_date<=asof)]
    if x.empty:
        return dict(catalyst_status="NO_AUDITED_CATALYST_NEUTRAL",
                    catalyst_title_only_count=0,catalyst_bonus_points=0)
    # The event collection is historical, sampled, and title-only.
    # No claim of fresh quantified guidance from these titles.
    return dict(catalyst_status="TITLE_ONLY_NOT_A_CONFIRMED_CATALYST",
                catalyst_title_only_count=len(x),catalyst_bonus_points=0)

def review_one(row,financial,events,asof=ASOF):
    if str(row["asof"])!=asof:raise ValueError("RANK_ASOF_MISMATCH")
    ticker=str(row["ticker"]).zfill(6)
    base=float(row["opportunity_score_not_probability"])
    f=latest_eligible_financial(financial,ticker,asof)
    news=catalyst_context(events,ticker,asof)
    # No negative points for unavailable, late or provisional evidence.
    # The v5 selection/rank remains intact until independently audited feeds
    # are available; manual qualitative review is separate.
    return dict(ticker=ticker,name=str(row["name"]),
        asof=asof,technical_rank_score=round(base,2),
        context_adjustment_points=0,context_adjustment_reason="UNVERIFIED_OR_MISSING_NEUTRAL",
        combined_research_score=round(base,2),
        price_priority_class=str(row["priority_class"]),
        selection_from_price_and_entry_not_headline=True,
        no_news_does_not_disqualify=True,
        late_report_never_backfilled_into_signal=True,
        **f,**news,
        independent_financial_snapshot_verified=False,
        independent_positive_news_verified=False,
        actual_investor_flow_verified=False,
        major_filing_risk_needs_separate_manual_review=True,
        buy_approved=False,orders_enabled=False)

def run(archive,ranked,outdir):
    fin,events=read_archive(archive)
    ranks=pd.read_csv(ranked,dtype={"ticker":str,"asof":str})
    required={"ticker","name","asof","opportunity_score_not_probability",
              "priority_class"}
    if not required<=set(ranks):raise ValueError("RANK_COLUMNS_MISSING")
    if len(ranks)!=96 or ranks.ticker.duplicated().any():
        raise ValueError("RANK_UNIVERSE_INVALID")
    found=[review_one(x,fin,events) for x in ranks.to_dict("records")]
    assert all(x["context_adjustment_points"]==0 for x in found)
    # Explicit retained TOP2 selection from the v5 decision model.
    chosen=[next(x for x in found if x["ticker"]==t) for t in ("271560","026960")]
    folder=Path(outdir);folder.mkdir(parents=True,exist_ok=True)
    csvfile=folder/"c3_v6_light_context_96.csv"
    with csvfile.open("w",newline="",encoding="utf-8-sig") as fh:
        writer=csv.DictWriter(fh,fieldnames=list(found[0]))
        writer.writeheader();writer.writerows(found)
    report=dict(schema=SCHEMA,source_date=ASOF,source_run_id="41051723762",
        candidate_count=len(found),top2=chosen,
        top2_unchanged_by_missing_fundamentals=True,
        total_fundamental_coverage=sum(x["financial_status"]!="NO_COVERAGE_NEUTRAL" for x in found),
        total_title_only_mentions=sum(x["catalyst_title_only_count"] for x in found),
        news_absence_not_a_hard_gate=True,
        fundamental_absence_not_a_hard_gate=True,
        severe_verified_risk_requires_manual_review=True,
        supplementary_weight_target_pct=10,
        target_weight_is_not_yet_a_calculated_scoring_model=True,
        financial_data_provisional_not_point_in_time_certified=True,
        no_historical_profitability_backtesting=True,
        prices_regular_only_certified=False,trade_approved=False,orders_enabled=False,
        result_csv_sha256=hashlib.sha256(csvfile.read_bytes()).hexdigest())
    (folder/"c3_v6_light_context_status.json").write_text(
        json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2)+"\n",
        encoding="utf-8")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--ranked",required=True)
    p.add_argument("--output",required=True)
    x=p.parse_args()
    report=run(x.input,x.ranked,x.output)
    print(json.dumps({k:v for k,v in report.items() if k!="top2"},
         ensure_ascii=False,indent=2))
    print(json.dumps(report["top2"],ensure_ascii=False,indent=2))
