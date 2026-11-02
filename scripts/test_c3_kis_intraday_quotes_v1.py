import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from c3_kis_intraday_quotes_v1 import parse_latest,collect
KST=ZoneInfo("Asia/Seoul")
NOW=datetime(2026,11,2,10,10,tzinfo=KST)
class TestKISQuote(unittest.TestCase):
 def test_fresh_quote(self):
  rows=[{"stck_bsop_date":"20261102","stck_cntg_hour":"100800","stck_prpr":"112,000"}]
  q=parse_latest(rows,"271560",NOW)
  self.assertEqual(q["price"],112000)
  self.assertEqual(q["source"],"verified_provider")
 def test_stale_quote(self):
  self.assertIsNone(parse_latest([{"stck_bsop_date":"20261102","stck_cntg_hour":"095000","stck_prpr":"112000"}],"271560",NOW))
 def test_wrong_date(self):
  self.assertIsNone(parse_latest([{"stck_bsop_date":"20261030","stck_cntg_hour":"100800","stck_prpr":"112000"}],"271560",NOW))
 def test_no_credentials(self):
  self.assertEqual(collect(["271560"],NOW,"","")["status"],"PENDING_PROVIDER_CREDENTIALS")
 def test_before_market(self):
  self.assertEqual(collect(["271560"],datetime(2026,11,2,8,59,tzinfo=KST),"","")["status"],"OUTSIDE_REGULAR_SESSION")
 def test_close_boundary(self):
  self.assertEqual(collect(["271560"],datetime(2026,11,2,15,30,tzinfo=KST),"","")["status"],"OUTSIDE_REGULAR_SESSION")
 def test_weekend(self):
  self.assertEqual(collect(["271560"],datetime(2026,11,1,10,tzinfo=KST),"","")["status"],"OUTSIDE_REGULAR_SESSION")
 def test_aftermarket(self):
  self.assertEqual(collect(["271560"],datetime(2026,11,2,16,tzinfo=KST),"","")["status"],"OUTSIDE_REGULAR_SESSION")
if __name__=="__main__":unittest.main()
