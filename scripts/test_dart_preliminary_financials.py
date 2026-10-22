#!/usr/bin/env python3
"""Strict official DART preliminary fair disclosure table regression cases."""
import io,unittest,zipfile
from datetime import date
from dart_preliminary_financials import (
    assess,decode_document,parse_date_pairs,metrics_from_rows,parse_amount)

DAY=date(2026,10,22)
FILE=dict(ticker="010120",date="2026-10-21",receipt_no="20261021800151",
    title="연결재무제표기준영업(잠정)실적(공정공시)",
    correction_flag=False)
ROWS=[
    ["당해실적","2026.07.01 ~ 2026.09.30"],
    ["전년동기실적","2025.07.01 ~ 2025.09.30"],
    ["구분","당해실적","전기실적","전년동기실적","증감률"],
    ["매출액","1,250,000","1,200,000","1,000,000","25.0%"],
    ["영업이익","120,000","140,000","100,000","20.0%"]]
def data(rows=None,units=None):
    return dict(status="PRELIMINARY_TABLE_ROWS_READ",
        rows=ROWS if rows is None else rows,
        unit_candidates=["백만원"] if units is None else units)
def zipped(text,encoding="utf-8"):
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("original.xml",text.encode(encoding))
    return bio.getvalue()
class PreliminaryTests(unittest.TestCase):
    def test_quarter_2026_v_2025_yoy_real_units(self):
        r=assess(data(),FILE,DAY)
        self.assertEqual(r["status"],"PRELIMINARY_SINGLE_QUARTER_SOURCE_RESEARCH_ONLY")
        self.assertEqual(r["revenue_current_krw"],1_250_000_000_000)
        self.assertEqual(r["operating_profit_current_krw"],120_000_000_000)
        self.assertEqual(r["revenue_yoy_pct"],25.0)
        self.assertEqual(r["operating_profit_yoy_pct"],20.0)
        self.assertEqual(r["quarter_period"]["frequency"],"SINGLE_QUARTER_NON_CUMULATIVE")
        self.assertEqual(r["statement_scope"],"CFS")
        self.assertFalse(r["trade_approved"])
    def test_latest_filing_with_last_year_quarter_is_not_fresh_growth(self):
        rows=[*ROWS]
        rows[0]=["당해실적","2025.07.01 ~ 2025.09.30"]
        rows[1]=["전년동기실적","2024.07.01 ~ 2024.09.30"]
        parsed=assess(data(rows),FILE,DAY)
        self.assertEqual(parsed["status"],
            "PRELIMINARY_QUARTER_TOO_OLD_FOR_LATEST_EARNINGS")
        self.assertGreater(parsed["filing_lag_calendar_days"],120)
        self.assertFalse(parsed["preliminary_figures_source_verified"])
        self.assertIsNone(parsed["revenue_yoy_pct"])
    def test_partial_three_month_period_is_not_standard_quarter(self):
        rows=[*ROWS]
        rows[0]=["당해실적","2026.07.02 ~ 2026.09.30"]
        rows[1]=["전년동기실적","2025.07.02 ~ 2025.09.30"]
        parsed=assess(data(rows),FILE,DAY)
        self.assertEqual(parsed["status"],
            "PRELIMINARY_QUARTER_COMPARISON_PERIOD_NOT_VERIFIED")
        self.assertFalse(parsed["preliminary_figures_source_verified"])
    def test_days_mismatch_same_calendar_quarter_blocked(self):
        rows=[*ROWS]
        rows[1]=["전년동기실적","2025.07.02 ~ 2025.09.30"]
        parsed=assess(data(rows),FILE,DAY)
        self.assertEqual(parsed["status"],
            "PRELIMINARY_QUARTER_COMPARISON_PERIOD_NOT_VERIFIED")
    def test_newly_reported_complete_q3_remains_valid(self):
        r=assess(data(),FILE,DAY)
        self.assertEqual(r["quarter_period"]["current_start"],"2026-07-01")
        self.assertEqual(r["filing_lag_calendar_days"],21)
        self.assertTrue(r["preliminary_figures_source_verified"])
    def test_published_yoy_rate_must_match_verified_quarter_amounts(self):
        rows=[
            ["당기실적","2026-07-01","~","2026-09-30"],
            ["전년동기실적","2025-07-01","~","2025-09-30"],
            ["__TABLE_BOUNDARY__"],
            ["구분","당기실적","전기실적","전기대비",
             "전년동기실적","전년동기대비"],
            ["('26.3Q)","('26.2Q)","증감율(%)","-",
             "('25.3Q)","증감율(%)","-"],
            ["매출액","당해실적","1250","1100","5","-","1000","99.99","-"],
            ["영업이익","당해실적","120","110","4","-","100","20.0","-"]]
        result=assess(data(rows),FILE,DAY)
        self.assertEqual(result["status"],
                         "PRELIMINARY_DISCLOSED_YOY_RATE_MISMATCH")
        self.assertFalse(result["preliminary_figures_source_verified"])
        self.assertIsNone(result["revenue_yoy_pct"])
    def test_matched_disclosed_yoy_rate_allows_quarter_research_only(self):
        rows=[
            ["당기실적","2026-07-01","~","2026-09-30"],
            ["전년동기실적","2025-07-01","~","2025-09-30"],
            ["__TABLE_BOUNDARY__"],
            ["구분","당기실적","전기실적","전기대비",
             "전년동기실적","전년동기대비"],
            ["('26.3Q)","('26.2Q)","증감율(%)","-",
             "('25.3Q)","증감율(%)","-"],
            ["매출액","당해실적","1250","1100","5","-","1000","25.00","-"],
            ["영업이익","당해실적","120","110","4","-","100","20.00","-"]]
        result=assess(data(rows),FILE,DAY)
        self.assertEqual(result["revenue_yoy_pct"],25.0)
        self.assertEqual(result["operating_profit_yoy_pct"],20.0)
        self.assertTrue(result["preliminary_figures_source_verified"])
        self.assertFalse(result["trade_approved"])
    def test_no_disclosed_unit_blocks_amount_as_known(self):
        r=assess(data(units=[]),FILE,DAY)
        self.assertEqual(r["status"],"PRELIMINARY_UNIT_MISSING_OR_AMBIGUOUS")
        self.assertIsNone(r["revenue_current_krw"])
    def test_two_conflicting_units_blocks_numbers(self):
        r=assess(data(units=["백만원","억원"]),FILE,DAY)
        self.assertEqual(r["status"],"PRELIMINARY_UNIT_MISSING_OR_AMBIGUOUS")
    def test_mismatched_previous_comparison_year_blocks_growth(self):
        rows=[*ROWS]
        rows[1]=["전년동기실적","2024.07.01 ~ 2024.09.30"]
        r=assess(data(rows),FILE,DAY)
        self.assertEqual(r["status"],"PRELIMINARY_QUARTER_COMPARISON_PERIOD_NOT_VERIFIED")
    def test_missing_period_does_not_approve_same_row_values(self):
        r=assess(data(ROWS[2:]),FILE,DAY)
        self.assertEqual(r["status"],"PRELIMINARY_QUARTER_COMPARISON_PERIOD_NOT_VERIFIED")
    def test_cross_quarter_compare_not_valid(self):
        rows=[*ROWS]
        rows[1]=["전년동기실적","2025.04.01 ~ 2025.06.30"]
        r=assess(data(rows),FILE,DAY)
        self.assertEqual(r["status"],"PRELIMINARY_QUARTER_COMPARISON_PERIOD_NOT_VERIFIED")
    def test_only_current_quarter_without_previous_fails_closed(self):
        rows=[*ROWS]
        rows[2]=["구분","당해실적","전기실적","작년실적","증감률"]
        self.assertEqual(assess(data(rows),FILE,DAY)["status"],
                         "PRELIMINARY_SAME_ROW_YOY_VALUES_MISSING")
    def test_unsupported_gain_loss_prose_not_parseable(self):
        rows=[*ROWS]
        rows[3]=["매출액","약 1,250,000","1,200,000","1,000,000",""]
        self.assertEqual(assess(data(rows),FILE,DAY)["status"],
                         "PRELIMINARY_SAME_ROW_YOY_VALUES_MISSING")
    def test_duplicate_conflicting_metric_does_not_choose_first(self):
        rows=ROWS+[["매출액","1,400,000","1,300,000","1,000,000",""]]
        self.assertEqual(assess(data(rows),FILE,DAY)["status"],
                         "PRELIMINARY_DUPLICATE_METRIC_CONFLICT")
    def test_recent_revenue_decline_vetoes_growth_claim(self):
        rows=[*ROWS]
        rows[3]=["매출액","800,000","900,000","1,000,000","-20%"]
        r=assess(data(rows),FILE,DAY)
        self.assertEqual(r["earnings_quality"],"RECENT_PRELIMINARY_WEAKENING")
        self.assertEqual(r["revenue_yoy_pct"],-20)
    def test_prior_operating_loss_reports_turnaround_no_infinite_percent(self):
        rows=[*ROWS]
        rows[4]=["영업이익","120,000","140,000","-20,000",""]
        r=assess(data(rows),FILE,DAY)
        self.assertTrue(r["preliminary_figures_source_verified"])
        self.assertIsNone(r["operating_profit_yoy_pct"])
        self.assertEqual(r["earnings_quality"],"PRELIMINARY_OPERATING_TURNAROUND_NO_YOY_PERCENT")
    def test_future_or_same_day_filing_not_included_without_timestamp(self):
        f={**FILE,"date":"2026-10-22"}
        self.assertEqual(assess(data(),f,DAY)["status"],
                         "PRELIMINARY_FILING_DATE_NOT_PIT_SAFE")
    def test_corrected_filing_not_silently_assumed_final(self):
        f={**FILE,"correction_flag":True}
        self.assertEqual(assess(data(),f,DAY)["status"],
                         "PRELIMINARY_AMENDED_REQUIRES_RECONCILIATION")
    def test_data_period_after_receipt_invalid(self):
        f={**FILE,"date":"2026-07-01"}
        self.assertEqual(assess(data(),f,DAY)["status"],
                         "PRELIMINARY_FILING_DATE_NOT_PIT_SAFE")
    def test_malformed_document_blocks(self):
        self.assertEqual(decode_document(b"not zip")["status"],
                         "INVALID_OR_OVERSIZE_PRELIMINARY_ZIP")
    def test_real_zip_xml_table_with_dated_scope(self):
        xml="""<?xml version="1.0" encoding="utf-8"?>
          <DOCUMENT><P>단위: 백만원</P>
          <TABLE><TR><TD>당해실적</TD><TD>2026.07.01 ~ 2026.09.30</TD></TR>
          <TR><TD>전년동기실적</TD><TD>2025.07.01 ~ 2025.09.30</TD></TR>
          <TR><TH>구분</TH><TH>당해실적</TH><TH>전기실적</TH><TH>전년동기실적</TH></TR>
          <TR><TD>매출액</TD><TD>1,250,000</TD><TD>1,200,000</TD><TD>1,000,000</TD></TR>
          <TR><TD>영업이익</TD><TD>120,000</TD><TD>140,000</TD><TD>100,000</TD></TR>
          </TABLE></DOCUMENT>"""
        parsed=decode_document(zipped(xml))
        self.assertEqual(parsed["unit_candidates"],["백만원"])
        result=assess(parsed,FILE,DAY)
        self.assertEqual(result["revenue_yoy_pct"],25)
    def test_real_zip_sgml_malformed_table_with_dates(self):
        html="""<HTML><P>단위 : 백만원</P><TABLE>
        <TR><TD>당해실적<TD>2026.07.01~2026.09.30
        <TR><TD>전년동기실적<TD>2025.07.01~2025.09.30
        <TR><TD>구분<TD>당해실적<TD>전기실적<TD>전년동기실적
        <TR><TD>매출액<TD>1,250,000<TD>1,200,000<TD>1,000,000
        <TR><TD>영업이익<TD>120,000<TD>140,000<TD>100,000
        </TABLE></HTML>"""
        parsed=decode_document(zipped(html))
        self.assertEqual(parsed["status"],"PRELIMINARY_TABLE_ROWS_READ")
        self.assertEqual(assess(parsed,FILE,DAY)["operating_profit_yoy_pct"],20)
    def test_real_dart_sgml_split_period_and_merged_quarter_headers(self):
        rows=[
            ["__TABLE_BOUNDARY__"],
            ["당기실적","2026-07-01","~","2026-09-30"],
            ["전기실적","2026-04-01","~","2026-06-30"],
            ["전년동기실적","2025-07-01","~","2025-09-30"],
            ["당기누계실적","2026-01-01","~","2026-09-30"],
            ["전년동기누적실적","2025-01-01","~","2025-09-30"],
            ["__TABLE_BOUNDARY__"],
            ["1. 연결실적내용","단위 : 백만원, %"],
            ["구분","당기실적","전기실적","전기대비","전년동기실적","전년동기대비"],
            ["('26.3Q)","('26.2Q)","증감율(%)","흑자적자전환여부",
             "('25.3Q)","증감율(%)","흑자적자전환여부"],
            ["매출액","당해실적","1,250,000","1,200,000",
             "4.2","-","1,000,000","25.0","-"],
            ["누계실적","3,560,000","-","-","-","3,000,000","18.7","-"],
            ["영업이익","당해실적","120,000","140,000",
             "-14.3","-","100,000","20.0","-"],
            ["누계실적","360,000","-","-","-","200,000","80.0","-"],
            ["__TABLE_BOUNDARY__"]]
        r=assess(data(rows),FILE,DAY)
        self.assertEqual(r["status"],"PRELIMINARY_SINGLE_QUARTER_SOURCE_RESEARCH_ONLY")
        self.assertEqual(r["quarter_period"]["current_end"],"2026-09-30")
        self.assertEqual(r["revenue_current_krw"],1_250_000_000_000)
        self.assertEqual(r["operating_profit_current_krw"],120_000_000_000)
        self.assertEqual(r["revenue_yoy_pct"],25)
        self.assertEqual(r["operating_profit_yoy_pct"],20)
        self.assertFalse(r["trade_approved"])
    def test_merged_quarter_header_wrong_year_cannot_mix_values(self):
        rows=[
            ["당기실적","2026-07-01","~","2026-09-30"],
            ["전년동기실적","2025-07-01","~","2025-09-30"],
            ["__TABLE_BOUNDARY__"],
            ["구분","당기실적","전기실적","전기대비","전년동기실적","전년동기대비"],
            ["('26.3Q)","('26.2Q)","증감율(%)","-",
             "('24.3Q)","증감율(%)","-"],
            ["매출액","당해실적","1250","1200","4","-","1000","25","-"],
            ["영업이익","당해실적","120","140","-14","-","100","20","-"]]
        r=assess(data(rows),FILE,DAY)
        self.assertEqual(r["status"],"PRELIMINARY_SAME_ROW_YOY_VALUES_MISSING")
        self.assertFalse(r["preliminary_figures_source_verified"])
    def test_quarterly_gain_must_not_be_replaced_with_ytd_values(self):
        rows=[
            ["당기실적","2026-07-01","~","2026-09-30"],
            ["전년동기실적","2025-07-01","~","2025-09-30"],
            ["__TABLE_BOUNDARY__"],
            ["구분","당기실적","전기실적","전기대비","전년동기실적","전년동기대비"],
            ["('26.3Q)","('26.2Q)","증감율(%)","-",
             "('25.3Q)","증감율(%)","-"],
            ["매출액","당해실적","1250","1200","4","-","1000","25","-"],
            ["누계실적","9999","-","-","-","1111","800","-"],
            ["영업이익","당해실적","120","140","-14","-","100","20","-"],
            ["누계실적","9000","-","-","-","800","1100","-"]]
        r=assess(data(rows),FILE,DAY)
        self.assertEqual(r["revenue_current_krw"],1_250_000_000)
        self.assertEqual(r["operating_profit_current_krw"],120_000_000)
        self.assertEqual(r["revenue_yoy_pct"],25)
    def test_dated_period_from_different_table_never_authorizes_numbers(self):
        rows=ROWS[:2]+[["__TABLE_BOUNDARY__"]]+ROWS[2:]
        r=assess(data(rows),FILE,DAY)
        self.assertEqual(r["status"],"PRELIMINARY_SAME_ROW_YOY_VALUES_MISSING")
        self.assertFalse(r["preliminary_figures_source_verified"])
    def test_two_conflicting_complete_quarter_tables_are_not_picked_silently(self):
        other=[*ROWS]
        other[3]=["매출액","2,500,000","2,400,000","1,000,000","150%"]
        rows=ROWS+[["__TABLE_BOUNDARY__"]]+other
        r=assess(data(rows),FILE,DAY)
        self.assertEqual(r["status"],"PRELIMINARY_MULTIPLE_QUARTER_TABLES_AMBIGUOUS")
        self.assertIsNone(r["revenue_current_krw"])
    def test_negative_current_operating_is_earnings_warning(self):
        rows=[*ROWS]
        rows[4]=["영업이익","-20,000","1,000","100,000",""]
        r=assess(data(rows),FILE,DAY)
        self.assertEqual(r["earnings_quality"],"RECENT_PRELIMINARY_WEAKENING")
    def test_unverifiable_unit_is_not_silently_krw(self):
        self.assertIsNone(parse_amount("120,000","달러"))
        self.assertEqual(parse_amount("(100)","원"),-100)
    def test_ambiguous_duplicate_comparison_headers_rejected(self):
        rows=[*ROWS]
        rows[2]=["구분","당해실적","당해실적","전년동기실적"]
        self.assertEqual(assess(data(rows),FILE,DAY)["status"],
                         "PRELIMINARY_SAME_ROW_YOY_VALUES_MISSING")

if __name__=="__main__":unittest.main()
