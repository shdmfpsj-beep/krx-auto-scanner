import unittest
from c3_top2_provisional_report_v1 import report, validate_export

A=dict(plan_id="a",ticker="271560",name="오리온",
       selection_date="2026-10-30",registered_day="2026-10-31",
       source_close="114200",watch_low="110900",watch_high="113700",
       structure_stop="109600",target1="131500",target2="141700",
       expires_after_sessions="5")
B=dict(A,plan_id="b",ticker="026960",name="동서")

class ProvisionalReportTests(unittest.TestCase):
    def test_no_independent_feed(self):
        x=report([A,B],{},{"rows":0})
        self.assertFalse(x["independent_reference_available"])
        self.assertIn("SAME_PROVIDER",x["provenance"]["errors"])
    def test_no_trade_permission(self):
        x=report([A,B],{},{"rows":0})
        self.assertFalse(x["trade_approved"])
        self.assertFalse(x["orders_enabled"])
    def test_empty_data_no_completed_horizon(self):
        x=report([A,B],{},{"rows":0})
        self.assertFalse(x["coverage"]["271560"]["five_session_complete"])
    def test_freshness_manifest_matches_actual_dates(self):
        prices={("271560","2026-11-02"): {}, ("026960","2026-11-02"): {}}
        manifest=dict(provider="pykrx",price_adjustment="ADJUSTED",rows=2,
                      tickers=["271560","026960"],end="2026-11-03",failures={},
                      latest_observed_dates_aligned=True,
                      ticker_date_coverage={code:dict(observed_rows=1,
                          first_observed_date="2026-11-02",last_observed_date="2026-11-02",calendar_days_from_last_to_end=1)
                          for code in ("271560","026960")})
        self.assertTrue(validate_export([A,B],prices,manifest))
        manifest["ticker_date_coverage"]["271560"]["last_observed_date"]="2026-11-03"
        with self.assertRaisesRegex(ValueError,"COVERAGE_LAST_DATE_MISMATCH"):
            validate_export([A,B],prices,manifest)

    def test_freshness_manifest_rejects_false_lag(self):
        prices={("271560","2026-11-02"): {}, ("026960","2026-11-02"): {}}
        manifest=dict(provider="pykrx",price_adjustment="ADJUSTED",rows=2,
                      tickers=["271560","026960"],end="2026-11-03",failures={},
                      latest_observed_dates_aligned=True,
                      ticker_date_coverage={code:dict(observed_rows=1,
                          first_observed_date="2026-11-02",last_observed_date="2026-11-02",
                          calendar_days_from_last_to_end=1)
                          for code in ("271560","026960")})
        manifest["ticker_date_coverage"]["271560"]["calendar_days_from_last_to_end"]=0
        with self.assertRaisesRegex(ValueError,"COVERAGE_LAST_DATE_LAG_MISMATCH"):
            validate_export([A,B],prices,manifest)

    def test_freshness_manifest_rejects_false_alignment(self):
        prices={("271560","2026-11-02"): {}, ("026960","2026-11-03"): {}}
        manifest=dict(provider="pykrx",price_adjustment="ADJUSTED",rows=2,
                      tickers=["271560","026960"],end="2026-11-03",failures={},
                      latest_observed_dates_aligned=True,
                      ticker_date_coverage={
                          "271560":dict(observed_rows=1,first_observed_date="2026-11-02",last_observed_date="2026-11-02",calendar_days_from_last_to_end=1),
                          "026960":dict(observed_rows=1,first_observed_date="2026-11-03",last_observed_date="2026-11-03",calendar_days_from_last_to_end=0)})
        with self.assertRaisesRegex(ValueError,"COVERAGE_ALIGNMENT_MISMATCH"):
            validate_export([A,B],prices,manifest)

    def test_manifest_preserved(self):
        x=report([A,B],{},{"rows":0,"failures":{"271560":"EMPTY"}})
        self.assertIn("271560",x["collector_manifest"]["failures"])

if __name__=="__main__":
    unittest.main()
