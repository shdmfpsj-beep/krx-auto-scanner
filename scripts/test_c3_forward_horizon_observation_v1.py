import unittest
from c3_forward_horizon_observation_v1 import evaluate,build

PLAN=dict(plan_id="a",ticker="271560",name="오리온",
          selection_date="2026-10-30",registered_day="2026-10-31",
          source_close="114200",watch_low="110900",watch_high="113700",
          structure_stop="109600",target1="131500",target2="141700")
def bar(lo=110000,hi=120000,close=116000):
    return dict(low=lo,high=hi,open=close,close=close,volume=100)

class ForwardTests(unittest.TestCase):
    def test_incomplete_horizon_no_return(self):
        x=evaluate(PLAN,{("271560","2026-11-02"):bar()})
        self.assertFalse(x["horizons"][0]["complete"])
        self.assertIsNone(x["horizons"][0]["source_close_to_horizon_close_pct"])
    def test_five_complete_twenty_incomplete(self):
        bars={("271560",f"2026-11-{i:02d}"):bar() for i in range(2,7)}
        x=evaluate(PLAN,bars)
        self.assertTrue(x["horizons"][0]["complete"])
        self.assertFalse(x["horizons"][1]["complete"])
        self.assertEqual(x["horizons"][0]["source_close_to_horizon_close_pct"],1.58)
    def test_same_day_stop_target_ambiguous(self):
        bars={("271560","2026-11-02"):bar(109000,132000)}
        x=evaluate(PLAN,bars)
        self.assertEqual(x["horizons"][0]["same_day_stop_target_ambiguous"],["2026-11-02"])
    def test_registration_day_excluded(self):
        x=evaluate(PLAN,{("271560","2026-10-31"):bar()})
        self.assertEqual(x["horizons"][0]["observed_sessions"],0)
    def test_no_strategy_pnl_or_fill_claim(self):
        bars={("271560",f"2026-11-{i:02d}"):bar() for i in range(2,7)}
        x=evaluate(PLAN,bars)
        self.assertIsNone(x["horizons"][0]["strategy_return_pct"])
        self.assertFalse(x["horizons"][0]["verified_entry"])
    def test_two_unique_plans_required(self):
        with self.assertRaisesRegex(ValueError,"EXPECTED_TWO_UNIQUE"):
            build([PLAN,PLAN],{})
    def test_no_trade_approval(self):
        x=build([PLAN,dict(PLAN,plan_id="b",ticker="026960")],{})
        self.assertFalse(x["trade_approved"])
        self.assertFalse(x["orders_enabled"])

if __name__=="__main__":
    unittest.main()
