import unittest
from c3_entry_geometry_research_v1 import review, build

PLAN = dict(plan_id="C3-20261030-271560", ticker="271560", name="오리온",
            selection_date="2026-10-30", registered_day="2026-10-31",
            source_close="114200", structure_stop="109600", watch_low="110900",
            watch_high="113700", target1="131500", target2="141700")

class GeometryTests(unittest.TestCase):
    def test_stop_first_both_entry_ends(self):
        r=review(PLAN)
        self.assertEqual(r["lower_entry"]["risk_pct"], 1.17)
        self.assertEqual(r["upper_entry"]["risk_pct"], 3.61)
        self.assertGreater(r["lower_entry"]["reward_to_first_target"],
                           r["upper_entry"]["reward_to_first_target"])
    def test_no_auto_buy_approval(self):
        r=build([PLAN, dict(PLAN, plan_id="C3-20261030-026960",ticker="026960")])
        self.assertFalse(r["trade_approved"])
        self.assertFalse(r["plans"][0]["entry_trigger_verified"])
    def test_stop_above_watch_rejected(self):
        with self.assertRaisesRegex(ValueError,"INVALID_PRICE_GEOMETRY"):
            review(dict(PLAN, structure_stop="111000"))
    def test_target_below_entry_rejected(self):
        with self.assertRaisesRegex(ValueError,"INVALID_PRICE_GEOMETRY"):
            review(dict(PLAN, target1="113000"))
    def test_nan_rejected(self):
        with self.assertRaisesRegex(ValueError,"INVALID_WATCH_LOW"):
            review(dict(PLAN, watch_low="nan"))
    def test_duplicate_plan_rejected(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_PLAN_ID"):
            build([PLAN, PLAN])
    def test_not_exactly_top2_rejected(self):
        with self.assertRaisesRegex(ValueError,"EXPECTED_EXACTLY_TWO"):
            build([PLAN])

if __name__=="__main__":
    unittest.main()
