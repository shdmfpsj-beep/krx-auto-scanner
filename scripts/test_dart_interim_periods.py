#!/usr/bin/env python3
"""Interim YTD statement regression suite: forbid 3-month false growth."""
import unittest
from datetime import date
from dart_interim_periods import identify_interim_filing,evaluate_interim,select

ASOF=date(2026,10,22)
def filing(name="반기보고서 (2026.06)",day=date(2026,8,14)):
    return (day,"20260814000011",name)
def row(k,v,prev,source="IS"):
    return dict(sj_div=source,account_id=k,fs_div="CFS",
        thstrm_add_amount=str(v),frmtrm_add_amount=str(prev),
        thstrm_amount="900000",frmtrm_amount="10000",
        bsns_year="2026",reprt_code="11012",currency="KRW")
def rows():
    return [row("ifrs-full_Revenue",120,100),
            row("dart_OperatingIncomeLoss",16,10)]
def payload(x=None):
    return {"status":"000","list":rows() if x is None else x}
P=identify_interim_filing(filing(),ASOF)

class InterimFinancialTests(unittest.TestCase):
    def test_h1_dated_report_maps_to_11012(self):
        self.assertEqual(P["report_code"],"11012")
        self.assertEqual(P["period_end"],"2026-06-30")
        self.assertEqual(P["basis"],"CUMULATIVE_YEAR_TO_DATE")
    def test_q1_maps_to_11013_not_half_year(self):
        p=identify_interim_filing(filing("분기보고서 (2026.03)"),ASOF)
        self.assertEqual(p["report_code"],"11013")
        self.assertEqual(p["period_end"],"2026-03-31")
    def test_q3_maps_to_11014_correct_30_day_end(self):
        p=identify_interim_filing(filing("분기보고서 (2025.09)"),ASOF)
        self.assertEqual(p["report_code"],"11014")
        self.assertEqual(p["period_end"],"2025-09-30")
    def test_future_report_never_used(self):
        self.assertIsNone(identify_interim_filing(
            filing(day=date(2026,10,23)),ASOF))
    def test_annual_report_not_interim(self):
        self.assertIsNone(identify_interim_filing(
            filing("사업보고서 (2025.12)"),ASOF))
    def test_report_title_period_mismatch_rejected(self):
        self.assertIsNone(identify_interim_filing(
            filing("반기보고서 (2026.09)"),ASOF))
    def test_ytd_sales_profit_growth_and_margin(self):
        r=evaluate_interim(payload(),"CFS",P)
        self.assertEqual(r["status"],"DATED_INTERIM_YTD_RESEARCH_ONLY")
        self.assertEqual(r["yoy_revenue_pct"],20)
        self.assertEqual(r["yoy_operating_profit_pct"],60)
        self.assertEqual(r["ytd_operating_margin_pct"],13.33)
        self.assertEqual(r["quality"],"INTERIM_SALES_AND_PROFIT_GROWTH_OBSERVED")
        self.assertTrue(r["latest_periodic_financials_verified"])
    def test_only_three_month_amount_does_not_count_as_ytd(self):
        x=[{k:v for k,v in r.items() if k not in
            ("thstrm_add_amount","frmtrm_add_amount")} for r in rows()]
        r=evaluate_interim(payload(x),"CFS",P)
        self.assertEqual(r["status"],"INTERIM_CUMULATIVE_METRICS_INCOMPLETE")
        self.assertFalse(r["latest_periodic_financials_verified"])
    def test_missing_account_detail_is_allowed(self):
        r=evaluate_interim(payload(),"CFS",P)
        self.assertEqual(r["missing_cumulative_keys"],[])
    def test_explicit_wrong_division_not_relabelled(self):
        x=[{**r,"fs_div":"OFS"} for r in rows()]
        r=evaluate_interim(payload(x),"CFS",P)
        self.assertEqual(r["status"],"INTERIM_CUMULATIVE_METRICS_INCOMPLETE")
    def test_conflicting_unique_standard_account_blocks_growth(self):
        x=rows()+[row("ifrs-full_Revenue",150,100)]
        r=evaluate_interim(payload(x),"CFS",P)
        self.assertEqual(r["status"],"INTERIM_CUMULATIVE_METRICS_INCOMPLETE")
    def test_wrong_fiscal_year_is_rejected(self):
        x=[{**r,"bsns_year":"2025"} for r in rows()]
        self.assertEqual(evaluate_interim(payload(x),"CFS",P)["status"],
                         "INTERIM_SOURCE_PERIOD_MISMATCH")
    def test_wrong_report_code_is_rejected(self):
        x=[{**r,"reprt_code":"11014"} for r in rows()]
        self.assertEqual(evaluate_interim(payload(x),"CFS",P)["status"],
                         "INTERIM_SOURCE_PERIOD_MISMATCH")
    def test_unknown_nonkrw_currency_rejected(self):
        x=[{**r,"currency":"USD"} for r in rows()]
        self.assertEqual(evaluate_interim(payload(x),"CFS",P)["status"],
                         "INTERIM_NON_KRW")
    def test_sales_decline_classified_as_weaker(self):
        x=[row("ifrs-full_Revenue",90,100),row("dart_OperatingIncomeLoss",6,10)]
        r=evaluate_interim(payload(x),"CFS",P)
        self.assertEqual(r["quality"],"INTERIM_PROFIT_OR_SALES_WEAKENING")
    def test_prior_operating_loss_not_fake_pct_infinite(self):
        x=[row("ifrs-full_Revenue",120,100),row("dart_OperatingIncomeLoss",3,-5)]
        r=evaluate_interim(payload(x),"CFS",P)
        self.assertIsNone(r["yoy_operating_profit_pct"])
        self.assertEqual(r["quality"],"INTERIM_SALES_AND_PROFIT_GROWTH_OBSERVED")
    def test_no_api_data_stays_unverified(self):
        r=evaluate_interim({"status":"013"},"CFS",P)
        self.assertEqual(r["status"],"INTERIM_API_UNAVAILABLE")
        self.assertFalse(r["latest_periodic_financials_verified"])

if __name__=="__main__":unittest.main()
