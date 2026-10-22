#!/usr/bin/env python3
"""Company-specific evidence matrix for C3/K100 sector research.

This is the bridge BETWEEN overseas discovery, official DART, completed KRX
money flow, quarterly finance, and daily chart structure. It is NOT a trading
signal. A sector article MUST NOT be attributed as a confirmed company catalyst.
Never turn a headline/filing title into an invented final-100 score.
"""
import argparse,json,re
from datetime import date,datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

VERSION="company_evidence_matrix_v1"
VALID_PRICE=("HISTORICAL_DAILY_REFERENCE_ONLY",)
BAD_PRICE=("CROSS_SOURCE_CLOSE_CONFLICT","FOCUS_DATE_MISMATCH")
GOOD_INTERIM="DATED_INTERIM_YTD_RESEARCH_ONLY"
GOOD_ANNUAL="DATED_ANNUAL_RESEARCH_ONLY"
STOCK_PATTERN=re.compile(r"^[0-9]{6}$")

def iso(v):
    try:return date.fromisoformat(str(v)[:10])
    except (TypeError,ValueError):return None

def asof_seen(seen,asof):
    """GDELT first discovery must not be *after* the requested market day."""
    if not seen:return False
    try:
        dt=datetime.fromisoformat(str(seen).replace("Z","+00:00"))
        if dt.tzinfo is None:return False
        return dt.astimezone(ZoneInfo("Asia/Seoul")).date()<=asof
    except (ValueError,TypeError):return False

def official_url(url):
    """Only DART receipt URL can be direct issuer evidence in this report."""
    if not isinstance(url,str):return None
    try:u=urlsplit(url)
    except ValueError:return None
    if u.scheme!="https" or u.hostname!="dart.fss.or.kr":return None
    if re.fullmatch(r"/dsaf001/main.do",u.path) and re.fullmatch(
      r"rcpNo=[0-9]{14}",u.query):
        return url
    return None

def finite_number(v):
    try:
        x=float(v)
        return x if x==x and abs(x)!=float("inf") else None
    except (TypeError,ValueError):return None

def build(report,contracts=None):
    asof=iso(report.get("asof"))
    contracts=(contracts if isinstance(contracts,dict) and
        contracts.get("schema")=="dart_contract_source_v1" and
        contracts.get("asof")==str(asof) else {})
    issuer_docs={str(x.get("ticker")):x for x in
        contracts.get("issuer_samples",[]) if isinstance(x,dict)}
    stocks=report.get("stock_research_top5") or []
    sectors=report.get("sector_top3") or []
    leader=report.get("sector_leader_watch") or []
    financial_watch=report.get("financial_quality_watch_top5") or []
    financial_dual=report.get("annual_plus_interim_growth_watch_top5") or []
    sector_map={str(s.get("sector_id")):s for s in sectors}
    market_gate=bool(report.get("daily_money_rank_applied") is True)
    matrix=[]
    seen=set()
    candidates=[]
    for kind,source in [("ABSOLUTE_TOP5",stocks),
                        ("SECTOR_LEADER_WATCH",leader),
                        ("ANNUAL_GROWTH_WATCH",financial_watch),
                        ("ANNUAL_AND_INTERIM_GROWTH_WATCH",financial_dual)]:
        for original in source:
            ticker=str(original.get("ticker",""))
            if not STOCK_PATTERN.fullmatch(ticker) or ticker in seen:continue
            sid=str(original.get("sector_id",""))
            if sid not in sector_map:continue
            seen.add(ticker)
            candidates.append((kind,original))
    annual={str(x.get("ticker")):x for x in financial_watch}
    dual={str(x.get("ticker")):x for x in financial_dual}
    stock_top={str(x.get("ticker")):x for x in stocks}
    for kind,original in candidates[:20]:
        t=str(original["ticker"]);sid=str(original["sector_id"])
        sector=sector_map[sid]
        price=stock_top.get(t,{})
        finances=annual.get(t,{})
        issuer=issuer_docs.get(t,{})
        prelim=[]
        for notice in issuer.get("latest_preliminary_earnings",[])[:2]:
            date_=iso(notice.get("date"))
            url=official_url(notice.get("url"))
            if not(asof and date_ and date_<asof and
                   (asof-date_).days<=7 and url):continue
            study=notice.get("original_financial_analysis") or {}
            verified=(notice.get("financial_figures_verified") is True and
                study.get("status")=="PRELIMINARY_SINGLE_QUARTER_SOURCE_RESEARCH_ONLY" and
                study.get("preliminary_figures_source_verified") is True and
                study.get("receipt_no")==notice.get("receipt_no") and
                study.get("receipt_date")==str(date_))
            prelim.append(dict(date=str(date_),url=url,
                title=str(notice.get("title",""))[:120],
                financial_figures_verified=verified,
                quarter_end=study.get("quarter_period",{}).get("current_end")
                    if verified else None,
                preliminary_revenue_yoy_pct=study.get("revenue_yoy_pct")
                    if verified else None,
                preliminary_operating_profit_yoy_pct=study.get("operating_profit_yoy_pct")
                    if verified else None,
                preliminary_earnings_quality=study.get("earnings_quality")
                    if verified else "UNVERIFIED",
                original_source_status=notice.get("original_financial_status",
                                             "NOT_DOWNLOADED"),
                recent_quarter_catalyst_verified=False))
        # Make the newest as-of notice authoritative even if API rows are
        # unordered. Do not let an older parsed statement override a newer
        # unparsed correction or withdrawn statement.
        prelim.sort(key=lambda x:(x["date"],x["url"]),reverse=True)
        newest_prelim=prelim[0] if prelim else None
        latest_prelim_unverified=bool(
            newest_prelim and not newest_prelim["financial_figures_verified"])
        originals=[]
        for filing in issuer.get("filings",[])[:3]:
            filed=iso(filing.get("date"))
            receipt=str(filing.get("receipt_no",""))
            url=official_url(filing.get("url"))
            if (not asof or not filed or filed>=asof or
                (asof-filed).days>7 or
                not re.fullmatch(r"\d{14}",receipt) or
                not url or receipt not in url):
                continue
            terms=filing.get("structured_contract_terms") or {}
            originals.append(dict(receipt_no=receipt,date=str(filed),
                title=str(filing.get("title",""))[:110],
                url=url,original_status=filing.get("filing_contents_status"),
                correction_risk=filing.get("correction_risk"),
                typed_term_status=terms.get("status","NO_TYPED_CONTRACT_AMOUNT"),
                document_amount_krw=terms.get("amount_krw"),
                document_sales_ratio_pct=terms.get("disclosed_sales_ratio_pct"),
                single_filing_arithmetic_status=terms.get("consistency","NOT_TESTABLE"),
                potential_intragroup_revenue_recognition_risk=bool(
                    terms.get("potential_intragroup_revenue_recognition_risk")),
                counterparty_affiliation_review=terms.get(
                    "counterparty_affiliation_review","COUNTERPARTY_NOT_VERIFIED"),
                raw_xml_cells_are_corroborated_contract_terms=False,
                actual_revenue_effect_verified=False))
        direct=[]
        for filing in sector.get("prior_day_dart_observations",[]) or []:
            if str(filing.get("ticker",""))!=t:continue
            d=iso(filing.get("date"))
            url=official_url(filing.get("url"))
            if not(asof and d and d<asof and (asof-d).days<=5 and url):continue
            direct.append(dict(title=str(filing.get("title",""))[:100],
                 filing_date=d.isoformat(),url=url,
                 material_impact="NOT_CONTENT_VERIFIED"))
        unique={}
        for x in direct:unique[x["url"]]=x
        direct=sorted(unique.values(),key=lambda x:x["filing_date"],reverse=True)[:3]
        global_items=[]
        for item in sector.get("global_news_observations",[]) or []:
            if not asof or not asof_seen(item.get("seen_at_utc"),asof):continue
            # URLs previously validated in global discovery; still only
            # include HTTPS and never treat press as confirmed direct impact.
            url=str(item.get("url",""))
            try:u=urlsplit(url)
            except ValueError:continue
            if u.scheme!="https" or not u.hostname:continue
            global_items.append(dict(title=str(item.get("title",""))[:90],
                  url=url,first_discovered_utc=item.get("seen_at_utc"),
                  meaning="SECTOR_CONTEXT_ONLY_NOT_COMPANY_IMPACT"))
        # Avoid same global article counted multiple times.
        dedup_global={i["url"]:i for i in global_items}
        global_items=list(dedup_global.values())[:2]
        has_money=market_gate and finite_number(
            sector.get("day_net_flow_1d_incremental_krw")) is not None and (
                finite_number(sector.get("day_net_flow_1d_incremental_krw"))>0)
        verified_interim=bool(price.get("latest_periodic_financials_verified")) or (
            bool(finances.get("latest_periodic_financials_verified")))
        dual_growth=bool(price.get("annual_plus_interim_growth_pass")) or (
            t in dual and dual[t].get("annual_plus_interim_growth_pass") is True)
        historical_weakness=bool(price.get("recent_financial_weakening_veto") or
                      finances.get("recent_financial_weakening_veto"))
        preliminary_weakness=bool(
            newest_prelim and newest_prelim["financial_figures_verified"] and
            newest_prelim["preliminary_earnings_quality"]=="RECENT_PRELIMINARY_WEAKENING")
        weakness=historical_weakness or preliminary_weakness
        # Annual+interim growth was historically observed, but it cannot
        # stand as a *current* combined growth signal once a newer
        # unverified Q3/Q4 preliminary result exists.
        if weakness or latest_prelim_unverified:dual_growth=False
        conflict=t in (report.get("focus_close_conflict_tickers") or []) or (
            price.get("independent_stop_status")=="CROSS_SOURCE_CLOSE_CONFLICT")
        stop=finite_number(price.get("independently_collected_daily_stop_reference"))
        price_ready=(kind=="ABSOLUTE_TOP5" and not conflict and
            price.get("independent_stop_status") in VALID_PRICE and
            stop is not None and stop>0 and
            bool(price.get("independent_first_entry_reference")))
        annual_verified=bool(price.get("fundamentals_filing_verified")) or (
             t in annual and annual[t].get("sales_yoy_pct") is not None)
        checks=dict(positive_daily_sector_flow=has_money,
            annual_filing_verified=annual_verified,
            current_interim_ytd_verified=verified_interim,
            annual_and_interim_growth=dual_growth,
            recent_ytd_weakening=historical_weakness,
            recent_preliminary_quarter_weakening=preliminary_weakness,
            any_recent_earnings_weakening=weakness,
            direct_dart_filing_title_observed=bool(direct),
            global_sector_article_observed=bool(global_items),
            completed_daily_structure_reference=price_ready,
            price_conflict=conflict)
        reasons=[]
        if not has_money:reasons.append("DAY_MONEY_EVIDENCE_MISSING")
        if not annual_verified:reasons.append("ANNUAL_FINANCIALS_UNVERIFIED")
        if not verified_interim:reasons.append("CURRENT_INTERIM_YTD_UNVERIFIED")
        if latest_prelim_unverified:
            reasons.append("FRESH_PRELIMINARY_EARNINGS_NUMBERS_NOT_PARSED")
            reasons.append("PRIOR_GROWTH_NOT_CURRENT_WHEN_NEWER_FILING_UNVERIFIED")
        if preliminary_weakness:reasons.append("RECENT_PRELIMINARY_QUARTER_WEAKENING")
        if historical_weakness:reasons.append("RECENT_YTD_WEAKENING")
        if conflict:reasons.append("CROSS_SOURCE_CLOSE_CONFLICT")
        if not price_ready:reasons.append("COMPLETED_DAILY_ENTRY_STOP_NOT_VERIFIED")
        if any(x["potential_intragroup_revenue_recognition_risk"]
               for x in originals):
            reasons.append("AFFILIATE_COUNTERPARTY_CONSOLIDATED_REVENUE_RISK")
        if not direct:reasons.append("NO_DIRECT_COMPANY_FILING_IN_SAMPLE")
        if global_items:reasons.append("GLOBAL_NEWS_ONLY_SECTOR_CONTEXT")
        row=dict(ticker=t,name=str(original.get("name") or t),
            sector_id=sid,sector_name=str(sector.get("name") or sid),
            cohort=kind,asof=str(asof) if asof else None,
            checks=checks,unmet_evidence=reasons,
            research_evidence_strength=sum(
                int(checks[k]) for k in (
                "positive_daily_sector_flow","annual_filing_verified",
                "current_interim_ytd_verified","annual_and_interim_growth",
                "direct_dart_filing_title_observed",
                "completed_daily_structure_reference")),
            direct_company_filings=direct,
            official_contract_originals=originals,
            newer_preliminary_earnings_not_parsed=latest_prelim_unverified,
            recent_preliminary_quarter_source_verified=bool(
                newest_prelim and newest_prelim["financial_figures_verified"]),
            recent_preliminary_quarter_weakening=preliminary_weakness,
            recent_preliminary_earnings_disclosures=prelim,
            original_contract_text_observed=any(
                x["original_status"] in (
                    "DART_DOCUMENT_XML_TABLES_PARSED",
                    "DART_DOCUMENT_SGML_TABLES_PARSED")
                for x in originals),
            direct_contract_amount_confirmed=False,
            potential_intragroup_revenue_recognition_risk=any(
                x["potential_intragroup_revenue_recognition_risk"]
                for x in originals),
            document_labeled_contract_amounts=[dict(
                receipt_no=x["receipt_no"],amount_krw=x["document_amount_krw"],
                ratio_pct=x["document_sales_ratio_pct"],
                arithmetic=x["single_filing_arithmetic_status"],
                potential_intragroup_revenue_recognition_risk=x[
                  "potential_intragroup_revenue_recognition_risk"])
                for x in originals if isinstance(x.get("document_amount_krw"),int)],
            global_sector_context=global_items,
            latest_annual_receipt_url=price.get("financial_receipt_url") or
                 finances.get("annual_receipt_url"),
            current_ytd_sales_yoy_pct=price.get("interim_ytd_sales_yoy_pct") or
                 finances.get("interim_ytd_sales_yoy_pct"),
            current_ytd_operating_profit_yoy_pct=price.get(
                 "interim_ytd_operating_profit_yoy_pct") or
                 finances.get("interim_ytd_operating_profit_yoy_pct"),
            stop_research_krw=stop if price_ready else None,
            entry1_research=price.get("independent_first_entry_reference")
                 if price_ready else None,
            company_catalyst_impact_verified=False,news_positive_verified=False,
            final_85_score_verified=False,trade_approved=False)
        matrix.append(row)
    return dict(schema=VERSION,asof=str(asof) if asof else None,
         sector_money_asof_aligned=market_gate and asof is not None,
         candidate_count=len(matrix),absolute_top5_count=sum(
            x["cohort"]=="ABSOLUTE_TOP5" for x in matrix),
         candidates=matrix,
         dart_original_source_status=contracts.get("status","NOT_COLLECTED_OR_DATE_MISMATCH"),
         contract_originals_read_count=sum(
            bool(x["original_contract_text_observed"]) for x in matrix),
         contract_amount_or_positive_impact_confirmed_count=0,
         company_catalyst_verified_count=0,
         relative_evidence_strength_is_investment_score=False,
         research_price_is_trade_approval=False,
         no_lookahead_signal_generated=True,
         orders_enabled=False,trade_approved=False,decision="CASH")

def cell(b,success="확인",failure="미검증"):
    return success if b else failure

def render(data):
    lines=["","## 종목별 실증 근거 교차검증 (최종 BUY 점수 아님)","",
       "**신규 매수: CASH** | 근거 확인 수준만 표시, 매수 승인 및 상승확률 아님.",
       "| 종목 | 섹터 당일 순매수 | 최근 YTD 실적 | 직접 공시 | 구조 손절 |",
       "|---|---|---|---|---|"]
    for x in data.get("candidates",[]):
        if x["cohort"]!="ABSOLUTE_TOP5":continue
        c=x["checks"]
        financial=("약화" if c["any_recent_earnings_weakening"]
            else "신규 잠정실적 수치 확인 전·성장판정 보류"
                 if x["newer_preliminary_earnings_not_parsed"]
            else "성장 확인" if c["annual_and_interim_growth"]
            else "누적 확인" if c["current_interim_ytd_verified"]
            else "미검증")
        lines.append("| "+x["name"].replace("|","/")[:26]+" | "+
          cell(c["positive_daily_sector_flow"])+
          " | "+financial+
          (("·"+x["recent_preliminary_earnings_disclosures"][0]["date"]+
           " 잠정 3개월 실적 "+str(
              x["recent_preliminary_earnings_disclosures"][0]["preliminary_earnings_quality"])
             if x["recent_preliminary_quarter_source_verified"] and
                x["recent_preliminary_earnings_disclosures"] else
           "·"+x["recent_preliminary_earnings_disclosures"][0]["date"]+
           " 잠정공시 수치 미검증" if x["newer_preliminary_earnings_not_parsed"] else ""))+
          " | "+
          (("원문 계약액 "+format(x["document_labeled_contract_amounts"][0]["amount_krw"]/100_000_000,",.2f")+
            "억·실질효과 미검증") if x["document_labeled_contract_amounts"]
           else "원문 표 확인·실질효과 미검증" if x["original_contract_text_observed"]
           else "접수번호 확인·원문 미검증" if x["official_contract_originals"]
           else "제목만 확인" if c["direct_dart_filing_title_observed"]
           else "없음/미수집")+
          " | "+("참고가 확인" if c["completed_daily_structure_reference"] else
                "출처 충돌" if c["price_conflict"] else "미검증")+" |")
    if not any(x["cohort"]=="ABSOLUTE_TOP5" for x in data.get("candidates",[])):
        lines.append("| 당일 적격 후보 없음 | — | — | — | — |")
    for x in data.get("candidates",[]):
        if x["cohort"]=="ABSOLUTE_TOP5" and x.get(
              "potential_intragroup_revenue_recognition_risk"):
            lines.append("- **"+x["name"].replace("|","/")+
               ": 계약상대 계열사 가능성 / 연결재무 내부거래 제거 여부 확인 전"
               " 계약금액을 확정 외부매출·이익으로 환산 금지**")
    lines+=["","### 섹터별 글로벌 선행 뉴스의 올바른 해석",""]
    sectors=set()
    for x in data.get("candidates",[]):
        if x["sector_id"] in sectors or not x["global_sector_context"]:continue
        sectors.add(x["sector_id"])
        a=x["global_sector_context"][0]
        lines.append("- "+x["sector_name"].replace("|","/")[:25]+": "+
          a["title"].replace("|","/")[:90]+
          " — 해외 산업 관찰이며 해당 한국 기업의 직접 수혜는 검증되지 않음")
    if not sectors:lines.append("- 연결된 해외 섹터 뉴스 없음/미수집")
    lines+=["","*직접 공시는 공시번호·접수일과 회사 종목코드를 대조한 **제목 관찰**일 뿐"
        " 계약의 금액·긍정적 실적 영향은 확인하지 않았습니다.",
        "*기사 검색 최초 관찰 시각과 원문 최초 발행 시각은 다릅니다.",
        "*연간 실적/분기 누적 실적/구조손절 참고가가 모두 있어도"
        " 확정 호재·실제 타점·전방 손익비 등 독립 검증 전에는 최종 85점 및 매수 불가.",""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("output"))
    a=p.parse_args()
    target=a.root/"sector_first_with_financials.json"
    if not target.is_file():raise SystemExit("MISSING_FINANCIAL_SECTOR_REPORT")
    base=json.loads(target.read_text(encoding="utf-8"))
    contract_source=a.root/"direct_dart_contracts.json"
    try:contracts=json.loads(contract_source.read_text(encoding="utf-8")) if (
        contract_source.is_file()) else {}
    except (ValueError,OSError):contracts={}
    result=build(base,contracts)
    (a.root/"company_evidence_matrix.json").write_text(
         json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    (a.root/"company_evidence_matrix_mobile.md").write_text(
         render(result),encoding="utf-8")
    compact=a.root/"sector_first_compact_mobile.md"
    if compact.is_file():
        old=compact.read_text(encoding="utf-8")
        marker="## 종목별 실증 근거 교차검증 (최종 BUY 점수 아님)"
        compact.write_text(old.split(marker)[0].rstrip()+"\n\n"+render(result),encoding="utf-8")
    print(json.dumps(dict(asof=result["asof"],candidates=result["candidate_count"],
         direct_company_impact_verified=0,trade_approved=False,decision="CASH"),
         ensure_ascii=False))

if __name__=="__main__":main()
