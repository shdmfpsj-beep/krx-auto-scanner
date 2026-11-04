import csv
import tempfile
import unittest
from pathlib import Path
from c3_yahoo_adjustment_diagnostic_v1 import compare

class AdjustmentDiagnosticTests(unittest.TestCase):
    def test_raw_and_adjusted_separately(self):
        with tempfile.TemporaryDirectory() as d:
            primary=Path(d)/"primary.csv"
            yahoo=Path(d)/"yahoo.csv"
            with primary.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["ticker","date","close"]);w.writeheader()
                w.writerow({"ticker":"271560","date":"2026-11-03","close":"100"})
            with yahoo.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["ticker","date","close","adj_close"]);w.writeheader()
                w.writerow({"ticker":"271560","date":"2026-11-03","close":"101","adj_close":"100"})
            result=compare(primary,yahoo)
            row=result["rows"][0]
            self.assertFalse(row["raw_equal"])
            self.assertTrue(row["adj_equal"])
            self.assertEqual(row["raw_gap_pct"],1.0)
            self.assertFalse(result["trade_approved"])

if __name__=="__main__":unittest.main()
