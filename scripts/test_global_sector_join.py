#!/usr/bin/env python3
"""Offline global early-watch joins: no stock buys or fake news timestamps."""
import unittest
from datetime import datetime,timedelta,timezone
from global_sector_join import combine,render,status_gate
NOW=datetime(2026,10,22,13,30,tzinfo=timezone.utc)
BASE=dict(sector_top3=[dict(sector_id="SEMICON",name="반도체")],
          decision="CASH",trade_approved=False)
AUDIT=dict(schema="global_sector_discovery_v1",
           collected_at_utc=NOW.isoformat(timespec="seconds"),
           queries_succeeded=16,requests_attempted=20)
def article(sector="SEMICON",domain="example.com",country="Taiwan",seen=None):
    return dict(sector_id=sector,title="Chip factory expansion in Taiwan",
       url="https://"+domain+"/story",publisher_domain=domain,
       seen_at_utc=seen or NOW.isoformat(timespec="seconds"),
       source_country=country,language="Chinese",source="GDELT_DOC_2_ARTLIST")

class GlobalJoinTests(unittest.TestCase):
    def test_global_top3_sources_do_not_change_cash_or_ranking(self):
        report=combine(BASE,AUDIT,[article()],NOW)
        self.assertEqual(report["decision"],"CASH")
        self.assertFalse(report["trade_approved"])
        self.assertFalse(report["global_news_sector_rank_adjusted"])
        self.assertEqual(report["global_positive_catalysts_verified"],0)
        self.assertEqual(len(report["sector_top3"][0]["global_news_observations"]),1)
        self.assertIn("해외",render(report,"# sector report"))
    def test_two_independent_publishers_create_research_watch_only(self):
        second=article(sector="POWER",domain="two.com")
        second["title"]="European grid operators announce new transformer backlog"
        a=[article(sector="POWER",domain="one.com"),second]
        out=combine(BASE,AUDIT,a,NOW)
        self.assertEqual(out["global_early_watch_outside_top3"][0]["sector_id"],"POWER")
        self.assertEqual(out["global_early_watch_outside_top3"][0]["trade_approval"],"NO")
        self.assertEqual(out["decision"],"CASH")
    def test_two_publishers_same_syndicated_title_do_not_create_early_watch(self):
        a=[article(sector="POWER",domain="one.com"),
           article(sector="POWER",domain="two.com")]
        out=combine(BASE,AUDIT,a,NOW)
        self.assertEqual(out["global_early_watch_outside_top3"],[])
        self.assertEqual(out["decision"],"CASH")

    def test_duplicate_same_publisher_does_not_imply_confirmation(self):
        a=[article(sector="POWER"),article(sector="POWER")]
        out=combine(BASE,AUDIT,a,NOW)
        self.assertEqual(out["global_early_watch_outside_top3"],[])
    def test_future_and_wrong_source_are_dropped(self):
        a=article(seen=(NOW+timedelta(minutes=3)).isoformat())
        b=article();b["source"]="UNTRUSTED"
        out=combine(BASE,AUDIT,[a,b],NOW)
        self.assertEqual(out["sector_top3"][0]["global_news_observations"],[])
    def test_stale_global_data_do_not_decorate_today_report(self):
        status={**AUDIT,"collected_at_utc":(NOW-timedelta(days=1)).isoformat()}
        out=combine(BASE,status,[article()],NOW)
        self.assertEqual(out["foreign_news_source_status"],"STALE_GLOBAL_DISCOVERY")
        self.assertEqual(out["sector_top3"][0]["global_news_observations"],[])
    def test_data_failure_is_not_silently_treated_as_no_news(self):
        out=combine(BASE,{},[article()],NOW)
        self.assertEqual(out["foreign_news_source_status"],"NO_GLOBAL_SOURCE")
        self.assertEqual(out["decision"],"CASH")
    def test_insufficient_query_coverage_blocks_headlines(self):
        out=combine(BASE,{**AUDIT,"queries_succeeded":1},[article()],NOW)
        self.assertEqual(out["foreign_news_source_status"],"INSUFFICIENT_GLOBAL_DISCOVERY")
        self.assertEqual(out["sector_top3"][0]["global_news_observations"],[])
    def test_korean_origin_not_in_foreign_stream(self):
        out=combine(BASE,AUDIT,[article(country="South Korea")],NOW)
        self.assertEqual(out["sector_top3"][0]["global_news_observations"],[])

if __name__=="__main__":
    unittest.main()
