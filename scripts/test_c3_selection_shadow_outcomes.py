import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_selection_shadow_outcomes import summarize
class ShadowTests(unittest.TestCase):
 def test_empty_fail_closed(self):
  x=summarize([])
  self.assertEqual(x["decision"],"CASH")
  self.assertIsNone(x["horizon_metrics"]["20"]["positive_rate"])
  self.assertEqual(x["financial_filter_before_after_comparison"],"BLOCKED_NO_VERIFIED_HISTORICAL_PIT")
 def test_duplicate_rejected(self):
  row={"ticker":"000001","date":"2026-01-01","open":10,"high":11,"low":9,"close":10,"volume":1}
  with self.assertRaises(ValueError):summarize([row,row])
 def test_short_history_never_invents_outcome(self):
  rows=[{"ticker":"000001","date":f"2026-{1+i//28:02d}-{1+i%28:02d}",
   "open":100+i,"high":102+i,"low":99+i,"close":101+i,"volume":1000} for i in range(10)]
  x=summarize(rows);self.assertEqual(x["shadow_selection_events"],0)
if __name__=="__main__":unittest.main()
