import unittest
from c3_intraday_ledger_v1 import merge
def watch(status="WATCH_ZONE"):
 return {"status":"READ_ONLY_MONITOR","trade_approved":False,"alerts":[{"ticker":"271560","name":"오리온","observed_at":"2026-11-02T10:00:00+09:00","observed_price":112000,"status":status,"paper_filled":False}]}
class TestLedger(unittest.TestCase):
 def test_record_once(self):
  a,new=merge([],watch());self.assertEqual(len(new),1)
  b,new2=merge(a,watch());self.assertEqual(len(b),1);self.assertEqual(new2,[])
 def test_unverified_no_record(self):
  self.assertEqual(merge([],watch("NO_VERIFIED_QUOTE"))[0],[])
 def test_no_trade_approval(self):
  w=watch();w["trade_approved"]=True;self.assertEqual(merge([],w)[0],[])
 def test_no_paper_fill(self):
  w=watch();w["alerts"][0]["paper_filled"]=True;self.assertEqual(merge([],w)[0],[])
if __name__=="__main__":unittest.main()
