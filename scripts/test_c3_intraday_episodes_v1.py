import unittest
from c3_intraday_episodes_v1 import episodes
def r(t,p=112000,status="WATCH_ZONE"):
 return {"ticker":"271560","observed_at":f"2026-11-02T{t}:00+09:00","observed_price":str(p),"status":status}
class Tests(unittest.TestCase):
 def test_same_episode(self):
  x=episodes([r("10:00"),r("10:10",112200)])
  self.assertEqual(len(x),1);self.assertEqual(x[0]["observations"],2)
  self.assertFalse(x[0]["is_fill"])
 def test_gap_split(self):
  self.assertEqual(len(episodes([r("10:00"),r("11:00")])),2)
 def test_no_false_entry(self):
  self.assertEqual(episodes([r("10:00",status="ABOVE_ZONE")]),[])
 def test_no_overnight_merge(self):
  self.assertEqual(len(episodes([r("10:00"),{"ticker":"271560","observed_at":"2026-11-03T10:00:00+09:00","observed_price":"112000","status":"WATCH_ZONE"}])),2)
if __name__=="__main__":unittest.main()
