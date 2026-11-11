import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_entry_expiry_diagnostics import touch
class ExpiryTests(unittest.TestCase):
 def bars(self):
  return [{"open":100,"high":105,"low":100,"close":102},
          {"open":110,"high":115,"low":106,"close":112},
          {"open":108,"high":111,"low":99,"close":105},
          {"open":110,"high":113,"low":101,"close":111}]
 def test_first_touch_on_day_two(self):
  b=self.bars()
  self.assertEqual(touch(b,0,103,95,1)[0],"UNFILLED")
  self.assertEqual(touch(b,0,103,95,2),("FILLED_RESEARCH",2))
 def test_gap_below_stop_is_not_entry(self):
  b=self.bars();b[1]["open"]=90;b[1]["low"]=85
  self.assertEqual(touch(b,0,103,95,3)[0],"GAP_BELOW_STOP_NO_ENTRY")
 def test_stop_and_limit_same_day_is_ambiguous(self):
  b=self.bars();b[1]["low"]=94
  self.assertEqual(touch(b,0,103,95,1)[0],"STOP_TOUCHED_SEQUENCE_UNCERTAIN")
 def test_missing_future_is_censored(self):
  self.assertEqual(touch(self.bars()[:2],0,103,95,3)[0],"CENSORED")
if __name__=="__main__":unittest.main()
