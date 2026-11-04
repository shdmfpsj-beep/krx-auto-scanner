import unittest
from c3_top2_provisional_report_v1 import report

A=dict(plan_id="a",ticker="271560",name="오리온",
       selection_date="2026-10-30",registered_day="2026-10-31",
       source_close="114200",watch_low="110900",watch_high="113700",
       structure_stop="109600",target1="131500",target2="141700",
       expires_after_sessions="5")
B=dict(A,plan_id="b",ticker="026960",name="동서")

class ProvisionalReportTests(unittest.TestCase):
    def test_no_independent_feed(self):
        x=report([A,B],{},{"rows":0})
        self.assertFalse(x["independent_reference_available"])
        self.assertIn("SAME_PROVIDER",x["provenance"]["errors"])
    def test_no_trade_permission(self):
        x=report([A,B],{},{"rows":0})
        self.assertFalse(x["trade_approved"])
        self.assertFalse(x["orders_enabled"])
    def test_empty_data_no_completed_horizon(self):
        x=report([A,B],{},{"rows":0})
        self.assertFalse(x["coverage"]["271560"]["five_session_complete"])
    def test_manifest_preserved(self):
        x=report([A,B],{},{"rows":0,"failures":{"271560":"EMPTY"}})
        self.assertIn("271560",x["collector_manifest"]["failures"])

if __name__=="__main__":
    unittest.main()
