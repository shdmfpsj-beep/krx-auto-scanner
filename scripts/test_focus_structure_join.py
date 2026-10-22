#!/usr/bin/env python3
"""Offline regression tests for joining independent stop references."""
import unittest
from focus_structure_join import merge,render

BASE={"asof":"2026-10-22",
      "stock_research_top5":[{"ticker":"005930","name":"삼성전자"}],
      "sector_top3":[],"decision":"CASH"}
def row(when="2026-10-22",stop="905"):
    return dict(ticker="005930",name="삼성전자",
       latest_complete_date=when,close="1000",
       historical_stop_reference=stop,entry1_research_range="990~1010",
       entry2_support_research_range="",pivot_date="2026-10-15",
       data_source="pykrx",structure_state="SECOND_SUPPORT_NOT_CONFIRMED",
       next_action="2차 매수 지지 대기")
class JoinTests(unittest.TestCase):
    def test_price_reference_shown_even_when_second_entry_unconfirmed(self):
        o=merge(BASE,[row()])
        self.assertEqual(o["focus_independent_stop_reference_count"],1)
        self.assertEqual(o["stock_research_top5"][0]["independently_collected_daily_stop_reference"],"905")
        self.assertEqual(o["decision"],"CASH")
        self.assertFalse(o["trade_approved"])
        self.assertIn("905",render(o,"# report"))
    def test_stale_price_must_not_show_as_current(self):
        o=merge(BASE,[row(when="2026-10-21")])
        self.assertEqual(o["focus_independent_stop_reference_count"],0)
        self.assertIsNone(o["stock_research_top5"][0]["independently_collected_daily_stop_reference"])
        self.assertIn("날짜 불일치",render(o,"# report"))
        self.assertEqual(o["decision"],"CASH")
    def test_missing_source_is_explicit_without_making_up_prices(self):
        o=merge(BASE,[])
        self.assertEqual(o["focus_daily_structure_research"],[])
        self.assertIn("가격 파일 없음",render(o,"# report"))
    def test_missing_pivot_is_not_silently_approved(self):
        broken=row(stop="")
        broken["structure_state"]="NO_HELD_CONFIRMED_PIVOT"
        o=merge(BASE,[broken])
        self.assertEqual(o["focus_independent_stop_reference_count"],0)
        self.assertIsNone(o["stock_research_top5"][0]["independently_collected_daily_stop_reference"])
        self.assertIn("NO_HELD_CONFIRMED_PIVOT",render(o,"# report"))
    def test_focus_price_does_not_create_85_score(self):
        o=merge(BASE,[row()])
        self.assertFalse(o["focus_price_is_independent_trade_approval"])
        self.assertNotIn("final_verified_score",o["stock_research_top5"][0])

if __name__=="__main__":
    unittest.main()
