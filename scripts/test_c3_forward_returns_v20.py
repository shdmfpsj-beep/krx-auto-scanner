import unittest
from c3_forward_returns_v20 import audit

class ForwardReturnsIntegrity(unittest.TestCase):
    def setUp(self):
        self.registry=[{"ticker":"000001","key":"a","price_date":"2026-11-02",
                        "registered_utc":"2026-11-02T14:00:00+00:00"}]
        self.calendar=["2026-11-02","2026-11-03","2026-11-04",
                       "2026-11-05","2026-11-06","2026-11-09"]
    def test_duplicate_base_rejected(self):
        prices=[{"ticker":"000001","date":"2026-11-02","close":"100"}]*2
        result=audit(self.registry,self.calendar,prices,"2026-11-09")
        self.assertEqual(result["items"][0]["status"],"BASE_OR_REGISTRATION_INVALID")
    def test_missing_future_stays_pending(self):
        prices=[{"ticker":"000001","date":"2026-11-02","close":"100"}]
        result=audit(self.registry,self.calendar,prices,"2026-11-02")
        self.assertEqual(result["items"][0]["horizons"]["5"]["status"],"PENDING")
        self.assertIsNone(result["trade_pnl"])
if __name__=="__main__":unittest.main()
