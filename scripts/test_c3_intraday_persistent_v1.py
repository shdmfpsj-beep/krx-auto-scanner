import unittest
from c3_intraday_persistent_v1 import summarize
from c3_intraday_ledger_v1 import merge
class TestPersistent(unittest.TestCase):
 def test_repeated_runs_are_idempotent(self):
  w={"status":"READ_ONLY_MONITOR","trade_approved":False,"alerts":[{"ticker":"271560","name":"오리온","observed_at":"2026-11-02T10:00:00+09:00","observed_price":112000,"status":"WATCH_ZONE","paper_filled":False}]}
  first,_=merge([],w)
  second,new=merge(first,w)
  self.assertEqual(len(second),1);self.assertEqual(new,[])
  self.assertEqual(summarize(second)["271560"]["watch_zone"],1)
 def test_no_quotes_no_invention(self):
  rows,new=merge([],{"status":"READ_ONLY_MONITOR","trade_approved":False,"alerts":[]})
  self.assertEqual(rows,[]);self.assertEqual(new,[])
if __name__=="__main__":unittest.main()
