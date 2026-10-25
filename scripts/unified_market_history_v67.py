#!/usr/bin/env python3
"""v6.7 full-history source consistency research (never executable signals).

Uses completed market-WIDE pykrx v18 OHLCV on each of the SAME 120 session
dates for every selected recovery candidate. Latest day must equal the
approved official KRX EOD across all five price-volume dimensions.
This is NOT the official 120-day history and NOT regular-15:30 certification.
Unusable historical OHLCV is PENDING, never filled with synthetic bars.
"""
from __future__ import annotations
import argparse,csv,json,math
from collections import Counter,defaultdict
from datetime import date
from pathlib import Path
from entry_strategy_v58 import evaluate,METHODS
from free_structural_v52 import history_check,atr14
from forward_ledger_v63 import read_csv,read_json,verify_snapshot,digest
from krx_official_eod_v65 import COLLECT_SCHEMA,official_rows

SCHEMA="C3_K100_UNIFORM_MARKET_WIDE_120BAR_SENSITIVITY_V67"
FIELDS=("asof","ticker","name","method","historical_provider_recovery",
    "old_setup","reproduced_old_setup","uniform_120bar_setup",
    "old_atr14","uniform_atr14","atr_delta",
    "old_daily_structure_stop","uniform_daily_structure_stop",
    "old_first_reference","uniform_first_reference",
    "old_second_reference","uniform_second_reference",
    "original_trigger_removed","new_uniform_trigger_added","setup_changed",
    "historic_120bar_open_mismatch","historic_120bar_high_mismatch",
    "historic_120bar_low_mismatch","historic_120bar_close_mismatch",
    "historic_120bar_volume_mismatch",
    "same_120_trading_dates","uniform_120bar_geometry_usable",
    "invalid_history_reason","latest_official_equals_marketwide_ohlcv",
    "official_120day_history_authenticated","regular_1530_session_verified",
    "independent_historic_provider_agreement","trade_approved","orders_enabled")

def n(x):
    try:
        if isinstance(x,bool) or x in ("",None):return None
        v=float(x)
        return v if math.isfinite(v) and v>=0 else None
    except (ValueError,TypeError):return None

def market_history(path,days,ticker,asof):
    if not path.is_file():return None,"MARKET_WIDE_HISTORY_TICKER_FILE_MISSING"
    data=read_csv(path)
    idx={}
    for r in data:
        d=r.get("Date")
        if not d or d in idx:raise ValueError("UNIFORM_HISTORY_DUPLICATED_DATE")
        if d>str(asof):raise ValueError("MARKET_WIDE_CONTAINS_FUTURE_DATE")
        idx[d]=r
    if any(d not in idx for d in days):
        return None,"UNIFORM_HISTORY_SESSION_MISSING"
    out=[]
    for d in days:
        row=idx[d]
        p={x:n(row[x.capitalize()]) for x in ("open","high","low","close","volume")}
        out.append(dict(ticker=ticker,date=d,**p,data_source="pykrx"))
    bars,issue=history_check(out,ticker,asof)
    return (out,None) if issue is None else (out,issue)

def analyze(recovery,v58,freeze,v18,v65_official):
    manifest=read_json(freeze/"frozen_v63_manifest.json")
    plans=read_json(freeze/"frozen_v63_signals.json")
    asof,_=verify_snapshot(manifest,plans)
    scan=read_json(recovery/"status.json")
    x=read_json(v58/"entry_strategy_v58_status.json")
    original=read_csv(v58/"entry_strategy_v58_all.csv")
    candidates=read_csv(recovery/"candidates.csv")
    histories=read_csv(recovery/"candidate_daily_history_v52.csv")
    v18stat=read_json(v18/"diagnostics/collection_status.json")
    officialstat=read_json(v65_official/"krx_v65_collect_status.json")
    if (scan.get("market_data_date")!=str(asof)
        or scan.get("scan_complete") is not True
        or scan.get("data_date_verified") is not True
        or manifest["source_sha256"].get("recovery_status")!=
           digest((recovery/"status.json").read_bytes())
        or manifest["source_sha256"].get("recovery_history")!=
           digest((recovery/"candidate_daily_history_v52.csv").read_bytes())
        or x.get("asof")!=str(asof)
        or x.get("trade_approved") is not False
        or x.get("orders_enabled") is not False
        or len(original)!=len(candidates)*len(METHODS)
        or v18stat.get("asof")!=str(asof)
        or v18stat.get("orders_enabled") is not False
        or v18stat.get("datasets",{}).get("prices",{}).get("status")!="OK"
        or officialstat.get("schema")!=COLLECT_SCHEMA
        or officialstat.get("asof")!=str(asof)
        or officialstat.get("official_dataset_usable") is not True
        or officialstat.get("independent_1530_regular_session_certified") is not False
        or officialstat.get("trade_approved") is not False
        or officialstat.get("orders_enabled") is not False):
        raise ValueError("IMMUTABLE_DATED_MARKET_SOURCE_OR_TRADE_POLICY_FAILED")
    official=official_rows(v65_official,officialstat)
    existing={(r["ticker"],r["method"]):r for r in original}
    cand={r["ticker"]:r for r in candidates}
    hs=defaultdict(list)
    for r in histories:hs[r["ticker"]].append(r)
    if len(existing)!=len(original) or len(cand)!=len(candidates) or len(hs)!=len(cand):
        raise ValueError("DUPLICATE_OR_MISSING_BASIS_UNIVERSE")
    records=[]
    same_history_tickers=0
    last_official_checks=0
    valid_histories=0
    bad_history=Counter()
    old_nonverified=Counter()
    for t,c in sorted(cand.items()):
        older=hs.get(t)
        if (not older or len(older)!=120 or older[-1]["date"]!=str(asof)
            or any(r["ticker"]!=t for r in older)):
            raise ValueError("HISTORIC_RECOVERY_120BARS_INCOMPLETE")
        original_bar,original_err=history_check(older,t,asof)
        if original_err:old_nonverified[original_err]+=1
        days=[r["date"] for r in older]
        uniform,problem=market_history(v18/"market/prices"/(t+".csv"),days,t,asof)
        if uniform is None:
            bad_history[problem]+=1
            continue
        full,fullerr=history_check(uniform,t,asof)
        if fullerr:
            problem=fullerr
            bad_history[problem]+=1
        else:
            valid_histories+=1
        if t not in official:raise ValueError("OFFICIAL_TICKER_MISSING_AT_SAME_ASOF")
        office=official[t][1]
        if (any(n(uniform[-1][f])!=office[f] for f in
                ("open","high","low","close","volume"))
            or not all(office.get(f) is not None for f in
                     ("open","high","low","close","volume"))):
            raise ValueError("LATEST_MARKET_WIDE_BAR_NOT_OFFICIAL_KRX")
        last_official_checks+=1
        neq={field:sum(n(old[field])!=n(new[field]) for old,new in
                    zip(older,uniform)) for field in
                    ("open","high","low","close","volume")}
        if all(neq[f]==0 for f in neq):same_history_tickers+=1
        newcandidate={**c,"close":office["close"],"data_source":"pykrx"}
        for method in METHODS:
            baseline=existing[(t,method)]
            if (baseline.get("trade_approved")!="False" or
                baseline.get("orders_enabled")!="False" or
                baseline.get("asof")!=str(asof)):
                raise ValueError("OLD_ARCHIVED_METHOD_TAMPERED")
            paired=dict(category="NO_INDEPENDENT_REGULAR_PROOF",
                        close_equal=False)
            old_calc=evaluate(c,older,asof,method,paired)
            if old_calc["setup"]!=baseline["setup"]:
                raise ValueError("LEGACY_METHOD_SETUP_NOT_REPRODUCIBLE")
            now_calc=evaluate(newcandidate,uniform,asof,method,paired)
            old_trigger=baseline["setup"]=="RESEARCH_TRIGGER_CONFIRMED_ASOF"
            new_trigger=now_calc["setup"]=="RESEARCH_TRIGGER_CONFIRMED_ASOF"
            atr_old=atr14(original_bar) if original_bar and not original_err else None
            atr_new=atr14(full) if full and not fullerr else None
            def val(d,key):return n(d.get(key))
            stop_old=val(baseline,"stop_reference")
            stop_new=val(now_calc,"stop_reference")
            records.append(dict(asof=str(asof),ticker=t,name=c.get("name",""),
                method=method,historical_provider_recovery=c.get("data_source",""),
                old_setup=baseline["setup"],reproduced_old_setup=old_calc["setup"],
                uniform_120bar_setup=now_calc["setup"],
                old_atr14=round(atr_old,4) if atr_old is not None else None,
                uniform_atr14=round(atr_new,4) if atr_new is not None else None,
                atr_delta=round(atr_new-atr_old,4)
                    if atr_new is not None and atr_old is not None else None,
                old_daily_structure_stop=stop_old,uniform_daily_structure_stop=stop_new,
                old_first_reference=val(baseline,"first_entry_reference"),
                uniform_first_reference=val(now_calc,"first_entry_reference"),
                old_second_reference=val(baseline,"second_entry_reference"),
                uniform_second_reference=val(now_calc,"second_entry_reference"),
                original_trigger_removed=old_trigger and not new_trigger,
                new_uniform_trigger_added=new_trigger and not old_trigger,
                setup_changed=(baseline["setup"]!=now_calc["setup"]),
                **{"historic_120bar_"+f+"_mismatch":neq[f] for f in neq},
                same_120_trading_dates=True,uniform_120bar_geometry_usable=(fullerr is None),
                invalid_history_reason=problem or "",latest_official_equals_marketwide_ohlcv=True,
                official_120day_history_authenticated=False,
                regular_1530_session_verified=False,
                independent_historic_provider_agreement=False,
                trade_approved=False,orders_enabled=False))
    if last_official_checks!=len(candidates) or len(records)!=len(original):
        raise ValueError("TOTAL_CANDIDATE_MARKET_HISTORY_DATA_MISSING")
    per={x["ticker"]:x for x in records}
    fields=("open","high","low","close","volume")
    counts={f:sum(x["historic_120bar_"+f+"_mismatch"] for x in per.values())
            for f in fields}
    old_trigger=sum(r["old_setup"]=="RESEARCH_TRIGGER_CONFIRMED_ASOF" for r in records)
    new_trigger=sum(r["uniform_120bar_setup"]=="RESEARCH_TRIGGER_CONFIRMED_ASOF" for r in records)
    report=dict(schema=SCHEMA,asof=str(asof),
        fixed_recovery_run=manifest["source_run_ids"]["recovery_run_id"],
        fixed_v58_run=manifest["source_run_ids"]["v58_run_id"],
        frozen_manifest_sha256=manifest["frozen_payload_sha256"],
        source_market_wide_v18_asof=v18stat["asof"],
        official_krx_eod_count=officialstat["official_market_rows"],
        selected_recovery_tickers=len(candidates),
        market_history_session_days_per_ticker=120,
        aligned_tickers=len(per),
        full_120_session_valid_stock_count=valid_histories,
        full_120_session_invalid_stock_count=len(per)-valid_histories,
        invalid_history_reasons=dict(bad_history),
        recovery_history_invalid_reasons=dict(old_nonverified),
        historic_daily_ohlcv_mismatched_rows=counts,
        tickers_with_any_120day_field_difference=len(per)-same_history_tickers,
        newest_day_v18_official_ohlcv_all_82_match=(last_official_checks==len(candidates)),
        analysis_method_rows=len(records),
        original_technical_trigger_count=old_trigger,
        single_source_uniform_trigger_count=new_trigger,
        changed_technical_method_setups=sum(x["setup_changed"] for x in records),
        removed_original_triggers=sum(x["original_trigger_removed"] for x in records),
        newly_rebuilt_research_triggers=sum(x["new_uniform_trigger_added"] for x in records),
        old_method_replay_matches_archive=True,
        reconstructed_history_not_fully_official_api_authenticated=True,
        official_daily_api_regular_1530_certified=False,
        historic_raw_ohlcv_not_independent_feed_certified=True,
        full_asof_market_point_in_time_stock_universe_verified=False,
        frozen_old_signals_must_remain_immutable=True,
        final_80_score_verified=False,
        trade_approved=False,orders_enabled=False,decision="CASH",
        note="All 120 completed market-wide bars come from one v18 pykrx endpoint; only last date cross-checked against official KRX EOD. No provider-adjustment causality proof.")
    return report,records

def mobile(report):
    r=report
    lines=["# v6.7 120일 전체 가격출처 일원화 민감도 검증", "",
      f"기준 {r['asof']} · **CASH / 주문 0**", "",
      f"후보 {r['selected_recovery_tickers']}종목 × 120거래일, 방법별 {r['analysis_method_rows']}개 평가",
      f"단일 pykrx 시장전체 출처로 120일 유효 이력 확보: {r['full_120_session_valid_stock_count']}종목",
      f"기존 120일 이력과 필드 1개라도 달랐던 종목: {r['tickers_with_any_120day_field_difference']}종목",
      "", "| 120일 전체 원본 가격 차이 | 봉 수 |","|---|---:|"]
    for f,x in r["historic_daily_ohlcv_mismatched_rows"].items():
        lines.append(f"| {f} | {x} |")
    lines +=["","| 매매방법 연구 민감도 | 건수 |","|---|---:|",
      f"| 이전 기술 신호 | {r['original_technical_trigger_count']} |",
      f"| 동일 출처 120일로 재구성한 신호 | {r['single_source_uniform_trigger_count']} |",
      f"| 판정 변경된 방법별 시나리오 | {r['changed_technical_method_setups']} |",
      f"| 사라진 기존 신호 | {r['removed_original_triggers']} |",
      f"| 새로 나타난 연구 신호 | {r['newly_rebuilt_research_triggers']} |",
      "", "### 검증의 한계",
      "모든 역사적 시장전체 가격이 공식 KRX Open API로 독립 인증된 것은 아닙니다.",
      "가장 마지막 하루만 공식 KRX EOD와 시고저종거래량이 모두 같았습니다.",
      "우선주/ETF·실제 수급과 날짜별 전체시장 PIT·정규장 15:30 세션은 미검증입니다.",
      "기존 frozen 신호와 보유주·매수·손절 결정을 자동 교체하지 않습니다.",
      "", "## Required Next Data",
      "공식 KRX 120거래일 응답 원본 및 명시적 정규장 15:30 세션 증빙; 공시·거래정지·종목분류 PIT와 실측 거래대금.",
      ""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    for n in ("--recovery","--v58","--freeze","--v18","--official","--outdir"):
        p.add_argument(n,type=Path,required=True)
    args=p.parse_args()
    report,rr=analyze(args.recovery,args.v58,args.freeze,args.v18,args.official)
    args.outdir.mkdir(parents=True,exist_ok=True)
    (args.outdir/"uniform_history_v67_status.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (args.outdir/"uniform_history_v67_all.csv").open(
        "w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
        w.writeheader();w.writerows(rr)
    (args.outdir/"uniform_history_v67_mobile.md").write_text(
        mobile(report)+"\n",encoding="utf-8")
    print("V67_FULL_MARKET_120_DAY_SENSITIVITY",
          json.dumps({k:report[k] for k in (
            "asof","selected_recovery_tickers","full_120_session_valid_stock_count",
            "tickers_with_any_120day_field_difference",
            "original_technical_trigger_count","single_source_uniform_trigger_count",
            "changed_technical_method_setups","decision")},ensure_ascii=False))
if __name__=="__main__":main()
