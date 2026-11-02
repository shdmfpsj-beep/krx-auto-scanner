import unittest
from c3_structure_entry_research_v1 import EntryEvidence, evaluate

def case(**overrides):
    args=dict(price_date="2026-11-02", registered_at="2026-11-02T22:00:00+09:00",
              support_date="2026-10-30", support_low=10000, atr14=500,
              first_resistance=12500, close=10300, right_completed_bars=2,
              source_regular_certified=True, support_confirmed=True, first_resistance_verified=True, source_family='A')
    args.update(overrides)
    return EntryEvidence(**args)

class StructuralEntryTests(unittest.TestCase):
    def test_valid_range(self):
        result=evaluate(case(), tick=100)
        self.assertEqual(result["state"],"RESEARCH_CONDITIONAL")
        self.assertLessEqual(result["range"][0],result["range"][1])
    def test_no_nearby_reward(self):
        self.assertEqual(evaluate(case(first_resistance=10400), tick=100)["state"],"NO_COSTED_2R_RANGE")
    def test_missing_right_bars(self):
        self.assertEqual(evaluate(case(right_completed_bars=1), tick=100)["state"],"WAIT_SUPPORT_CONFIRMATION")
    def test_no_fake_higher_support(self):
        self.assertEqual(evaluate(case(close=12000), tick=100)["state"],"WAIT_NEW_SUPPORT")
    def test_source_not_approved(self):
        self.assertEqual(evaluate(case(source_regular_certified=False), tick=100)["state"],"WAIT_SOURCE_CERTIFICATION")
    def test_stop_breach(self):
        self.assertEqual(evaluate(case(close=9800), tick=100)["state"],"CANCEL_CLOSE_BELOW_STOP")

if __name__=="__main__":
    unittest.main()

    def test_missing_tick(self):
        self.assertEqual(evaluate(case())["state"], "WAIT_VERIFIED_TICK")
    def test_no_support_confirmation(self):
        self.assertEqual(evaluate(case(support_confirmed=False),tick=100)["state"], "WAIT_SUPPORT_CONFIRMATION")
    def test_future_price_date(self):
        self.assertEqual(evaluate(case(registered_at="2026-10-30T22:00:00+09:00"),tick=100)["state"], "INVALID_DATE_OR_REGISTRATION")
    def test_equal_stop_is_not_breach(self):
        self.assertNotEqual(evaluate(case(close=9900),tick=100)["state"], "CANCEL_CLOSE_BELOW_STOP")
