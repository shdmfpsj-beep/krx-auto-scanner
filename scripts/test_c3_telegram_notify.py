"""Regression checks for the C3 Telegram notification safety gates."""
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from c3_telegram_notify import build_message, expected_session, receipt_path, report_error


class TelegramNotifyTests(unittest.TestCase):
    def setUp(self):
        self.clock = datetime(2026, 11, 6, 22, 45, tzinfo=ZoneInfo("Asia/Seoul"))
        self.latest = {
            "source_price_asof": "2026-11-06",
            "source_run_id": "12345",
            "generated_at": "2026-11-06T13:30:00+00:00",
            "source_received_at": "2026-11-06T13:29:00+00:00",
            "data_quality_state": "OFFICIAL_VERIFIED",
            "source_provider": "KRX_OFFICIAL_EOD",
            "source_quality_gate": {"status": "QUALITY_GATE_PASSED",
                                    "markets": {"KOSPI": {"rows": 900}, "KOSDAQ": {"rows": 1800}}},
            "current_scope": {"price_rows": 2700, "analysis_eligible": 1800},
            "errors": [],
            "orders_enabled": False,
            "current_action": "CASH",
            "new_registered_signals": 0,
            "research_top2_registered_for_source_session": False,
            "research_top2": [
                {"name": "가상종목", "ticker": "000001", "close": 50000,
                 "entry_plans": {"A_SUPPORT_LIMIT": {"plan": {"low": 48000, "high": 49000,
                                                         "stop": 45000, "resistance": 54000,
                                                         "resistance2": 58000}}}}
            ],
        }
        self.summary = {
            "source_price_asof": "2026-11-06",
            "source_run_id": "12345",
            "generated_at": "2026-11-06T13:30:00+00:00",
        }

    def test_good_verified_new_session(self):
        self.assertIsNone(report_error(self.latest, self.summary, self.clock))

    def test_yesterday_cannot_claim_today(self):
        self.latest["source_price_asof"] = "2026-11-05"
        self.summary["source_price_asof"] = "2026-11-05"
        self.assertEqual(report_error(self.latest, self.summary, self.clock),
                         "NO_NEW_COMPLETED_SESSION")

    def test_before_close_expects_previous_day(self):
        self.assertEqual(expected_session(datetime(2026, 11, 6, 14, 0,
                         tzinfo=ZoneInfo("Asia/Seoul"))), "2026-11-05")

    def test_monday_morning_expects_friday(self):
        self.assertEqual(expected_session(datetime(2026, 11, 9, 9, 0,
                         tzinfo=ZoneInfo("Asia/Seoul"))), "2026-11-06")

    def test_weekends_do_not_send(self):
        self.assertIsNone(expected_session(datetime(2026, 11, 7, 12, 0,
                            tzinfo=ZoneInfo("Asia/Seoul"))))

    def test_mixed_runs_rejected(self):
        self.summary["source_run_id"] = "other"
        self.assertEqual(report_error(self.latest, self.summary, self.clock),
                         "RUN_ID_MISMATCH")

    def test_summary_version_rejected(self):
        self.summary["generated_at"] = "2026-11-06T13:00:00+00:00"
        self.assertEqual(report_error(self.latest, self.summary, self.clock),
                         "REPORT_VERSION_MISMATCH")

    def test_missing_quality_rejected(self):
        self.latest["data_quality_state"] = "PROVISIONAL"
        self.assertEqual(report_error(self.latest, self.summary, self.clock),
                         "UNVERIFIED_MARKET_DATA")

    def test_wrong_market_rows_rejected(self):
        self.latest["current_scope"]["price_rows"] = 2600
        self.assertEqual(report_error(self.latest, self.summary, self.clock),
                         "MARKET_ROW_COUNT_MISMATCH")

    def test_order_enabled_rejected(self):
        self.latest["orders_enabled"] = True
        self.assertEqual(report_error(self.latest, self.summary, self.clock),
                         "LIVE_ORDER_OR_ACTION_POLICY_VIOLATION")

    def test_old_report_rejected(self):
        self.latest["generated_at"] = "2026-11-04T09:00:00+00:00"
        self.summary["generated_at"] = self.latest["generated_at"]
        self.assertEqual(report_error(self.latest, self.summary, self.clock),
                         "STALE_OR_FUTURE_REPORT")

    def test_message_has_prices_but_no_buy(self):
        msg = build_message(self.latest, self.summary)
        self.assertIn("48,000원 ~ 49,000원", msg)
        self.assertIn("45,000원", msg)
        self.assertIn("미등록 미리보기", msg)
        self.assertIn("CASH", msg)

    def test_receipt_path_blocks_injection(self):
        with self.assertRaises(ValueError):
            receipt_path("../../etc/passwd")
        self.assertIn("2026-11-06.json", receipt_path("2026-11-06"))


if __name__ == "__main__":
    unittest.main()
