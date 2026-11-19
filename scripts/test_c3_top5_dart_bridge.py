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

    def test_next_day_research_runs_but_cannot_claim_pit(self):
        called=[]
        def stub(day, stocks, key, today):
            called.append(day)
            return {"researched": [{"ticker":"294870",
                "status":"DATED_ANNUAL_RESEARCH_ONLY",
                "receipt_date":"2026-03-20",
                "financial_screen_pass":True,
                "annual_plus_interim_growth_pass":True,
                "interim_research":{"status":"DATED_INTERIM_YTD_RESEARCH_ONLY",
                                   "filing":{"receipt_date":"2026-11-16"}}}]}
        x=bridge({**BASE,"asof":"20261118"},"dummy",TODAY,stub)
        self.assertEqual(called,[TODAY])
        self.assertEqual(x["status"],"NEXT_DAY_FINANCIAL_RESEARCH_NOT_PIT_CERTIFIED")
        self.assertFalse(x["financial_verified"])
        self.assertEqual(x["financial_observed_on"],"2026-11-19")
    def test_missing_key_cannot_pass(self):
        r = bridge(BASE, None, TODAY, collector=lambda *a, **k: self.fail("API called"))
        self.assertEqual(r["status"], "MISSING_DART_KEY")

    def test_valid_financial_evidence_is_research_only(self):
        def stub(day, stocks, key, today):
            return {"status": "ANNUAL_RESEARCH_READ", "researched": [{
                "ticker": "294870", "name": "IPARK현대산업개발",
                "status": "DATED_ANNUAL_RESEARCH_ONLY",
                "receipt_date": "2026-03-20",
                "financial_screen_pass": True,
                "annual_plus_interim_growth_pass": True,
                "recent_financial_weakening_veto": False,
                "interim_research": {"status": "DATED_INTERIM_YTD_RESEARCH_ONLY",
                                     "filing": {"receipt_date": "2026-11-16"}},
                "financial_quality": "ANNUAL_GROWTH_AND_MARGIN_OBSERVED"}]}
        r = bridge(BASE, "dummy", TODAY, stub)
        self.assertTrue(r["financial_verified"])
        self.assertFalse(r["trade_approved"])
        self.assertEqual(r["decision"], "CASH")

    def test_invalid_calendar_date_is_blocked(self):
        r = bridge({**BASE, "asof": "20261199"}, "dummy", TODAY,
                   collector=lambda *a, **k: self.fail("API called"))
        self.assertEqual(r["status"], "INVALID_ASOF")

    def test_duplicate_candidate_is_blocked(self):
        r = bridge({**BASE, "candidates": BASE["candidates"] * 2}, "dummy", TODAY,
                   collector=lambda *a, **k: self.fail("API called"))
        self.assertEqual(r["status"], "DUPLICATE_TICKER")

    def test_future_interim_filing_is_not_eligible(self):
        def stub(day, stocks, key, today):
            return {"researched": [{"ticker": "294870",
                "status": "DATED_ANNUAL_RESEARCH_ONLY",
                "receipt_date": "2026-03-20",
                "financial_screen_pass": True,
                "annual_plus_interim_growth_pass": True,
                "interim_research": {"status": "DATED_INTERIM_YTD_RESEARCH_ONLY",
                                     "filing": {"receipt_date": "2026-11-20"}}}]}
        r = bridge(BASE, "dummy", TODAY, stub)
        self.assertEqual(r["status"], "PARTIAL_OR_FAILED_FINANCIAL_GATE")
        self.assertFalse(r["financial_verified"])

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
