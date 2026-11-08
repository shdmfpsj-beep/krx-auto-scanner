import unittest
from c3_intraday_outcomes_v1 import outcomes
def r(t,p,status):
 return {"ticker":"271560","observed_at":f"2026-11-02T{t}:00+09:00","observed_price":str(p),"status":status}
class Tests(unittest.TestCase):
 def test_later_prices_only(self):
  x=outcomes([r("10:00",112000,"WATCH_ZONE"),r("10:10",111000,"WATCH_ZONE"),r("10:20",114000,"ABOVE_ZONE")],(30,))
  self.assertEqual(x[0]["later_observations"],2)
  self.assertEqual(x[0]["min_observed_price"],111000)
  self.assertEqual(x[0]["max_observed_price"],114000)
  self.assertFalse(x[0]["is_trade_fill"])
 def test_missing_followup_not_zero_return(self):
  x=outcomes([r("10:00",112000,"WATCH_ZONE")],(30,))
  self.assertEqual(x[0]["status"],"NO_FOLLOWUP_OBSERVATION")
  self.assertNotIn("min_observed_change_pct",x[0])
 def test_only_watch_starts_episode(self):
  self.assertEqual(outcomes([r("10:00",114000,"ABOVE_ZONE")]),[])
if __name__=="__main__":unittest.main()
