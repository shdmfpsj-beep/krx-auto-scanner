import unittest
from c3_registry_integrity_v22 import audit
class IntegrityTest(unittest.TestCase):
    def test_historical_specials_remain_counted_but_ineligible(self):
        rows=[{"key":"a","ticker":"145270","status":"RESEARCH_ONLY"},{"key":"b","ticker":"466690","status":"RESEARCH_ONLY"}]
        preliminary=[{"ticker":"145270","name":"케이탑리츠"},{"ticker":"466690","name":"키움히어로제1호스팩"}]
        evidence=[{"ticker":r["ticker"],"instrument_review":"EXCLUDE_SPECIAL"} for r in rows]
        original=[dict(r) for r in rows]
        result=audit(rows,preliminary,evidence)
        self.assertEqual(result["total_registered"],2)
        self.assertEqual(result["excluded_from_eligible_performance"],2)
        self.assertEqual(rows,original)
        self.assertEqual(result["buy_approvals"],0)
    def test_unknown_evidence_is_not_certification(self):
        result=audit([{"ticker":"000001"}],[{"ticker":"000001","name":"일반기업"}],[])
        self.assertEqual(result["excluded_from_eligible_performance"],1)
if __name__=="__main__":unittest.main()
