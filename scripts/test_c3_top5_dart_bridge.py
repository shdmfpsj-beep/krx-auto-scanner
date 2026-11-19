#!/usr/bin/env python3
"""Offline safety tests for the TOP5 OpenDART adapter."""
import unittest
from datetime import date
from c3_top5_dart_bridge import bridge

TODAY = date(2026, 11, 19)
BASE = {"asof": "20261119", "candidates": [
    {"code": "294870", "name": "IPARK현대산업개발"}]}

class BridgeTests(unittest.TestCase):
    def test_historical_data_fails_closed_without_api(self):
        called = []
        r = bridge({**BASE, "asof": "20261118"}, "dummy", TODAY,
                   collector=lambda *a, **k: called.append(True))
        self.assertEqual(r["status"], "HISTORICAL_REPLAY_NO_RETROACTIVE_FINANCIALS")
        self.assertFalse(called)
        self.assertFalse(r["financial_verified"])

    def test_missing_key_cannot_pass(self):
        def stub(day, stocks, key, today):
            self.assertIsNone(key)
            return {"status": "MISSING_DART_KEY", "researched": []}
        r = bridge(BASE, None, TODAY, stub)
        self.assertEqual(r["status"], "INCOMPLETE_FINANCIAL_COVERAGE")

    def test_valid_financial_evidence_is_research_only(self):
        def stub(day, stocks, key, today):
            return {"status": "ANNUAL_RESEARCH_READ", "researched": [{
                "ticker": "294870", "name": "IPARK현대산업개발",
                "status": "DATED_ANNUAL_RESEARCH_ONLY",
                "receipt_date": "2026-03-20",
                "financial_screen_pass": True,
                "annual_plus_interim_growth_pass": True,
                "recent_financial_weakening_veto": False,
                "interim_research": {"status": "DATED_INTERIM_YTD_RESEARCH_ONLY"},
                "financial_quality": "ANNUAL_GROWTH_AND_MARGIN_OBSERVED"}]}
        r = bridge(BASE, "dummy", TODAY, stub)
        self.assertTrue(r["financial_verified"])
        self.assertFalse(r["trade_approved"])
        self.assertEqual(r["decision"], "CASH")

    def test_unverified_interim_is_excluded(self):
        def stub(day, stocks, key, today):
            return {"researched": [{"ticker": "294870",
                "status": "DATED_ANNUAL_RESEARCH_ONLY",
                "receipt_date": "2026-03-20",
                "financial_screen_pass": True,
                "annual_plus_interim_growth_pass": False,
                "interim_research": {"status": "NO_ELIGIBLE_INTERIM_FILING"}}]}
        r = bridge(BASE, "dummy", TODAY, stub)
        self.assertFalse(r["financial_verified"])
        self.assertEqual(len(r["excluded"]), 1)

if __name__ == "__main__":
    unittest.main()
