import csv
import tempfile
import unittest
from pathlib import Path
from c3_yahoo_adjustment_diagnostic_v1 import compare,markdown_table,ratio_pattern

class AdjustmentDiagnosticTests(unittest.TestCase):
    def test_ratio_pattern_constant_and_variable(self):
        rows=lambda gaps: {"rows":[{"ticker":"271560","status":"OBSERVED_NOT_CERTIFIED","raw_gap_pct":v} for v in gaps]}
        constant=ratio_pattern(rows([1.0,1.01,1.02]))["271560"]
        self.assertEqual(constant["pattern"],"NEAR_CONSTANT_GAP_HEURISTIC")
        self.assertFalse(constant["cause_verified"])
        variable=ratio_pattern(rows([1.0,1.2,1.4]))["271560"]
        self.assertEqual(variable["pattern"],"VARIABLE_GAP")
        sparse=ratio_pattern(rows([0,1.0]))["271560"]
        self.assertEqual(sparse["pattern"],"INSUFFICIENT_NONZERO_OBSERVATIONS")

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
            table=markdown_table(result)
            self.assertIn("271560",table)
            self.assertIn("+1.0000%",table)
            self.assertIn("CASH",table)
            self.assertIn(chr(10)+"|",table)
            self.assertNotIn("\\\\n",table)
            self.assertEqual(result["gap_summary"]["271560"]["positive_gap_days"],1)
            self.assertEqual(result["gap_summary"]["271560"]["mean_abs_gap_pct"],1.0)

if __name__=="__main__":unittest.main()
