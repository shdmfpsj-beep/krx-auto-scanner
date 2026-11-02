import unittest
from datetime import date
from c3_forward_calendar_v19 import evaluate

class CalendarAuditTest(unittest.TestCase):
    def setUp(self):
        self.plan=[{"ticker":"000001","key":"sample","price_date":"2026-11-02",
                    "registered_utc":"2026-11-02T14:00:00+00:00"}]
        self.days=["2026-11-02","2026-11-03","2026-11-04"]
    def test_no_skipped_open(self):
        result=evaluate(self.plan,self.days,[{"ticker":"000001","date":"2026-11-04","open":"120"}],date(2026,11,4))
        self.assertEqual(result["observations"][0]["status"],"NEXT_PRICE_MISSING_OR_DUPLICATE")
        self.assertIsNone(result["observations"][0]["next_open"])
    def test_future_calendar_not_used(self):
        result=evaluate(self.plan,self.days,[],date(2026,11,2))
        self.assertEqual(result["observations"][0]["status"],"NEXT_SESSION_PENDING")
    def test_observed_not_fill(self):
        result=evaluate(self.plan,self.days,[{"ticker":"000001","date":"2026-11-03","open":"105"}],date(2026,11,3))
        self.assertEqual(result["observations"][0]["next_open"],105)
        self.assertIsNone(result["observations"][0]["filled"])
        self.assertIsNone(result["range_opportunity_rate"])
if __name__=="__main__":unittest.main()
