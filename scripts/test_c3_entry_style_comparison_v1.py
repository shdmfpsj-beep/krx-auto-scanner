import unittest
from c3_entry_style_comparison_v1 import evaluate,build

PLAN=dict(plan_id="a",ticker="271560",name="오리온",
          selection_date="2026-10-30",registered_day="2026-10-31",
          source_close="114200",watch_low="110900",watch_high="113700",
          structure_stop="109600",target1="131500",target2="141700",
          expires_after_sessions="5")

def bar(lo,hi,close):
    return dict(low=lo,high=hi,open=close,close=close,volume=100)

class EntryStyleTests(unittest.TestCase):
    def test_first_touch_is_pullback_not_retest(self):
        x=evaluate(PLAN,{("271560","2026-11-02"):bar(111000,116000,115000)})
        self.assertEqual(x["pullback"]["opportunity_days"],1)
        self.assertEqual(x["breakout_retest"]["opportunity_days"],0)
    def test_prior_close_then_touch_is_retest(self):
        p={("271560","2026-11-02"):bar(115000,118000,117000),
           ("271560","2026-11-03"):bar(111000,117000,113000)}
        x=evaluate(PLAN,p)
        self.assertEqual(x["breakout_retest"]["first_opportunity"],"2026-11-03")
    def test_intraday_high_without_close_not_confirmed(self):
        p={("271560","2026-11-02"):bar(115000,118000,113000),
           ("271560","2026-11-03"):bar(111000,117000,113000)}
        x=evaluate(PLAN,p)
        self.assertIsNone(x["breakout_retest"]["first_opportunity"])
    def test_breakout_continuation_without_pullback(self):
        p={("271560","2026-11-02"):bar(114000,118000,117000),
           ("271560","2026-11-03"):bar(115000,119000,118000)}
        x=evaluate(PLAN,p)
        self.assertEqual(x["breakout_without_pullback"]["first_opportunity"],"2026-11-03")
        self.assertFalse(x["breakout_without_pullback"]["actual_fill_verified"])
    def test_intraday_breakout_not_counted_as_prior_close(self):
        p={("271560","2026-11-02"):bar(114000,118000,113000),
           ("271560","2026-11-03"):bar(115000,119000,118000)}
        x=evaluate(PLAN,p)
        self.assertEqual(x["breakout_without_pullback"]["opportunity_days"],0)

    def test_registration_day_excluded(self):
        x=evaluate(PLAN,{("271560","2026-10-31"):bar(111000,116000,115000)})
        self.assertEqual(x["observed_sessions"],0)
    def test_no_actual_fill_claim(self):
        x=evaluate(PLAN,{("271560","2026-11-02"):bar(111000,116000,115000)})
        self.assertFalse(x["pullback"]["actual_fill_verified"])
        self.assertFalse(x["trade_approved"])
    def test_two_plans_required(self):
        with self.assertRaisesRegex(ValueError,"EXPECTED_EXACTLY_TWO"):
            build([PLAN],{})
    def test_incomplete_observation(self):
        x=evaluate(PLAN,{})
        self.assertFalse(x["observation_complete"])

if __name__=="__main__":
    unittest.main()
