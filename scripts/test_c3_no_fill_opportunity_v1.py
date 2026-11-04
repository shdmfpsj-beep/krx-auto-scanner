import unittest
from c3_no_fill_opportunity_v1 import evaluate,build

PLAN=dict(plan_id="a",ticker="271560",name="오리온",selection_date="2026-10-30",
          registered_day="2026-10-31",source_close="114200",watch_low="110900",
          watch_high="113700",structure_stop="109600",target1="131500",
          target2="141700",expires_after_sessions="5")

def bar(low,high):
    return dict(low=low,high=high,open=(low+high)/2,close=(low+high)/2,volume=1)

class OpportunityTests(unittest.TestCase):
    def test_gap_above_band_is_not_touch(self):
        x=evaluate(PLAN,{("271560","2026-11-02"):bar(115000,118000)})
        self.assertIsNone(x["first_band_touch_day"])
        self.assertEqual(x["no_touch_higher_high_sessions"],1)
    def test_touch_not_fill(self):
        x=evaluate(PLAN,{("271560","2026-11-02"):bar(111000,117000)})
        self.assertEqual(x["first_band_touch_day"],"2026-11-02")
        self.assertFalse(x["confirmed_fill"])
        self.assertFalse(x["band_touch_is_fill"])
    def test_registration_day_not_backfilled(self):
        x=evaluate(PLAN,{("271560","2026-10-31"):bar(111000,117000)})
        self.assertEqual(x["window_sessions"],0)
    def test_missing_sessions_not_complete(self):
        x=evaluate(PLAN,{("271560","2026-11-02"):bar(115000,118000)})
        self.assertFalse(x["observation_complete"])
    def test_horizon_limits_observation(self):
        bars={("271560",f"2026-11-{i:02d}"):bar(115000,118000)
              for i in range(2,10)}
        x=evaluate(PLAN,bars)
        self.assertEqual(x["window_sessions"],5)
    def test_no_automatic_trade_approval(self):
        x=build([PLAN,dict(PLAN,plan_id="b",ticker="026960")],{})
        self.assertFalse(x["trade_approved"])
        self.assertFalse(x["orders_enabled"])
    def test_invalid_horizon_rejected(self):
        with self.assertRaisesRegex(ValueError,"INVALID_HORIZON"):
            evaluate(dict(PLAN,expires_after_sessions="-1"),{})

if __name__=="__main__":
    unittest.main()
