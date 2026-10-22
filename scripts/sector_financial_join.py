#!/usr/bin/env python3
"""Join dated DART financial research with sector-first top5 (NO auto BUY).

An incomplete financial source may never become a zero-earnings or zero-risk
score. Financially stronger stocks appear in a SEPARATE watchlist, not
retroactively substituted into the pre-recorded price-only TOP5 cohort.
"""
import argparse,json,math
from pathlib import Path

PASS="ANNUAL_GROWTH_AND_MARGIN_OBSERVED"
def proxy_value(v):
    try:
        f=float(v)
        return f if math.isfinite(f) else -1
    except (ValueError,TypeError):return -1

def join(base,finance):
    out=dict(base)
    asof=str(base.get("asof") or "")
    sectors={x.get("sector_id") for x in base.get("sector_top3",[])}
    match=(finance.get("schema")=="opendart_annual_research_v1"
           and finance.get("asof")==asof and bool(asof))
    available={}
    if match:
        for r in finance.get("researched",[]):
            t=str(r.get("ticker",""))
            if r.get("sector_id") not in sectors or len(t)!=6 or not t.isdigit():
                continue
            if r.get("status")!="DATED_ANNUAL_RESEARCH_ONLY":
                continue
            filing_date=str(r.get("receipt_date",""))
            if not filing_date or filing_date>asof:continue
            if r.get("financial_quality") not in (
                PASS,"ANNUAL_POSITIVE_MIXED","ANNUAL_RISK_OR_SLOWDOWN"):
                continue
            available[t]=r
    top=[]
    for s in base.get("stock_research_top5",[]):
        r=dict(s)
        financial=available.get(str(r.get("ticker","")))
        r["fundamentals_filing_verified"]=bool(financial)
        r["financial_quality"]=financial["financial_quality"] if financial else "NOT_VERIFIED"
        r["financial_screen_pass"]=bool(financial and financial.get("financial_screen_pass"))
        r["financial_receipt_url"]=financial.get("receipt_url") if financial else None
        r["financial_report_year"]=financial.get("annual_fiscal_year") if financial else None
        r["final_verified_score"]=None
        r["buy_approval"]="NO"
        top.append(r)
    out["stock_research_top5"]=top
    qualified=[dict(ticker=x["ticker"],name=x.get("name",x["ticker"]),
                    sector_id=x["sector_id"],
                    research_proxy_index=proxy_value(x.get("research_proxy_index")),
                    sales_yoy_pct=x.get("sales_yoy_pct"),
                    operating_margin_pct=x.get("operating_margin_pct"),
                    audited_financial_statement_division=x.get("division"),
                    annual_fiscal_year=x.get("annual_fiscal_year"),
                    annual_receipt_url=x.get("receipt_url"),
                    quality_kind="DATED_ANNUAL_PRICE_FLOW_RESEARCH_ONLY",
                    trade_approval="NO")
        for x in available.values() if x.get("financial_screen_pass")]
    qualified.sort(key=lambda s:(-s["research_proxy_index"],s["ticker"]))
    out["financial_quality_watch_top5"]=qualified[:5]
    out["financial_evidence_status"]=(finance.get("status") if match
                                       else "MISSING_OR_DATE_MISMATCH")
    out["fundamentals_full_final_15_points_scored"]=False
    out["financial_evidence_enriched_count"]=len(available)
    out["final_stock_85_point_score_verified"]=False
    out["trade_approved"]=False
    out["decision"]="CASH"
    out["orders_enabled"]=False
    return out

def render(report,original=""):
    lines=["","## 재무·실적 검증: 연간 공시와 TOP5의 구분","",
        "출처: OpenDART 공시 접수일이 분석일 이전인 사업보고서만 사용합니다. "
        "최종 실적·미래 전망 검증 전 매수 승인은 없습니다.",
        "재무 수집 상태: "+str(report.get("financial_evidence_status","UNKNOWN")),"",
        "| 종목 | 매출 성장률 | 영업이익률 | 연결/별도 |",
        "|---|---:|---:|---|"]
    for x in report.get("financial_quality_watch_top5",[]):
        lines.append("| "+str(x.get("name"))+" | "+
          str(x.get("sales_yoy_pct"))+"% | "+str(x.get("operating_margin_pct"))+
          "% | "+str(x.get("audited_financial_statement_division"))+" |")
    if not report.get("financial_quality_watch_top5"):
        lines.append("| 연간 실적 검증된 성장 후보 없음 | — | — | — |")
    lines+=["","*상기 재무 적격 후보는 원래 기술적 TOP5에 강제로 편입하지 않은 **별도 연구 목록**입니다.",
            "*업종별 적정 부채비율·현금흐름, 최신 분기 실적, 수주잔고, 컨센서스 및 상승 타점은 별도 검증 대상입니다.",
            "*공식 공시가 없거나 OpenDART 키가 누락된 경우 실적을 추정하거나 15점을 임의로 채우지 않습니다.",""]
    return original.rstrip()+"\n"+"\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("output"))
    a=p.parse_args()
    target=a.root/"sector_first_with_prices.json"
    if not target.is_file():
        raise SystemExit("NO_DATED_PRICE_REPORT")
    base=json.loads(target.read_text(encoding="utf-8"))
    src=a.root/"financial_research.json"
    try:finance=json.loads(src.read_text(encoding="utf-8")) if src.is_file() else {}
    except (ValueError,OSError):finance={}
    joined=join(base,finance)
    (a.root/"sector_first_with_financials.json").write_text(
        json.dumps(joined,ensure_ascii=False,indent=2),encoding="utf-8")
    compact=a.root/"sector_first_compact_mobile.md"
    if compact.is_file():
        compact.write_text(render(joined,compact.read_text(encoding="utf-8")),encoding="utf-8")
    print(json.dumps(dict(finance_status=joined["financial_evidence_status"],
       usable=joined["financial_evidence_enriched_count"],
       financial_quality_watch=len(joined["financial_quality_watch_top5"]),
       decision="CASH"),ensure_ascii=False))

if __name__=="__main__":main()
