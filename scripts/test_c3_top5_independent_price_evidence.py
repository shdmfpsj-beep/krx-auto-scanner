import unittest
from c3_top5_independent_price_evidence import verify
R={"asof":"20261119","candidates":[{"code":"005930","close":100000}]}
E={"source_type":"INDEPENDENT_OFFICIAL_EXCHANGE","asof":"20261119",
   "adjustment_policy_verified":True,"prices":[{"code":"005930","close":100000,"regular_session":True}]}
class PriceEvidenceTests(unittest.TestCase):
    def test_official_alphanumeric_ticker_is_preserved_without_certification(self):
        r={**R,'candidates':[{'code':'0220W0','close':7780}]}
        e={**E,'prices':[{'code':'0220W0','close':7780,'regular_session':True}]}
        x=verify(r,e)
        self.assertEqual(x['matched'],['0220W0'])
        self.assertFalse(x['regular_session_price_certified'])
    def test_matching_rows_never_self_certify(self):
        x=verify(R,E)
        self.assertEqual(x["status"],"PRICE_ROWS_MATCHED_PROVENANCE_UNVERIFIED")
        self.assertFalse(x["regular_session_price_certified"])
        self.assertFalse(x["corporate_actions_certified"])
        self.assertFalse(x["trade_approved"])
    def test_wrong_date_blocks(self):
        self.assertEqual(verify(R,{**E,"asof":"20261118"})["status"],"ASOF_MISMATCH")
    def test_wrong_price_blocks(self):
        e={**E,"prices":[{"code":"005930","close":99900,"regular_session":True}]}
        self.assertEqual(verify(R,e)["status"],"PRICE_MISMATCH_OR_SESSION_UNVERIFIED")
    def test_missing_adjustment_audit_blocks(self):
        self.assertEqual(verify(R,{**E,"adjustment_policy_verified":False})["status"],"ADJUSTMENT_POLICY_UNVERIFIED")
    def test_untrusted_source_blocks(self):
        self.assertEqual(verify(R,{**E,"source_type":"SCREENSHOT"})["status"],"NON_INDEPENDENT_SOURCE")
    def test_incomplete_candidate_coverage_blocks(self):
        r={**R,"candidates":R["candidates"]+[{"code":"000080","close":15000}]}
        self.assertEqual(verify(r,E)["status"],"INCOMPLETE_EVIDENCE")
if __name__=="__main__":unittest.main()
