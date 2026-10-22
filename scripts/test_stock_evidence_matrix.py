#!/usr/bin/env python3
"""Dated stock evidence joining: no mistaken catalysts, no fake BUY scores."""
import unittest
from stock_evidence_matrix import build,render,asof_seen,official_url

DAY="2026-10-22"
SEEN="2026-10-21T12:00:00+00:00"
def inputs():
    return dict(asof=DAY,daily_money_rank_applied=True,decision="CASH",
      sector_top3=[
        dict(sector_id="SEMICON",name="반도체",
             day_net_flow_1d_incremental_krw=100000000000,
             prior_day_dart_observations=[
                dict(ticker="005930",date="2026-10-21",
                     title="공급계약 체결",
                     url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261021000001"),
                dict(ticker="000660",date="2026-10-21",
                     title="다른 회사 공시",
                     url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261021000002")],
             global_news_observations=[
                dict(title="Global semiconductor capex expands",
                     seen_at_utc=SEEN,url="https://example.com/semis")]),
        dict(sector_id="POWER",name="전력설비",
             day_net_flow_1d_incremental_krw=32000000000,
             prior_day_dart_observations=[],global_news_observations=[])],
      stock_research_top5=[
        dict(ticker="005930",name="삼성전자",sector_id="SEMICON",
             independently_collected_daily_stop_reference="201000",
             independent_first_entry_reference="219000~220000",
             independent_stop_status="HISTORICAL_DAILY_REFERENCE_ONLY",
             fundamentals_filing_verified=True,
             latest_periodic_financials_verified=True,
             annual_plus_interim_growth_pass=True,
             interim_ytd_sales_yoy_pct=18.7,
             interim_ytd_operating_profit_yoy_pct=22.1,
             financial_receipt_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318000001"),
        dict(ticker="010120",name="LS ELECTRIC",sector_id="POWER",
             independent_stop_status="CROSS_SOURCE_CLOSE_CONFLICT",
             fundamentals_filing_verified=True,
             recent_financial_weakening_veto=True)],
      sector_leader_watch=[
         dict(ticker="005930",name="삼성전자",sector_id="SEMICON"),
         dict(ticker="010120",name="LS ELECTRIC",sector_id="POWER")],
      financial_quality_watch_top5=[
         dict(ticker="005930",name="삼성전자",sector_id="SEMICON",sales_yoy_pct=10,
              annual_receipt_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318000001")],
      annual_plus_interim_growth_watch_top5=[
         dict(ticker="005930",name="삼성전자",sector_id="SEMICON",
              annual_plus_interim_growth_pass=True)])

class StockEvidenceTests(unittest.TestCase):
    def test_direct_dart_receipt_stock_match_not_separate_company(self):
        r=build(inputs())
        stock=r["candidates"][0]
        self.assertEqual(len(stock["direct_company_filings"]),1)
        self.assertEqual(stock["direct_company_filings"][0]["material_impact"],
                         "NOT_CONTENT_VERIFIED")
        self.assertFalse(stock["company_catalyst_impact_verified"])
        self.assertEqual(r["company_catalyst_verified_count"],0)
    def test_verified_interim_not_85_score_and_orders_disabled(self):
        r=build(inputs())
        stock=r["candidates"][0]
        self.assertTrue(stock["checks"]["annual_and_interim_growth"])
        self.assertIsNone(stock.get("final_85_score"))
        self.assertFalse(stock["final_85_score_verified"])
        self.assertEqual(r["decision"],"CASH")
        self.assertFalse(r["trade_approved"])
        self.assertFalse(r["orders_enabled"])
    def test_news_is_sector_context_never_company_catalyst(self):
        stock=build(inputs())["candidates"][0]
        self.assertEqual(stock["global_sector_context"][0]["meaning"],
                         "SECTOR_CONTEXT_ONLY_NOT_COMPANY_IMPACT")
        self.assertFalse(stock["news_positive_verified"])
        self.assertIn("확정",render(build(inputs())))
    def test_foreign_seen_after_asof_not_in_historical_context(self):
        b=inputs()
        b["sector_top3"][0]["global_news_observations"][0][
          "seen_at_utc"]="2026-10-23T00:00:00+00:00"
        self.assertEqual(build(b)["candidates"][0]["global_sector_context"],[])
    def test_direct_company_filing_on_asof_day_not_used_without_timestamp(self):
        b=inputs()
        b["sector_top3"][0]["prior_day_dart_observations"][0]["date"]=DAY
        self.assertEqual(build(b)["candidates"][0]["direct_company_filings"],[])
    def test_stale_old_filing_not_counted(self):
        b=inputs()
        b["sector_top3"][0]["prior_day_dart_observations"][0]["date"]="2026-10-01"
        self.assertEqual(build(b)["candidates"][0]["direct_company_filings"],[])
    def test_wrong_dart_host_and_unsafe_url_rejected(self):
        self.assertIsNone(official_url("https://evil.example.com/dsaf001/main.do?rcpNo=20261021000001"))
        self.assertIsNone(official_url("https://dart.fss.or.kr/dsaf001/main.do?rcpNo=3"))
    def test_price_source_conflict_disables_entry_reference(self):
        r=build(inputs())
        price=r["candidates"][1]
        self.assertFalse(price["checks"]["completed_daily_structure_reference"])
        self.assertIsNone(price["entry1_research"])
        self.assertTrue(price["checks"]["price_conflict"])
    def test_recent_financial_weakening_veto_after_annual_success(self):
        r=build(inputs())
        price=r["candidates"][1]
        self.assertTrue(price["checks"]["recent_ytd_weakening"])
        self.assertFalse(price["checks"]["annual_and_interim_growth"])
    def test_stale_or_missing_flow_never_faked(self):
        b=inputs();b["daily_money_rank_applied"]=False
        r=build(b)
        self.assertFalse(r["sector_money_asof_aligned"])
        self.assertFalse(r["candidates"][0]["checks"]["positive_daily_sector_flow"])
    def test_relative_evidence_strength_is_not_85_score(self):
        r=build(inputs())
        self.assertLessEqual(r["candidates"][0]["research_evidence_strength"],6)
        self.assertFalse(r["relative_evidence_strength_is_investment_score"])
        self.assertFalse(r["trade_approved"])
    def test_cohort_dedup_preserves_absolute_top5_before_watchlists(self):
        r=build(inputs())
        self.assertEqual([x["ticker"] for x in r["candidates"]],
                         ["005930","010120"])
        self.assertEqual(r["absolute_top5_count"],2)
    def test_missing_all_evidence_cash_without_fake_data(self):
        r=build(dict(asof=DAY,sector_top3=[],stock_research_top5=[]))
        self.assertEqual(r["candidate_count"],0)
        self.assertEqual(r["decision"],"CASH")
        self.assertIn("당일 적격 후보 없음",render(r))
    def test_duplicate_same_company_filing_is_counted_once(self):
        b=inputs()
        b["sector_top3"][0]["prior_day_dart_observations"].append(
            b["sector_top3"][0]["prior_day_dart_observations"][0].copy())
        self.assertEqual(len(build(b)["candidates"][0]["direct_company_filings"]),1)
    def test_naive_discovery_time_is_rejected(self):
        self.assertFalse(asof_seen("2026-10-21T12:00:00",__import__("datetime").date(2026,10,22)))
    def test_official_subsidiary_counterparty_blocks_assumed_external_sales(self):
        report=inputs()
        contract=dict(schema="dart_contract_source_v1",asof=DAY,
            issuer_samples=[dict(ticker="005930",filings=[dict(
                date="2026-10-21",receipt_no="20261021000001",
                title="단일판매 공급계약",
                url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261021000001",
                filing_contents_status="DART_DOCUMENT_SGML_TABLES_PARSED",
                correction_risk="NO_CORRECTION_TITLE_FLAG",
                structured_contract_terms=dict(
                    amount_krw=168_871_711_050,
                    disclosed_sales_ratio_pct=3.4,
                    consistency="SINGLE_FILING_ARITHMETIC_MATCH",
                    counterparty_affiliation_review=
                        "ISSUER_BRANDED_COUNTERPARTY_POSSIBLE_AFFILIATE",
                    potential_intragroup_revenue_recognition_risk=True))])])
        r=build(report,contract)
        row=r["candidates"][0]
        self.assertTrue(row["potential_intragroup_revenue_recognition_risk"])
        self.assertIn("AFFILIATE_COUNTERPARTY_CONSOLIDATED_REVENUE_RISK",
                      row["unmet_evidence"])
        self.assertTrue(row["document_labeled_contract_amounts"][0][
            "potential_intragroup_revenue_recognition_risk"])
        self.assertIn("연결재무 내부거래 제거 여부",render(r))
        self.assertFalse(row["company_catalyst_impact_verified"])
        self.assertEqual(r["decision"],"CASH")
    def test_matched_official_contract_xml_is_raw_evidence_not_positive_impact(self):
        report=inputs()
        original=dict(schema="dart_contract_source_v1",asof=DAY,
             status="DIRECT_DART_EVIDENCE_COLLECTED_UNVERIFIED_IMPACT",
             issuer_samples=[dict(ticker="005930",filings=[dict(
               date="2026-10-21",receipt_no="20261021000001",
               title="단일판매 공급계약",correction_risk="NO_CORRECTION_TITLE_FLAG",
               url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261021000001",
               filing_contents_status="DART_DOCUMENT_XML_TABLES_PARSED")])])
        r=build(report,original)
        a=r["candidates"][0]
        self.assertTrue(a["original_contract_text_observed"])
        self.assertFalse(a["direct_contract_amount_confirmed"])
        self.assertFalse(a["company_catalyst_impact_verified"])
        self.assertEqual(r["contract_amount_or_positive_impact_confirmed_count"],0)
        self.assertIn("원문 표 확인",render(r))
        self.assertEqual(r["decision"],"CASH")
    def test_real_sgml_official_original_is_document_not_positive_catalyst(self):
        observed=dict(schema="dart_contract_source_v1",asof=DAY,
          issuer_samples=[dict(ticker="005930",filings=[dict(
            date="2026-10-21",receipt_no="20261021000001",
            url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261021000001",
            filing_contents_status="DART_DOCUMENT_SGML_TABLES_PARSED")])])
        actual=build(inputs(),observed)
        self.assertTrue(actual["candidates"][0]["original_contract_text_observed"])
        self.assertFalse(actual["candidates"][0]["direct_contract_amount_confirmed"])
        self.assertEqual(actual["company_catalyst_verified_count"],0)
        self.assertFalse(actual["trade_approved"])
    def test_issuer_contract_amount_visible_but_not_approved_if_single_filing_only(self):
        b=inputs()
        source=dict(schema="dart_contract_source_v1",asof=DAY,
            issuer_samples=[dict(ticker="005930",filings=[dict(
                date="2026-10-21",receipt_no="20261021000001",
                url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261021000001",
                filing_contents_status="DART_DOCUMENT_SGML_TABLES_PARSED",
                correction_risk="NO_CORRECTION_TITLE_FLAG",
                structured_contract_terms=dict(
                    status="LABELED_AMOUNT_READ_FROM_OFFICIAL_SOURCE",
                    amount_krw=50_000_000_000,
                    disclosed_sales_ratio_pct=10.0,
                    consistency="SINGLE_FILING_ARITHMETIC_MATCH"))])])
        result=build(b,source)
        r=result["candidates"][0]
        self.assertEqual(r["document_labeled_contract_amounts"][0]["amount_krw"],50000000000)
        self.assertFalse(r["direct_contract_amount_confirmed"])
        self.assertFalse(r["company_catalyst_impact_verified"])
        self.assertFalse(result["trade_approved"])
        self.assertIn("500.00억",render(result))
    def test_fresh_preliminary_earnings_title_flags_stale_ytd_assessment(self):
        source=dict(schema="dart_contract_source_v1",asof=DAY,
            issuer_samples=[dict(ticker="005930",filings=[],
                latest_preliminary_earnings=[
                    dict(date="2026-10-21",title="연결재무제표기준영업(잠정)실적",
                    receipt_no="20261021800151",financial_figures_verified=False,
                    url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261021800151")])])
        r=build(inputs(),source)
        stock=r["candidates"][0]
        self.assertTrue(stock["newer_preliminary_earnings_not_parsed"])
        self.assertIn("FRESH_PRELIMINARY_EARNINGS_NUMBERS_NOT_PARSED",
                      stock["unmet_evidence"])
        self.assertIn("2026-10-21 잠정공시 수치 미검증",render(r))
        self.assertFalse(stock["company_catalyst_impact_verified"])
        self.assertEqual(r["decision"],"CASH")
    def test_latest_unverified_preliminary_supersedes_older_parsed_growth(self):
        # Original API order is deliberately reversed. An older verified
        # quarter can never overrule a newer corrected, unavailable report.
        source=dict(schema="dart_contract_source_v1",asof=DAY,
            issuer_samples=[dict(ticker="005930",filings=[],
                latest_preliminary_earnings=[
                    dict(date="2026-10-20",title="연결영업(잠정)실적",
                         receipt_no="20261020800150",
                         url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261020800150",
                         financial_figures_verified=True,
                         original_financial_status="PRELIMINARY_SINGLE_QUARTER_SOURCE_RESEARCH_ONLY",
                         original_financial_analysis=dict(
                             status="PRELIMINARY_SINGLE_QUARTER_SOURCE_RESEARCH_ONLY",
                             preliminary_figures_source_verified=True,
                             receipt_no="20261020800150",receipt_date="2026-10-20",
                             earnings_quality="PRELIMINARY_SALES_AND_OP_GROWTH_OBSERVED",
                             revenue_yoy_pct=20.0,operating_profit_yoy_pct=50.0,
                             quarter_period={"current_end":"2026-09-30"})),
                    dict(date="2026-10-21",title="(정정)연결영업(잠정)실적",
                         receipt_no="20261021800151",
                         url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261021800151",
                         financial_figures_verified=False,
                         original_financial_status="PRELIMINARY_AMENDED_REQUIRES_RECONCILIATION")
                ])])
        outcome=build(inputs(),source)
        stock=outcome["candidates"][0]
        self.assertEqual(stock["recent_preliminary_earnings_disclosures"][0]["date"],
                         "2026-10-21")
        self.assertTrue(stock["newer_preliminary_earnings_not_parsed"])
        self.assertFalse(stock["recent_preliminary_quarter_source_verified"])
        self.assertFalse(stock["checks"]["annual_and_interim_growth"])
        self.assertIn("PRIOR_GROWTH_NOT_CURRENT_WHEN_NEWER_FILING_UNVERIFIED",
                      stock["unmet_evidence"])
        self.assertIn("성장판정 보류",render(outcome))
        self.assertFalse(outcome["trade_approved"])
    def test_newest_verified_preliminary_keeps_strict_historical_growth_research(self):
        source=dict(schema="dart_contract_source_v1",asof=DAY,
            issuer_samples=[dict(ticker="005930",filings=[],
                latest_preliminary_earnings=[dict(
                    date="2026-10-21",title="연결영업(잠정)실적",
                    receipt_no="20261021800151",
                    url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261021800151",
                    financial_figures_verified=True,
                    original_financial_status="PRELIMINARY_SINGLE_QUARTER_SOURCE_RESEARCH_ONLY",
                    original_financial_analysis=dict(
                        status="PRELIMINARY_SINGLE_QUARTER_SOURCE_RESEARCH_ONLY",
                        receipt_no="20261021800151",receipt_date="2026-10-21",
                        preliminary_figures_source_verified=True,
                        earnings_quality="PRELIMINARY_SALES_AND_OP_GROWTH_OBSERVED",
                        revenue_yoy_pct=15.0,operating_profit_yoy_pct=30.0,
                        quarter_period={"current_end":"2026-09-30"}))])])
        outcome=build(inputs(),source)
        stock=outcome["candidates"][0]
        self.assertTrue(stock["recent_preliminary_quarter_source_verified"])
        self.assertFalse(stock["newer_preliminary_earnings_not_parsed"])
        self.assertTrue(stock["checks"]["annual_and_interim_growth"])
        self.assertFalse(outcome["trade_approved"])
    def test_actual_quarterly_weakening_vetoes_older_positive_half_year(self):
        source=dict(schema="dart_contract_source_v1",asof=DAY,
            issuer_samples=[dict(ticker="005930",filings=[],
                latest_preliminary_earnings=[dict(
                    date="2026-10-21",title="연결재무제표기준영업(잠정)실적",
                    receipt_no="20261021800151",
                    url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261021800151",
                    financial_figures_verified=True,
                    original_financial_status="PRELIMINARY_SINGLE_QUARTER_SOURCE_RESEARCH_ONLY",
                    original_financial_analysis=dict(
                        status="PRELIMINARY_SINGLE_QUARTER_SOURCE_RESEARCH_ONLY",
                        receipt_no="20261021800151",receipt_date="2026-10-21",
                        preliminary_figures_source_verified=True,
                        revenue_yoy_pct=-11.2,operating_profit_yoy_pct=-17.5,
                        earnings_quality="RECENT_PRELIMINARY_WEAKENING",
                        quarter_period={"current_end":"2026-09-30"}))])])
        result=build(inputs(),source)
        stock=result["candidates"][0]
        self.assertTrue(stock["recent_preliminary_quarter_source_verified"])
        self.assertTrue(stock["recent_preliminary_quarter_weakening"])
        self.assertFalse(stock["checks"]["recent_ytd_weakening"])
        self.assertTrue(stock["checks"]["recent_preliminary_quarter_weakening"])
        self.assertTrue(stock["checks"]["any_recent_earnings_weakening"])
        self.assertFalse(stock["checks"]["annual_and_interim_growth"])
        self.assertFalse(stock["newer_preliminary_earnings_not_parsed"])
        self.assertIn("RECENT_PRELIMINARY_QUARTER_WEAKENING",
                      stock["unmet_evidence"])
        self.assertEqual(result["decision"],"CASH")
        self.assertFalse(stock["final_85_score_verified"])
    def test_unmatched_preliminary_source_receipt_is_unverified(self):
        b=inputs()
        source=dict(schema="dart_contract_source_v1",asof=DAY,
            issuer_samples=[dict(ticker="005930",filings=[],
                latest_preliminary_earnings=[dict(
                    date="2026-10-21",title="연결재무제표기준영업(잠정)실적",
                    receipt_no="20261021800151",
                    url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261021800151",
                    financial_figures_verified=True,
                    original_financial_analysis=dict(
                        status="PRELIMINARY_SINGLE_QUARTER_SOURCE_RESEARCH_ONLY",
                        receipt_no="WRONG",receipt_date="2026-10-21",
                        preliminary_figures_source_verified=True,
                        revenue_yoy_pct=20,earnings_quality="PRELIMINARY_SALES_AND_OP_GROWTH_OBSERVED"))])])
        r=build(b,source)["candidates"][0]
        self.assertFalse(r["recent_preliminary_quarter_source_verified"])
        self.assertTrue(r["newer_preliminary_earnings_not_parsed"])

    def test_current_day_or_future_preliminary_notice_cannot_backfill(self):
        source=dict(schema="dart_contract_source_v1",asof=DAY,
            issuer_samples=[dict(ticker="005930",filings=[],
                latest_preliminary_earnings=[
                    dict(date=DAY,title="연결재무제표기준영업(잠정)실적",
                    receipt_no="20261022800151",
                    url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261022800151")])])
        r=build(inputs(),source)
        self.assertFalse(r["candidates"][0]["newer_preliminary_earnings_not_parsed"])
    def test_future_or_other_date_contract_cannot_enter_company_matrix(self):
        contract=dict(schema="dart_contract_source_v1",asof="2026-10-23",
              issuer_samples=[dict(ticker="005930",filings=[dict(
                date="2026-10-23",receipt_no="20261023000001",
                url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261023000001",
                filing_contents_status="DART_DOCUMENT_XML_TABLES_PARSED")])])
        r=build(inputs(),contract)
        self.assertFalse(r["candidates"][0]["original_contract_text_observed"])
        self.assertEqual(r["dart_original_source_status"],"NOT_COLLECTED_OR_DATE_MISMATCH")
    def test_same_asof_contract_must_precede_day_without_exact_time(self):
        contract=dict(schema="dart_contract_source_v1",asof=DAY,
              issuer_samples=[dict(ticker="005930",filings=[dict(
                date=DAY,receipt_no="20261022000001",
                url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261022000001",
                filing_contents_status="DART_DOCUMENT_XML_TABLES_PARSED")])])
        self.assertFalse(build(inputs(),contract)["candidates"][0][
            "original_contract_text_observed"])
    def test_unmatched_sector_prevents_leak_of_fundamental_watches(self):
        b=inputs()
        b["financial_quality_watch_top5"].append(dict(
            ticker="012345",name="외부회사",sector_id="UNSELECTED",sales_yoy_pct=27))
        self.assertNotIn("012345",[r["ticker"] for r in build(b)["candidates"]])

if __name__=="__main__":unittest.main()
