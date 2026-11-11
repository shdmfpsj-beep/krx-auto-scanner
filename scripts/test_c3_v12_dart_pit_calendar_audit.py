import unittest,sys,datetime as dt
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_v12_dart_pit_calendar_audit import inspect
def e(code,sel,fil,avail):
 return {"ticker":code,"date":sel,"financial":{"receipt_no":fil.replace("-","")+"001111","filing_date":fil,"available_date":avail}}
class PITCalendarAuditTests(unittest.TestCase):
 def setUp(self):self.dates=[dt.date(2026,8,13),dt.date(2026,8,14),dt.date(2026,8,17),dt.date(2026,8,18)]
 def test_aug15_weekend_must_not_be_trading_date(self):
    x=inspect([e("001000","2026-08-18","2026-08-14","2026-08-15")],self.dates)
    z=x["events"][0]
    self.assertTrue(z["old_available_was_weekend"])
    self.assertEqual(z["first_observed_KRX_market_session_after_filing"],"2026-08-17")
    self.assertFalse(z["financial_original_numeric_vintage_verified"])
 def test_true_next_session(self):
    x=inspect([e("001000","2026-08-18","2026-08-13","2026-08-14")],self.dates)
    self.assertEqual(x["counts"]["MATCHES_FIRST_FROZEN_KRX_SESSION"],1)
 def test_before_archive_cannot_infer_holiday(self):
    x=inspect([e("001000","2026-08-18","2025-11-14","2025-11-15")],self.dates)
    self.assertIsNone(x["events"][0]["first_observed_KRX_market_session_after_filing"])
    self.assertEqual(x["counts"]["OUTSIDE_ARCHIVED_KRX_CALENDAR_CANNOT_CERTIFY"],1)
 def test_date_after_selection_does_not_authorize(self):
    x=inspect([e("001000","2026-08-13","2026-08-14","2026-08-15")],self.dates)
    self.assertEqual(x["counts"]["PROPOSED_NEXT_SESSION_AFTER_SELECTION"],1)
 def test_filing_after_last_history_not_guessed(self):
    x=inspect([e("001000","2026-08-18","2026-08-18","2026-08-19")],self.dates)
    self.assertEqual(x["events"][0]["classification"],"OUTSIDE_ARCHIVED_KRX_CALENDAR_CANNOT_CERTIFY")
 def test_no_financial_receipts_not_injected(self):
    x=inspect([{"ticker":"001000","date":"2026-08-17","financial":{}}],self.dates)
    self.assertEqual(x["linked_provisional_receipt_events"],0)
if __name__=="__main__":unittest.main()
