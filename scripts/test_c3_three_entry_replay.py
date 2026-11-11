import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_three_entry_replay import signals,evaluate,replay
class ReplayTests(unittest.TestCase):
 def bars(self,n=100):
  return [{"ticker":"000001","date":f"2026-{1+i//28:02d}-{1+i%28:02d}",
           "open":100+i*.2,"high":102+i*.2,"low":99+i*.2,
           "close":100+i*.2,"volume":1000} for i in range(n)]
 def test_no_future_signal_leak(self):
  b=self.bars()
  self.assertEqual(signals(b,80),signals(b[:81],80))
 def test_stop_wins_ambiguous_bar(self):
  b=self.bars();b[81]["low"]=90;b[81]["high"]=130
  x=evaluate(b,80,"X",115,100,125)
  self.assertTrue(x["filled"])
  self.assertEqual(x["outcomes"]["5"]["status"],"STOP")
 def test_unfilled(self):
  b=self.bars()
  x=evaluate(b,80,"X",80,70,100)
  self.assertFalse(x["filled"])
  self.assertEqual(x["outcomes"]["5"]["status"],"UNFILLED")
 def test_censor(self):
  b=self.bars(85)
  x=evaluate(b,80,"X",115,100,125)
  self.assertEqual(x["outcomes"]["20"]["status"],"CENSORED")
 def test_duplicate_day_rejected(self):
  b=self.bars();b[1]["date"]=b[0]["date"]
  with self.assertRaises(ValueError):replay(b)
if __name__=="__main__":unittest.main()
