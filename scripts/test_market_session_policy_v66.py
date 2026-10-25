"""Ensure scanner never assumes an unfinished 16:10/17:00 bar is final."""
import unittest
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from market_session_policy_v66 import (
    KST,MARKET_SOURCE_READY_AFTER_KST,completed_scan_cutoff_date,
    source_policy_metadata)

def at(year,month,day,hour,minute):
    return datetime(year,month,day,hour,minute,tzinfo=KST)

class KRXCloseGuardTests(unittest.TestCase):
    def test_2026_oct23_aftermarket_mid_session_reads_previous_day(self):
        self.assertEqual(str(completed_scan_cutoff_date(at(2026,10,23,17,18))),"2026-10-22")
        self.assertEqual(str(completed_scan_cutoff_date(at(2026,10,23,20,14))),"2026-10-22")

    def test_2026_oct23_after_2015_allowed_current_complete_date(self):
        self.assertEqual(str(completed_scan_cutoff_date(at(2026,10,23,20,15))),"2026-10-23")
        self.assertEqual(str(completed_scan_cutoff_date(at(2026,10,23,20,45))),"2026-10-23")

    def test_before_close_on_monday_uses_friday_not_sunday(self):
        self.assertEqual(str(completed_scan_cutoff_date(at(2026,10,26,16,0))),"2026-10-23")

    def test_after_session_finish_monday_uses_monday(self):
        self.assertEqual(str(completed_scan_cutoff_date(at(2026,10,26,21,0))),"2026-10-26")

    def test_weekend_always_uses_last_weekday(self):
        self.assertEqual(str(completed_scan_cutoff_date(at(2026,10,25,11,0))),"2026-10-23")
        self.assertEqual(str(completed_scan_cutoff_date(at(2026,10,24,21,0))),"2026-10-23")

    def test_timezone_conversion_is_explicit(self):
        instant=datetime(2026,10,23,11,15,tzinfo=timezone.utc)
        self.assertEqual(str(completed_scan_cutoff_date(instant)),"2026-10-23")

    def test_naive_datetime_must_not_guess_timezone(self):
        with self.assertRaisesRegex(ValueError,"AWARE_DATETIME_REQUIRED"):
            completed_scan_cutoff_date(datetime(2026,10,23,20,15))

    def test_policy_never_certifies_regular_1530_or_orders(self):
        meta=source_policy_metadata(at(2026,10,23,20,45))
        self.assertEqual(meta["krx_aftermarket_end_kst"],"20:00")
        self.assertEqual(meta["earliest_final_session_check_kst"],"20:15")
        self.assertFalse(meta["source_session_scope_certified"])
        self.assertFalse(meta["market_holiday_calendar_verified"])
        self.assertFalse(meta["trade_approved"])
        self.assertFalse(meta["orders_enabled"])

if __name__=="__main__":unittest.main()
