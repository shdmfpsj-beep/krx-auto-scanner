#!/usr/bin/env python3
"""No-network tests for global premarket mobile brief."""
import unittest
from datetime import datetime,timedelta,timezone
from global_preopen_brief import build,render

NOW=datetime(2026,10,22,0,5,tzinfo=timezone.utc)
STAMP=NOW.isoformat(timespec="seconds")
def status():
    return {"schema":"global_sector_discovery_v1","collected_at_utc":STAMP,
     "query_states":{"POWER":{"status":"OK"},"SEMICON":{"status":"OK"},
                     "GLOBAL_RATES":{"status":"OK"}}}
def article(title="Electric grid spending rises across Europe",domain="a.com",
            sector="POWER",seen=STAMP):
    return {"sector_id":sector,"title":title,"url":"https://"+domain+"/a",
     "publisher_domain":domain,"source_country":"Germany",
     "seen_at_utc":seen,"source":"GDELT_DOC_2_ARTLIST"}

class MorningTests(unittest.TestCase):
    def test_two_different_publishers_and_headlines_watch_only(self):
        two=[article(),article("New transformer demand contracts announced","b.com")]
        o=build(status(),two,NOW)
        self.assertEqual(o["global_early_watch"][0]["sector_id"],"POWER")
        self.assertFalse(o["domestic_sector_top3_verified"])
        self.assertFalse(o["trade_approved"])
        self.assertEqual(o["decision"],"CASH")
        self.assertIn("해외",render(o))
    def test_same_syndicated_headline_not_two_independent_facts(self):
        a=[article(domain="a.com"),article(domain="b.com")]
        self.assertEqual(build(status(),a,NOW)["global_early_watch"],[])
    def test_stale_feed_must_not_retain_candidate(self):
        state={**status(),"collected_at_utc":(NOW-timedelta(days=1)).isoformat()}
        a=[article(),article("Europe grid investment rose sharply","b.com")]
        out=build(state,a,NOW)
        self.assertEqual(out["global_early_watch"],[])
        self.assertEqual(out["source_status"],"MISSING_OR_STALE_GLOBAL_SOURCE")
    def test_failed_sector_source_no_false_watch(self):
        state=status()
        state["query_states"]["POWER"]={"status":"FAILED"}
        out=build(state,[article(),article("Different power grid orders","b.com")],NOW)
        self.assertEqual(out["global_early_watch"],[])
    def test_future_article_rejected(self):
        future=(NOW+timedelta(minutes=1)).isoformat()
        out=build(status(),[article(seen=future),article("Another story","b.com")],NOW)
        self.assertEqual(out["global_early_watch"],[])
    def test_macro_separate_from_korean_sector(self):
        out=build(status(),[article(sector="GLOBAL_RATES")],NOW)
        self.assertEqual(out["global_early_watch"],[])
        self.assertEqual(out["global_macro_observations"][0]["sector_id"],"GLOBAL_RATES")
    def test_missing_files_fallback(self):
        out=build({},[],NOW)
        self.assertEqual(out["source_status"],"MISSING_OR_STALE_GLOBAL_SOURCE")
        self.assertEqual(out["decision"],"CASH")
        self.assertFalse(out["orders_enabled"])
    def test_korean_article_blocked(self):
        a=article();a["source_country"]="South Korea"
        out=build(status(),[a,article("New contracts for transmission","b.com")],NOW)
        self.assertEqual(out["global_early_watch"],[])

if __name__=="__main__":
    unittest.main()
