#!/usr/bin/env python3
"""Actual-style OpenDART contract arithmetic: explicit units and no buys."""
import unittest
from dart_contract_terms import amount_krw,ratio_percent,extract,dates_in

def field(label,val):
    return {"label":label,"neighboring_text":val,
            "interpretation":"SGML_ADJACENT_CELL_UNVERIFIED"}

class ContractTermsTests(unittest.TestCase):
    def test_krw_integer_from_labeled_won(self):
        self.assertEqual(amount_krw("12,345,678,000","계약금액(원)"),12345678000)
    def test_korean_hundred_million_unit(self):
        self.assertEqual(amount_krw("500억원","계약금액"),50_000_000_000)
    def test_million_and_thousand_unit(self):
        self.assertEqual(amount_krw("12,300","계약금액(백만원)"),12_300_000_000)
        self.assertEqual(amount_krw("2000천원","계약금액"),2_000_000)
    def test_unlabeled_number_and_unit_mismatch_rejected(self):
        self.assertIsNone(amount_krw("500000000","계약금액"))
        self.assertIsNone(amount_krw("500억원","계약금액(원)"))
    def test_foreign_currency_and_ambiguous_amount_fail(self):
        for value in ("12.4억달러","USD 1,200,000","약 5억원",
                      "12~15억원","-100억원","100억원 이상","1,20,000 원"):
            self.assertIsNone(amount_krw(value,"계약금액"))
    def test_percent_requires_label_or_visible_percent_symbol(self):
        self.assertEqual(ratio_percent("12.5%","매출액 대비"),12.5)
        self.assertEqual(ratio_percent("12.5","매출액대비(%)"),12.5)
        self.assertIsNone(ratio_percent("12.5","매출액대비"))
    def test_single_filing_ratio_reconciles_if_all_fields_are_explicit(self):
        r=extract([field("계약금액(원)","50,000,000,000"),
                   field("최근매출액(원)","500,000,000,000"),
                   field("매출액대비(%)","10.0"),
                   field("계약상대","해외 발주처"),
                   field("계약기간","2026.10.01 ~ 2028.12.31")])
        self.assertEqual(r["amount_krw"],50_000_000_000)
        self.assertEqual(r["recent_sales_krw"],500_000_000_000)
        self.assertEqual(r["calculated_sales_ratio_pct"],10.0)
        self.assertEqual(r["consistency"],"SINGLE_FILING_ARITHMETIC_MATCH")
        self.assertEqual(r["contract_period"]["end"],"2028-12-31")
        self.assertFalse(r["contract_amount_independently_verified"])
        self.assertFalse(r["direct_company_positive_impact_verified"])
    def test_ratio_arithmetic_mismatch_blocks_promotion(self):
        r=extract([field("계약금액(원)","50,000,000,000"),
                   field("최근매출액(원)","500,000,000,000"),
                   field("매출액 대비","19%")])
        self.assertEqual(r["status"],"FILING_RATIO_MISMATCH")
        self.assertEqual(r["consistency"],"DOCUMENT_RATIO_MISMATCH_REVIEW")
        self.assertFalse(r["direct_company_positive_impact_verified"])
    def test_multiple_conflicting_amounts_not_silently_chosen(self):
        r=extract([field("계약금액","40억원"),field("계약금액","60억원")])
        self.assertEqual(r["status"],"CONFLICTING_LABELED_FILING_VALUES")
        self.assertIsNone(r["amount_krw"])
    def test_same_duplicate_amount_remains_candidate_only(self):
        r=extract([field("계약금액","40억원"),field("계약금액","40억원")])
        self.assertEqual(r["amount_krw"],4_000_000_000)
        self.assertFalse(r["contract_amount_independently_verified"])
    def test_changed_and_old_contract_values_not_mixed(self):
        r=extract([field("변경전계약금액(원)","1000000000"),
                   field("변경후계약금액(원)","3000000000"),
                   field("계약금액(원)","2000000000")],
                   correction_risk="CORRECTION_OR_WITHDRAWAL")
        self.assertEqual(r["status"],"CORRECTION_OR_WITHDRAWAL_REVIEW")
        self.assertEqual(r["amount_krw"],2000000000)
        self.assertFalse(r["direct_company_positive_impact_verified"])
    def test_missing_original_amount_does_not_estimate_contract_size(self):
        r=extract([field("계약상대","A사"),field("매출액 대비","25%")])
        self.assertIsNone(r["amount_krw"])
        self.assertEqual(r["consistency"],"RATIO_ONLY_NO_SALES_BASE")
    def test_unsupported_currency_unit_not_guessed(self):
        r=extract([field("계약금액 (USD)","1,000,000"),
                   field("최근매출액","200억원")])
        self.assertIsNone(r["amount_krw"])
    def test_invalid_dates_are_not_period(self):
        self.assertEqual(dates_in("2026.02.30 ~ 2027.03.01"),[])
        self.assertIsNone(extract([field("계약기간","2026-12-31 ~ 2026-01-01")])["contract_period"])
    def test_ratio_fraction_is_not_misread_as_number_of_won(self):
        r=extract([field("매출액 대비(%)","5.2")])
        self.assertEqual(r["disclosed_sales_ratio_pct"],5.2)
        self.assertIsNone(r["amount_krw"])
    def test_certain_fractional_won_is_rejected_without_rounding_up(self):
        self.assertIsNone(amount_krw("1.5 원","계약금액"))
        self.assertEqual(amount_krw("1.5억원","계약금액"),150000000)
    def test_many_conflicting_label_values_fail_closed(self):
        fields=[field("계약금액(백만원)",str(i)) for i in range(30)]
        r=extract(fields)
        self.assertIsNone(r["amount_krw"])
        self.assertEqual(r["consistency"],"CONFLICT")
    def test_direct_document_value_is_never_an_order(self):
        r=extract([field("계약금액","500억원")])
        self.assertFalse(r["entry_or_stop_signal"])
        self.assertFalse(r["direct_company_positive_impact_verified"])
        self.assertFalse(r["contract_amount_independently_verified"])

if __name__=="__main__":unittest.main()
