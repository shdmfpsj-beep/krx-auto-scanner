"""Post-merge C3 gate against true archived Nov6 report, not a hand-written fixture.

The exact Git ref was read from the PR46 integrity audit and is frozen. Code
under test is the main-derived v19 readiness gate; no secret, no orders, no
updating the research ledger or Telegram.
"""
import json
import unittest
from pathlib import Path
from c3_readiness_gate_v19 import assess,parsed

ROOT=Path("state/reports/c3_forward_v8")

class OriginalEncryptedSourceSummaryReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.latest=json.loads((ROOT/"latest.json").read_text())
        cls.summary=json.loads((ROOT/"mobile/summary.json").read_text())

    def test_the_actual_archived_report_really_has_later_reload_than_analysis(self):
        self.assertEqual(self.latest["source_price_asof"],"2026-11-06")
        self.assertEqual(self.latest["source_run_id"],"42302086749")
        self.assertLess(parsed(self.latest["analysis_completed_at"]),
                        parsed(self.latest["source_received_at"]))
        self.assertLess(parsed(self.latest["source_received_at"]),
                        parsed(self.latest["generated_at"]))
        self.assertEqual(self.latest["performance"]["registered_signals"],4)
        self.assertEqual(self.latest["new_registered_signals"],0)

    def test_nov6_at_2230_cannot_time_travel_to_later_report(self):
        r=assess(self.latest,self.summary,parsed("2026-11-06T22:30:00+09:00"))
        self.assertFalse(r["registered_top2_final_at_check_time"])
        self.assertEqual(r["status"],"RESEARCH_NOT_YET_AVAILABLE_AT_CHECK_TIME")
        self.assertEqual(r["known_top2"],[])
        self.assertFalse(r["trade_approved"])

    def test_next_monday_0830_source_is_final_but_not_buy_approved(self):
        r=assess(self.latest,self.summary,parsed("2026-11-09T08:30:00+09:00"))
        self.assertEqual(r["expected_source_day"],"2026-11-06")
        self.assertEqual(r["status"],"FINAL_RESEARCH_TOP2_UNCERTIFIED_SESSION")
        self.assertEqual([x["ticker"] for x in r["known_top2"]],["028050","030530"])
        self.assertFalse(r["source_attestation"]["regular_only_independently_certified"])
        self.assertEqual(r["decision"],"CASH")

    def test_no_weekend_new_signal_from_fridays_report(self):
        r=assess(self.latest,self.summary,parsed("2026-11-07T14:57:00+09:00"))
        self.assertEqual(r["status"],"NO_NOMINAL_WEEKDAY_SESSION")
        self.assertFalse(r["registered_top2_final_at_check_time"])

    def test_duplicated_same_source_report_cannot_claim_new_registration(self):
        r=assess(self.latest,self.summary,parsed("2026-11-09T08:30:00+09:00"))
        self.assertEqual(r["original_report_registered_signal_count"],4)
        self.assertEqual(r["new_registered_signals_since_latest_report"],0)
        self.assertFalse(r["send_telegram"])

if __name__=="__main__":
    unittest.main(verbosity=2)
