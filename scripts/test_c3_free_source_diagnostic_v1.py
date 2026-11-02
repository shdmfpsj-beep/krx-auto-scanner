import unittest
from c3_free_source_diagnostic_v1 import diagnose
LEDGER={"positions":{"a":{"plan":{"ticker":"271560","name":"오리온"},"status":"WAITING","sessions_observed":0}}}
class Test(unittest.TestCase):
 def reason(self,source=None,scan=None):
  return diagnose(LEDGER,source,scan)["positions"][0]["reason"]
 def test_no_capture_artifact(self):
  self.assertEqual(self.reason(),"CAPTURE_ARTIFACT_NOT_AVAILABLE")
 def test_provider_failure(self):
  self.assertEqual(self.reason({"ticker_states":{"271560":{"capture_status":"FAILED_OR_SUSPENDED_NO_PAPER_TRADE"}}}),"PRICE_PROVIDER_FAILED_OR_SUSPENDED")
 def test_scan_not_verified(self):
  self.assertEqual(self.reason({"ticker_states":{"271560":{"capture_status":"OHLCV_OBSERVED_UNVERIFIED_SCOPE","last_session":"2026-11-02"}}},{}),"FULL_MARKET_SCAN_NOT_VERIFIED")
 def test_date_mismatch(self):
  s={"ticker_states":{"271560":{"capture_status":"OHLCV_OBSERVED_UNVERIFIED_SCOPE","last_session":"2026-10-30"}}}
  self.assertEqual(self.reason(s,{"scan_complete":True,"market_data_date":"2026-11-02"}),"SOURCE_DATES_MISMATCH")
 def test_pre_registration_bar_is_expected_wait(self):
  ledger={"positions":{"a":{"plan":{"ticker":"271560","registered_day":"2026-10-31"},"status":"WAITING","sessions_observed":0}}}
  source={"ticker_states":{"271560":{"capture_status":"OHLCV_OBSERVED_UNVERIFIED_SCOPE","last_session":"2026-10-30"}}}
  self.assertEqual(diagnose(ledger,source,{"scan_complete":True,"market_data_date":"2026-10-30"})["positions"][0]["reason"],"NO_POST_REGISTRATION_SESSION_YET")
 def test_eligible_requires_further_review(self):
  s={"ticker_states":{"271560":{"capture_status":"OHLCV_OBSERVED_UNVERIFIED_SCOPE","last_session":"2026-11-02"}}}
  self.assertEqual(self.reason(s,{"scan_complete":True,"market_data_date":"2026-11-02"}),"CHECK_REGISTRATION_AND_FORWARD_ELIGIBILITY")
if __name__=="__main__":unittest.main()
