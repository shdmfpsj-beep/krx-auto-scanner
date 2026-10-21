#!/usr/bin/env python3
"""Offline regression tests for research-only KRX preliminary ranking."""
import unittest
from scripts.rank_candidates import score

BASE = dict(ticker="004490",name="Example",latest_date="2026-10-20",
            close="110",ma20="105",ma60="100",ma120="95",rvol20="1.5",
            weekly_filter="true",monthly_filter="true",
            first_pullback_proxy="true",instrument_type="COMMON",
            turnover_krw="1000000000",turnover_source="SOURCE_REPORTED")

class RankingSafetyTests(unittest.TestCase):
    def test_no_trade_approval_or_prices(self):
        result=score(BASE)
        self.assertEqual(result["trade_approval"],"NO")
        self.assertEqual(result["buy_price"],"")
        self.assertEqual(result["stop_price"],"")
        self.assertLessEqual(result["c3_preliminary_score"],85)
        self.assertIn("LIQUIDITY_FLOW_NOT_VERIFIED",result["warnings"])

    def test_missing_price_is_not_ranked(self):
        self.assertIsNone(score({**BASE,"ma20":""}))
        self.assertIsNone(score({**BASE,"close":"nan"}))

    def test_special_instruments_excluded(self):
        result=score({**BASE,"instrument_type":"ETF"})
        self.assertEqual(result["eligibility"],"EXCLUDE")
        self.assertEqual(result["trade_approval"],"NO")

    def test_unknown_instrument_needs_review(self):
        result=score({**BASE,"instrument_type":""})
        self.assertEqual(result["eligibility"],"REVIEW")
        self.assertIn("INSTRUMENT_TYPE_UNKNOWN",result["warnings"])

    def test_unverified_turnover_is_flagged(self):
        result=score({**BASE,"turnover_source":"ESTIMATED"})
        self.assertIn("TURNOVER_NOT_SOURCE_VERIFIED",result["warnings"])

    def test_extreme_volume_is_flagged(self):
        result=score({**BASE,"rvol20":"12"})
        self.assertIn("RVOL_GT_10_VERIFY",result["warnings"])

if __name__=="__main__":
    unittest.main()
