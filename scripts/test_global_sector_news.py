#!/usr/bin/env python3
"""Offline tests for free global sector news: timestamp, country and no buys."""
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from global_sector_news import (
    SECTORS, MACRO, build_url, collect, seen_time, safe_url, unpack
)
NOW=datetime(2026,10,22,1,30,tzinfo=timezone.utc)

def payload(country="Taiwan",seen="20261022T012000Z",url="https://example.com/story"):
    return {"articles":[{"url":url,"title":"Semiconductor manufacturing investment expansion",
       "seendate":seen,"sourcecountry":country,"language":"Chinese"}]}

class GlobalSectorTests(unittest.TestCase):
    def test_universe_aligns_with_v18_and_excludes_health(self):
        self.assertEqual(len(SECTORS),16)
        self.assertNotIn("HEALTH",SECTORS)
        self.assertGreaterEqual(len(MACRO),3)
    def test_date_range_url_is_explicit_not_evergreen(self):
        url=build_url('"power grid" OR transformers',NOW-timedelta(hours=72),NOW)
        query=parse_qs(urlsplit(url).query)
        self.assertEqual(query["mode"],["artlist"])
        self.assertEqual(query["format"],["json"])
        self.assertEqual(query["startdatetime"],["20261019013000"])
        self.assertEqual(query["enddatetime"],["20261022013000"])
    def test_valid_global_article_from_non_korean_source(self):
        result=unpack(payload(),"SEMICON","semiconductors",NOW)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["source_country"],"Taiwan")
        self.assertEqual(result[0]["positive_catalyst_verified"],"NO")
        self.assertEqual(result[0]["korean_stock_impact_verified"],"NO")
    def test_korean_publisher_or_unattributed_origin_is_not_in_global_feed(self):
        self.assertEqual(unpack(payload(country="South Korea"),"SEMICON","test",NOW),[])
        self.assertEqual(unpack(payload(country=""),"SEMICON","test",NOW),[])
    def test_future_seen_or_old_news_never_enters(self):
        future=payload(seen="20261023T012000Z")
        stale=payload(seen="20261010T012000Z")
        self.assertEqual(unpack(future,"SEMICON","test",NOW),[])
        self.assertEqual(unpack(stale,"SEMICON","test",NOW),[])
    def test_unsafe_links_rejected(self):
        for url in ["javascript:alert(1)","http://example.com",
                    "https://example.com/stories)","https://127.0.0.1/path"]:
            self.assertEqual(safe_url(url),"")
    def test_mock_collection_never_authorizes_trades(self):
        rows,audit=collect(NOW,fetch=lambda _:payload(),limit=2,sleep_seconds=0)
        self.assertEqual(audit["queries_succeeded"],2)
        self.assertEqual(audit["requests_attempted"],2)
        self.assertEqual(len(rows),2)
        self.assertEqual(audit["decision"],"CASH")
        self.assertFalse(audit["trade_approved"])
        self.assertFalse(audit["sector_100_score_verified"])
        self.assertFalse(audit["sector_observations"]["SEMICON"]["early_watch"])
    def test_source_failure_is_explicit_not_zero_coverage_claim(self):
        def broken(_):
            raise RuntimeError("temporary outage")
        rows,audit=collect(NOW,fetch=broken,limit=2,sleep_seconds=0)
        self.assertEqual(rows,[])
        self.assertEqual(audit["queries_succeeded"],0)
        self.assertEqual(audit["query_states"]["SEMICON"]["status"],"FAILED")
        self.assertEqual(audit["decision"],"CASH")
    def test_seen_timestamp_is_utc(self):
        self.assertEqual(seen_time("20261022T012000Z"),NOW-timedelta(minutes=10))
        self.assertIsNone(seen_time("bad"))

if __name__=="__main__":
    unittest.main()
