import unittest
from c3_top2_watch_risk_reward_v1 import evaluate,build

PLAN=dict(plan_id="p",ticker="271560",structure_stop="95",
          watch_low="100",watch_high="105",target1="120",target2="135")
class GeometryTests(unittest.TestCase):
    def test_conservative_uses_watch_high(self):
        r=evaluate(PLAN)
        self.assertEqual(r["conservative_at_watch_high"]["reward_to_risk"],1.5)
        self.assertEqual(r["favorable_at_watch_low"]["reward_to_risk"],4.0)
        self.assertFalse(r["trade_approved"])
    def test_invalid_geometry_rejected(self):
        with self.assertRaisesRegex(ValueError,"INVALID_STOP_WATCH_TARGET_ORDER"):
            evaluate(dict(PLAN,structure_stop="106"))
    def test_nan_rejected(self):
        with self.assertRaisesRegex(ValueError,"INVALID_NONFINITE"):
            evaluate(dict(PLAN,watch_high="nan"))
    def test_duplicate_ticker_rejected(self):
        with self.assertRaisesRegex(ValueError,"EXPECTED_UNIQUE_TOP2"):
            build([PLAN,PLAN])
if __name__=="__main__":unittest.main()
