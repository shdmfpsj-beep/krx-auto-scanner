import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from regular_only_policy import evaluate
from regular_final_report import generate,render,last_regular_close_date
from krx_session_probe import new_snapshot

KST=ZoneInfo("Asia/Seoul")
def session(h,m):return datetime(2026,10,23,h,m,tzinfo=KST)
def raw_snapshot(start=None,end=None):
    rows={f"{i:06d}":{"Open":100,"High":105,"Low":98,"Close":101,
                           "Volume":300,"TurnoverKRW":30300}
          for i in range(1,111)}
    return new_snapshot("regular",start or session(15,45),{"KOSPI":rows},ended_at=end or session(15,47))
class RegularOnlyTests(unittest.TestCase):
    def test_date_only_captured_before_16_still_not_session_certified(self):
        s=raw_snapshot()
        result=generate(s,"2026-10-23")
        self.assertEqual(s["window"],"REGULAR_WINDOW")
        self.assertEqual(s["quality"]["invalid"],0)
        self.assertIn("REGULAR_DATE_ONLY_FEED_CANNOT_CERTIFY_SCOPE",result["blockers"])
        self.assertIn("MARKET_SOURCE_SESSION_UNVERIFIED",result["blockers"])
        self.assertEqual(result["market_scope"],"KRX_REGULAR_ONLY")
        self.assertFalse(result["extended_market_included"])
        self.assertFalse(result["trade_approved"])
        self.assertEqual(result["approved_buy_count"],0)

    def test_end_after_16_fails_even_start_before(self):
        s=raw_snapshot(end=session(16,3))
        self.assertEqual(s["window"],"REGULAR_CAPTURE_FINISHED_AFTER_1600")
        self.assertIn("REGULAR_CAPTURE_WINDOW_UNVERIFIED",
                      generate(s,"2026-10-23")["blockers"])

    def test_regular_date_mismatch_and_corrupt_bar_fail_closed(self):
        s=raw_snapshot();s["stocks"]["000001"]["Close"]=115
        s["quality"]["invalid"]=1
        r=generate(s,"2026-10-22")
        self.assertIn("REGULAR_ASOF_MISMATCH",r["blockers"])
        self.assertIn("REGULAR_OHLC_CONFLICT",r["blockers"])
        self.assertEqual(r["decision"],"CASH")

    def test_missing_snapshot_does_not_mean_zero_good_sectors(self):
        r=generate({},"2026-10-22")
        self.assertIn("REGULAR_SNAPSHOT_MISSING",r["blockers"])
        self.assertIn("REGULAR_PRICE_NOT_READY",r["blockers"])
        self.assertIsNone(r["final_research_candidate_count"])
        self.assertIn("TOP3:** 최종 판정 보류",render(r))

    def test_sold_position_and_no_prices_made_up(self):
        r=generate({},"2026-10-22",dict(closed_ticker="004490",
            closed_shares_remaining=0,user_reported=True))
        md=render(r)
        self.assertIn("세방전지(004490) 전량 매도",md)
        self.assertIn("애프터마켓·NXT 시간외 시세 분석 제외",md)
        self.assertIn("BUY 승인 0건",md)

    def test_regular_market_cutoff_and_weekends(self):
        self.assertEqual(last_regular_close_date(session(15,34)),"2026-10-22")
        self.assertEqual(last_regular_close_date(session(15,35)),"2026-10-23")
        self.assertEqual(last_regular_close_date(session(20,30)),"2026-10-23")
        self.assertEqual(last_regular_close_date(datetime(2026,10,24,18,tzinfo=KST)),"2026-10-23")
if __name__=="__main__":unittest.main()
