import unittest
from c3_selection_evidence_v16 import select

class EvidenceSelectionTest(unittest.TestCase):
    def test_explicit_exclusion_and_unknown_not_approved(self):
        prelim=[
            {"ticker":"000001","name":"A","c3_preliminary_score":"90","extension_vs_ma20_pct":"1","rvol20":"2"},
            {"ticker":"000002","name":"B","c3_preliminary_score":"80","extension_vs_ma20_pct":"2","rvol20":"1"}]
        evidence=[
            {"ticker":"000001","business_scope_status":"EXCLUDE_FROM_C3"},
            {"ticker":"000002","business_scope_status":"UNREVIEWED_BUSINESS","instrument_review":"COMMON_IN_PRIOR_SNAPSHOT",
             "regular_session_certified":"False","actual_turnover_status":"ACTUAL_SOURCE_TURNOVER_MISSING"}]
        result=select(prelim,evidence)
        self.assertEqual(result["excluded"]["EXCLUDED_BUSINESS"],1)
        self.assertEqual(result["joined_count"],1)
        self.assertFalse(result["provisional_watch_top2"][0]["buy_approved"])
        self.assertIn("BUSINESS_SCOPE_UNVERIFIED",result["provisional_watch_top2"][0]["evidence_blockers"])
        self.assertEqual(result["decision"],"CASH")
if __name__=="__main__":unittest.main()
