import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_v11_entry_geometry_diagnostic import explain_model,range_status

class EntryGeometryTests(unittest.TestCase):
    def test_price_range_not_actual_fill(self):
        b={"open":105,"low":99,"high":108}
        self.assertEqual(range_status([b],100,102,90,120),"RANGE_OVERLAP_NOT_EXECUTION")
    def test_gap_below_stop_blocked(self):
        self.assertEqual(range_status([{"open":89,"low":87,"high":105}],100,102,90,120),"GAP_BELOW_STOP_NOT_VALID_FILL")
    def test_stop_target_same_bar_unknown(self):
        self.assertEqual(range_status([{"open":105,"low":89,"high":121}],100,102,90,120),"TOUCH_STOP_TARGET_SEQUENCE_UNKNOWN")
    def test_partial_history_censored_not_unfilled(self):
        self.assertEqual(range_status([],100,102,90,120),"CENSORED")
        self.assertEqual(range_status([None],100,102,90,120),"BLOCKED_MISSING_TICKER_SESSION")
    def test_prior_pass_with_future_touch(self):
        b1={"open":110,"low":107,"high":111}
        b2={"open":105,"low":99,"high":106}
        self.assertEqual(range_status([b1],100,102,90,120),"PASS_UNTOUCHED")
        self.assertEqual(range_status([b1,b2],100,102,90,120),"RANGE_OVERLAP_NOT_EXECUTION")
    def test_breakout_not_confirmed_does_not_create_entry(self):
        # 61 rising bars with a prior spike above current price: breakout unconfirmed
        bars=[{"close":100+i*.6,"high":101+i*.6,
               "low":99+i*.6,"open":100+i*.6} for i in range(61)]
        bars[-2]["high"]=1000.
        x=explain_model(bars,60)
        self.assertIn(x["BREAKOUT_RETEST"]["reason"],("BREAKOUT_NOT_CONFIRMED","STOP_DISTANCE_GT_12PCT"))
if __name__=="__main__":unittest.main()
