import unittest
from c3_session_coverage_gate_v1 import validate

P=[dict(ticker="271560",registered_day="2026-10-31"),
   dict(ticker="026960",registered_day="2026-10-31")]
D=["2026-11-02","2026-11-03","2026-11-04","2026-11-05","2026-11-06"]
def prices(days=D):
    return {(p["ticker"],d):dict(open=1,high=1,low=1,close=1,volume=1)
            for p in P for d in days}

class SessionCoverageTests(unittest.TestCase):
    def test_five_sessions_complete(self):
        x=validate(P,prices(),D)
        self.assertTrue(x["coverage"]["271560"]["five_complete"])
        self.assertFalse(x["coverage"]["271560"]["ten_complete"])
        self.assertFalse(x["data_certified"])
    def test_missing_middle_session(self):
        x=validate(P,prices(D[:2]+D[3:]),D)
        self.assertIn("2026-11-04",x["coverage"]["271560"]["missing_session_dates"])
        self.assertFalse(x["coverage"]["271560"]["five_complete"])
    def test_no_calendar_rejected(self):
        self.assertIn("SESSION_CALENDAR_REQUIRED",validate(P,{},[])["errors"])
    def test_duplicate_calendar_rejected(self):
        self.assertIn("DUPLICATE_CALENDAR_DAY",validate(P,prices(),D+[D[-1]])["errors"])
    def test_unsorted_calendar_rejected(self):
        self.assertIn("CALENDAR_NOT_SORTED",validate(P,prices(),D[::-1])["errors"])
    def test_unexpected_ticker(self):
        x=validate(P,{**prices(),("123456","2026-11-02"):dict()},D)
        self.assertIn("UNEXPECTED_TICKERS",x["errors"])
    def test_outside_calendar(self):
        x=validate(P,{**prices(),("271560","2026-11-07"):dict()},D)
        self.assertIn("PRICE_DAY_NOT_IN_SESSION_CALENDAR",x["errors"])
    def test_duplicate_plan(self):
        self.assertIn("EXPECTED_TWO_UNIQUE_TICKERS",validate([P[0],P[0]],{},D)["errors"])

if __name__=="__main__":
    unittest.main()
