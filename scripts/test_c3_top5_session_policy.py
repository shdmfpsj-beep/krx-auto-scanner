"""Calendar/date regressions only; no market, return or Telegram calls."""
import unittest
from datetime import datetime
import exchange_calendars as xc
from c3_top5_session_policy import session_plan

class SessionPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calendar=xc.get_calendar('XKRX',start='2026-01-01',end='2027-02-01')

    def plan(self, clock, manual=''):
        return session_plan(datetime.fromisoformat(clock), manual, self.calendar)

    def test_weekend_and_monday_use_completed_friday(self):
        for clock in ('2026-11-21T07:00:00+09:00','2026-11-23T08:45:00+09:00'):
            x=self.plan(clock)
            self.assertEqual(x['asof'],'20261120')
            self.assertEqual(x['entry_valid_until'],'2026-11-23T15:30:00+09:00')

    def test_actual_exchange_holiday_is_skipped(self):
        self.assertEqual(self.plan('2026-10-12T07:00:00+09:00')['asof'],'20261008')

    def test_year_end_closure_and_new_year_are_skipped(self):
        self.assertEqual(self.plan('2027-01-02T07:00:00+09:00')['asof'],'20261230')

    def test_existing_collection_cutoff_is_preserved(self):
        self.assertEqual(self.plan('2026-11-20T20:59:00+09:00')['asof'],'20261119')
        self.assertEqual(self.plan('2026-11-20T21:00:00+09:00')['asof'],'20261120')

    def test_future_or_incomplete_manual_date_is_blocked(self):
        with self.assertRaisesRegex(ValueError,'MANUAL_ASOF_NOT_COMPLETED'):
            self.plan('2026-11-20T08:00:00+09:00','20261120')

    def test_manual_holiday_is_not_silently_replaced(self):
        with self.assertRaisesRegex(ValueError,'MANUAL_ASOF_NOT_KRX_SESSION'):
            self.plan('2026-10-12T07:00:00+09:00','20261009')

    def test_reference_calendar_is_not_official_certification(self):
        x=self.plan('2026-11-21T07:00:00+09:00')
        self.assertFalse(x['calendar_is_official_attestation'])
        self.assertEqual(x['calendar_version'],'4.13.2')

if __name__=='__main__':unittest.main()
