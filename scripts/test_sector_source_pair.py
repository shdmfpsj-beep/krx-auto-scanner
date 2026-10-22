import unittest,io,json,zipfile
from sector_source_pair import read_status,assess,REQUIRED_V18
D="2026-10-22"
def recovery(d=D):
    return dict(market_data_date=d,scan_complete=True,data_date_verified=True,
                coverage_ratio=.992,valid_ohlcv=2604,universe=2625)
def v18(d=D):
    return dict(asof=d,mode="backfill",overall_status="EVIDENCE_PARTIAL_CATALYST_PIT_PENDING",
                orders_enabled=False,datasets={k:{"status":"OK"} for k in REQUIRED_V18})
def zipped(items):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w") as f:
        for key,val in items.items():f.writestr(key,json.dumps(val))
    stream.seek(0)
    return zipfile.ZipFile(stream)
class Tests(unittest.TestCase):
    def test_date_matched_complete_sources_allow_research_only(self):
        x=assess(recovery(),v18(),D)
        self.assertTrue(x["ready"]);self.assertTrue(x["same_exchange_date"])
        self.assertFalse(x["trade_approved"])
        self.assertFalse(x["independent_price_equivalence_verified"])
    def test_stale_recovery_must_not_mix_with_v18(self):
        x=assess(recovery("2026-10-21"),v18(),D)
        self.assertFalse(x["ready"]);self.assertIn("RECOVERY_ASOF_MISMATCH",x["errors"])
    def test_stale_v18_must_not_mix_with_recovery(self):
        x=assess(recovery(),v18("2026-10-21"),D)
        self.assertFalse(x["ready"]);self.assertIn("V18_ASOF_MISMATCH",x["errors"])
    def test_source_without_ohlc_quality_cannot_promote(self):
        s=v18();del s["datasets"]["price_ohlc_integrity"]
        x=assess(recovery(),s,D)
        self.assertFalse(x["ready"])
        self.assertIn("V18_GATE_UNVERIFIED_PRICE_OHLC_INTEGRITY",x["errors"])
    def test_incomplete_scan_not_approved(self):
        s=recovery();s["scan_complete"]=False;s["coverage_ratio"]=.93
        x=assess(s,v18(),D);self.assertIn("RECOVERY_SCAN_INCOMPLETE",x["errors"])
        self.assertIn("RECOVERY_COVERAGE_UNVERIFIED",x["errors"])
    def test_baseline_or_order_enabled_v18_not_approved(self):
        s=v18();s["mode"]="baseline_only";s["orders_enabled"]=True
        x=assess(recovery(),s,D)
        self.assertIn("V18_NOT_BACKFILL",x["errors"]);self.assertIn("V18_NOT_READ_ONLY",x["errors"])
    def test_matching_archive_paths_support_v18_and_recovery(self):
        with zipped({"status.json":recovery()}) as z:self.assertEqual(read_status(z,"recovery")["market_data_date"],D)
        with zipped({"reports/sector_evidence_v18/diagnostics/collection_status.json":v18()}) as z:self.assertEqual(read_status(z,"v18")["asof"],D)
        with zipped({"sector_evidence_v18/diagnostics/collection_status.json":v18()}) as z:self.assertEqual(read_status(z,"v18")["asof"],D)
    def test_collision_or_weird_path_not_accepted(self):
        with zipped({"status.json":recovery(),"reports/status.json":recovery()}) as z:
            self.assertEqual(read_status(z,"recovery"),{})
        with zipped({"foo/status.json":recovery()}) as z:
            self.assertEqual(read_status(z,"recovery"),{})
if __name__=="__main__":unittest.main()
