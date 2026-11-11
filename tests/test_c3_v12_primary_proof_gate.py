import unittest
from scripts.c3_v12_primary_proof_gate import (
    certify_corporate_action, certify_financial, classify_entry)

class ProofGateTests(unittest.TestCase):
    def test_dart_title_alone_does_not_certify(self):
        self.assertEqual(certify_corporate_action({"ticker":"023150", "event_date":"2026-10-19",
            "source_url":"https://dart.fss.or.kr/"} )["status"], "BLOCKED_MISSING_PRIMARY_PROOF")
    def test_issuer_same_par_and_shares_not_proof(self):
        self.assertEqual(certify_corporate_action({"par_value_same":True,
            "listed_shares_same":True})["status"], "BLOCKED_MISSING_PRIMARY_PROOF")
    def test_no_numeric_pit(self):
        self.assertEqual(certify_financial({"ticker":"023150"})["status"], "BLOCKED_NO_ORIGINAL_NUMERIC_PIT")
    def test_same_day_filing_blocked(self):
        r={"ticker":"A","selection_date":"2026-10-19","receipt_date":"2026-10-19",
           "original_filing_id":"x","original_sha256":"y","revenue":100,
           "operating_profit":10,"debt":20,"equity":40,"previous_year_revenue":80,
           "is_latest_correction_asof":True}
        self.assertEqual(certify_financial(r)["status"], "BLOCKED_FUTURE_OR_SAME_DAY_FILING")
    def test_daily_high_low_not_fill(self):
        self.assertEqual(classify_entry({"ticker":"A","high":110,"low":90})["status"],
                         "UNCONFIRMED_DAILY_OVERLAP_NOT_FILL")
    def test_execution_source_required(self):
        r={"ticker":"A","signal_date":"2026-10-19","entry_low":95,"entry_high":100,
           "structural_stop":90,"resistance":115,"expiration_sessions":3,
           "execution_timestamp":"2026-10-20T09:30:00","execution_price":97}
        self.assertEqual(classify_entry(r)["status"], "UNCONFIRMED_DAILY_OVERLAP_NOT_FILL")
    def test_invalid_expiration(self):
        r={"ticker":"A","signal_date":"2026-10-19","entry_low":95,"entry_high":100,
           "structural_stop":90,"resistance":115,"expiration_sessions":4,
           "execution_timestamp":"2026-10-20T09:30:00","execution_price":97,
           "execution_source_sha256":"abc"}
        self.assertEqual(classify_entry(r)["status"], "BLOCKED_EXPIRATION")
if __name__ == "__main__":
    unittest.main()
