#!/usr/bin/env python3
"""v6.4 per-frozen-limit source safety gate for v6.3 forward observations.

Links exactly dated SHA-frozen hypotheses to complete source-disagreement
roster. Conflicted/invalid bars are explicitly quarantined, and even agreed
bars are not assumed to be independent KRX regular-session quotes.
Never upgrade to BUY or publish synthetic/provisional ROI as live P&L.
"""
from __future__ import annotations
import argparse,csv,json,math
from collections import Counter,defaultdict
from pathlib import Path

from forward_ledger_v63 import read_csv,read_json,verify_snapshot
from source_consensus_v64 import SCHEMA as SOURCE_SCHEMA

SCHEMA="C3_K100_FORWARD_SOURCE_GATE_V64"
FIELDS=("asof","ticker","name","method","variant",
        "frozen_research_entry","frozen_structure_stop","frozen_nearest_target",
        "recovery_close","v18_close","source_classification",
        "asof_price_conflict_or_invalid","originates_from_2_sources_agreeing",
        "independent_regular_session_certified","source_watch_status",
        "forward_observed_market_days","performance_return_withheld",
        "provisional_pre_gate_result_suppressed","net_return_pct",
        "final_score_verified","trade_approved","orders_enabled")

def gate(freeze_manifest,freeze_plans,source_status,source_rows,forward_status,forward_rows):
    asof,stamp=verify_snapshot(freeze_manifest,freeze_plans)
    if (source_status.get("schema")!=SOURCE_SCHEMA or
        source_status.get("asof")!=str(asof) or
        source_status.get("manifest_sha256")!=freeze_manifest["frozen_payload_sha256"] or
        source_status.get("trade_approved") is not False or
        source_status.get("orders_enabled") is not False or
        source_status.get("kst_regular_session_0900_1530_independently_certified") is not False or
        source_status.get("all_frozen_prices_tainted_until_certified") is not True or
        len(source_rows)!=source_status.get("candidate_count")):
        raise ValueError("SOURCE_CONSENSUS_DATE_OR_COMPLETE_FINGERPRINT_INVALID")
    if (forward_status.get("schema")!="C3_K100_FORWARD_LEDGER_V63" or
        forward_status.get("asof")!=str(asof) or
        forward_status.get("frozen_payload_sha256")!=freeze_manifest["frozen_payload_sha256"] or
        forward_status.get("trade_approved") is not False or
        forward_status.get("orders_enabled") is not False or
        forward_status.get("all_prices_regular_only_verified") is not False or
        len(forward_rows)!=forward_status.get("frozen_research_alternatives") or
        len(forward_rows)!=len(freeze_plans)):
        raise ValueError("V63_FORWARD_AND_SOURCE_DATED_RUN_UNSAFE_OR_INCOMPLETE")
    classes=Counter()
    symbols={}
    for row in source_rows:
        ticker=row.get("ticker")
        if (not isinstance(ticker,str) or len(ticker)!=6 or ticker in symbols
            or row.get("asof")!=str(asof)
            or row.get("trade_approved")!="False"
            or row.get("orders_enabled")!="False"
            or row.get("independent_regular_close_certified")!="False"):
            raise ValueError("SOURCE_AUDIT_DUPLICATED_UNSAFE_OR_DATE_MISMATCH")
        symbols[ticker]=row
        classes[row["classification"]]+=1
    if classes!=Counter(source_status.get("classifications",{})):
        raise ValueError("SOURCE_AUDIT_CLASSIFICATION_TOTAL_CHANGED")
    frozen_by_key={}
    for p in freeze_plans:
        key=(p["ticker"],p["method"],p["variant"])
        frozen_by_key[key]=p
    seen=set();out=[]
    for f in forward_rows:
        key=(f.get("ticker"),f.get("method"),f.get("variant"))
        if (key in seen or key not in frozen_by_key
            or f.get("asof")!=str(asof)
            or f.get("trade_approved")!="False"
            or f.get("orders_enabled")!="False"):
            raise ValueError("FORWARD_SIGNALS_NOT_EXACT_FROZEN_SET")
        seen.add(key)
        orig=frozen_by_key[key]
        for field,txt in (("research_entry_reference","research_entry_reference"),
                          ("daily_structure_stop_reference","daily_structure_stop_reference"),
                          ("nearest_target_repriced_reference","nearest_target_repriced_reference"),
                          ("signal_close_reference","signal_close_reference")):
            expected=orig.get(field)
            observed=f.get(txt)
            if expected is None:
                if observed not in ("",None):raise ValueError("FROZEN_PRICE_CHANGED")
            elif observed in ("",None) or abs(float(observed)-float(expected))>1e-7:
                raise ValueError("FROZEN_PRICE_CHANGED")
        src=symbols.get(key[0])
        if src is None or src.get("is_frozen_signal")!="True":
            raise ValueError("SOURCE_AUDIT_OMITS_FROZEN_TICKER")
        if key[1] not in src.get("frozen_technical_signal_methods","").split(";"):
            raise ValueError("FROZEN_TECHNICAL_METHOD_UNRECONCILED")
        source_type=src["classification"]
        agreed=source_type=="CLOSE_AGREED_SESSION_UNCERTIFIED"
        if src.get("recovery_close") not in (None,"") and (
             abs(float(src["recovery_close"])-float(orig["signal_close_reference"]))>1e-7):
            raise ValueError("FROZEN_SIGNAL_CLOSE_AND_SOURCE_DISAGREE")
        # Strict veto even if some past research job produced a provisional
        # simulated return; price origin is not session-certified.
        label=("AGREED_CLOSE_BUT_REGULAR_SESSION_UNCERTIFIED"
               if agreed else "SOURCE_CLOSE_CONFLICT_OR_INVALID_QUARANTINED")
        provisional=f.get("net_return_pct") not in (None,"")
        out.append(dict(asof=str(asof),ticker=key[0],name=orig.get("name",""),
            method=key[1],variant=key[2],
            frozen_research_entry=orig.get("research_entry_reference"),
            frozen_structure_stop=orig.get("daily_structure_stop_reference"),
            frozen_nearest_target=orig.get("nearest_target_repriced_reference"),
            recovery_close=src.get("recovery_close"),
            v18_close=src.get("v18_close"),
            source_classification=source_type,
            asof_price_conflict_or_invalid=not agreed,
            originates_from_2_sources_agreeing=agreed,
            independent_regular_session_certified=False,
            source_watch_status=label,
            forward_observed_market_days=forward_status["observed_full_market_snapshot_days"],
            performance_return_withheld=True,
            provisional_pre_gate_result_suppressed=provisional,
            net_return_pct=None,final_score_verified=False,
            trade_approved=False,orders_enabled=False))
    if len(out)!=len(freeze_plans):
        raise ValueError("FROZEN_FORWARD_PAIR_MISSING")
    reason=Counter(x["source_watch_status"] for x in out)
    report=dict(schema=SCHEMA,asof=str(asof),
        frozen_payload_sha256=freeze_manifest["frozen_payload_sha256"],
        exact_source_v18_run=source_status["provenance_run_ids"]["sector_v18_run_id"],
        frozen_alternative_count=len(out),
        frozen_distinct_tickers=len(set(x["ticker"] for x in out)),
        asof_source_conflict_or_invalid_variants=sum(x["asof_price_conflict_or_invalid"] for x in out),
        asof_source_concordant_but_uncertified_variants=sum(x["originates_from_2_sources_agreeing"] for x in out),
        categories=dict(reason),
        any_pre_gate_simulated_roi_suppressed=sum(x["provisional_pre_gate_result_suppressed"] for x in out),
        observed_forward_market_dates=forward_status["observed_future_distinct_market_dates"],
        official_regular_session_price_certified=False,
        outcome_performance_published=False,
        final_80_score_certified=False,
        trade_approved=False,orders_enabled=False,decision="CASH")
    return report,out

def mobile(r,allrows):
    lines=[
        "# v6.4 동결된 종목 가격출처 안전 검증",
        "",
        f"2026-10-23 동결기준 / **매수 0 · CASH**" if r["asof"]=="2026-10-23"
        else f"{r['asof']} 동결기준 / **매수 0 · CASH**",
        f"원본 동결 매수가 대체안 {r['frozen_alternative_count']}건",
        f"**서로 다른 종가 또는 비정상 가격으로 격리 {r['asof_source_conflict_or_invalid_variants']}건**",
        f"두 수집원의 종가가 같으나 정규장 독립검증 미완료 {r['asof_source_concordant_but_uncertified_variants']}건",
        "",
        "| 종목코드 | 1차/2차 | 복구원 종가 | v18 종가 | 근거 |",
        "|---|---|---:|---:|---|",
    ]
    for p in allrows:
        lines.append(f"| {p['ticker']} | {p['variant']} | {p['recovery_close']} | {p['v18_close']} | {p['source_watch_status']} |")
    lines.extend(["",
        "해당 보고서는 날짜별 모의 수익률을 매매 실적처럼 보여주지 않습니다.",
        "**일치한 종목도 정규장 전용 가격 출처라는 증명이 없어서 주문 미승인**입니다.",
        "",
        "## Required Next Data",
        "정규장 세션이 명확히 기록된 독립 거래소/증권사 분봉(15:30 마감), 법적 상장종류, 가격 수정사유, 5거래일 실제 완결 수익 확인.",
        ""])
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    for arg in ("--freeze","--source-audit","--forward","--outdir"):
        p.add_argument(arg,required=True,type=Path)
    q=p.parse_args()
    report,data=gate(
        read_json(q.freeze/"frozen_v63_manifest.json"),
        read_json(q.freeze/"frozen_v63_signals.json"),
        read_json(q.source_audit/"source_consensus_v64_status.json"),
        read_csv(q.source_audit/"source_consensus_v64_all.csv"),
        read_json(q.forward/"forward_v63_status.json"),
        read_csv(q.forward/"forward_v63_all.csv"))
    q.outdir.mkdir(parents=True,exist_ok=True)
    (q.outdir/"forward_source_gate_v64_status.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (q.outdir/"forward_source_gate_v64_all.csv").open(
            "w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
        w.writeheader();w.writerows(data)
    (q.outdir/"forward_source_gate_v64_mobile.md").write_text(
        mobile(report,data)+"\n",encoding="utf-8")
    print("V64_FORWARD_SOURCE_QUARANTINE",report["asof"],
          report["asof_source_conflict_or_invalid_variants"],
          report["asof_source_concordant_but_uncertified_variants"],
          report["decision"])
if __name__=="__main__":main()
