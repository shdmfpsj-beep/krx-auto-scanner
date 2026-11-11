import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_v11_dart_anomaly_titles import classify_title,join

class DARTTitleTests(unittest.TestCase):
 def test_action_kind_not_verified_effective_date(self):
    self.assertEqual(classify_title("권리락 (무상증자)"),"CORPORATE_DISCLOSURE_TITLE")
 def test_halt_protected(self):
    self.assertEqual(classify_title("주권매매거래정지 (상장폐지 사유발생)"),"HALT_OR_DELISTING_DISCLOSURE_TITLE")
 def test_same_day_receipt_not_asof_safe(self):
    x=join([{"ticker":"000001","date":"2026-10-20"}],[{"ticker":"000001","receipt_date":"2026-10-20",
             "receipt_no":"20261020000111","report_name":"권리락 (무상증자)"}])
    self.assertEqual(x["events"][0]["label"],"NO_MATCHING_PRIOR_TITLE_IN_SNAPSHOT")
 def test_prior_receipt_remains_noncausal(self):
    x=join([{"ticker":"000001","date":"2026-10-20"}],[{"ticker":"000001","receipt_date":"2026-10-19",
             "receipt_no":"20261019000111","report_name":"권리락 (무상증자)"}])
    self.assertEqual(x["events"][0]["label"],"PRIOR_ACTION_TITLE_UNVERIFIED_CAUSE")
    self.assertFalse(x["original_corporate_action_filing_body_and_effective_date_verified"])
 def test_later_disclosure_never_backfilled(self):
    x=join([{"ticker":"000001","date":"2026-10-20"}],[{"ticker":"000001","receipt_date":"2026-10-21",
             "receipt_no":"20261021000111","report_name":"감자결정"}])
    self.assertEqual(x["events"][0]["label"],"NO_MATCHING_PRIOR_TITLE_IN_SNAPSHOT")
 def test_old_disclosure_outside_fixed_window(self):
    x=join([{"ticker":"000001","date":"2026-11-10"}],[{"ticker":"000001","receipt_date":"2026-09-01",
             "receipt_no":"20260901000111","report_name":"주식분할"}])
    self.assertEqual(x["events"][0]["label"],"NO_MATCHING_PRIOR_TITLE_IN_SNAPSHOT")

if __name__=="__main__":unittest.main()
