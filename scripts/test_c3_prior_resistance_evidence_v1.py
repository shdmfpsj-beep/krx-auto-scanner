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
    def test_no_candidate_above_entry(self):
        prices={("271560","2026-10-{:02d}".format(i)):bar(104) for i in range(1,21)}
        r=assess(PLAN,prices)
        self.assertEqual(r["status"],"NO_PRIOR_HIGH_ABOVE_ENTRY")
if __name__=="__main__":unittest.main()
