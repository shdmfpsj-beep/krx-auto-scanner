"""Regression tests for same-day independent evidence integrity."""
import unittest
from daily_asof_gate import evaluate, to_markdown


class DailyAsOfGateTests(unittest.TestCase):
    def setUp(self):
        self.today = "2026-10-22"
        self.recovery = {"market_data_date": self.today, "coverage_ratio": .992,
                         "universe": 2625, "valid_ohlcv": 2604,
                         "geometry_pass_count": 1, "c3_research_top5": ["005160"]}
        self.focus = {"asof": self.today, "research_count": 8,
                      "stop_reference_count": 8,
                      "orders_enabled": False, "trade_approved": False}
        self.sector = {"asof": self.today, "orders_enabled": False,
                       "trade_approved": False, "sector_top3": [{"sector": "SEMICON"}],
                       "stock_research_top5": [{"ticker": "005930"}]}
        self.money = {"asof": self.today}

    def run_gate(self):
        return evaluate(self.today, self.recovery, self.focus, self.sector, self.money)

    def test_20261022_real_artifact_mismatch_stays_cash(self):
        self.sector["asof"] = "2026-10-21"
        self.money["asof"] = "2026-10-21"
        self.sector["sector_top3"] = []
        self.sector["stock_research_top5"] = []
        output = self.run_gate()
        self.assertFalse(output["all_source_dates_aligned"])
        self.assertFalse(output["trade_approved"])
        self.assertEqual("CASH", output["decision"])
        self.assertIn("SECTOR_RANKING_NOT_TODAY:2026-10-21", output["data_integrity_blockers"])
        self.assertIn("SECTOR_CONSTITUENT_FLOW_NOT_TODAY:2026-10-21", output["data_integrity_blockers"])
        self.assertIn("2,604", f"{output['recovery_valid_ohlcv']:,}")
        self.assertIn("불일치", to_markdown(output))

    def test_dates_alone_never_trigger_buy(self):
        output = self.run_gate()
        self.assertTrue(output["all_source_dates_aligned"])
        self.assertEqual(output["final_score_threshold"], 80)
        self.assertEqual(output["score_scale_max"], 100)
        self.assertFalse(output["final_score_verified"])
        self.assertFalse(output["trade_approved"])
        self.assertFalse(output["orders_enabled"])
        self.assertIn("FINAL_80_LIVE_ENTRY_CASH_HOLDINGS_NOT_VERIFIED", output["data_integrity_blockers"])

    def test_low_coverage_and_candidate_mismatch_block(self):
        self.recovery["coverage_ratio"] = .89
        self.recovery["candidate_date_mismatch"] = True
        output = self.run_gate()
        self.assertIn("PRICE_COVERAGE_BELOW_95_PERCENT_OR_MISSING", output["data_integrity_blockers"])
        self.assertIn("KRX_CANDIDATE_DATE_MISMATCH", output["data_integrity_blockers"])

    def test_missing_artifacts_fail_closed(self):
        output = evaluate(self.today, {}, {}, {}, {})
        self.assertFalse(output["trade_approved"])
        self.assertFalse(output["all_source_dates_aligned"])
        self.assertEqual(output["recovery_research_watch_tickers"], [])
        self.assertIn("PRICE_COVERAGE_BELOW_95_PERCENT_OR_MISSING", output["data_integrity_blockers"])

    def test_upstream_illegal_order_approval_triggers_alarm(self):
        self.sector["trade_approved"] = True
        output = self.run_gate()
        self.assertFalse(output["orders_enabled"])
        self.assertIn("SECTOR_RESEARCH_ORDER_FLAG_NOT_SAFE", output["data_integrity_blockers"])


if __name__ == "__main__":
    unittest.main()
