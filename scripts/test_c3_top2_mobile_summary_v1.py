import unittest
from c3_top2_mobile_summary_v1 import render

class MobileSummaryTests(unittest.TestCase):
    def test_no_buy_signal(self):
        s=render({"coverage":{},"collector_manifest":{}})
        self.assertIn("CASH",s)
        self.assertIn("실계좌 주문: 비활성",s)
    def test_horizon_table(self):
        s=render({"coverage":{"271560":{"observed_sessions":5,"five_session_complete":True,
                   "ten_session_complete":False,"twenty_session_complete":False}}})
        self.assertIn("| 271560 | 5 | 관측 | 미완료 | 미완료 |",s)
    def test_missing_data_is_visible(self):
        s=render({"collector_manifest":{"failures":{"271560":"EMPTY_RESPONSE"}}})
        self.assertIn("EMPTY_RESPONSE",s)
    def test_uncertified_row_count_caveat(self):
        s=render({})
        self.assertIn("공식 거래소 영업일 달력",s)

if __name__=="__main__":
    unittest.main()
