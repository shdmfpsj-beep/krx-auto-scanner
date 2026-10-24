"""Regression tests for same-day independent evidence integrity."""
import unittest
import csv
from datetime import datetime
from zoneinfo import ZoneInfo
from tempfile import TemporaryDirectory
from pathlib import Path
from daily_asof_gate import evaluate, to_markdown, krx_common_tick_floor, research_candidate_from_csv, nominal_last_completed_krx_session


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

    def test_preopen_20261023_targets_20261022_close_not_future_session(self):
        dt=lambda iso:datetime.fromisoformat(iso).replace(tzinfo=ZoneInfo("Asia/Seoul"))
        cases=[
          ("2026-10-23T04:54:00","2026-10-22"),
          ("2026-10-23T15:59:00","2026-10-22"),
          ("2026-10-23T16:00:00","2026-10-22"),
          ("2026-10-23T19:59:00","2026-10-22"),
          ("2026-10-23T20:09:00","2026-10-22"),
          ("2026-10-23T20:10:00","2026-10-23"),
          ("2026-10-24T10:00:00","2026-10-23"),
          ("2026-10-25T23:00:00","2026-10-23"),
          ("2026-10-26T08:35:00","2026-10-23"),
          ("2026-10-26T16:00:00","2026-10-23"),
          ("2026-10-26T20:09:00","2026-10-23"),
          ("2026-10-26T20:10:00","2026-10-26")]
        for local,expected in cases:
            self.assertEqual(nominal_last_completed_krx_session(dt(local)),expected,local)
        with self.assertRaisesRegex(ValueError,"KST_TZ_AWARE"):
            nominal_last_completed_krx_session(datetime(2026,10,23,20,30))
        result=self.run_gate()
        self.assertEqual(result["target_session_semantics"],
                         "MOST_RECENT_NOMINAL_COMPLETED_KRX_WEEKDAY_NOT_HOLIDAY_VERIFIED")
        self.assertIn("직전 완료 거래일",to_markdown(result))

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

    def test_embedded_focus_is_not_labeled_an_independent_crosscheck(self):
        result=evaluate(self.today,self.recovery,self.focus,self.sector,
                        {**self.money,"market_ohlc_quality_verified":True},
                        focus_source="SECTOR_FIRST_EMBEDDED_FALLBACK")
        self.assertTrue(result["all_source_dates_aligned"])
        self.assertFalse(result["all_independent_sources_verified"])
        self.assertEqual(result["focus_research_count"],8)
        self.assertIn("FOCUS_SINGLE_PIPELINE_NOT_INDEPENDENT",
                      result["data_integrity_blockers"])
        self.assertNotIn("FOCUS_SOURCE_MISSING",result["data_integrity_blockers"])
        self.assertIn("SECTOR_FIRST_EMBEDDED_FALLBACK",to_markdown(result))
        self.assertEqual(result["decision"],"CASH")

    def test_missing_focus_is_missing_not_claimed_unsafe(self):
        result=evaluate(self.today,self.recovery,{},self.sector,self.money)
        self.assertIn("FOCUS_SOURCE_MISSING",result["data_integrity_blockers"])
        self.assertNotIn("FOCUS_RESEARCH_ORDER_FLAG_NOT_SAFE",
                         result["data_integrity_blockers"])

    def test_oct23_real_archives_report_missed_regular_window(self):
        # Actual 2026-10-23 research: 2604 valid OHLC, 59 of 81
        # shared candidate closes conflict; regular capture window missed.
        day = "2026-10-23"
        recovery = {**self.recovery, "market_data_date": day,
                    "candidate_date_mismatch": 0}
        focus = {**self.focus, "asof": day}
        sector = {**self.sector, "asof": day,
            "source_price_parity": {
                "asof": day, "status": "CROSS_SOURCE_CLOSE_CONFLICT",
                "overlap_tickers": 81, "close_mismatches": 59,
                "independent_provider_verified": False,
            }}
        money = {**self.money, "asof": day,
                 "market_ohlc_quality_verified": True}
        regular = {
            "target_asof": day, "mode": "KRX_REGULAR_ONLY_0900_1530",
            "after_market_excluded": True,
            "regular_snapshot_available": False,
            "provider_session_scope_verified": False,
            "market_source_status": "PENDING_DATA_VALIDATION",
            "blockers": ["CAPTURE_WINDOW_NOT_VERIFIED"],
            "trade_approved": False, "decision": "CASH",
        }
        result = evaluate(day, recovery, focus, sector, money,
                          regular=regular)
        self.assertTrue(result["all_source_dates_aligned"])
        self.assertFalse(result["all_independent_sources_verified"])
        self.assertFalse(result["regular_only_price_verified"])
        self.assertEqual(result["price_parity_mismatch_count"], 59)
        self.assertIn("CROSS_SOURCE_DAILY_CLOSE_CONFLICT_OR_UNVERIFIED",
                      result["data_integrity_blockers"])
        self.assertIn("REGULAR_ONLY_PRICE_SOURCE_NOT_CERTIFIED",
                      result["data_integrity_blockers"])
        report = to_markdown(result)
        self.assertIn("중복 81종목 중 종가 불일치 59종목", report)
        self.assertIn("정규장 전용 가격 인증:", report)
        self.assertIn("미완료", report)
        self.assertEqual(result["decision"], "CASH")

    def test_regular_only_archive_must_match_same_day_and_session(self):
        source = {
            "target_asof": self.today, "mode": "KRX_REGULAR_ONLY_0900_1530",
            "after_market_excluded": True, "regular_snapshot_available": True,
            "provider_session_scope_verified": True,
            "market_source_status": "REGULAR_PRICE_SOURCE_VERIFIED_RESEARCH_ONLY",
            "blockers": [], "trade_approved": False, "decision": "CASH",
        }
        self.assertTrue(self.run_gate()["all_source_dates_aligned"])
        missing = evaluate(self.today, self.recovery, self.focus,
                           self.sector, self.money, regular={})
        self.assertIn("REGULAR_ONLY_REPORT_MISSING",
                      missing["data_integrity_blockers"])
        stale = evaluate(self.today, self.recovery, self.focus,
                         self.sector, self.money,
                         regular={**source, "target_asof": "2026-10-21"})
        self.assertIn("REGULAR_ONLY_REPORT_ASOF_MISMATCH",
                      stale["data_integrity_blockers"])
        misleading = evaluate(self.today, self.recovery, self.focus,
                         self.sector, self.money, regular={
                           **source, "provider_session_scope_verified": False,
                         })
        self.assertFalse(misleading["regular_only_price_verified"])
        valid = evaluate(self.today, self.recovery, self.focus, self.sector,
                         self.money, regular=source)
        self.assertTrue(valid["regular_only_price_verified"])
        self.assertFalse(valid["all_independent_sources_verified"])
        self.assertEqual(valid["decision"], "CASH")

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
