#!/usr/bin/env python3
"""v5.7 date-locked KRX price discrepancy forensics; strictly read-only.

Classifies evidence, not causes. High/low/close mismatches may indicate
different snapshots/session scope, but are NEVER proof of after-market.
Optional official KIS J:KRX timestamped minute audit may adjudicate a small
dated subset, not replace all bars or certify the exchange-wide universe.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path

SCHEMA="free_krx_regular_source_forensics_v57"
PRICE_PARITY_SCHEMA="free_krx_full_parity_v56"
CLASSES=("OHLC_EXACT_MATCH_UNCERTIFIED",
         "CLOSE_ONLY_SAME_OPEN_HIGH_LOW",
         "RANGE_MISMATCH_SAME_OPEN",
         "OPEN_AND_OR_RANGE_MISMATCH")

def positive(value):
    if isinstance(value,bool):return None
    try:
        x=float(value)
        return x if math.isfinite(x) and x>0 else None
    except (TypeError,ValueError):return None

def ohlc(values):
    if not isinstance(values,(list,tuple)) or len(values)!=4:return None
    p=[positive(v) for v in values]
    if any(v is None for v in p):return None
    op,hi,lo,cl=p
    return p if lo<=min(op,cl)<=max(op,cl)<=hi else None

def daily(y):
    try:return date.fromisoformat(str(y)).isoformat()==y
    except (ValueError,TypeError):return False

def probe_index(audit,asof):
    """Accept only stated, date-matched, fully checked regular-minute bars."""
    out={}; blockers=[]
    if not isinstance(audit,dict) or not audit:
        return out,["DATED_KIS_MINUTES_NOT_PROVIDED"]
    if audit.get("schema")!="kis_krx_minute_audit_v1":
        return out,["KIS_AUDIT_SCHEMA_UNVERIFIED"]
    if audit.get("date")!=asof.replace("-",""):
        return out,["KIS_AUDIT_DATE_MISMATCH"]
    if audit.get("source")!="KIS_OFFICIAL_MINUTES_J_KRX" or audit.get("read_only") is not True:
        return out,["KIS_AUDIT_SOURCE_UNVERIFIED"]
    rows=audit.get("regular_reconstructions")
    if not isinstance(rows,list):return out,["KIS_MINUTE_ROWS_MISSING"]
    for item in rows:
        if not isinstance(item,dict):continue
        ticker=item.get("ticker")
        price=item.get("regular_ohlcv")
        if (not isinstance(ticker,str) or len(ticker)!=6 or not ticker.isdecimal()
          or item.get("asof")!=asof.replace("-","")
          or item.get("market_code")!="J"
          or item.get("session")!="KRX_REGULAR_0900_1530"
          or item.get("regular_ohlcv_reconstruction_verified") is not True
          or item.get("last_minute")!="153000"
          or not isinstance(item.get("minutes_seen"),int)
          or item["minutes_seen"]<300
          or item.get("extra_validation_issues")
          or item.get("duplicate_time_conflicts",1)!=0
          or item.get("wrong_date_rows",1)!=0
          or item.get("invalid_minute_rows",1)!=0
          or not isinstance(price,dict)
          or item.get("trade_approved") is not False):
            continue
        prices=ohlc([price.get(k) for k in ("Open","High","Low","Close")])
        if prices is None or ticker in out:
            # Repeated probe claims are ambiguous, including identical duplicates.
            if ticker in out:del out[ticker]
            blockers.append("AMBIGUOUS_KIS_TICKER_DUPLICATE")
            continue
        out[ticker]=prices
    if not out:blockers.append("NO_STRICT_KIS_REGULAR_MINUTE_PROBE")
    return out,list(dict.fromkeys(blockers))

def analyze(parity,asof,kis_audit=None):
    base=dict(schema=SCHEMA,asof=asof,decision="CASH",
        trade_approved=False,orders_enabled=False,
        regular_only_session_certified=False,
        market_wide_independent_source_verified=False,
        diagnosis_valid=False,blocking_reasons=[],
        categories={},comparisons=[],total_rows=0,mismatches=0,
        recovery_outside_v18_range=0,v18_outside_recovery_range=0,
        matching_open_count=0,range_mismatch_count=0,
        suspicion_not_proof="SOURCE_TIMING_OR_SESSION_DIFFERENCE_POSSIBLE_NOT_PROVEN",
        kis_regular_minute_evidence_count=0,kis_comparison_counts={},
        invalid_recovery_tickers=[],invalid_v18_tickers=[],
        spot_check_priority=[])
    fail=[]
    if not daily(asof):fail.append("INVALID_ASOF")
    if not isinstance(parity,dict):parity={}
    if parity.get("schema")!=PRICE_PARITY_SCHEMA or parity.get("asof")!=asof:
        fail.append("DATED_V56_PROVENANCE_REQUIRED")
    if parity.get("mismatch_tickers_complete") is not True:
        fail.append("INCOMPLETE_PRICE_CONFLICT_ROSTER")
    rows=parity.get("comparison_rows")
    if not isinstance(rows,list) or not rows:rows=[];fail.append("MISSING_COMPLETE_COMPARISON_ROWS")
    count=parity.get("overlap_tickers")
    if not isinstance(count,int) or count!=len(rows):
        fail.append("CANDIDATE_OVERLAP_COUNT_CONFLICT")
    roster=parity.get("mismatch_tickers")
    if not isinstance(roster,list):roster=[];fail.append("MISMATCH_ROSTER_MISSING")
    if len(roster)!=len(set(str(v) for v in roster)):
        fail.append("DUPLICATE_MISMATCH_ROSTER")
    if not isinstance(parity.get("close_mismatches"),int) or len(roster)!=parity["close_mismatches"]:
        fail.append("MISMATCH_COUNT_CONFLICT")
    if parity.get("independent_provider_verified") is not False:
        fail.append("UNEXPECTED_SOURCE_INDEPENDENCE_CLAIM")
    if parity.get("regular_only_session_certified") is not False:
        fail.append("UNEXPECTED_SESSION_CERTIFICATION_CLAIM")
    if parity.get("trade_approved") is not False:
        fail.append("UNEXPECTED_TRADE_APPROVAL")
    if fail:
        base["blocking_reasons"]=list(dict.fromkeys(fail))
        return base
    probe,probe_blocks=probe_index(kis_audit,asof)
    classifications=[]
    seen=set()
    for row in rows:
        if not isinstance(row,dict):
            fail.append("INVALID_PRICE_ROW")
            break
        ticker=row.get("ticker")
        if (not isinstance(ticker,str) or len(ticker)!=6 or not ticker.isdigit()
          or ticker in seen):
            fail.append("DUPLICATE_OR_BAD_COMPARISON_TICKER")
            break
        seen.add(ticker)
        r=ohlc(row.get("recovery_ohlc"))
        v=ohlc(row.get("v18_ohlc"))
        if r is None or v is None:
            fail.append("NONPOSITIVE_OR_IMPOSSIBLE_OHLC");break
        op_same=r[0]==v[0]
        high_same=r[1]==v[1]
        low_same=r[2]==v[2]
        close_same=r[3]==v[3]
        if close_same and op_same and high_same and low_same:
            category="OHLC_EXACT_MATCH_UNCERTIFIED"
        elif not close_same and op_same and high_same and low_same:
            category="CLOSE_ONLY_SAME_OPEN_HIGH_LOW"
        elif op_same and (not high_same or not low_same):
            category="RANGE_MISMATCH_SAME_OPEN"
        else:
            category="OPEN_AND_OR_RANGE_MISMATCH"
        recovery_outside=not(v[2]<=r[3]<=v[1])
        v18_outside=not(r[2]<=v[3]<=r[1])
        changed=not close_same
        if changed != (ticker in roster) or changed != (row.get("close_equal") is False):
            fail.append("ROW_ROSTER_CLOSE_MISMATCH");break
        # No 'proven after-market' label based only on OHLC shapes.
        kis_status="NO_DATED_FULL_COVERAGE_KIS_MINUTE_REFERENCE"
        krx_minute_close=None
        if ticker in probe:
            krx_minute_close=probe[ticker][3]
            match_r=krx_minute_close==r[3]
            match_v=krx_minute_close==v[3]
            if match_r and match_v:kis_status="KIS_J_MINUTE_CLOSE_MATCHES_BOTH"
            elif match_r:kis_status="KIS_J_MINUTE_CLOSE_MATCHES_RECOVERY_ONLY"
            elif match_v:kis_status="KIS_J_MINUTE_CLOSE_MATCHES_V18_ONLY"
            else:kis_status="KIS_J_MINUTE_CLOSE_MATCHES_NEITHER"
        drift=abs((v[3]/r[3]-1)*100)
        severity=("HIGH_VERIFY_FIRST" if recovery_outside or v18_outside or drift>=3
                  else "MEDIUM_REVIEW" if not close_same else "MATCH_NOT_CERTIFIED")
        classifications.append(dict(ticker=ticker,market=row.get("market"),
            category=category,open_equal=op_same,high_equal=high_same,
            low_equal=low_same,close_equal=close_same,
            recovery_close=r[3],v18_close=v[3],
            absolute_close_drift_pct=round(drift,5),
            recovery_close_outside_v18_range=recovery_outside,
            v18_close_outside_recovery_range=v18_outside,
            kis_regular_minute_close=krx_minute_close,
            kis_adjudication=kis_status,severity=severity,
            verified_regular_order_price=False,
            trade_approved=False))
    if fail or len(classifications)!=len(rows):
        base["blocking_reasons"]=list(dict.fromkeys(fail or ["INCOMPLETE_CLASSIFICATION"]))
        return base
    actual={x["ticker"] for x in classifications if not x["close_equal"]}
    if actual!=set(roster):
        base["blocking_reasons"]=["COMPLETE_ROSTER_INCONSISTENT"]
        return base
    ct=Counter(x["category"] for x in classifications)
    kct=Counter(x["kis_adjudication"] for x in classifications)
    scores=sorted((x for x in classifications if not x["close_equal"]),
        key=lambda x:(x["severity"]!="HIGH_VERIFY_FIRST",
                      -int(x["recovery_close_outside_v18_range"] or
                           x["v18_close_outside_recovery_range"]),
                      -x["absolute_close_drift_pct"],x["ticker"]))
    base.update(diagnosis_valid=True,
        categories={s:ct[s] for s in CLASSES},
        comparisons=classifications,total_rows=len(classifications),
        mismatches=len(actual),
        recovery_outside_v18_range=sum(x["recovery_close_outside_v18_range"] for x in classifications),
        v18_outside_recovery_range=sum(x["v18_close_outside_recovery_range"] for x in classifications),
        matching_open_count=sum(x["open_equal"] for x in classifications),
        range_mismatch_count=sum(not(x["high_equal"] and x["low_equal"]) for x in classifications),
        kis_regular_minute_evidence_count=sum(x["kis_regular_minute_close"] is not None for x in classifications),
        kis_comparison_counts=dict(kct),
        invalid_recovery_tickers=parity.get("invalid_recovery_tickers",[]),
        invalid_v18_tickers=parity.get("invalid_v18_tickers",[]),
        spot_check_priority=[x["ticker"] for x in scores[:12]],
        blocking_reasons=[
            "SESSION_AND_PROVIDER_ROOT_CAUSE_UNDETERMINED",
            "INDEPENDENT_WHOLE_MARKET_KRX_REGULAR_OHLC_NOT_ATTESTED",
            "HISTORICAL_REGULAR_ONLY_65_BARS_NOT_VERIFIED",
            *probe_blocks])
    return base

def mobile(report):
    lines=["# C3/K100 v5.7 정규장 가격 충돌 포렌식", "",
      f"대상일: {report['asof']}",
      "**실제 신규매수: CASH (0건)**", "",
      "| 가격 대조 구분 | 종목 수 |","|---|---:|"]
    labels={"OHLC_EXACT_MATCH_UNCERTIFIED":"OHLC 일치, 정규장 미인증",
      "CLOSE_ONLY_SAME_OPEN_HIGH_LOW":"시·고·저 동일, 종가만 차이",
      "RANGE_MISMATCH_SAME_OPEN":"시가 동일, 고저가 차이",
      "OPEN_AND_OR_RANGE_MISMATCH":"시가 및 다른 필드 차이"}
    for k in CLASSES:lines.append(f"| {labels[k]} | {report.get('categories',{}).get(k,0)} |")
    lines.extend(["",
      f"타 공급원 고저가 밖 종가(복구 자료): {report.get('recovery_outside_v18_range',0)}건",
      f"타 공급원 고저가 밖 종가(v18): {report.get('v18_outside_recovery_range',0)}건",
      f"독립 인증된 소규모 KIS 정규장 분봉 대조: {report.get('kis_regular_minute_evidence_count',0)}개",
      "원인: 특정 시점/세션/공급원 갱신 차이 가능성을 뜻할 뿐 시간외라고 입증한 것은 아닙니다.",
      "", "## 정밀 교차검증 우선 종목",
      ", ".join(report.get("spot_check_priority",[])) or "없음",
      "", "## 아직 못 한 일",
      "거래소 정규장 가격확인, 제공자별 수집타임스탬프 확보, 실측 거래대금, 계좌 및 80점 최종 점수 검증.",
      "가격이 맞는 종목도 정규장 독립 인증 전에는 자동 BUY 승격을 금지합니다.",
      ""]) 
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--v56",required=True,type=Path)
    p.add_argument("--kis-minute",default="",type=str)
    p.add_argument("--asof",required=True)
    p.add_argument("--outdir",required=True,type=Path)
    a=p.parse_args()
    def read(path):
        try:return json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError,ValueError):return {}
    report=analyze(read(a.v56),a.asof,read(a.kis_minute) if a.kis_minute else None)
    a.outdir.mkdir(parents=True,exist_ok=True)
    (a.outdir/"source_forensics_v57.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (a.outdir/"source_forensics_v57_all.csv").open(
        "w",encoding="utf-8-sig",newline="") as f:
        keys=("ticker","market","category","open_equal","high_equal","low_equal",
              "close_equal","recovery_close","v18_close","absolute_close_drift_pct",
              "recovery_close_outside_v18_range","v18_close_outside_recovery_range",
              "kis_regular_minute_close","kis_adjudication","severity",
              "verified_regular_order_price","trade_approved")
        w=csv.DictWriter(f,fieldnames=keys,extrasaction="ignore")
        w.writeheader();w.writerows(report["comparisons"])
    (a.outdir/"source_forensics_v57_mobile.md").write_text(mobile(report)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("asof","diagnosis_valid","total_rows",
         "mismatches","categories","recovery_outside_v18_range",
         "v18_outside_recovery_range","kis_regular_minute_evidence_count",
         "decision","blocking_reasons")},ensure_ascii=False))
    if not report["diagnosis_valid"]:raise SystemExit("INVALID_DATED_SOURCE_EVIDENCE")

if __name__=="__main__":main()
