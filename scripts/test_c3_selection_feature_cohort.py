import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_selection_feature_cohort import cohort
class CohortTests(unittest.TestCase):
 def test_empty_fail_closed(self):
  r=cohort([]);self.assertEqual(r["decision"],"CASH")
  self.assertEqual(r["horizon_groups"]["20"]["observed"],0)
 def test_duplicate_rejected(self):
  x={"ticker":"000001","date":"2026-01-01","open":10,"high":11,"low":9,"close":10,"volume":1}
  with self.assertRaises(ValueError):cohort([x,x])
 def test_no_future_outcomes_on_short_history(self):
  rows=[{"ticker":"000001","date":f"2026-{1+i//28:02d}-{1+i%28:02d}",
   "open":100+i,"high":102+i,"low":99+i,"close":101+i,"volume":1000} for i in range(10)]
  r=cohort(rows);self.assertEqual(r["deduplicated_events"],0)
if __name__=="__main__":unittest.main()
