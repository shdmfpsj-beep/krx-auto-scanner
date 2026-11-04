import unittest
from c3_xkrx_calendar_crosscheck_v1 import compare

PLANS=[{"ticker":"271560"},{"ticker":"026960"}]
ROWS=[{"ticker":ticker,"date":day} for ticker in ("271560","026960") for day in ("2026-11-02","2026-11-03")]

class ThirdPartyCalendarTests(unittest.TestCase):
    def test_complete_dates_still_uncertified(self):
        r=compare(PLANS,ROWS,"2026-11-02","2026-11-03",["2026-11-02","2026-11-03"])
        self.assertFalse(r["discrepancies_found"])
        self.assertFalse(r["official_krx_calendar_verified"])
        self.assertFalse(r["trade_approved"])
    def test_common_missing_date_is_detected(self):
        r=compare(PLANS,[row for row in ROWS if row["date"]!="2026-11-03"],"2026-11-02","2026-11-03",["2026-11-02","2026-11-03"])
        self.assertTrue(r["discrepancies_found"])
        self.assertEqual(r["results"]["271560"]["missing_expected_dates"],["2026-11-03"])
        self.assertEqual(r["results"]["026960"]["missing_expected_dates"],["2026-11-03"])
    def test_unexpected_ticker_rejected(self):
        with self.assertRaisesRegex(ValueError,"UNEXPECTED_PRICE_TICKER"):
            compare(PLANS,ROWS+[{"ticker":"005930","date":"2026-11-02"}],"2026-11-02","2026-11-03",["2026-11-02","2026-11-03"])
    def test_duplicate_price_day_rejected(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_PRICE_TICKER_DATE"):
            compare(PLANS,ROWS+[ROWS[0]],"2026-11-02","2026-11-03",["2026-11-02","2026-11-03"])
    def test_empty_calendar_rejected(self):
        with self.assertRaisesRegex(ValueError,"EMPTY_THIRD_PARTY_SESSION_CALENDAR"):
            compare(PLANS,ROWS,"2026-11-02","2026-11-03",[])
    def test_duplicate_calendar_rejected(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_THIRD_PARTY_SESSION_DATE"):
            compare(PLANS,ROWS,"2026-11-02","2026-11-03",["2026-11-02","2026-11-02"])
    def test_duplicate_plan_rejected(self):
        with self.assertRaisesRegex(ValueError,"EXPECTED_TWO_UNIQUE_PLANS"):
            compare([PLANS[0],PLANS[0]],ROWS,"2026-11-02","2026-11-03",["2026-11-02"])

if __name__=="__main__":
    unittest.main()
