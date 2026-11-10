"""Offline tests for paper capture date cutoff; no network or orders."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
import c3_paper_price_capture_v1 as cap


class FakeFrame:
    empty = False
    def __init__(self, day):
        self.day = day
    def iterrows(self):
        yield self.day, {"시가": 100, "고가": 105, "저가": 95, "종가": 101, "거래량": 1000}


class CaptureCutoffTests(unittest.TestCase):
    def check_cutoff(self, hour, minute, expected_day):
        seen = []
        def fetch(start, end, ticker):
            seen.append((start, end, ticker))
            return FakeFrame(datetime.fromisoformat(expected_day))
        with tempfile.TemporaryDirectory() as d:
            with patch.object(cap, "load_csv", return_value=[{"ticker": "005930"}]), patch.object(cap, "bar_valid", side_effect=lambda row: row):
                result = cap.collect(Path(d)/"plans.csv", Path(d)/"out", now=datetime(2026, 11, 10, hour, minute, tzinfo=ZoneInfo("Asia/Seoul")), fetch=fetch)
            self.assertEqual(result["completed_bar_cutoff_day"], expected_day)
            self.assertEqual(seen[0][1], expected_day.replace("-", ""))
            self.assertEqual(result["ticker_states"]["005930"]["last_session"], expected_day)
            self.assertFalse(result["regular_only_ohlcv_certified"])
            self.assertFalse(result["orders_enabled"])

    def test_morning_uses_previous_day(self):
        self.check_cutoff(7, 59, "2026-11-09")

    def test_before_cutoff_uses_previous_day(self):
        self.check_cutoff(20, 14, "2026-11-09")

    def test_at_cutoff_uses_today(self):
        self.check_cutoff(20, 15, "2026-11-10")

    def test_future_bar_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(cap, "load_csv", return_value=[{"ticker": "005930"}]):
                result = cap.collect(Path(d)/"plans.csv", Path(d)/"out",
                    now=datetime(2026, 11, 10, 7, 59, tzinfo=ZoneInfo("Asia/Seoul")),
                    fetch=lambda *_: FakeFrame(datetime(2026, 11, 10)))
            self.assertEqual(result["ticker_states"]["005930"]["capture_status"], "FAILED_OR_SUSPENDED_NO_PAPER_TRADE")


if __name__ == "__main__":
    unittest.main()
