#!/usr/bin/env python3
"""v6.5 optional KRX official EOD API + date-locked source triage.

Official KRX API: https://data-dbg.krx.co.kr/svc/apis/sto/{stk_bydd_trd,
ksq_bydd_trd}?basDd=YYYYMMDD with a separately approved AUTH_KEY.

Official daily EOD is NOT automatically 09:00–15:30 regular-session:
KRX After Market operates 16:00–20:00 from September 2026. This module
never claims the API excludes it without explicit session documentation.
No secrets saved/logged, no buy authorization, no certified live P&L.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,re
from collections import Counter
from datetime import date,datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from forward_ledger_v63 import read_json,read_csv,parse_date,digest
from source_consensus_v64 import SCHEMA as PREVIOUS,bar_valid

SCHEMA="C3_K100_OFFICIAL_KRX_EOD_RECONCILIATION_V65"
COLLECT_SCHEMA="C3_K100_KRX_OPENAPI_COLLECTION_V65"
MARKETS={"KOSPI":"stk_bydd_trd","KOSDAQ":"ksq_bydd_trd"}
BASE_URL="https://data-dbg.krx.co.kr/svc/apis/sto/"
MARKET_FIELDS=("market","ticker","name","asof","open","high","low",
               "close","volume","turnover_krw","valid_daily_bar")
COMPARISON_FIELDS=("asof","ticker","market","name","is_frozen_signal",
                   "recovery_close","v18_close","krx_eod_close",
                   "krx_eod_volume","krx_eod_turnover_krw",
                   "previous_v64_classification","v65_evidence_class",
                   "krx_eod_equal_recovery","krx_eod_equal_v18",
                   "krx_eod_is_valid_bar","official_krx_eod_api_authenticated",
                   "krx_1530_regular_session_certified",
                   "adjustment_cause_verified","source_price_ready_for_trading",
                   "trade_approved","orders_enabled")

def utc_timestamp():
    return datetime.now(timezone.utc).isoformat()

def price(s):
    if isinstance(s,bool):return None
    if s is None:return None
    s=str(s).strip().replace(",","")
    if s in ("","-","N/A","null"):return None
    try:
        v=float(s)
        return v if math.isfinite(v) and v>=0 else None
    except (TypeError,ValueError):return None

def take(v):
    if isinstance(v,bool):return None
    try:
        if v in ("",None):return None
        v=float(v)
        return v if math.isfinite(v) and v>=0 else None
    except (ValueError,TypeError):return None

def normalized_day(day):
    d=parse_date(day)
    return d.isoformat(),d.strftime("%Y%m%d")

def normalize_payload(payload,day,market):
    if (not isinstance(payload,dict) or
        not isinstance(payload.get("OutBlock_1"),list) or
        len(payload["OutBlock_1"])==0):
        raise ValueError("OFFICIAL_RESPONSE_MISSING_OR_EMPTY_OUTBLOCK")
    vals=[];seen=set();opaque_count=0
    for item in payload["OutBlock_1"]:
        if not isinstance(item,dict):
            raise ValueError("OFFICIAL_RECORD_NOT_MAPPING")
        raw=str(item.get("ISU_CD","")).strip()
        if not re.fullmatch(r"[A-Z0-9]{6}",raw):
            # Some official endpoints may return 12-digit ISIN or non-share
            # securities. Do NOT trim ISIN suffix into a fictitious ticker.
            opaque_count+=1
            continue
        if raw in seen:raise ValueError("OFFICIAL_DUPLICATE_SECURITY_ID")
        seen.add(raw)
        returned=str(item.get("BAS_DD","")).strip().replace("-","")
        if returned!=day.replace("-",""):
            raise ValueError("OFFICIAL_ROW_BAS_DATE_MISMATCH")
        row=dict(market=market,ticker=raw,name=str(item.get("ISU_NM","")),
            asof=day,open=price(item.get("TDD_OPNPRC")),
            high=price(item.get("TDD_HGPRC")),
            low=price(item.get("TDD_LWPRC")),
            close=price(item.get("TDD_CLSPRC")),
            volume=price(item.get("ACC_TRDVOL")),
            turnover_krw=price(item.get("ACC_TRDVAL")))
        row["valid_daily_bar"]=bar_valid(row)
        vals.append(row)
    if not vals:raise ValueError("OFFICIAL_NO_SHORT_SECURITY_IDS_TO_JOIN")
    return vals,opaque_count

def write_csv(path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(rows)

def fetch_official(endpoint,day,key,opener=urlopen):
    if not key:raise ValueError("AUTH_KEY_NOT_CONNECTED")
    url=BASE_URL+endpoint+"?"+urlencode({"basDd":day.replace("-","")})
    req=Request(url,headers={"AUTH_KEY":key,"Accept":"application/json"},
                method="GET")
    # Never print req/header or exception content; some proxies echo keys.
    try:
        with opener(req,timeout=20) as result:
            data=result.read(5*1024*1024+1)
            if len(data)>5*1024*1024:raise ValueError("OFFICIAL_RESPONSE_TOO_LARGE")
    except HTTPError as e:
        if e.code in (401,403):raise ValueError("KRX_AUTH_OR_SERVICE_APPROVAL_MISSING")
        raise ValueError("KRX_SERVICE_HTTP_ERROR")
    except (URLError,TimeoutError,OSError):
        raise ValueError("KRX_SERVICE_NETWORK_UNAVAILABLE")
    try:
        doc=json.loads(data.decode("utf-8"))
    except (ValueError,UnicodeDecodeError):
        raise ValueError("OFFICIAL_RESPONSE_NON_JSON")
    return doc,digest(data)

def collect(day,outdir,auth_key=None,opener=urlopen):
    day,_=normalized_day(day)
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    response=dict(schema=COLLECT_SCHEMA,asof=day,
        retrieval_utc=utc_timestamp(),api_reference_base=BASE_URL,
        endpoints=list(MARKETS.values()),authentication_secret_persisted=False,
        krx_eod_authenticated=False,official_dataset_usable=False,
        independent_1530_regular_session_certified=False,
        session_scope_includes_aftermarket_verified=False,
        source_price_authorized_for_trading=False,
        trade_approved=False,orders_enabled=False,decision="CASH",
        official_market_rows=0,unmatched_nonshort_codes=0,
        status="AUTH_KEY_NOT_CONNECTED",
        market_file_sha256={},raw_response_sha256={})
    if not auth_key:
        (outdir/"krx_v65_collect_status.json").write_text(
            json.dumps(response,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return response
    data={};opaque={};fingerprints={}
    try:
        for market,endpoint in MARKETS.items():
            raw,fp=fetch_official(endpoint,day,auth_key,opener)
            listed,nonshort=normalize_payload(raw,day,market)
            data[market]=listed;opaque[market]=nonshort;fingerprints[market]=fp
        shared={x["ticker"] for x in data["KOSPI"]}&{x["ticker"] for x in data["KOSDAQ"]}
        if shared:raise ValueError("OFFICIAL_SECURITY_IN_MULTIPLE_MARKETS")
        for market in MARKETS:
            path=outdir/(market+"_official.csv")
            write_csv(path,data[market],MARKET_FIELDS)
            response["market_file_sha256"][market]=digest(path.read_bytes())
        response.update(krx_eod_authenticated=True,official_dataset_usable=True,
            official_market_rows=sum(len(v) for v in data.values()),
            unmatched_nonshort_codes=sum(opaque.values()),
            raw_response_sha256=fingerprints,
            status="OFFICIAL_EOD_AVAILABLE_SESSION_SCOPE_UNCERTIFIED")
    except ValueError as exc:
        # Fail CLOSED as a set, never publish one successful market as a
        # complete third-price universe. Missing auth/permission is normal.
        for name in MARKETS:
            p=outdir/(name+"_official.csv")
            if p.exists():p.unlink()
        response["market_file_sha256"]={}
        response["raw_response_sha256"]={}
        response["status"]=str(exc)
    (outdir/"krx_v65_collect_status.json").write_text(
        json.dumps(response,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return response

def official_rows(root,manifest):
    if manifest.get("official_dataset_usable") is not True:return {}
    got={}
    for market in MARKETS:
        path=root/(market+"_official.csv")
        if (not path.is_file() or
            digest(path.read_bytes())!=manifest.get("market_file_sha256",{}).get(market)):
            raise ValueError("OFFICIAL_FILE_SHA256_MISMATCH")
        records=read_csv(path)
        if not records:raise ValueError("OFFICIAL_MARKET_EMPTY")
        for r in records:
            t=r["ticker"]
            if (not re.fullmatch(r"[A-Z0-9]{6}",t) or
                r["asof"]!=manifest["asof"] or r["market"]!=market or t in got):
                raise ValueError("OFFICIAL_CSV_DUPLICATE_OR_WRONG_DATE")
            values={k:take(r[k]) for k in
                ("open","high","low","close","volume","turnover_krw")}
            if str(bar_valid(values))!=r["valid_daily_bar"]:
                raise ValueError("OFFICIAL_BAR_VALIDITY_REWRITTEN")
            got[t]=(market,values)
    if len(got)!=manifest["official_market_rows"]:
        raise ValueError("OFFICIAL_MARKET_TOTAL_INVALID")
    return got

def compare(v64,rows,official_manifest,official_root):
    if (v64.get("schema")!=PREVIOUS or
        v64.get("trade_approved") is not False or
        v64.get("orders_enabled") is not False or
        v64.get("kst_regular_session_0900_1530_independently_certified") is not False or
        official_manifest.get("schema")!=COLLECT_SCHEMA or
        official_manifest.get("asof")!=v64.get("asof") or
        official_manifest.get("independent_1530_regular_session_certified") is not False or
        official_manifest.get("source_price_authorized_for_trading") is not False or
        official_manifest.get("trade_approved") is not False or
        official_manifest.get("orders_enabled") is not False or
        len(rows)!=v64.get("candidate_count")):
        raise ValueError("V65_SOURCE_ASOF_POLICY_OR_COMPLETE_ROWS_INVALID")
    official=official_rows(Path(official_root),official_manifest)
    seen=set();out=[];labels=Counter()
    for r in rows:
        t=r["ticker"]
        if (t in seen or r["asof"]!=v64["asof"] or
            r["trade_approved"]!="False" or r["orders_enabled"]!="False" or
            r["independent_regular_close_certified"]!="False"):
            raise ValueError("V64_AUDIT_DUPLICATE_OR_TAMPERED_ROW")
        seen.add(t)
        item=official.get(t)
        actual=item[1] if item else {}
        x=actual.get("close")
        valid=bar_valid(actual) if item else False
        recovery=take(r.get("recovery_close"))
        v18=take(r.get("v18_close"))
        matchr=bool(valid and recovery is not None and x==recovery)
        matchv=bool(valid and v18 is not None and x==v18)
        if not official_manifest.get("official_dataset_usable"):
            label="KRX_AUTH_OR_SERVICE_NOT_CONNECTED"
        elif not item:
            label="OFFICIAL_TICKER_NOT_RETURNED"
        elif not valid:
            label="OFFICIAL_BAR_INVALID_OR_SUSPENDED"
        elif matchr and matchv:
            label="OFFICIAL_EOD_EQUALS_BOTH_NO_1530_PROOF"
        elif matchr:
            label="OFFICIAL_EOD_EQUALS_RECOVERY_ONLY"
        elif matchv:
            label="OFFICIAL_EOD_EQUALS_V18_ONLY"
        else:
            label="OFFICIAL_EOD_DIFFERS_FROM_BOTH"
        labels[label]+=1
        out.append(dict(asof=v64["asof"],ticker=t,
            market=(item[0] if item else r.get("market")),
            name=r.get("name",""),is_frozen_signal=r.get("is_frozen_signal")=="True",
            recovery_close=recovery,v18_close=v18,krx_eod_close=x,
            krx_eod_volume=actual.get("volume"),
            krx_eod_turnover_krw=actual.get("turnover_krw"),
            previous_v64_classification=r["classification"],
            v65_evidence_class=label,
            krx_eod_equal_recovery=matchr,krx_eod_equal_v18=matchv,
            krx_eod_is_valid_bar=valid,
            official_krx_eod_api_authenticated=official_manifest.get("krx_eod_authenticated") is True,
            krx_1530_regular_session_certified=False,
            adjustment_cause_verified=False,
            source_price_ready_for_trading=False,
            trade_approved=False,orders_enabled=False))
    if len(seen)!=v64.get("candidate_count"):
        raise ValueError("CANDIDATE_SET_NOT_COMPLETE")
    frozen=[r for r in out if r["is_frozen_signal"]]
    report=dict(schema=SCHEMA,asof=v64["asof"],
        official_source_status=official_manifest["status"],
        official_api_connected=official_manifest.get("krx_eod_authenticated") is True,
        official_eod_rows=official_manifest.get("official_market_rows",0),
        official_raw_response_sha256=official_manifest.get("raw_response_sha256",{}),
        v64_frozen_manifest_sha256=v64.get("manifest_sha256"),
        candidates_evaluated=len(out),
        frozen_distinct_tickers=len(frozen),
        official_evidence_classes=dict(labels),
        official_eod_matches_both=sum(r["krx_eod_equal_recovery"] and
                                  r["krx_eod_equal_v18"] for r in out),
        official_eod_matches_only_recovery=sum(r["krx_eod_equal_recovery"] and
                                  not r["krx_eod_equal_v18"] for r in out),
        official_eod_matches_only_v18=sum(r["krx_eod_equal_v18"] and
                                  not r["krx_eod_equal_recovery"] for r in out),
        still_unexplained_v64_discrepancies=v64.get("valid_close_conflicts"),
        after_hours_vs_adjustment_causality_confirmed=False,
        authenticated_eod_is_not_proven_regular_1530=True,
        official_1530_close_eligible_for_signal=False,
        certified_5day_real_return_count=0,
        final_80point_certified=False,trade_approved=False,
        orders_enabled=False,decision="CASH")
    return report,out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--asof",required=True)
    p.add_argument("--v64",type=Path,required=True)
    p.add_argument("--outdir",type=Path,required=True)
    p.add_argument("--krx-eod",type=Path)
    p.add_argument("--collect",action="store_true")
    a=p.parse_args()
    a.outdir.mkdir(parents=True,exist_ok=True)
    if a.krx_eod and (a.krx_eod/"krx_v65_collect_status.json").is_file():
        origin=a.krx_eod
        collected=read_json(origin/"krx_v65_collect_status.json")
    else:
        origin=a.outdir/"official"
        # Explicit --collect and use the secret ONLY in environment. Do not
        # accept AUTH_KEY as command-line flag, which leaks shell process args.
        key=os.environ.get("KRX_AUTH_KEY") if a.collect else None
        collected=collect(a.asof,origin,key)
    v64=read_json(a.v64/"source_consensus_v64_status.json")
    rows=read_csv(a.v64/"source_consensus_v64_all.csv")
    report,results=compare(v64,rows,collected,origin)
    (a.outdir/"krx_v65_source_comparison_status.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    write_csv(a.outdir/"krx_v65_source_comparison_all.csv",results,COMPARISON_FIELDS)
    lines=["# v6.5 공식 KRX 일봉 교차검증 (정규장 인증 전)",
           "",f"기준: {report['asof']} · 결론 **CASH**",
           f"공식 API 상태: **{report['official_source_status']}**",
           f"후보 {report['candidates_evaluated']}종목 · 기존 소스 간 불일치 "+
               f"{report['still_unexplained_v64_discrepancies']}종목",
           "", "| 공식 일봉 대조 구분 | 건수 |","|---|---:|"]
    lines.extend(f"| {n} | {v} |" for n,v in report["official_evidence_classes"].items())
    lines +=["","**공식 일별매매정보라도 2026년 KRX 애프터마켓 때문에 "+
         "15:30 정규장 종가임이 별도 증명되지는 않습니다.**",
         "거래소에서 정규장 09:00~15:30만을 포함한다고 명시한 원본이 "+
         "별도로 확인되기 전에는 모든 매수 승인·실전 수익률 확정 불가.",
         "실거래 주문 0건, 신규매수 CASH 유지.",
         "", "필요 자료: KRX OPEN API 인증키 및 유가증권·코스닥 일별매매정보 "+
         "각각 승인, 정규장 전용 시각 확인 공식 근거."]
    (a.outdir/"krx_v65_mobile.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("V65_OFFICIAL_EOD_STATUS",report["asof"],report["official_source_status"],
          report["candidates_evaluated"],report["decision"])

if __name__=="__main__":main()
