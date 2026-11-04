import unittest
from c3_prior_resistance_evidence_v1 import assess

PLAN=dict(ticker="271560",selection_date="2026-11-01",watch_high="105",
          target1="120",structure_stop="95")
def bar(high):
    return dict(open=100,high=high,low=90,close=100,volume=100)
class PriorResistanceTests(unittest.TestCase):
    def test_insufficient_history_never_claims_resistance(self):
        prices={("271560","2026-10-30"):bar(110)}
        r=assess(PLAN,prices)
        self.assertEqual(r["status"],"INSUFFICIENT_PRIOR_HISTORY")
        self.assertIsNone(r["nearest_prior_high_above_watch_high"])
        self.assertFalse(r["resistance_confirmed"])
    def test_future_bars_not_used(self):
        prices={("271560","2026-10-{:02d}".format(i)):bar(110+i) for i in range(1,21)}
        prices[("271560","2026-11-02")]=bar(1000)
        r=assess(PLAN,prices)
        self.assertEqual(r["nearest_prior_high_above_watch_high"],111)
        self.assertEqual(r["prior_sessions"],20)
        self.assertEqual(r["status"],"PRIOR_HIGH_CANDIDATE_ONLY")
        self.assertTrue(r["nearest_prior_high_may_limit_target"])
    def test_pivot_requires_two_prior_bars_each_side(self):
        prices={("271560","2026-10-{:02d}".format(i)):bar(104) for i in range(1,21)}
        prices[("271560","2026-10-10")]=bar(118)
        prices[("271560","2026-11-02")]=bar(900)
        r=assess(PLAN,prices)
        self.assertEqual(r["nearest_confirmed_prior_swing_high"],118)
        self.assertEqual(r["nearest_confirmed_prior_swing_high_date"],"2026-10-10")
        self.assertEqual(r["prior_swing_high_count"],1)
        self.assertTrue(r["prior_swing_high_below_target"])
        self.assertEqual(r["prior_swing_reward_risk_at_watch_high"],1.3)
        self.assertEqual(r["planned_target_reward_risk_at_watch_high"],1.5)
        self.assertTrue(r["prior_swing_before_planned_target"])
        self.assertFalse(r["pivot_is_confirmed_resistance"])
        self.assertEqual(r["swing_rr_warning"],"SWING_REWARD_1_TO_1_5R")
        self.assertEqual(r["research_triage"],"WATCH_RESEARCH_ONLY")
        self.assertEqual(r["prior_closes_above_swing_high"],0)
        self.assertFalse(r["breakout_retest_verified"])
    def test_selection_day_cannot_confirm_pivot(self):
        prices={("271560","2026-10-{:02d}".format(i)):bar(104) for i in range(1,21)}
        prices[("271560","2026-10-19")]=bar(118)
        prices[("271560","2026-11-01")]=bar(100)
        r=assess(PLAN,prices)
        self.assertIsNone(r["nearest_confirmed_prior_swing_high"])
        self.assertEqual(r["swing_rr_warning"],"NO_PRIOR_SWING_CANDIDATE")
        self.assertEqual(r["research_triage"],"REVIEW_NO_SWING_EVIDENCE")
    def test_near_resistance_is_review_not_buy(self):
        prices={("271560","2026-10-{:02d}".format(i)):bar(104) for i in range(1,21)}
        prices[("271560","2026-10-10")]=bar(109)
        r=assess(PLAN,prices)
        self.assertEqual(r["research_triage"],"REVIEW_NEAR_RESISTANCE")
        self.assertFalse(r["trade_approved"])
    def test_breakout_evidence_excludes_selection_and_future(self):
        prices={("271560","2026-10-{:02d}".format(i)):bar(104) for i in range(1,21)}
        prices[("271560","2026-10-10")]=bar(109)
        prices[("271560","2026-10-15")]=dict(bar(110),close=110)
        prices[("271560","2026-11-02")]=dict(bar(200),close=200)
        r=assess(PLAN,prices)
        self.assertEqual(r["prior_closes_above_swing_high"],1)
        self.assertTrue(r["breakout_closes_are_post_pivot_only"])
        self.assertFalse(r["last_prior_close_above_swing_high"])
        self.assertFalse(r["breakout_retest_verified"])
        self.assertFalse(r["trade_approved"])
    def test_pre_pivot_closes_do_not_count_as_breakouts(self):
        prices={("271560","2026-10-{:02d}".format(i)):bar(104) for i in range(1,21)}
        prices[("271560","2026-10-02")]=dict(bar(120),close=119)
        prices[("271560","2026-10-10")]=bar(109)
        r=assess(PLAN,prices)
        self.assertEqual(r["nearest_confirmed_prior_swing_high_date"],"2026-10-10")
        self.assertEqual(r["prior_closes_above_swing_high"],0)
        self.assertFalse(r["trade_approved"])
    def test_no_candidate_above_entry(self):
        prices={("271560","2026-10-{:02d}".format(i)):bar(104) for i in range(1,21)}
        r=assess(PLAN,prices)
        self.assertEqual(r["status"],"NO_PRIOR_HIGH_ABOVE_ENTRY")
if __name__=="__main__":unittest.main()
