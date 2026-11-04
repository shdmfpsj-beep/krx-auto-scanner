import unittest
from c3_watch_touch_forward_outcomes_v1 import analyze

PLAN=dict(ticker="271560",plan_id="test",registered_day="2026-11-01",
          watch_low="100",watch_high="105",structure_stop="95",
          target1="120",expires_after_sessions="2")
def bar(o,h,l,c):
    return dict(open=o,high=h,low=l,close=c,volume=100)
class WatchTouchForwardTests(unittest.TestCase):
    def test_touch_is_not_fill_and_future_incomplete(self):
        prices={("271560","2026-11-02"):bar(106,108,102,104),
                ("271560","2026-11-03"):bar(107,109,106,108)}
        r=analyze(PLAN,prices)
        self.assertEqual(r["watch_events"],1)
        self.assertEqual(r["events"][0]["status"],"WATCH_TOUCH_ONLY")
        self.assertFalse(r["events"][0]["outcomes"][0]["complete"])
        self.assertIsNone(r["events"][0]["outcomes"][0]["strategy_return_pct"])
        self.assertEqual(r["verified_fills"],0)
        self.assertEqual(r["events"][0]["outcomes"][0]["observed_future_sessions"],1)
        self.assertEqual(r["events"][0]["outcomes"][0]["observed_max_favorable_excursion_pct"],4.808)
        self.assertEqual(r["events"][0]["outcomes"][0]["observed_max_adverse_excursion_pct"],1.923)
        self.assertTrue(r["events"][0]["outcomes"][0]["reference_is_touch_day_close"])
    def test_stop_before_target_and_same_day_ambiguity(self):
        prices={("271560","2026-11-02"):bar(103,108,101,104),
                ("271560","2026-11-03"):bar(100,104,94,98),
                ("271560","2026-11-04"):bar(108,121,105,119)}
        r=analyze(PLAN,prices)
        h=r["events"][0]["outcomes"][0]
        self.assertEqual(h["stop_target_touch_order"],"STOP_FIRST")
        self.assertEqual(h["first_future_stop_touch_date"],"2026-11-03")
        self.assertEqual(h["first_future_target_touch_date"],"2026-11-04")
        prices[("271560","2026-11-03")]=bar(105,121,94,106)
        prices.pop(("271560","2026-11-04"))
        r=analyze(PLAN,prices)
        self.assertEqual(r["events"][0]["outcomes"][0]["stop_target_touch_order"],
                         "SAME_DAY_ORDER_UNKNOWN")
    def test_zero_future_days_has_no_excursion(self):
        prices={("271560","2026-11-02"):bar(106,108,102,104)}
        r=analyze(PLAN,prices)
        h=r["events"][0]["outcomes"][0]
        self.assertIsNone(h["observed_max_favorable_excursion_pct"])
        self.assertIsNone(h["observed_max_adverse_excursion_pct"])
        self.assertFalse(h["complete"])
    def test_stop_collision_separate(self):
        prices={("271560","2026-11-02"):bar(103,108,94,99)}
        r=analyze(PLAN,prices)
        self.assertEqual(r["events"][0]["status"],"SAME_BAR_STOP_AMBIGUOUS")
    def test_gap_below_stop(self):
        prices={("271560","2026-11-02"):bar(90,102,89,101)}
        r=analyze(PLAN,prices)
        self.assertEqual(r["events"][0]["status"],"GAP_BELOW_STOP")
if __name__=="__main__":unittest.main()
