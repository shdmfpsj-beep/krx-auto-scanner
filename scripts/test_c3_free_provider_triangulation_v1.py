import unittest
from c3_free_provider_triangulation_v1 import summarize

class FreeTriangulationTests(unittest.TestCase):
    def test_agreement_does_not_certify(self):
        a={"comparison_count":14,"result_counts":{"MATCH":14}}
        b={"comparison_count":14,"result_counts":{"MATCH":2,"MISMATCH":12}}
        r=summarize(a,b)
        self.assertTrue(r["observed_naver_agreement"])
        self.assertFalse(r["naver_source_independence_verified"])
        self.assertFalse(r["regular_only_certified"])
        self.assertFalse(r["trade_approved"])
        self.assertEqual(r["yahoo_vs_pykrx"]["mismatches"],12)
    def test_inconsistent_count_rejected(self):
        a={"comparison_count":14,"result_counts":{"MATCH":13}}
        with self.assertRaisesRegex(ValueError,"INVALID_CONCORDANCE_COUNTS"):
            summarize(a,a)
if __name__=="__main__":
    unittest.main()
