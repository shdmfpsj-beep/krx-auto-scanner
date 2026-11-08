import unittest
from c3_free_mobile_report_v1 import render
class Tests(unittest.TestCase):
 def test_missing_data_means_cash(self):
  s=render({"positions":[{"name":"오리온","ticker":"271560","paper_status":"WAITING","observed_sessions":0,"reason":"CAPTURE_ARTIFACT_NOT_AVAILABLE"}]})
  self.assertIn("오리온 (271560)",s)
  self.assertIn("가격 수집 결과 파일 없음",s)
  self.assertIn("CASH",s)
  self.assertIn("실제 매수·주문 없음",s)
 def test_untrusted_name_escaped(self):
  s=render({"positions":[{"name":"X|Y","ticker":"026960","reason":"SOURCE_DATES_MISMATCH"}]})
  self.assertIn("X/Y",s)
  self.assertIn("가격 수집일과 스캔일 불일치",s)
if __name__=="__main__":unittest.main()
