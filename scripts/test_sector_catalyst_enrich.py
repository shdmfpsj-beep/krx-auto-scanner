#!/usr/bin/env python3
"""Offline tests for disclosure/news as-of provenance; no API tokens."""
import unittest
from datetime import date
from sector_catalyst_enrich import (
    index_evidence,enrich,markdown,news_url,official_dart_url
)
ASOF=date(2026,10,22)
BASE={"sector_top3":[{"sector_id":"SEMICON","name":"반도체"},
                     {"sector_id":"POWER","name":"전력설비"}],
      "decision":"CASH","asof":"2026-10-22","trade_approved":False}
STATUS={"datasets":{"news":{"status":"PARTIAL_SEARCH_ARCHIVE"},
                    "dart":{"status":"DATE_ONLY_COMPLETE"}}}

def article(sector="SEMICON",published="2026-10-22T10:20:00+09:00",url="https://example.com/news1"):
    return {"sector_id":sector,"published_at":published,"url":url,
      "title":"장비 신규 공급계약 관련 보도 내용","timestamp_basis":"NAVER_pubDate_not_original_first_publish_verified"}

def filing(ticker="005930",when="2026-10-21",receipt="20261021001234"):
    return {"ticker":ticker,"receipt_date":when,"receipt_no":receipt,
            "report_name":"주요사항보고서 테스트",
            "published_precision":"DAY_ONLY_no_intraday_time"}

def membership(when="2026-10-21"):
    return [{"sector_id":"SEMICON","ticker":"005930","snapshot_date":when}]

class CatalystEvidenceTests(unittest.TestCase):
    def test_valid_news_and_prior_dart_are_observations_only(self):
        idx,audit=index_evidence(BASE,[article()],[filing()],membership(),STATUS,ASOF)
        self.assertEqual(len(idx["SEMICON"]["news"]),1)
        self.assertEqual(len(idx["SEMICON"]["filings"]),1)
        out=enrich(BASE,idx,audit)
        self.assertEqual(out["decision"],"CASH")
        self.assertFalse(out["trade_approved"])
        self.assertFalse(out["orders_enabled"])
        self.assertEqual(out["catalyst_positive_count_verified"],0)
        self.assertTrue(out["sector_top3"][0]["recent_news_observations"])
        self.assertIn("dart.fss.or.kr",markdown(out))
    def test_same_day_dart_excluded_without_exact_publication_time(self):
        idx,_=index_evidence(BASE,[],[filing(when="2026-10-22")],
                             membership(),STATUS,ASOF)
        self.assertEqual(idx["SEMICON"]["filings"],[])
    def test_future_news_excluded_for_pit(self):
        idx,_=index_evidence(BASE,[article(published="2026-10-23T00:01:00+09:00")],
                             [],membership(),STATUS,ASOF)
        self.assertEqual(idx["SEMICON"]["news"],[])
    def test_stale_membership_excludes_corporate_filing(self):
        idx,_=index_evidence(BASE,[],[filing()],membership("2026-10-01"),STATUS,ASOF)
        self.assertEqual(idx["SEMICON"]["filings"],[])
    def test_missing_credential_dataset_does_not_invent_results(self):
        idx,audit=index_evidence(BASE,[article()],[filing()],membership(),
                  {"datasets":{"news":{"status":"MISSING_KEYS"},
                               "dart":{"status":"MISSING_KEY"}}},ASOF)
        self.assertEqual(audit["eligible_rows"],0)
        self.assertEqual(idx["SEMICON"]["news"],[])
        self.assertEqual(idx["SEMICON"]["filings"],[])
    def test_unselected_sector_news_never_attached(self):
        idx,_=index_evidence(BASE,[article(sector="HEALTH")],[filing("999999")],
                             membership(),STATUS,ASOF)
        self.assertEqual(idx["SEMICON"]["news"],[])
        self.assertEqual(idx["SEMICON"]["filings"],[])
    def test_invalid_urls_never_render_as_links(self):
        for bad in ("javascript:alert(1)","http://example.com/a","https://localhost/a",
                    "https://example.com/a)"):
            self.assertEqual(news_url(bad),"")
        self.assertEqual(official_dart_url("INVALID"),"")
    def test_duplicate_headlines_not_overcounted(self):
        idx,audit=index_evidence(BASE,[article(),article()],[],membership(),STATUS,ASOF)
        self.assertEqual(audit["eligible_rows"],1)
        self.assertEqual(len(idx["SEMICON"]["news"]),1)
    def test_old_news_beyond_five_days_excluded(self):
        idx,_=index_evidence(BASE,[article(published="2026-10-11T10:20:00+09:00")],
                             [],membership(),STATUS,ASOF)
        self.assertEqual(idx["SEMICON"]["news"],[])
    def test_empty_report_still_cash(self):
        idx,audit=index_evidence({"sector_top3":[]},[],[],[],{},None)
        result=enrich({"sector_top3":[],"decision":"CASH"},idx,audit)
        self.assertEqual(result["sector_top3"],[])
        self.assertEqual(result["decision"],"CASH")

if __name__=="__main__":
    unittest.main()
