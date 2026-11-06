import unittest
import csv
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import c3_top2_cross_ticker_gap_v1 as module
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
    def test_fail_on_gap_cli_exits_nonzero_and_preserves_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            plans=Path(temp)/"plans.csv"
            prices=Path(temp)/"prices.csv"
            output=Path(temp)/"gaps.json"
            with plans.open("w",newline="") as handle:
                writer=csv.DictWriter(handle,fieldnames=["ticker"])
                writer.writeheader()
                writer.writerows(P)
            with prices.open("w",newline="") as handle:
                writer=csv.DictWriter(handle,fieldnames=["ticker","date","open","high","low","close","volume"])
                writer.writeheader()
                for code,day in [("271560","2026-11-02"),("271560","2026-11-03"),("026960","2026-11-02")]:
                    writer.writerow(dict(ticker=code,date=day,open=100,high=101,low=99,close=100,volume=10))
            with patch("sys.argv",["gap","--plans",str(plans),"--prices",str(prices),"--output",str(output),"--fail-on-gap"]):
                with self.assertRaises(SystemExit) as caught:
                    module.main()
            self.assertEqual(caught.exception.code,2)
            self.assertEqual(json.loads(output.read_text())["asymmetric_gap_count"],1)

    def test_duplicate_ticker_fails(self):
        with self.assertRaises(ValueError):
            inspect([P[0],P[0]],{})
if __name__=="__main__":
    unittest.main()
