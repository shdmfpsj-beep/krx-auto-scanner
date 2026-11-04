import unittest
from c3_top2_cross_ticker_gap_v1 import inspect
P=[{"ticker":"271560"},{"ticker":"026960"}]
class CrossTickerGapTests(unittest.TestCase):
    def test_asymmetric_gap(self):
        r=inspect(P,{("271560","2026-11-02"):1,("271560","2026-11-03"):1,
                     ("026960","2026-11-02"):1})
        self.assertEqual(r["asymmetric_missing_dates"]["026960"],["2026-11-03"])
        self.assertFalse(r["cross_ticker_dates_aligned"])
    def test_aligned_does_not_certify(self):
        r=inspect(P,{("271560","2026-11-02"):1,("026960","2026-11-02"):1})
        self.assertTrue(r["cross_ticker_dates_aligned"])
        self.assertFalse(r["official_exchange_calendar_verified"])
        self.assertFalse(r["common_missing_sessions_detectable"])
        self.assertFalse(r["trade_approved"])
    def test_both_empty_not_certified(self):
        r=inspect(P,{})
        self.assertEqual(r["observed_date_union"],0)
        self.assertFalse(r["official_exchange_calendar_verified"])
    def test_duplicate_ticker_fails(self):
        with self.assertRaises(ValueError):
            inspect([P[0],P[0]],{})
if __name__=="__main__":
    unittest.main()
