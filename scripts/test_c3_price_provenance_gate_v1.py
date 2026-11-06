import unittest
from c3_price_provenance_gate_v1 import inspect

A=dict(provider="pykrx",upstream="KRX",market_scope="REGULAR_ONLY",
       price_adjustment="ADJUSTED",timezone="Asia/Seoul",
       retrieved_at="2026-11-04T00:00:00+09:00")
B=dict(provider="independent-exchange-feed",upstream="OTHER_EXCHANGE",
       market_scope="REGULAR_ONLY",price_adjustment="ADJUSTED",
       timezone="Asia/Seoul",retrieved_at="2026-11-04T00:00:00+09:00")

class ProvenanceTests(unittest.TestCase):
    def test_compatible_claims_still_uncertified(self):
        x=inspect(A,B)
        self.assertTrue(x["metadata_claims_consistent"])
        self.assertFalse(x["independently_verified"])
        self.assertFalse(x["trade_approved"])
    def test_same_provider_alias(self):
        x=inspect(A,dict(B,provider="PY-KRX"))
        self.assertIn("SAME_PROVIDER",x["errors"])
    def test_same_upstream(self):
        x=inspect(A,dict(B,upstream="krx"))
        self.assertIn("SAME_UPSTREAM",x["errors"])
    def test_pykrx_and_naver_labels_cannot_hide_shared_source(self):
        x=inspect(A,dict(B,provider="FinanceDataReader_NAVER",upstream="NAVER"))
        self.assertIn("SOURCE_LINEAGE_OVERLAP",x["errors"])
    def test_adjustment_mismatch(self):
        x=inspect(A,dict(B,price_adjustment="UNADJUSTED"))
        self.assertIn("ADJUSTMENT_MISMATCH",x["errors"])
    def test_unknown_adjustment(self):
        x=inspect(A,dict(B,price_adjustment="UNKNOWN"))
        self.assertIn("UNKNOWN_ADJUSTMENT",x["errors"])
    def test_extended_hours_rejected(self):
        x=inspect(A,dict(B,market_scope="REGULAR_PLUS_EXTENDED"))
        self.assertIn("REGULAR_SCOPE_UNVERIFIED",x["errors"])
    def test_missing_timestamp(self):
        x=inspect(A,dict(B,retrieved_at=""))
        self.assertIn("REFERENCE_MISSING_RETRIEVED_AT",x["errors"])
    def test_wrong_timezone(self):
        x=inspect(A,dict(B,timezone="UTC"))
        self.assertIn("REFERENCE_TIMEZONE_NOT_KST",x["errors"])

if __name__=="__main__":
    unittest.main()
