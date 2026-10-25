#!/usr/bin/env python3
"""Date, world/market conflict and never-buy v6.18 fusion tests."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from global_krx_fusion_v618 import fuse,expected_domestic_session,SCHEMA
KST=ZoneInfo("Asia/Seoul")
def macro(r="GLOBAL_CAUTION_RESEARCH_ONLY",day="2026-10-23"):
    return dict(schema="C3_K100_GLOBAL_MACRO_US_EQUITIES_V618_RESEARCH",
      trade_approved=False,orders_enabled=False,krx_session_data_included=False,
      us_last_session=day,regime=r,group_classifications={"US_BROAD":"AMBER"})
def dom(day="2026-10-23",risk="RED_MARKET_RISK_OFF"):
    return [dict(asof=day,risk_mode=risk)]
def watch(day="2026-10-23"):
    return [dict(asof=day,ticker="000001",name="TEST",method="FIRST_MA20_RESUME",
       classification="C_SIGNAL_NOT_READY_RISK_OR_HEADROOM",
       discovery_index_only="80.1",first_limit_study="100.11",
       structure_stop_study="90.11",trade_approved="False",orders_enabled="False")]
def now(d="2026-10-25T17:35:00+09:00"):
    return datetime.fromisoformat(d)

class FusionTests(unittest.TestCase):
    def test_sunday_applies_friday_only_and_keeps_c_watch(self):
        r=fuse(macro(),dom(),watch(),now())
        self.assertEqual(r["recommendation"],"CASH_DOMESTIC_RISK")
        self.assertEqual(r["domestic_source_date"],"2026-10-23")
        self.assertEqual(len(r["research_watch5"]),1)
        self.assertEqual(r["research_watch5"][0]["action"],"NO_ORDER_RESEARCH_ONLY")
        self.assertFalse(r["orders_enabled"])
    def test_monday_preopen_accepts_friday_but_monday_after_close_requires_today(self):
        self.assertEqual(expected_domestic_session(now("2026-10-26T08:35:00+09:00")).isoformat(),"2026-10-23")
        self.assertEqual(expected_domestic_session(now("2026-10-26T16:00:00+09:00")).isoformat(),"2026-10-26")
        r=fuse(macro(),dom(),watch(),now("2026-10-26T16:00:00+09:00"))
        self.assertEqual(r["recommendation"],"CASH_DOMESTIC_SOURCE_PENDING")
        self.assertEqual(len(r["research_watch5"]),0)
    def test_stale_domestic_not_called_no_opportunity(self):
        r=fuse(macro(),dom(),watch(),now("2026-10-27T08:35:00+09:00"))
        self.assertFalse(r["domestic_source_same_expected_date"])
        self.assertEqual(r["recommendation"],"CASH_DOMESTIC_SOURCE_PENDING")
    def test_missing_global_never_cash_to_buy(self):
        r=fuse(macro("GLOBAL_DATA_INCOMPLETE_RESEARCH_ONLY",None),dom(risk="GREEN_RESEARCH_ONLY"),watch(),now())
        self.assertEqual(r["recommendation"],"CASH_GLOBAL_SOURCE_PENDING")
        self.assertFalse(r["trade_approved"])
    def test_market_green_and_global_supportive_still_need_final_gates(self):
        r=fuse(macro("GLOBAL_SUPPORTIVE_RESEARCH_ONLY"),
            dom(risk="GREEN_RESEARCH_ONLY"),watch(),now())
        self.assertEqual(r["recommendation"],"CASH_FINAL_GATES_UNVERIFIED")
        self.assertFalse(r["fee_adjusted_two_R_verified"])
        self.assertEqual(r["schema"],SCHEMA)
    def test_no_future_macro_or_false_order_input(self):
        r=fuse(macro(day="2026-10-26"),dom(risk="GREEN_RESEARCH_ONLY"),watch(),now())
        self.assertEqual(r["recommendation"],"CASH_GLOBAL_SOURCE_PENDING")
        bad=macro();bad["trade_approved"]=True
        with self.assertRaisesRegex(ValueError,"NO_TRADE"):
            fuse(bad,dom(),watch(),now())
    def test_unapproved_source_candidate_cannot_sneak_in(self):
        w=watch();w[0]["trade_approved"]="True"
        with self.assertRaisesRegex(ValueError,"POLICY"):
            fuse(macro(),dom(),w,now())
    def test_naive_datetime_rejected(self):
        with self.assertRaisesRegex(ValueError,"KST"):
            fuse(macro(),dom(),watch(),datetime(2026,10,25,17,35))

if __name__=="__main__":unittest.main()
