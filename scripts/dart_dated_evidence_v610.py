#!/usr/bin/env python3
"""v6.10.1 conservative date-only OpenDART receipts for KRX research.

Preceding-day receipts only; same-asof receipts cannot prove historical
publication time. Report-title observation != content-read earnings results.
Never hallucinate performance, signed deal amount, forecast, or verified
positive catalyst; no trading orders or final 80-point BUY.
"""
from __future__ import annotations
import argparse,csv,json,re
from collections import defaultdict,Counter
from datetime import date,timedelta
from pathlib import Path
from forward_ledger_v63 import read_csv,read_json,digest
from official_issuer_entry_v610 import SCHEMA as V610

SCHEMA="C3_K100_DART_DATE_ONLY_DISCLOSURE_V6101"
SOURCE_FIELDS=("ticker","corp_code","corp_name","report_name","receipt_no",
               "receipt_date","url","published_precision","collected_at","source")
ROWS=("asof","ticker","name","sector_flow_watch",
      "prior_30_calendar_day_receipts","prior_30day_receipt_titles_earnings",
      "prior_30day_receipt_titles_contract","prior_30day_receipt_titles_buyback",
      "prior_30day_receipt_titles_amendment","latest_preceding_receipt_date",
      "latest_preceding_report_title","latest_preceding_receipt_no",
      "same_day_receipts_excluded_unknown_publication_time",
      "headline_only_not_financial_statement","intraday_point_in_time_verified",
      "actual_earnings_direction_verified","contract_amount_verified",
      "verified_fresh_catalyst","trade_approved","orders_enabled")
REPORTS=("ticker","name","receipt_date","receipt_no","report_name",
         "url","report_title_category","date_only_not_publication_time",
         "report_content_verified","trade_approved","orders_enabled")

def report_categories(text):
    s=str(text)
    result=[]
    if "실적" in s or "재무제표" in s:result.append("EARNINGS_OR_FINANCIAL_TITLE")
    if "수주" in s or "단일판매" in s or "공급계약" in s:result.append("CONTRACT_OR_ORDER_TITLE")
    if "자기주식" in s or "주식소각" in s:result.append("SHARE_BUYBACK_OR_CANCEL_TITLE")
    if "기재정정" in s or "정정신고" in s:result.append("AMENDED_REPORT_TITLE")
    return result or ["OTHER_DISCLOSURE_TITLE"]

def calculate(v18,v610):
    manifest=read_json(v610/"issuer_entry_v610_status.json")
    listed=read_csv(v610/"issuer_entry_v610_all.csv")
    v18stat=read_json(v18/"diagnostics/collection_status.json")
    if (manifest.get("schema")!=V610
        or manifest.get("trade_approved") is not False
        or manifest.get("orders_enabled") is not False
        or manifest.get("exact_regular_1530_prices_verified") is not False
        or manifest.get("asof")!=v18stat.get("asof")
        or v18stat.get("orders_enabled") is not False
        or v18stat.get("datasets",{}).get("dart",{}).get("status")!="DATE_ONLY_COMPLETE"
        or v18stat.get("datasets",{}).get("dart",{}).get("exact_publication_time")!="UNAVAILABLE"):
        raise ValueError("DART_ASOF_OR_PUBLICATION_TIME_POLICY_INVALID")
    asof=date.fromisoformat(manifest["asof"])
    if asof.isoformat()!=manifest["asof"]:raise ValueError("DART_ASOF_DATE_INVALID")
    threshold=asof-timedelta(days=30)
    details=read_csv(v18/"catalysts/disclosures.csv")
    if (not details or len(details)!=v18stat["datasets"]["dart"]["rows"]
        or tuple(details[0])!=SOURCE_FIELDS):
        raise ValueError("DART_RAW_DISCLOSURE_COVERAGE_OR_SCHEMA_BAD")
    candidates={x["ticker"]:x for x in listed}
    if len(candidates)!=len(listed) or len(listed)!=manifest["input_v68_candidates"]:
        raise ValueError("V610_CANDIDATE_SET_NOT_COMPLETE")
    groups=defaultdict(list);unique=set();same_day=defaultdict(int)
    for r in details:
        t=r.get("ticker","");num=r.get("receipt_no","")
        if (not re.fullmatch(r"[A-Z0-9]{6}",t)
            or not re.fullmatch(r"[0-9]{14}",num or "")
            or num in unique
            or r.get("published_precision")!="DAY_ONLY_no_intraday_time"
            or r.get("source")!="OPENDART_list"):
            raise ValueError("DART_RECEIPT_NOT_REPRODUCIBLE")
        unique.add(num)
        d=date.fromisoformat(r["receipt_date"])
        if d.isoformat()!=r["receipt_date"] or d>asof:
            raise ValueError("DART_FUTURE_RECEIPT_OR_DATE_NOT_ASOF")
        if t not in candidates:continue
        if d==asof:
            same_day[t]+=1
        elif threshold<=d<asof:
            groups[t].append(r)
    output=[];receipts=[]
    for t,stock in sorted(candidates.items()):
        if stock["asof"]!=manifest["asof"] or stock["trade_approved"]!="False":
            raise ValueError("DART_UPSTREAM_RESEARCH_STOCK_MUTATED")
        sample=sorted(groups[t],key=lambda x:(x["receipt_date"],x["receipt_no"]),reverse=True)
        cc=Counter(kind for x in sample for kind in report_categories(x["report_name"]))
        recent=sample[0] if sample else None
        output.append(dict(asof=manifest["asof"],ticker=t,name=stock["name"],
            sector_flow_watch=stock["sector_liquidity_money_flow_research_gate"]=="True",
            prior_30_calendar_day_receipts=len(sample),
            prior_30day_receipt_titles_earnings=cc["EARNINGS_OR_FINANCIAL_TITLE"],
            prior_30day_receipt_titles_contract=cc["CONTRACT_OR_ORDER_TITLE"],
            prior_30day_receipt_titles_buyback=cc["SHARE_BUYBACK_OR_CANCEL_TITLE"],
            prior_30day_receipt_titles_amendment=cc["AMENDED_REPORT_TITLE"],
            latest_preceding_receipt_date=recent["receipt_date"] if recent else "",
            latest_preceding_report_title=recent["report_name"] if recent else "",
            latest_preceding_receipt_no=recent["receipt_no"] if recent else "",
            same_day_receipts_excluded_unknown_publication_time=same_day[t],
            headline_only_not_financial_statement=True,
            intraday_point_in_time_verified=False,
            actual_earnings_direction_verified=False,
            contract_amount_verified=False,
            verified_fresh_catalyst=False,trade_approved=False,orders_enabled=False))
        for r in sample:
            receipts.append(dict(ticker=t,name=stock["name"],receipt_date=r["receipt_date"],
                receipt_no=r["receipt_no"],report_name=r["report_name"],
                url=r["url"],report_title_category=";".join(report_categories(r["report_name"])),
                date_only_not_publication_time=True,report_content_verified=False,
                trade_approved=False,orders_enabled=False))
    watch=[r for r in output if r["sector_flow_watch"]]
    report=dict(schema=SCHEMA,asof=manifest["asof"],
        v610_v18_source_run_id=manifest["v68_source_run_id"],
        upstream_v610_candidates=manifest["input_v68_candidates"],
        date_only_source_receipt_count=len(details),
        dart_source_sha256=digest((v18/"catalysts/disclosures.csv").read_bytes()),
        observation_window_days=30,
        strictly_preceding_receipts_captured=len(receipts),
        same_day_receipts_excluded=sum(same_day.values()),
        stocks_with_strict_prior_receipt=sum(r["prior_30_calendar_day_receipts"]>0 for r in output),
        strong_sector_watch_stocks=len(watch),
        strong_sector_watch_prior_earnings_title_count=sum(r["prior_30day_receipt_titles_earnings"] for r in watch),
        strict_intraday_PIT_publication_time_available=False,
        title_keywords_are_not_positive_earnings_verification=True,
        news_archive_available=False,
        fundamental_growth_checked=False,
        catalyst_effect_and_amount_checked=False,
        score80_final_checked=False,
        trade_approved=False,orders_enabled=False,decision="CASH")
    return report,output,receipts

def write_outputs(out,report,rows,receipts):
    out.mkdir(parents=True,exist_ok=True)
    (out/"dart_date_only_v610_status.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for name,fields,data in (
        ("dart_date_only_v610_all.csv",ROWS,rows),
        ("dart_date_only_v610_prior_receipts.csv",REPORTS,receipts)):
        with (out/name).open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
            w.writeheader();w.writerows(data)
    lines=["# v6.10.1 OpenDART 실적·수주 공시 제목의 날짜 검증",
           "",f"{report['asof']} 마감기준 / **CASH · 신규매수 0**",
           f"OpenDART 날짜만 있는 공시 {report['date_only_source_receipt_count']:,}건 검사",
           f"52개 후보의 전일 이전 최근 30일 공시 제목 {report['strictly_preceding_receipts_captured']}건",
           f"같은 날짜 수신 공시 {report['same_day_receipts_excluded']}건은 발표시각 증명 불가로 제외",
           "", "| 섹터 수급 연구후보 | 최근 30일 공시수 | 실적·재무 제목수 | 최신 공시 |",
           "|---|---:|---:|---|"]
    for r in rows:
        if not r["sector_flow_watch"]:continue
        lines.append(f"| {r['name']}({r['ticker']}) | {r['prior_30_calendar_day_receipts']} | "+
            f"{r['prior_30day_receipt_titles_earnings']} | "+
            f"{r['latest_preceding_receipt_date'] or '없음'} |")
    lines+=["","**보고서 제목이 있다는 사실은 실적이 개선됐거나 수주금액이 늘었다는 증거가 아닙니다.**",
           "세부 공시 내용/계약금액/잠정실적·전년동기 성장률·정확한 공개시각은 아직 확인하지 않았습니다.",
           "같은 거래일 공시는 시각을 알 수 없으므로 뒤늦게 나온 공시를 과거 매수사유에 넣지 않았습니다.",
           "", "## Required Next Data",
           "DART 보고서 내용과 최초공개시각, 분기/연결 영업이익 및 전년동기 성장률, 재무 건전성, 정규장 가격 확인."]
    (out/"dart_date_only_v610_mobile.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

def main():
    a=argparse.ArgumentParser()
    for s in ("--v18","--v610","--outdir"):
        a.add_argument(s,required=True,type=Path)
    p=a.parse_args()
    r,rows,docs=calculate(p.v18,p.v610)
    write_outputs(p.outdir,r,rows,docs)
    print("V6101_DATE_ONLY_DART_CAUSAL_EVIDENCE",
          json.dumps({k:r[k] for k in (
            "asof","date_only_source_receipt_count",
            "strictly_preceding_receipts_captured",
            "same_day_receipts_excluded",
            "strong_sector_watch_prior_earnings_title_count","decision")},ensure_ascii=False))
if __name__=="__main__":main()
