#!/usr/bin/env python3
"""v6.4 source reconciliation, not KRX regular-session authentication.

For an as-of date, compare frozen v6.3 trading hypotheses, KRX recovery
raw OHLC, and v18 full-market same-day OHLC by exact security code/date.
Keep every discrepancy and malformed bar. Matching two providers DOES NOT
prove that either is KRX regular 09:00-15:30 or a truly independent feed.
No replacement of prices, backfilled BUY, or inferred winning returns.
"""
from __future__ import annotations

import argparse,csv,hashlib,json,math,re
from collections import Counter
from datetime import date
from pathlib import Path
from forward_ledger_v63 import read_json,read_csv,verify_snapshot,parse_date,parse_utc,digest

SCHEMA="C3_K100_SOURCE_CONSENSUS_V64"
MARKETS=("KOSPI","KOSDAQ")
SOURCE_REQUIRED=("ticker","Date","Open","High","Low","Close","Volume","TurnoverKRW")
FIELDS=("asof","ticker","name","market","is_frozen_signal",
        "frozen_technical_signal_methods","recovery_instrument_type",
        "recovery_traded_value_origin",
        "recovery_open","recovery_high","recovery_low","recovery_close","recovery_volume",
        "v18_open","v18_high","v18_low","v18_close","v18_volume","v18_turnover_krw",
        "recovery_ohlc_valid","v18_ohlc_valid",
        "close_difference_v18_minus_recovery",
        "close_difference_pct_of_recovery",
        "classification","independent_regular_close_certified",
        "eligible_for_80point_score","trade_approved","orders_enabled")

def pos(value):
    try:
        if isinstance(value,bool):return None
        x=float(value)
        return x if math.isfinite(x) and x>0 else None
    except (ValueError,TypeError):return None

def num(value):
    try:
        if isinstance(value,bool):return None
        x=float(value)
        return x if math.isfinite(x) and x>=0 else None
    except (ValueError,TypeError):return None

def bar_valid(values):
    op,hi,lo,cl,vol=[values.get(k) for k in ("open","high","low","close","volume")]
    return bool(all(pos(values.get(x)) is not None for x in ("open","high","low","close"))
                and num(vol) is not None and vol>0
                and lo<=min(op,cl)<=max(op,cl)<=hi)

def records_from_v18(folder,asof):
    meta=read_json(folder/"meta.json")
    if (meta.get("schema")!="C3_K100_FULLMARKET_DAY_SLICE_V63"
        or meta.get("asof")!=str(asof)
        or meta.get("regular_only_verified") is not False
        or meta.get("source_run_success") is not True
        or not str(meta.get("v18_run_id","")).isdigit()
        or meta.get("trade_approved") is not False
        or meta.get("orders_enabled") is not False):
        raise ValueError("V18_MARKET_ASOF_OR_SAFETY_INVALID")
    parse_utc(meta.get("source_completed_utc"))
    allrows={}
    counts={}
    for market in MARKETS:
        p=folder/(market+".csv")
        if not p.is_file() or digest(p.read_bytes())!=meta.get("sha256",{}).get(market):
            raise ValueError("V18_DAILY_SOURCE_SHA256_MISMATCH")
        found=read_csv(p)
        if tuple(found[0].keys())!=SOURCE_REQUIRED if found else True:
            raise ValueError("V18_DAILY_SOURCE_COLUMNS_INVALID")
        if not found:raise ValueError("V18_DAILY_SOURCE_MISSING_MARKET")
        counts[market]=len(found)
        for row in found:
            ticker=row.get("ticker","")
            if (not re.fullmatch(r"[0-9A-Z]{6}",ticker)
                or row.get("Date")!=str(asof) or ticker in allrows):
                raise ValueError("V18_TICKER_DUPLICATED_OR_MARKET_DAY_WRONG")
            values={}
            for k in ("open","high","low","close","volume"):
                values[k]=num(row[k.capitalize()])
            values["turnover_krw"]=num(row["TurnoverKRW"])
            allrows[ticker]=(market,values)
    if meta.get("market_counts")!=counts or meta.get("total_covered_tickers")!=len(allrows):
        raise ValueError("V18_EXCHANGE_COVERAGE_METADATA_MISMATCH")
    return meta,allrows

def run(recovery,market_day,freeze):
    manifest=read_json(freeze/"frozen_v63_manifest.json")
    plans=read_json(freeze/"frozen_v63_signals.json")
    asof,freeze_time=verify_snapshot(manifest,plans)
    status=read_json(recovery/"status.json")
    candidates=read_csv(recovery/"candidates.csv")
    history=read_csv(recovery/"candidate_daily_history_v52.csv")
    if (status.get("market_data_date")!=str(asof)
        or status.get("scan_complete") is not True
        or status.get("data_date_verified") is not True
        or manifest.get("source_sha256",{}).get("recovery_status") !=
            digest((recovery/"status.json").read_bytes())
        or manifest.get("source_sha256",{}).get("recovery_history") !=
            digest((recovery/"candidate_daily_history_v52.csv").read_bytes())
        or not candidates or not history):
        raise ValueError("RECOVERY_DATED_HASH_OR_COMPLETENESS_INVALID")
    if manifest.get("source_run_ids",{}).get("recovery_run_id") in (None,""):
        raise ValueError("RECOVERY_SOURCE_RUN_MISSING")
    meta,market=records_from_v18(market_day,asof)
    # A same-day cross-source price comparison does not need v18 to have
    # been collected before a later frozen manifest. Never claim the
    # v18 run was independent or collected pre-signal from this metadata.
    bars={}
    for item in history:
        ticker=item.get("ticker","")
        if not re.fullmatch(r"[0-9]{6}",ticker):raise ValueError("RECOVERY_TICKER_INVALID")
        if item.get("date")!=str(asof):continue
        if ticker in bars:raise ValueError("DUPLICATE_RECOVERY_DAILY_BAR")
        bars[ticker]={k:num(item.get(k)) for k in ("open","high","low","close","volume")}
    cands={}
    for r in candidates:
        ticker=r.get("ticker","")
        if (not re.fullmatch(r"[0-9]{6}",ticker)
            or ticker in cands or r.get("latest_date")!=str(asof)):
            raise ValueError("DUPLICATE_OR_INVALID_RECOVERY_CANDIDATE")
        if ticker not in bars or pos(r.get("close"))!=bars[ticker]["close"]:
            raise ValueError("RECOVERY_CANDIDATE_CLOSE_DIFFERENT_FROM_ARCHIVE")
        cands[ticker]=r
    frozen={}
    pairs=Counter()
    for row in plans:
        ticker=row["ticker"]
        if ticker not in cands:raise ValueError("FROZEN_SIGNAL_OUTSIDE_RECOVERY_UNIVERSE")
        frozen.setdefault(ticker,set()).add(row["method"])
        pairs[(ticker,row["method"])]+=1
        if row.get("signal_close_reference")!=bars[ticker]["close"]:
            raise ValueError("FROZEN_ASOF_CLOSE_DIFFERS_FROM_RECOVERY_BAR")
    if any(v!=2 for v in pairs.values()):
        raise ValueError("FROZEN_FIRST_SECOND_PAIR_INCOMPLETE")
    out=[]
    for ticker,r in sorted(cands.items()):
        old=bars[ticker]
        present=market.get(ticker)
        new=present[1] if present else {}
        market_code=present[0] if present else None
        ov=bar_valid(old)
        nv=bar_valid(new) if present else False
        difference=(new["close"]-old["close"]
                    if new.get("close") is not None and old.get("close") is not None else None)
        pct=(100*difference/old["close"] if difference is not None and pos(old["close"]) else None)
        if not ov:cls="RECOVERY_OHLC_INVALID"
        elif not present:cls="NO_V18_MARKET_ROW"
        elif not nv:cls="V18_OHLC_INVALID"
        elif difference!=0:cls="CLOSE_CONFLICT_SESSION_UNKNOWN"
        else:cls="CLOSE_AGREED_SESSION_UNCERTIFIED"
        out.append(dict(asof=str(asof),ticker=ticker,name=r.get("name",""),
            market=market_code,is_frozen_signal=ticker in frozen,
            frozen_technical_signal_methods=";".join(sorted(frozen.get(ticker,[]))),
            recovery_instrument_type=r.get("instrument_type"),
            recovery_traded_value_origin=r.get("turnover_source"),
            **{"recovery_"+k:old[k] for k in ("open","high","low","close","volume")},
            **{"v18_"+k:new.get(k) for k in ("open","high","low","close","volume","turnover_krw")},
            recovery_ohlc_valid=ov,v18_ohlc_valid=nv,
            close_difference_v18_minus_recovery=(round(difference,4) if difference is not None else None),
            close_difference_pct_of_recovery=(round(pct,4) if pct is not None else None),
            classification=cls,
            independent_regular_close_certified=False,
            eligible_for_80point_score=False,trade_approved=False,orders_enabled=False))
    cls=Counter(x["classification"] for x in out)
    signal=Counter(x["classification"] for x in out if x["is_frozen_signal"])
    counts=dict(classifications=dict(cls),
        frozen_ticker_classifications=dict(signal),
        candidate_count=len(out),same_date_v18_covered=sum(x["market"] is not None for x in out),
        recovery_ohlc_valid=sum(x["recovery_ohlc_valid"] for x in out),
        valid_close_conflicts=cls.get("CLOSE_CONFLICT_SESSION_UNKNOWN",0),
        valid_close_matches=cls.get("CLOSE_AGREED_SESSION_UNCERTIFIED",0),
        malformed_recovery_ohlc=cls.get("RECOVERY_OHLC_INVALID",0),
        mismatch_over_1pct=sum(
            x["classification"]=="CLOSE_CONFLICT_SESSION_UNKNOWN"
            and x["close_difference_pct_of_recovery"] is not None
            and abs(x["close_difference_pct_of_recovery"])>1 for x in out),
        frozen_signal_distinct_tickers=len(frozen),
        frozen_signal_method_count=len(pairs),
        frozen_alternatives=len(plans),
        frozen_ticker_valid_close_conflicts=signal.get("CLOSE_CONFLICT_SESSION_UNKNOWN",0))
    report=dict(schema=SCHEMA,asof=str(asof),
        provenance_run_ids=dict(manifest["source_run_ids"],
                                sector_v18_run_id=meta["v18_run_id"]),
        manifest_sha256=manifest["frozen_payload_sha256"],
        market_slice_sha256=meta["sha256"],
        market_slice_source_completed_utc=meta["source_completed_utc"],
        frozen_timestamp_utc=manifest["freeze_utc"],
        market_universe_size=meta["total_covered_tickers"],
        **counts,
        objective_conflict_cause_determined=False,
        after_hours_causation_verified=False,
        close_adjustment_policy_independently_verified=False,
        cross_source_agreement_does_not_prove_independent_regular_feed=True,
        kst_regular_session_0900_1530_independently_certified=False,
        all_frozen_prices_tainted_until_certified=True,
        final_score_80_validated=False,
        trade_approved=False,orders_enabled=False,decision="CASH")
    return report,out

def mobile(report):
    r=report
    return "\n".join([
        "# v6.4 무료 가격 출처 대조 — 09:00–15:30 정규장 증명 전",
        "",
        f"**거래일 {r['asof']} / CASH / 매수 승인 0건**",
        f"수집 보관 주식코드 {r['market_universe_size']}개, 검사 후보 {r['candidate_count']}개.",
        f"유효 가격 두 자료의 종가 충돌 **{r['valid_close_conflicts']}개**, 유효하게 동일 **{r['valid_close_matches']}개**.",
        f"원본 일봉 비정상 {r['malformed_recovery_ohlc']}개, 종가 1% 이상 충돌 {r['mismatch_over_1pct']}개.",
        f"신호로 고정한 {r['frozen_signal_distinct_tickers']}개 종목 중 종가 충돌 **{r['frozen_ticker_valid_close_conflicts']}개**.",
        "",
        "| 상태 | 종목수 |", "|---|---:|",
        *[f"| {k} | {v} |" for k,v in r['classifications'].items()],
        "",
        "**같은 종가여도 정규장 인증이 아닙니다.** 한쪽이 장후인지, 수정주가 처리인지, API 추적 문제인지는 원본만으로 확정 불가능합니다.",
        "매수/손절가·실거래 승률 산출과 주문은 보류합니다.",
        "기술 신호 1차·2차의 원본 가격은 덮어쓰지 않고 SHA로 그대로 유지합니다.",
        "",
        "## Required Next Data",
        "09:00–15:30 장내 거래를 명확하게 구분한 제3의 정식 시간별 가격 출처, 수정주가·거래정지 증빙, 당시 전 종목 PIT 및 실측 체결금액.",
        ""])
def main():
    p=argparse.ArgumentParser()
    for name in ("--recovery","--market-day","--freeze","--outdir"):
        p.add_argument(name,required=True,type=Path)
    a=p.parse_args()
    report,rows=run(a.recovery,a.market_day,a.freeze)
    a.outdir.mkdir(parents=True,exist_ok=True)
    (a.outdir/"source_consensus_v64_status.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (a.outdir/"source_consensus_v64_all.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (a.outdir/"source_consensus_v64_mobile.md").write_text(
        mobile(report),encoding="utf-8")
    print(json.dumps({k:report[k] for k in (
        "asof","candidate_count","valid_close_conflicts",
        "valid_close_matches","malformed_recovery_ohlc",
        "frozen_ticker_valid_close_conflicts","decision")},ensure_ascii=False))
if __name__=="__main__":main()
