import copy
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from krx_session_clock import nominal_last_completed_krx_session
from sector_pipeline_health_gate import REQUIRED, judge_collection

TODAY="2026-10-23"

def sample():
    return {"asof":TODAY,"overall_status":"EVIDENCE_PARTIAL_CATALYST_PIT_PENDING",
            "orders_enabled":False,
            "datasets":{k:{"status":"OK"} for k in REQUIRED}}

class HealthTests(unittest.TestCase):
    def test_post_midnight_completion_retains_source_started_session(self):
        v18_started=datetime.fromisoformat("2026-10-23T11:15:00+00:00")
        audit_finished=datetime.fromisoformat("2026-10-24T01:05:00+09:00")
        self.assertEqual(nominal_last_completed_krx_session(v18_started),"2026-10-23")
        self.assertEqual(nominal_last_completed_krx_session(audit_finished),"2026-10-23")
        weekend_end=datetime.fromisoformat("2026-10-25T02:05:00+09:00")
        self.assertEqual(nominal_last_completed_krx_session(weekend_end),"2026-10-23")
        self.assertTrue(judge_collection(sample(),"2026-10-23","success")["source_verified"])

    def test_health_yaml_tracks_real_v18_not_manual_only_dispatcher(self):
        # CI invokes from project root; user config cannot silently revive the
        # long-disabled manual-only dispatch check or ignore after-midnight runs.
        p=Path(__file__).resolve().parents[1]/".github/workflows/sector_pipeline_health.yml"
        src=p.read_text(encoding="utf-8")
        self.assertIn('workflows: ["Sector Evidence v18 (standalone)"]',src)
        self.assertIn("V18_TRIGGER_RUN_ID",src)
        self.assertIn("V18_TRIGGER_CREATED_AT",src)
        self.assertIn('target=nominal_last_completed_krx_session(',src)
        self.assertIn('result=judge_collection({},report["target_session"]',src)
        self.assertIn('report["checks"].get(k,{}).get("conclusion")=="success"',src)
        self.assertNotIn('"sector_evidence_v18_daily.yml":"sector_dispatch"',src)
        self.assertIn('report["sector_trade_ready"]=False',src)

    def test_complete_clean_collection_is_research_only(self):
        s=sample()
        s["datasets"]["price_ohlc_integrity"].update(checked=2500,invalid=0,invalid_pct=0.0)
        r=judge_collection(s,TODAY,"success")
        self.assertTrue(r["source_verified"])
        self.assertEqual(r["reason"],"PRICE_SOURCE_QUALITY_VERIFIED_RESEARCH_ONLY")
        self.assertFalse(r["trade_approved"])
        self.assertEqual(r["price_checked"],2500)

    def test_source_fail_closed_even_if_prices_requests_marked_ok(self):
        s=sample()
        s["overall_status"]="DATA_PENDING"
        s["datasets"]["price_ohlc_integrity"].update(
            status="DATA_PENDING",checked=2563,invalid=657,invalid_pct=25.63)
        r=judge_collection(s,TODAY,"failure")
        self.assertEqual(r["reason"],"SOURCE_OHLC_INTEGRITY_FAILED")
        self.assertTrue(r["source_diagnostic_available"])
        self.assertTrue(r["prices_api_ok"])
        self.assertFalse(r["price_integrity_ok"])
        self.assertEqual(r["price_invalid"],657)
        self.assertEqual(r["price_invalid_pct"],25.63)
        self.assertFalse(r["source_verified"])
        self.assertFalse(r["trade_approved"])

    def test_legacy_archive_without_source_quality_is_not_promoted(self):
        s=sample()
        del s["datasets"]["price_ohlc_integrity"]
        r=judge_collection(s,TODAY,"success")
        self.assertEqual(r["reason"],"SOURCE_OHLC_INTEGRITY_GATE_NOT_RECORDED")
        self.assertFalse(r["source_verified"])

    def test_failed_workflow_cannot_become_good_source_despite_all_ok(self):
        r=judge_collection(sample(),TODAY,"failure")
        self.assertEqual(r["reason"],"SOURCE_WORKFLOW_FAILED_EVEN_IF_ARTIFACT_EXISTS")
        self.assertFalse(r["source_verified"])
        self.assertTrue(r["source_diagnostic_available"])

    def test_yesterday_asof_is_not_same_day_sector_data(self):
        s=sample();s["asof"]="2026-10-22"
        r=judge_collection(s,TODAY,"success")
        self.assertEqual(r["reason"],"SOURCE_ASOF_MISMATCH")
        self.assertFalse(r["fresh_for_today"])
        self.assertFalse(r["source_verified"])

    def test_no_status_archive_is_missing_evidence_not_zero_good_sectors(self):
        r=judge_collection({},TODAY,"failure")
        self.assertEqual(r["status"],"NOT_VERIFIED")
        self.assertFalse(r["source_diagnostic_available"])
        self.assertFalse(r["source_verified"])
        self.assertFalse(r["trade_approved"])

    def test_unexpected_live_order_flag_disqualifies_source(self):
        s=sample();s["orders_enabled"]=True
        r=judge_collection(s,TODAY,"success")
        self.assertEqual(r["reason"],"SOURCE_ORDER_FLAG_NOT_READ_ONLY")
        self.assertFalse(r["source_verified"])

if __name__=="__main__":unittest.main()
