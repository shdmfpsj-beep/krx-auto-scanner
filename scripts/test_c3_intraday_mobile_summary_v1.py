import unittest
from c3_intraday_mobile_summary_v1 import render
class TestMobileSummary(unittest.TestCase):
 def test_missing_provider_never_implies_fill(self):
  s=render({"status":"PENDING_PROVIDER_CREDENTIALS","checked_at":"2026-11-02T12:00:00+09:00"},{"alerts":[{"ticker":"271560","name":"오리온","status":"NO_VERIFIED_QUOTE","paper_filled":False}]})
  self.assertIn("PENDING_PROVIDER_CREDENTIALS",s)
  self.assertIn("NO_VERIFIED_QUOTE",s)
  self.assertNotIn("112,000원",s)
 def test_verified_watch_price(self):
  s=render({"status":"QUOTES_VERIFIED"},{"alerts":[{"name":"동서","status":"WATCH_ZONE","observed_price":27800}]})
  self.assertIn("27,800원",s)
  self.assertIn("WATCH_ZONE",s)
if __name__=="__main__":unittest.main()
