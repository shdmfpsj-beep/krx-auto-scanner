import unittest
from c3_forward_opportunity_v18 import audit

class ForwardTests(unittest.TestCase):
    def test_no_later_open_substitution(self):
        registry=[{"ticker":"000001","registered_utc":"2026-11-02T14:00:00+00:00","price_date":"2026-11-02"}]
        later=[{"ticker":"000001","date":"2026-11-04","open":"110","is_immediate_next_session":"False"}]
        result=audit(registry,later)
        self.assertEqual(result["observations"][0]["status"],"NEXT_SESSION_CALENDAR_UNVERIFIED")
        self.assertIsNone(result["observations"][0]["next_open"])
        self.assertIsNone(result["fills"])
    def test_no_observations(self):
        registry=[{"ticker":"000001","registered_utc":"2026-11-02T14:00:00+00:00","price_date":"2026-11-02"}]
        result=audit(registry,[])
        self.assertEqual(result["observations"][0]["status"],"NEXT_SESSION_UNOBSERVED")
        self.assertIsNone(result["opportunity_rate"])
if __name__=="__main__":unittest.main()
