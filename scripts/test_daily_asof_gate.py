"""Regression tests for same-day independent evidence integrity."""
import unittest
import csv
from tempfile import TemporaryDirectory
from pathlib import Path
from daily_asof_gate import evaluate, to_markdown, krx_common_tick_floor, research_candidate_from_csv


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

    def test_korean_common_stock_tick_floor_boundaries(self):
        pairs = {
            "1999.9": 1999, "2004.9": 2000, "3995.0": 3995,
            "3981.25": 3980, "3784.73": 3780, "4114.85": 4110,
            "4999.9": 4995, "5009.99": 5000, "20099": 20050,
            "50099": 50000, "200499": 200000, "500999": 500000,
        }
        for raw, expected in pairs.items():
            self.assertEqual(krx_common_tick_floor(raw), expected, raw)
        for invalid in (None, "NaN", "Infinity", -1, 0, "invalid"):
            self.assertIsNone(krx_common_tick_floor(invalid))

    def test_oct_22_real_research_candidate_prices_are_tick_aligned(self):
        row = {
            "ticker": "005160", "name": "동국산업",
            "snapshot_date": "2026-10-22", "structure_status": "RESEARCH_GEOMETRY_PASS",
            "trade_approval": "NO", "close_reference": "3995.0", "atr14": "601.07",
            "entry1_close_reference": "3995.0", "entry2_ma20_proxy": "3981.25",
            "structural_stop_reference": "3784.73", "no_chase_reference": "4114.85",
            "prior_60d_resistance": "5060.0", "rr_to_prior_resistance": "2.86",
            "c3_preliminary_score": "56", "k100_preliminary_score": "56",
            "blocking_reasons": "COMMON_STOCK_NOT_VERIFIED|TURNOVER_IS_ESTIMATED",
        }
        with TemporaryDirectory() as td:
            p = Path(td) / "today.csv"
            with p.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(row))
                w.writeheader()
                w.writerow(row)
            candidate = research_candidate_from_csv(p, ["005160"], "2026-10-22")
            self.assertEqual(candidate["entry2_ma20_proxy_tick_floor"], 3980)
            self.assertEqual(candidate["structural_stop_reference_tick_floor"], 3780)
            self.assertEqual(candidate["no_chase_reference_tick_floor"], 4110)
            self.assertTrue(candidate["tick_aligned_research_only"])
            self.assertFalse(candidate["rr_after_tick_and_costs_verified"])
            self.assertFalse(candidate["second_entry_is_distinct_research"])
            self.assertEqual(candidate["second_entry_quality_warning"],
                             "SECOND_ENTRY_TOO_NEAR_FIRST_VS_ATR")
            self.assertAlmostEqual(candidate["second_entry_spacing_atr"], 0.025, places=3)
            self.assertEqual(candidate["swing_stop_atr_warning"], "SWING_STOP_WITHIN_ONE_DAILY_ATR")
            self.assertAlmostEqual(candidate["structural_stop_distance_atr"], .358, places=3)
            self.assertEqual(research_candidate_from_csv(p, ["005160"], "2026-10-21"), {})
            row["trade_approval"] = "YES"
            with p.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(row))
                w.writeheader()
                w.writerow(row)
            self.assertEqual(research_candidate_from_csv(p, ["005160"], "2026-10-22"), {})

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

    def test_pending_sector_output_and_closed_position_are_explicit(self):
        from c3_account_state import load_c3_position
        self.sector["sector_selection_outcome"]="PENDING_DATA_VALIDATION"
        self.sector["stock_selection_outcome"]="PENDING_DATA_VALIDATION"
        self.sector["sector_top3"]=[]
        self.sector["stock_research_top5"]=[]
        state=load_c3_position()
        r=evaluate(self.today,self.recovery,self.focus,self.sector,self.money,
                   c3_state=state)
        self.assertIn("SECTOR_STOCK_FINAL_SELECTION_PENDING_DATA",
                      r["data_integrity_blockers"])
        self.assertEqual(r["sector_selection_outcome"],"PENDING_DATA_VALIDATION")
        self.assertEqual(r["c3_position_state"]["closed_shares_remaining"],0)
        self.assertIn("세방전지(004490) 전량 매도",to_markdown(r))
        self.assertEqual(r["decision"],"CASH")

    def test_dates_alone_never_trigger_buy(self):
        output = self.run_gate()
        self.assertTrue(output["all_source_dates_aligned"])
        self.assertEqual(output["final_score_threshold"], 80)
        self.assertEqual(output["score_scale_max"], 100)
        self.assertFalse(output["final_score_verified"])
        self.assertEqual(output["manual_review_gate"]["final_score_threshold"],80)
        self.assertEqual(output["manual_review_gate"]["decision"],"CASH")
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
