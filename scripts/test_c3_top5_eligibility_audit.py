import unittest
from c3_top5_eligibility_audit import audit

R = {"candidates": [{"code":"005930","name":"삼성전자","status":"ENTRY_READY"},
                     {"code":"000080","name":"하이트진로","status":"NEAR_ENTRY"}],
     "source_integrity":{"regular_session_price_certified":False,"corporate_actions_certified":False}}
F = {"status":"PARTIAL_OR_FAILED_FINANCIAL_GATE",
     "researched":[{"ticker":"005930","financial_screen_pass":True}]}
class EligibilityTests(unittest.TestCase):
    def test_no_price_certificate_blocks_every_candidate(self):
        x=audit(R,F)
        self.assertEqual(x["eligible_count"],0)
        self.assertTrue(all(c["status"]=="WATCH_UNVERIFIED" for c in x["candidates"]))
        self.assertFalse(x["trade_approved"])
    def test_self_asserted_certification_does_not_authorize(self):
        r={**R,"source_integrity":{"regular_session_price_certified":True,"corporate_actions_certified":True}}
        x=audit(r,F)
        self.assertEqual(x["eligible_count"],0)
        self.assertEqual(x["financial_qualified_codes"],["005930"])
        self.assertEqual(x["financial_qualified_count"],1)
        self.assertEqual(x["candidates"][0]["status"],"WATCH_UNVERIFIED")
        self.assertEqual(x["candidates"][1]["status"],"WATCH_UNVERIFIED")
        self.assertFalse(x["trade_approved"])
    def test_mismatched_financial_asof_blocks(self):
        self.assertEqual(audit({**R,"asof":"20261119"}, {**F,"asof":"20261118"})["eligible_count"],0)
    def test_unknown_financial_status_blocks(self):
        r={**R,"source_integrity":{"regular_session_price_certified":True,"corporate_actions_certified":True}}
        self.assertEqual(audit(r,{**F,"status":"UNVERIFIED"})["eligible_count"],0)
if __name__=="__main__":unittest.main()
