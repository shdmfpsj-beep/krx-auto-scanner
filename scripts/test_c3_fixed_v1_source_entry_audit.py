import tempfile,unittest,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_fixed_v1_source_entry_audit import Archive,entry_touch,consecutive_breakdowns,evaluate,sha

class FixedProtocolEvidenceTests(unittest.TestCase):
    def test_never_call_a_price_overlap_an_execution(self):
        bar={"open":105,"low":99,"high":108}
        self.assertEqual(entry_touch(bar,100,102,90,120),"RANGE_OVERLAP_NOT_FILL")
        self.assertEqual(entry_touch(bar,110,112,90,120),"PASS_NOT_TOUCHED")
    def test_same_day_stop_and_target_are_ambiguous(self):
        bar={"open":105,"low":89,"high":121}
        self.assertEqual(entry_touch(bar,100,102,90,120),"STOP_TARGET_ORDER_UNCERTAIN")
    def test_gap_below_stop_is_not_a_fill(self):
        self.assertEqual(entry_touch({"open":89,"low":88,"high":111},100,102,90,120),"GAP_BELOW_STOP")
        self.assertEqual(entry_touch(None,100,102,90,120),"TICKER_SESSION_MISSING")
    def test_discontinuity_distinguishes_market_gap(self):
        by={"000001":[{"date":"d1","close":100},{"date":"d2","close":50}],
            "000002":[{"date":"d1","close":100},{"date":"d3","close":200}]}
        f=consecutive_breakdowns(by,["d1","d2","d3"])
        self.assertEqual(sorted(x[3] for x in f),[1,2])
    def test_missing_archived_source_cannot_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaisesRegex(ValueError,"MISSING_V18_COLLECTION_PROVENANCE"):
                evaluate(root,root,{"events":[]})
    def test_checksum_is_content_sensitive(self):
        self.assertNotEqual(sha(b"2026-11-10"),sha(b"2026-11-09"))
    def test_archive_missing_path_is_not_zero(self):
        with tempfile.TemporaryDirectory() as d:
            a=Archive(d)
            self.assertIsNone(a.get("market/daily_flows/KOSPI/2026-11-10_foreign.csv"))

if __name__=="__main__":unittest.main()
