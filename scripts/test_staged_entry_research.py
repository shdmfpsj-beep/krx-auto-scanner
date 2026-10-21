import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
from staged_entry_research import simulate,SPLITS

def sample():
    b=[{"open":105.,"high":108.,"low":102.,"close":105.} for _ in range(75)]
    b[66]={"open":105.,"high":107.,"low":104.,"close":105.}
    b[67]={"open":103.,"high":106.,"low":102.,"close":104.}
    return b

class StagedTests(unittest.TestCase):
    def run_sim(self,b,split=(.6,.4),limit=103.):
        with patch("staged_entry_research.setup",return_value="BREAKOUT_20D"),patch(
            "staged_entry_research.pivot_stop",return_value=100.):
            return simulate(b,65,split=split,second_limit=limit)
    def test_second_fills_at_open(self):
        r=self.run_sim(sample())
        self.assertTrue(r["second_filled"])
        self.assertLess(r["average_entry"],105)
    def test_no_second_if_no_pullback(self):
        b=sample();b[67]["open"]=105;b[67]["low"]=104
        r=self.run_sim(b)
        self.assertFalse(r["second_filled"])
    def test_stop_before_second_if_gap(self):
        b=sample();b[67]={"open":95.,"high":98.,"low":90.,"close":96.}
        r=self.run_sim(b)
        self.assertEqual(r["status"],"STOP_GAP_OPEN")
        self.assertFalse(r["second_filled"])
    def test_intraday_second_and_stop_is_ambiguous(self):
        b=sample();b[67]={"open":105.,"high":106.,"low":99.,"close":101.}
        self.assertEqual(self.run_sim(b)["status"],"AMBIGUOUS_SECOND_AND_STOP")
    def test_four_splits(self):
        for split in SPLITS.values():
            r=self.run_sim(sample(),split=split,limit=103. if split[1] else None)
            self.assertIn("net_account_pct",r)
    def test_invalid_second_support(self):
        self.assertEqual(self.run_sim(sample(),limit=99)["status"],"NO_VALID_SECOND_SUPPORT")
if __name__=="__main__":unittest.main()
