import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from structural_support_comparison import levels,summarize,METHODS

class SupportTests(unittest.TestCase):
    def sample(self):
        b=[{"open":100.,"high":101.,"low":99.,"close":100.} for _ in range(80)]
        b[65]={"open":105.,"high":107.,"low":104.,"close":106.}
        return b
    def test_no_future_data_leakage(self):
        b=self.sample()
        a=levels(b,65,95,110)
        b[66]["low"]=20
        b[66]["high"]=300
        self.assertEqual(a,levels(b,65,95,110))
    def test_rejects_invalid_support_bounds(self):
        self.assertEqual(levels(self.sample(),65,110,100),{})
    def test_breakout_retest_is_prior_high(self):
        b=self.sample()
        self.assertEqual(levels(b,65,95,110)["BREAKOUT_RETEST"],101.)
    def test_breakout_requires_fresh_cross(self):
        b=self.sample()
        b[64]["close"]=103.
        self.assertNotIn("BREAKOUT_RETEST",levels(b,65,95,110))
    def test_broken_swing_low_is_not_support(self):
        b=self.sample()
        b[58]["low"]=97.
        b[59]["low"]=99.
        b[60]["low"]=99.
        b[62]["close"]=96.
        self.assertNotIn("PIVOT_RETEST",levels(b,65,95,110))
    def test_empty_summary_never_claims_profit(self):
        x=summarize([],{})
        self.assertEqual(x["trade_approval"],"NO")
        for method in METHODS:
            self.assertIsNone(x["methods"][method]["mean_delta_pctpt"])
if __name__=="__main__":unittest.main()
