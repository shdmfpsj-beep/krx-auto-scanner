#!/usr/bin/env python3
"""v6.6 forensic reproducibility + SINGLE final-bar perturbation, NO BUY.

Proven code difference: recovery uses pykrx per-ticker adjusted=True, while
v18 uses a market-wide pykrx endpoint and official KRX API matches that
market-wide feed. This identifies a divergent collection PATH but NOT whether
adjustments, source version, after-hours, or timestamp alignment caused it.

Never silently replace 120-bar candidate histories: this experiment changes
ONLY the dated last bar, leaves previous 119 potentially inconsistent and
records research setup/ATR/structure sensitivity, NOT validated signals.
"""
from __future__ import annotations
import argparse,csv,json,math
from collections import defaultdict,Counter
from datetime import date
from pathlib import Path

from forward_ledger_v63 import read_json,read_csv,verify_snapshot,digest
from source_consensus_v64 import bar_valid
from krx_official_eod_v65 import official_rows,COLLECT_SCHEMA,SCHEMA as V65_SCHEMA
from entry_strategy_v58 import evaluate,METHODS
from free_structural_v52 import history_check,atr14

SCHEMA="C3_K100_RECOVERY_SOURCE_SENSITIVITY_V66"
FIELDS=("asof","ticker","name","method",
        "recovery_provider","collection_path_recovery","collection_path_market",
        "recovery_bar_valid","official_bar_valid",
        "open_equal","high_equal","low_equal","close_equal","volume_equal",
        "v18_and_official_ohlcv_all_equal","difference_classification",
        "recovery_close","official_close","recovery_volume","official_volume",
        "close_delta_pct_of_recovery","volume_delta_pct_of_recovery",
        "archived_setup","replayed_original_setup","single_last_bar_research_setup",
        "technical_setup_changed","research_trigger_removed","research_trigger_added",
        "baseline_atr14","single_last_bar_atr14","atr14_difference",
        "baseline_stop","single_last_bar_stop","stop_difference",
        "baseline_first_reference","single_last_bar_first_reference",
        "historical_119_bars_independently_verified","regular_1530_verified",
        "adjustment_cause_verified","trade_approved","orders_enabled")

def num(value):
    try:
        if isinstance(value,bool) or value in ("",None):return None
        f=float(value)
        return f if math.isfinite(f) and f>=0 else None
    except (ValueError,TypeError):return None
def raw_bar(row,fields=("open","high","low","close","volume")):
    return {field:num(row.get(field)) for field in fields}
def diffpct(first,second):
    return round(100*(second-first)/first,4) if first is not None and first>0 and second is not None else None

def class_bar(rec,official):
    if not bar_valid(rec):return "RECOVERY_OHLCV_INVALID"
    if not bar_valid(official):return "OFFICIAL_OHLCV_INVALID"
    same={k:rec[k]==official[k] for k in ("open","high","low","close","volume")}
    if all(same.values()):return "ALL_FIVE_FIELDS_MATCH"
    if all(same[k] for k in ("open","high","low")) and not same["close"]:
        return "OHL_EQUAL_CLOSE_DIVERGENT"
    if same["close"] and not all(same.values()):
        return "CLOSE_EQUAL_OTHER_FIELDS_DIVERGENT"
    return "MULTIPLE_OHLC_FIELDS_DIVERGENT"

def group_history(history,asof):
    out=defaultdict(list)
    for r in history:
        if r.get("date") is None:raise ValueError("RECOVERY_HISTORY_DATE_MISSING")
        out[r["ticker"]].append(r)
    for ticker,items in out.items():
        if len(items)<80 or items[-1]["date"]!=str(asof):
            raise ValueError("RECOVERY_HISTORY_LENGTH_OR_DATE_INVALID")
    return out

def analysis(recovery,freeze,v58,v64,v65,official_dir):
    fm=read_json(freeze/"frozen_v63_manifest.json")
    plans=read_json(freeze/"frozen_v63_signals.json")
    asof,_=verify_snapshot(fm,plans)
    rec=read_json(recovery/"status.json")
    source=read_json(v64/"source_consensus_v64_status.json")
    source_rows=read_csv(v64/"source_consensus_v64_all.csv")
    v65_result=read_json(v65/"krx_v65_source_comparison_status.json")
    collected=read_json(official_dir/"krx_v65_collect_status.json")
    all_krx=official_rows(official_dir,collected)
    candidates=read_csv(recovery/"candidates.csv")
    histories=read_csv(recovery/"candidate_daily_history_v52.csv")
    scanned=read_json(v58/"entry_strategy_v58_status.json")
    scans=read_csv(v58/"entry_strategy_v58_all.csv")
    if (rec.get("market_data_date")!=str(asof)
        or rec.get("scan_complete") is not True
        or rec.get("data_date_verified") is not True
        or fm["source_sha256"]["recovery_status"]!=digest((recovery/"status.json").read_bytes())
        or fm["source_sha256"]["recovery_history"]!=digest(
            (recovery/"candidate_daily_history_v52.csv").read_bytes())
        or source.get("asof")!=str(asof)
        or source.get("manifest_sha256")!=fm["frozen_payload_sha256"]
        or source.get("trade_approved") is not False
        or source.get("orders_enabled") is not False
        or v65_result.get("schema")!=V65_SCHEMA
        or v65_result.get("asof")!=str(asof)
        or v65_result.get("v64_frozen_manifest_sha256")!=fm["frozen_payload_sha256"]
        or v65_result.get("official_api_connected") is not True
        or collected.get("schema")!=COLLECT_SCHEMA
        or collected.get("asof")!=str(asof)
        or collected.get("official_dataset_usable") is not True
        or collected.get("independent_1530_regular_session_certified") is not False
        or collected.get("trade_approved") is not False
        or collected.get("orders_enabled") is not False
        or scanned.get("asof")!=str(asof)
        or scanned.get("trade_approved") is not False
        or scanned.get("orders_enabled") is not False
        or len(scans)!=scanned.get("evaluated_method_rows")
        or len(scans)!=len(candidates)*len(METHODS)
        or len(source_rows)!=len(candidates)
        or len(candidates)!=source.get("candidate_count")
        or len(candidates)!=v65_result.get("candidates_evaluated")):
        raise ValueError("ASOF_OR_SOURCE_CHAIN_INCOMPLETE_UNSAFE")
    if any(v65_result["official_evidence_classes"].get(k,0)!=0
           for k in ("KRX_AUTH_OR_SERVICE_NOT_CONNECTED", "OFFICIAL_TICKER_NOT_RETURNED")):
        raise ValueError("OFFICIAL_SOURCE_DATA_NOT_COMPLETE")
    market_source={r["ticker"]:r for r in source_rows}
    previous={r["ticker"]:r for r in candidates}
    baseline={(r["ticker"],r["method"]):r for r in scans}
    if (len(previous)!=len(candidates) or len(baseline)!=len(scans)
        or len(market_source)!=len(source_rows)):
        raise ValueError("DUPLICATE_SOURCE_OR_BASELINE")
    history=group_history(histories,asof)
    issues=[]
    results=[]
    for ticker,c in sorted(previous.items()):
        if ticker not in all_krx or ticker not in market_source or ticker not in history:
            raise ValueError("MISSING_RECONCILED_TICKER")
        official_market,office=all_krx[ticker]
        reference=market_source[ticker]
        orig=raw_bar(history[ticker][-1])
        from_v18={field:num(reference.get("v18_"+field))
                  for field in ("open","high","low","close","volume")}
        if (any(office[f]!=from_v18[f] for f in from_v18)
            or any(orig[f]!=num(reference.get("recovery_"+f)) for f in orig)
            or num(c["close"])!=orig["close"]):
            raise ValueError("MARKET_V18_OFFICIAL_OR_RECOVERY_BAR_DRIFT")
        if num(c["close"]) is None or num(c["close"])<=0:
            raise ValueError("INVALID_CANDIDATE_CLOSE")
        eq={field:orig[field]==office[field]
            for field in ("open","high","low","close","volume")}
        classif=class_bar(orig,office)
        perturb=[dict(bar) for bar in history[ticker]]
        perturb[-1].update({k:office[k] for k in eq})
        newcand={**c,"close":office["close"]}
        origbars,originalerror=history_check(history[ticker],ticker,asof)
        altbars,alterror=history_check(perturb,ticker,asof)
        original_atr=atr14(origbars) if origbars and not originalerror else None
        updated_atr=atr14(altbars) if altbars and not alterror else None
        if originalerror and classif!="RECOVERY_OHLCV_INVALID":
            issues.append({"ticker":ticker,"error":originalerror})
        for method in METHODS:
            frozen=baseline[(ticker,method)]
            if (frozen["trade_approved"]!="False"
                or frozen["orders_enabled"]!="False"
                or frozen["asof"]!=str(asof)
                or frozen["method"]!=method):
                raise ValueError("ARCHIVED_V58_SIGNAL_CHANGED_OR_UNSAFE")
            paired=dict(category="SOURCE_UNCERTIFIED_ASOF_V66",
                        close_equal=False)
            restored=evaluate(c,history[ticker],asof,method,paired)
            if restored["setup"]!=frozen["setup"]:
                raise ValueError("V58_REPLAY_NOT_IDENTICAL_TO_ARCHIVE")
            fresh=evaluate(newcand,perturb,asof,method,paired)
            before=frozen["setup"]=="RESEARCH_TRIGGER_CONFIRMED_ASOF"
            after=fresh["setup"]=="RESEARCH_TRIGGER_CONFIRMED_ASOF"
            stop1=num(frozen.get("stop_reference"))
            stop2=num(fresh.get("stop_reference"))
            changed=frozen["setup"]!=fresh["setup"]
            results.append(dict(
                asof=str(asof),ticker=ticker,name=c.get("name",""),
                method=method,
                recovery_provider=c.get("data_source",""),
                collection_path_recovery="pykrx.get_market_ohlcv_by_date(adjusted=True)_PER_SECURITY"
                  if c.get("data_source")=="pykrx" else "FDR_PER_SECURITY_FALLBACK",
                collection_path_market="PYKRX_MARKET_WIDE_AND_KRX_OFFICIAL_EOD",
                recovery_bar_valid=bar_valid(orig),official_bar_valid=bar_valid(office),
                **{field+"_equal":eq[field] for field in eq},
                v18_and_official_ohlcv_all_equal=True,
                difference_classification=classif,
                recovery_close=orig["close"],official_close=office["close"],
                recovery_volume=orig["volume"],official_volume=office["volume"],
                close_delta_pct_of_recovery=diffpct(orig["close"],office["close"]),
                volume_delta_pct_of_recovery=diffpct(orig["volume"],office["volume"]),
                archived_setup=frozen["setup"],replayed_original_setup=restored["setup"],
                single_last_bar_research_setup=fresh["setup"],
                technical_setup_changed=changed,
                research_trigger_removed=before and not after,
                research_trigger_added=after and not before,
                baseline_atr14=round(original_atr,4) if original_atr is not None else None,
                single_last_bar_atr14=round(updated_atr,4) if updated_atr is not None else None,
                atr14_difference=round(updated_atr-original_atr,4)
                  if updated_atr is not None and original_atr is not None else None,
                baseline_stop=stop1,single_last_bar_stop=stop2,
                stop_difference=round(stop2-stop1,4)
                  if stop1 is not None and stop2 is not None else None,
                baseline_first_reference=num(frozen.get("first_entry_reference")),
                single_last_bar_first_reference=num(fresh.get("first_entry_reference")),
                historical_119_bars_independently_verified=False,
                regular_1530_verified=False,
                adjustment_cause_verified=False,
                trade_approved=False,orders_enabled=False))
    if len(results)!=len(scans):raise ValueError("INCOMPLETE_THREE_METHOD_REPLAY")
    per_ticker={}
    for r in results:
        per_ticker.setdefault(r["ticker"],r)
    by=Counter(r["difference_classification"] for r in per_ticker.values())
    col={field:sum(not r[field+"_equal"] for r in per_ticker.values())
         for field in ("open","high","low","close","volume")}
    if any(not r["v18_and_official_ohlcv_all_equal"] for r in results):
        raise ValueError("OFFICIAL_V18_NOT_IDENTICAL_ASOF")
    report=dict(schema=SCHEMA,asof=str(asof),
        upstream_run_ids={**fm["source_run_ids"],
             "krx_official_api_collected_utc":collected["retrieval_utc"]},
        frozen_manifest_sha256=fm["frozen_payload_sha256"],
        official_market_counts=collected["official_market_rows"],
        candidates=len(per_ticker),
        evaluated_method_rows=len(results),
        recovery_mismatch_counts=col,
        five_field_classifications=dict(by),
        official_equals_v18_all_five_fields_for_all_candidates=True,
        original_v58_setup_reproduced_for_all_evaluations=True,
        archival_signals=sum(r["archived_setup"]=="RESEARCH_TRIGGER_CONFIRMED_ASOF" for r in results),
        one_final_bar_substitution_research_signals=sum(
            r["single_last_bar_research_setup"]=="RESEARCH_TRIGGER_CONFIRMED_ASOF" for r in results),
        method_setups_changed=sum(r["technical_setup_changed"] for r in results),
        original_trigger_removed=sum(r["research_trigger_removed"] for r in results),
        alternative_trigger_added=sum(r["research_trigger_added"] for r in results),
        atr14_changed_tickers=sum(
            r["atr14_difference"] is not None and abs(r["atr14_difference"])>1e-9
            for r in results if r["method"]==METHODS[0]),
        stop_references_changed_when_both_exist=sum(
            r["stop_difference"] is not None and abs(r["stop_difference"])>1e-9 for r in results),
        open_same_across_all_candidates=(col["open"]==0),
        previous_119_sessions_may_be_provider_inconsistent=True,
        official_daily_data_independently_certified_regular_1530=False,
        asof_price_disagreement_cause_resolved=False,
        afterhours_attribution_proven=False,
        adjusted_close_vs_market_endpoint_causation_proven=False,
        official_volume_profile_or_intraday_execution_verified=False,
        all_reconstructed_hypotheses_research_only=True,
        selected_universe_hindsight_bias_unresolved=True,
        final_80point_approval=False,
        trade_approved=False,orders_enabled=False,decision="CASH",
        source_diagnostics=issues,
        next_action="REPLACE_CANDIDATE_SCREENING_SOURCE_WITH_ASOF_FINGERPRINTED_KRX_OFFICIAL_BARS_THEN_BACKFILL_120_SESSIONS_AND_SESSION_AUDIT")
    return report,results

def mobile(summary):
    p=summary
    lines=["# v6.6 공식 KRX vs 종목별 복구 수집 가격 원인추적", "",
      f"기준 {p['asof']} · **CASH / 주문 0**",
      f"후보 {p['candidates']}종목 × 3방법 = {p['evaluated_method_rows']}행",
      "공식 KRX 일봉과 pykrx 시장전체 일봉은 모든 후보의 시가·고가·저가·종가·거래량이 100% 일치.",
      "종목별 복구 호출(adjusted=True)과 시장전체 호출이 다른 데이터를 생성했습니다.",
      "코드의 함수·매개변수 경로 차이는 입증되지만, 장후/수정주가 중 무엇이 원인인지는 미확인.",
      "", "| 복구자료와 공식 KRX 간 불일치 필드 | 종목수 |",
      "|---|---:|"]
    for key,val in p["recovery_mismatch_counts"].items():
        lines.append(f"| {key} | {val} |")
    lines+=["", "| 마지막 날짜 일봉만 바꿔본 민감도 (실전 신호 아님) | 개수 |",
      "|---|---:|",
      f"| 기존 연구 신호 | {p['archival_signals']} |",
      f"| 공식 일봉을 마지막 1일에만 대입한 연구 신호 | {p['one_final_bar_substitution_research_signals']} |",
      f"| 세 가지 방식 중 판정이 달라진 행 | {p['method_setups_changed']} |",
      f"| 기존 신호가 사라진 행 | {p['original_trigger_removed']} |",
      f"| 새로 생긴 가상 신호 | {p['alternative_trigger_added']} |",
      f"| ATR14 변동 종목 | {p['atr14_changed_tickers']} |",
      f"| 양쪽에서 확인된 구조손절 참고값 변동 | {p['stop_references_changed_when_both_exist']} |",
      "", "이것은 과거 119개 봉이 검증되지 않은 상태에서 마지막 1개 봉만 대체한 **민감도 실험**입니다.",
      "최종 매수/손절 추천이나 검증된 상승확률이 아니며, 원본 과거 신호는 변경하지 않았습니다.",
      "", "## Required Next Data",
      "KRX 공식 과거 120거래일 OHLCV·날짜별 보통주 종목목록·15:30 시각별 정규장 봉 및 수정주가 정책.",
      ""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    for option in ("--recovery","--freeze","--v58","--v64","--v65","--official","--outdir"):
        p.add_argument(option,type=Path,required=True)
    a=p.parse_args()
    report,rr=analysis(a.recovery,a.freeze,a.v58,a.v64,a.v65,a.official)
    a.outdir.mkdir(parents=True,exist_ok=True)
    (a.outdir/"recovery_rootcause_v66_status.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (a.outdir/"recovery_rootcause_v66_all.csv").open(
        "w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
        w.writeheader();w.writerows(rr)
    (a.outdir/"recovery_rootcause_v66_mobile.md").write_text(
        mobile(report)+"\n",encoding="utf-8")
    print("V66_REPRODUCIBLE_PRICE_PATH",
        json.dumps({key:report[key] for key in (
         "asof","candidates","recovery_mismatch_counts","archival_signals",
         "one_final_bar_substitution_research_signals","method_setups_changed",
         "atr14_changed_tickers","decision")},ensure_ascii=False))
if __name__=="__main__":main()
