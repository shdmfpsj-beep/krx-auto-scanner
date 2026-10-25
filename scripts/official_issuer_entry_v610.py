#!/usr/bin/env python3
"""v6.10 exact-date official KRX basic-info + strong-sector risk-first veto.

Two KRX basic-info endpoints require separately approved OPEN API service.
Unlike stock daily EOD, base-info uses ISU_SRT_CD and typically has no
per-row BAS_DD. Record requested basDd + fetch timestamp, do not forge
independent historic vintage. 'SECT_TP_NM' is board/section, NOT industry.

Attach to frozen v6.8 (52 marketwide candidates & 156 method setups)
and v6.9 (17 ETF proxy sector/5day foreign institution flows); only
risk-first next-day hypotheses, never broker orders or BUY recommendations.
"""
from __future__ import annotations
import argparse,csv,json,math,os,re
from pathlib import Path
from datetime import date,datetime,timezone
from collections import Counter
from krx_official_eod_v65 import fetch_official,price,write_csv
from forward_ledger_v63 import read_csv,read_json,digest
from full_market_scanner_v68 import SCHEMA as V68,RESEARCH_FIELDS
from sector_flow_v69 import SCHEMA as V69

SCHEMA="C3_K100_OFFICIAL_ISSUER_ENTRY_V610"
BASIC_SCHEMA="C3_K100_KRX_ISSUER_BASE_INFO_V610"
ENDPOINTS={"KOSPI":"stk_isu_base_info","KOSDAQ":"ksq_isu_base_info"}
BASIC_FIELDS=("asof_requested","market","ticker","isin","name","security_group",
              "share_kind","board_section","listed_date","source_endpoint")
ROW_FIELDS=("asof","ticker","name","market","proxy_strong_sectors",
    "c3_liquid","five_day_flow_complete","five_day_net_buy_krw",
    "prelim_c3_score","prelim_k100_score","official_base_api_available",
    "official_equity_group_verified","common_share_basic_info_verified",
    "official_board_section_not_industry","sector_proxy_pit_verified",
    "sector_liquidity_money_flow_research_gate","sector_qualified_research_rank",
    "confirmed_method_count","risk_first_method","daily_structure_stop",
    "first_entry_reference","second_alternative_reference",
    "nearest_ceiling_reference","first_net_reward_risk",
    "second_net_reward_risk","risk_geometry_2r_pass",
    "technical_trigger_confirmed","financial_data_asof_verified",
    "earnings_catalyst_asof_verified","regular_1530_eod_certified",
    "historical_120bar_independently_verified",
    "complete_80point_certified","trade_approved","orders_enabled","blocking_reasons")
SHORT_FIELDS=("rank","sector","asof","ticker","name","prelim_c3_score",
    "actual_turnover_krw","foreign_plus_institution_5d_krw",
    "official_common_share_proof","technical_confirmed",
    "risk_2r_both_entries","trade_approved","reason")

def fmtdate(v):
    d=date.fromisoformat(v)
    if d.isoformat()!=v:raise ValueError("WRONG_ASOF_FORMAT")
    return v

def n(v):
    if isinstance(v,bool) or v in ("",None):return None
    try:
        x=float(str(v).strip().replace(",",""))
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):return None

def normalize_info(payload,market,asof):
    if not isinstance(payload,dict) or not isinstance(payload.get("OutBlock_1"),list) or not payload["OutBlock_1"]:
        raise ValueError("BASE_INFO_MISSING_OR_EMPTY_OUTBLOCK")
    out=[];unique=set()
    for v in payload["OutBlock_1"]:
        if not isinstance(v,dict):raise ValueError("BASE_INFO_RECORD_NOT_OBJECT")
        ticker=str(v.get("ISU_SRT_CD","")).strip()
        if not re.fullmatch(r"[0-9A-Z]{6}",ticker):
            # Do not turn the 12-character standard ISIN into a fake ticker.
            continue
        if ticker in unique:raise ValueError("DUPLICATE_KRX_SHORT_SECURITY_CODE")
        unique.add(ticker)
        listed=str(v.get("LIST_DD","")).strip().replace("-","")
        if listed and not re.fullmatch(r"[0-9]{8}",listed):
            raise ValueError("BASE_INFO_INVALID_LISTING_DATE")
        if listed and listed>asof.replace("-",""):
            raise ValueError("FUTURE_LISTING_INCLUDED_IN_DATED_BASE_INFO")
        out.append(dict(asof_requested=asof,market=market,ticker=ticker,
            isin=str(v.get("ISU_CD","")).strip(),
            name=str(v.get("ISU_NM") or v.get("ISU_ABBRV") or "").strip(),
            security_group=str(v.get("SECUGRP_NM","")).strip(),
            share_kind=str(v.get("KIND_STKCERT_TP_NM","")).strip(),
            board_section=str(v.get("SECT_TP_NM","")).strip(),
            listed_date=listed,source_endpoint=ENDPOINTS[market]))
    if not out:raise ValueError("BASE_INFO_NO_JOINABLE_6CHAR_SHORT_CODES")
    return out

def retrieve(asof,outdir,key=None,fetcher=fetch_official):
    asof=fmtdate(asof)
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    meta=dict(schema=BASIC_SCHEMA,asof=asof,received_utc=datetime.now(timezone.utc).isoformat(),
        endpoints=ENDPOINTS,official_base_usable=False,official_base_approved=False,
        official_request_asof_historical_vintage_independently_certified=False,
        secugrp_and_sharekind_explicit_but_classification_conservative=True,
        official_regular_session_certified=False,official_industry_taxonomy_certified=False,
        error="KRX_AUTH_KEY_NOT_CONNECTED",market_counts={},source_file_sha256={},
        raw_response_sha256={},trade_approved=False,orders_enabled=False)
    if key:
        rows={};hashes={}
        try:
            for market,endpoint in ENDPOINTS.items():
                body,rawhash=fetcher(endpoint,asof,key)
                rows[market]=normalize_info(body,market,asof)
                hashes[market]=rawhash
            t0={r["ticker"] for r in rows["KOSPI"]}
            t1={r["ticker"] for r in rows["KOSDAQ"]}
            if t0&t1:raise ValueError("BASE_INFO_CROSS_MARKET_DUPLICATE")
            for market in ENDPOINTS:
                path=outdir/(market+"_basic_v610.csv")
                write_csv(path,rows[market],BASIC_FIELDS)
                meta["source_file_sha256"][market]=digest(path.read_bytes())
                meta["market_counts"][market]=len(rows[market])
            meta["raw_response_sha256"]=hashes
            meta["official_base_usable"]=True
            meta["official_base_approved"]=True
            meta["error"]="BASE_INFO_AVAILABLE_ASOF_REQUESTED_NOT_INDUSTRY_PIT"
        except ValueError as ex:
            for market in ENDPOINTS:
                p=outdir/(market+"_basic_v610.csv")
                if p.exists():p.unlink()
            meta["market_counts"]={}
            meta["source_file_sha256"]={}
            meta["raw_response_sha256"]={}
            # Don't leak arbitrary remote error details or key to artifacts.
            cause=str(ex)
            allowed=("KRX_AUTH_OR_SERVICE_APPROVAL_MISSING",
                "KRX_SERVICE_HTTP_ERROR","KRX_SERVICE_NETWORK_UNAVAILABLE",
                "OFFICIAL_RESPONSE_NON_JSON","OFFICIAL_RESPONSE_TOO_LARGE")
            meta["error"]=cause if cause in allowed else "BASE_INFO_RESPONSE_SCHEMA_OR_INTEGRITY_INVALID"
    (outdir/"krx_basic_v610_status.json").write_text(
        json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return meta

def load_basic(folder,meta):
    if not meta.get("official_base_usable"):return {}
    ans={}
    for market in ENDPOINTS:
        p=folder/(market+"_basic_v610.csv")
        if (not p.is_file() or digest(p.read_bytes())!=meta["source_file_sha256"].get(market)):
            raise ValueError("OFFICIAL_BASIC_FILE_SHA256_NOT_VERIFIED")
        rr=read_csv(p)
        if len(rr)!=meta["market_counts"].get(market):
            raise ValueError("OFFICIAL_BASIC_COUNT_CHANGED")
        for row in rr:
            t=row["ticker"]
            if (not re.fullmatch(r"[A-Z0-9]{6}",t) or
                row["asof_requested"]!=meta["asof"] or
                row["market"]!=market or t in ans or
                row["source_endpoint"]!=ENDPOINTS[market]):
                raise ValueError("OFFICIAL_BASIC_ROW_DATE_OR_CODE_INVALID")
            ans[t]=row
    return ans

def is_common(row):
    if not row:return False
    # Conservative explicit KRX listing labels: SECUGRP_NM='주권',
    # KIND_STKCERT_TP_NM='보통주'; anything else remains unapproved.
    return (row.get("security_group")=="주권"
            and row.get("share_kind")=="보통주")

def verify_artifacts(scan,v69):
    v=read_json(scan/"full_market_v68_status.json")
    s=read_json(v69/"sector_money_v69_status.json")
    if (v.get("schema")!=V68 or s.get("schema")!=V69
        or v.get("asof")!=s.get("asof")
        or v.get("decision")!="CASH" or s.get("decision")!="CASH"
        or v.get("trade_approved") is not False or s.get("trade_approved") is not False
        or v.get("orders_enabled") is not False or s.get("orders_enabled") is not False
        or v.get("regular_1530_only_price_certified") is not False
        or s.get("official_regular_1530_not_certified") is not True
        or s.get("ETF_membership_not_independent_PIT") is not True
        or v.get("market_v18_daily_source_sha256")!=s.get("v68_market_sha256")
        or v.get("official_market_source_response_sha256")!=s.get("v68_official_response_sha256")):
        raise ValueError("V610_UPSTREAM_DATE_OR_POLICY_PROVENANCE_CHANGED")
    cand=read_csv(scan/"full_market_v68_candidates.csv")
    method=read_csv(scan/"full_market_v68_method_research.csv")
    sectors=read_csv(v69/"sector_money_v69_all.csv")
    stocks=read_csv(v69/"sector_money_v69_candidates.csv")
    for file in ("full_market_v68_candidates.csv",
                 "full_market_v68_method_research.csv",
                 "full_market_v68_universe_audit.csv",
                 "full_market_v68_candidate_120bars.csv"):
        path=scan/file
        if not path.is_file() or digest(path.read_bytes())!=v.get("artifact_file_sha256",{}).get(file):
            raise ValueError("V610_FULLMARKET_SOURCE_FILE_SHA256_CHANGED")
    if (len(cand)!=v.get("histories_screened")
        or len(method)!=3*len(cand)
        or len(stocks)!=s.get("individual_ticker_flow_rows")
        or len(stocks)!=len(cand)
        or len(sectors)!=s.get("total_proxy_sectors")):
        raise ValueError("V610_UPSTREAM_TABLE_COUNTS_CHANGED")
    ix={}
    for row in stocks:
        t=row["ticker"]
        if t in ix or row["asof"]!=v["asof"] or row["trade_approved"]!="False":
            raise ValueError("V610_STOCK_DUPLICATE_OR_UNSAFE")
        ix[t]=row
    cset={r["ticker"] for r in cand}
    if len(cset)!=len(cand) or set(ix)!=cset:raise ValueError("V610_STOCK_UNIVERSE_DRIFT")
    sset={r["sector_id"] for r in sectors}
    if len(sset)!=len(sectors):raise ValueError("V610_DUPLICATE_SECTOR")
    for row in stocks:
        for sid in filter(None,row["mapped_strong_sectors"].split(";")):
            if sid not in sset:raise ValueError("V610_SECTOR_MEMBER_NOT_MAPPED")
    bymethod={}
    for row in method:
        k=(row["ticker"],row["method"])
        if (k in bymethod or row["ticker"] not in cset
            or row["asof"]!=v["asof"] or row["trade_approved"]!="False"
            or row["orders_enabled"]!="False"):
            raise ValueError("V610_METHOD_DUPLICATED_OR_UNSAFE")
        bymethod[k]=row
    if len(bymethod)!=3*len(cand):raise ValueError("V610_METHOD_COUNT_CHANGED")
    return v,s,cand,ix,bymethod

def risk_valid(m):
    if m["setup"]!="RESEARCH_TRIGGER_CONFIRMED_ASOF":
        return False,"NO_DATE_CONFIRMED_TECHNICAL_SETUP"
    entry=n(m.get("first_entry_reference"))
    stop=n(m.get("stop_reference"))
    ceil=n(m.get("nearest_resistance_reference"))
    rr=n(m.get("first_net_rr"))
    rr2=n(m.get("second_net_rr"))
    second=n(m.get("second_entry_reference"))
    if (entry is None or stop is None or ceil is None
        or not(stop>0 and stop<entry<ceil) or
        rr is None or rr<2 or
        second is None or rr2 is None or rr2<2 or
        not stop<second<entry):
        return False,"RISK_FIRST_PRICE_OR_BOTH_ALTERNATIVES_LT_2R"
    risk=(entry-stop)/entry
    if not .02<=risk<=.12:return False,"DAILY_STRUCTURE_RISK_NOT_2_TO_12PCT"
    if m.get("structure_reference_valid")!="True":
        return False,"STRUCTURE_REFERENCE_NOT_READY"
    return True,"BOTH_LIMIT_ALTERNATIVES_2R_RESEARCH_ONLY"

def calculate(scan,v69,basefolder):
    v,s,candidates,stocks,bymethod=verify_artifacts(scan,v69)
    bmeta=read_json(basefolder/"krx_basic_v610_status.json")
    if (bmeta.get("schema")!=BASIC_SCHEMA or bmeta.get("asof")!=v["asof"]
        or bmeta.get("trade_approved") is not False
        or bmeta.get("orders_enabled") is not False
        or bmeta.get("official_regular_session_certified") is not False
        or bmeta.get("official_industry_taxonomy_certified") is not False):
        raise ValueError("V610_BASIC_SOURCE_DATE_OR_SAFETY_CHANGED")
    base=load_basic(basefolder,bmeta)
    if bmeta["official_base_usable"]:
        # base-info and EOD universe membership are NOT guaranteed identical;
        # fail-shut per absent ticker rather than silently mapping by ISIN.
        if not all(vv["market"] in ENDPOINTS for vv in base.values()):
            raise ValueError("V610_BAD_BASIC_MARKET")
    rows=[]
    for c in candidates:
        t=c["ticker"];srow=stocks[t];info=base.get(t)
        if info is not None and info["market"]!=c["market"]:
            raise ValueError("V610_ISSUER_MARKET_MISMATCH")
        methods=[bymethod[(t,m)] for m in
                 ("FIRST_PULLBACK_RECLAIM","BREAKOUT_RETEST","TREND_PULLBACK")]
        confirmed=[m for m in methods if m["setup"]=="RESEARCH_TRIGGER_CONFIRMED_ASOF"]
        passmethod=[m for m in methods if risk_valid(m)[0]]
        selected=sorted(passmethod,
             key=lambda m:(-float(m["first_net_rr"]),m["method"]))
        chosen=selected[0] if selected else (
            confirmed[0] if confirmed else None)
        qual=(srow["is_in_strict_strong_sector"]=="True" and
              srow["c3_liquidity_ok"]=="True" and
              srow["five_day_source_flow_complete"]=="True" and
              srow["foreign_institution_buy_signal_research_only"]=="True")
        blockers=[]
        if not qual:blockers.append("STRONG_SECTOR_C3_LIQUIDITY_OR_5D_FI_NOT_MET")
        if not info:blockers.append("OFFICIAL_BASE_INFO_MISSING_OR_NOT_APPROVED")
        elif not is_common(info):blockers.append("KRX_EXPLICIT_ORDINARY_SHARE_NOT_CONFIRMED")
        if not confirmed:blockers.append("NO_DATE_CONFIRMED_TECHNICAL_SETUP")
        elif not passmethod:blockers.append("BOTH_ALTERNATIVES_2R_STRUCTURE_GATE_FAILED")
        blockers+=["FINANCIAL_DATA_AND_CATALYST_ASOF_NOT_INDEPENDENTLY_VERIFIED",
                   "KRX_REGULAR_1530_ONLY_NOT_VERIFIED",
                   "HISTORIC_120BAR_NOT_OFFICIALLY_INDEPENDENTLY_VERIFIED",
                   "FINAL_80POINT_GATE_NOT_VERIFIED",
                   "PIT_SECTOR_INDUSTRY_CLASSIFICATION_NOT_VERIFIED"]
        rows.append(dict(asof=v["asof"],ticker=t,name=c["name"],market=c["market"],
            proxy_strong_sectors=srow["mapped_strong_sectors"],
            c3_liquid=srow["c3_liquidity_ok"]=="True",
            five_day_flow_complete=srow["five_day_source_flow_complete"]=="True",
            five_day_net_buy_krw=n(srow["foreign_plus_institution_5d_krw"]),
            prelim_c3_score=int(c["preliminary_c3_score"]),
            prelim_k100_score=int(c["preliminary_k100_score"]),
            official_base_api_available=bool(bmeta["official_base_usable"] and info),
            official_equity_group_verified=bool(info and info["security_group"]=="주권"),
            common_share_basic_info_verified=is_common(info),
            official_board_section_not_industry=(info["board_section"] if info else ""),
            sector_proxy_pit_verified=False,
            sector_liquidity_money_flow_research_gate=qual,
            sector_qualified_research_rank=None,
            confirmed_method_count=len(confirmed),
            risk_first_method=chosen["method"] if chosen else "",
            daily_structure_stop=n(chosen["stop_reference"]) if chosen else None,
            first_entry_reference=n(chosen["first_entry_reference"]) if chosen else None,
            second_alternative_reference=n(chosen["second_entry_reference"]) if chosen else None,
            nearest_ceiling_reference=n(chosen["nearest_resistance_reference"]) if chosen else None,
            first_net_reward_risk=n(chosen["first_net_rr"]) if chosen else None,
            second_net_reward_risk=n(chosen["second_net_rr"]) if chosen else None,
            risk_geometry_2r_pass=bool(passmethod),
            technical_trigger_confirmed=bool(confirmed),
            financial_data_asof_verified=False,
            earnings_catalyst_asof_verified=False,
            regular_1530_eod_certified=False,
            historical_120bar_independently_verified=False,
            complete_80point_certified=False,
            trade_approved=False,orders_enabled=False,
            blocking_reasons=";".join(blockers)))
    qualified=sorted((r for r in rows if r["sector_liquidity_money_flow_research_gate"]),
          key=lambda r:(-r["prelim_c3_score"],-(r["five_day_net_buy_krw"] or 0),r["ticker"]))
    for i,r in enumerate(qualified[:20],1):r["sector_qualified_research_rank"]=i
    shortlist=[]
    for r in qualified[:20]:
        shortlist.append(dict(rank=r["sector_qualified_research_rank"],
            sector=r["proxy_strong_sectors"],asof=r["asof"],
            ticker=r["ticker"],name=r["name"],
            prelim_c3_score=r["prelim_c3_score"],
            actual_turnover_krw=next(float(x["turnover_krw"])
                for x in candidates if x["ticker"]==r["ticker"]),
            foreign_plus_institution_5d_krw=r["five_day_net_buy_krw"],
            official_common_share_proof=r["common_share_basic_info_verified"],
            technical_confirmed=r["technical_trigger_confirmed"],
            risk_2r_both_entries=r["risk_geometry_2r_pass"],
            trade_approved=False,reason=r["blocking_reasons"]))
    report=dict(schema=SCHEMA,asof=v["asof"],
        v68_market_sha256=v["market_v18_daily_source_sha256"],
        v69_flow_sha256=s["flow_source_sha256"],
        v68_source_run_id=v.get("source_v18_github_run_id",""),
        basic_api_error=bmeta["error"],
        official_basic_api_usable=bool(bmeta["official_base_usable"]),
        official_basic_market_rows=sum(bmeta["market_counts"].values()),
        full_market_initial_codes=v["asof_universe_count"],
        input_v68_candidates=len(candidates),
        input_v69_candidates=len(stocks),
        strong_proxy_sectors=s["strict_strong_sectors"],
        strong_sector_research_shortlist_count=len(qualified),
        shortlist_top20_actual_count=len(shortlist),
        candidates_basic_common_share_verified=sum(r["common_share_basic_info_verified"] for r in rows),
        candidates_with_confirmed_3technical_setup=sum(r["technical_trigger_confirmed"] for r in rows),
        candidates_with_both_2R_reference=sum(r["risk_geometry_2r_pass"] for r in rows),
        in_strong_sector_with_confirmed_setup=sum(
            r["sector_liquidity_money_flow_research_gate"] and r["technical_trigger_confirmed"] for r in rows),
        in_strong_sector_with_both_2R=sum(
            r["sector_liquidity_money_flow_research_gate"] and r["risk_geometry_2r_pass"] for r in rows),
        in_strong_sector_with_common_2R=sum(
            r["sector_liquidity_money_flow_research_gate"] and
            r["risk_geometry_2r_pass"] and r["common_share_basic_info_verified"] for r in rows),
        issuer_board_section_is_not_formal_sector_classification=True,
        independent_PIT_issuer_vintage_verified=False,
        asof_earnings_and_catalyst_verified=False,
        exact_regular_1530_prices_verified=False,
        all_120day_official_daily_bars_verified=False,
        final_80point_certified=False,
        trade_approved=False,orders_enabled=False,decision="CASH")
    return report,rows,shortlist

def emit(folder,report,rows,short):
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"issuer_entry_v610_status.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    write_csv(folder/"issuer_entry_v610_all.csv",rows,ROW_FIELDS)
    write_csv(folder/"issuer_entry_v610_sector_top20.csv",short,SHORT_FIELDS)
    lines=["# v6.10 KRX 종목기본정보 + 섹터 내 1차/2차 구조손절 우선",
           "",f"확인 기준일 {report['asof']} · **CASH / 매수승인 0**",
           f"KRX 공식 종목기본정보: **{report['basic_api_error']}**",
           f"공식 기본정보 요청에서 확보된 종목정보 {report['official_basic_market_rows']}건",
           f"전체시장 {report['full_market_initial_codes']}종목 중 기술예비후보 {report['input_v68_candidates']}개",
           f"강세 섹터·C3유동성·기관/외국인 순매수 조건을 모두 충족한 연구종목: {report['strong_sector_research_shortlist_count']}개",
           f"위 조건 내 확인된 기술 신호: {report['in_strong_sector_with_confirmed_setup']}개",
           f"위 조건 내 1차/2차 모두 최소 2R 구조: {report['in_strong_sector_with_both_2R']}개",
           "", "## 최대 20개 연구후보 (실제 통과 종목만 표시)",
           "| 종목 | 강세 섹터 대용 | 예비기술점수 | 보통주 공식정보 | 기술자리 | 양쪽 2R |",
           "|---|---|---:|---|---|---|"]
    for r in short:
        lines.append(f"| {r['name']}({r['ticker']}) | {r['sector']} | {r['prelim_c3_score']} | "+
            f"{'확인' if r['official_common_share_proof'] else '미확인'} | "+
            f"{'감지' if r['technical_confirmed'] else '없음'} | "+
            f"{'통과' if r['risk_2r_both_entries'] else '미통과'} |")
    if not short:lines.append("| 적격 연구후보 없음 | — | — | — | — | — |")
    lines+=["","**참고: KRX 기본정보의 소속부(SECT_TP_NM)는 산업 업종분류가 아닙니다.**",
            "보통주와 우선주는 주식종류 필드에 명시돼 있는 경우에만 구별합니다.",
            "당일 15:30 종가·재무/촉매·120일 공식 이력·최종80점·현금·구조손절이 확정되지 않았다면 시장 매수를 승인하지 않습니다.",
            "## Required Next Data",
            "독립 정규장 15:30 분리 가격, 공식 업종/주식종류 PIT, 최초공시 실적·수주일자, 검증된 구조손절 2R, 현금/보유 및 5거래일 전진가격."]
    (folder/"issuer_entry_v610_mobile.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

def main():
    p=argparse.ArgumentParser()
    for nm in ("--scan","--v69","--outdir"):p.add_argument(nm,required=True,type=Path)
    p.add_argument("--basic",type=Path)
    p.add_argument("--collect",action="store_true")
    a=p.parse_args()
    asof=read_json(a.scan/"full_market_v68_status.json")["asof"]
    base=a.basic or a.outdir/"basic"
    if not (base/"krx_basic_v610_status.json").is_file() or a.collect:
        retrieve(asof,base,os.environ.get("KRX_AUTH_KEY") if a.collect else None)
    report,rows,short=calculate(a.scan,a.v69,base)
    emit(a.outdir,report,rows,short)
    print("V610_KRX_COMMON_SHARE_2R_SECTOR_ISSUER_GATE",
          json.dumps({k:report[k] for k in ("asof","official_basic_api_usable",
            "candidates_basic_common_share_verified",
            "strong_sector_research_shortlist_count",
            "in_strong_sector_with_confirmed_setup",
            "in_strong_sector_with_both_2R","decision")},ensure_ascii=False))
if __name__=="__main__":main()
