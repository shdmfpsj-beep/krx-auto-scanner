import unittest
from c3_structure_entry_research_v1 import EntryEvidence, evaluate

def case(**overrides):
    args=dict(price_date="2026-11-02", registered_at="2026-11-02T22:00:00+09:00",
              support_date="2026-10-30", support_low=10000, atr14=500,
              first_resistance=12500, close=10300, right_completed_bars=2,
              source_regular_certified=True)
    args.update(overrides)
    return EntryEvidence(**args)

class StructuralEntryTests(unittest.TestCase):
    def test_valid_range(self):
        result=evaluate(case())
        self.assertEqual(result["state"],"RESEARCH_CONDITIONAL")
        self.assertLessEqual(result["range"][0],result["range"][1])
    def test_no_nearby_reward(self):
        self.assertEqual(evaluate(case(first_resistance=10400))["state"],"NO_COSTED_2R_RANGE")
    def test_missing_right_bars(self):
        self.assertEqual(evaluate(case(right_completed_bars=1))["state"],"WAIT_RIGHT_BARS")
    def test_no_fake_higher_support(self):
        self.assertEqual(evaluate(case(close=12000))["state"],"WAIT_NEW_SUPPORT")
    def test_source_not_approved(self):
        self.assertEqual(evaluate(case(source_regular_certified=False))["state"],"WAIT_SOURCE_CERTIFICATION")
    def test_stop_breach(self):
        self.assertEqual(evaluate(case(close=9900))["state"],"CANCEL_CLOSE_BELOW_STOP")

if __name__=="__main__":
    unittest.main()
