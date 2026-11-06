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
    def test_missing_calendar_is_visible(self):
        s=render({"coverage":{"271560":{"observed_sessions":20,"five_session_complete":True,"ten_session_complete":True,"twenty_session_complete":True}}})
        self.assertIn("중간 누락 거래일 여부: 검증 불가",s)
        self.assertIn("수익성 검증은 미완료",s)
    def test_third_party_calendar_clean_is_not_official_certification(self):
        s=render({},{"discrepancies_found":False,"start":"2026-10-25","end":"2026-11-03"})
        self.assertIn("불일치 미발견",s)
        self.assertIn("공식 한국거래소 거래일 인증: 미완료",s)
        self.assertIn("2026-10-25 ~ 2026-11-03",s)
    def test_third_party_calendar_gap_is_visible(self):
        s=render({},{"discrepancies_found":True,"start":"2026-10-25","end":"2026-11-03"})
        self.assertIn("불일치 발견 / 검토 필요",s)
        self.assertIn("CASH",s)
    def test_missing_data_is_visible(self):
        s=render({"collector_manifest":{"failures":{"271560":"EMPTY_RESPONSE"}}})
        self.assertIn("EMPTY_RESPONSE",s)
    def test_uncertified_row_count_caveat(self):
        s=render({})
        self.assertIn("공식 거래소 영업일 달력",s)

if __name__=="__main__":
    unittest.main()
