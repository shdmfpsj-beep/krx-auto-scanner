import copy
import unittest
from sector_pipeline_health_gate import REQUIRED, judge_collection

TODAY="2026-10-23"

def sample():
    return {"asof":TODAY,"overall_status":"EVIDENCE_PARTIAL_CATALYST_PIT_PENDING",
            "orders_enabled":False,
            "datasets":{k:{"status":"OK"} for k in REQUIRED}}

class HealthTests(unittest.TestCase):
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
