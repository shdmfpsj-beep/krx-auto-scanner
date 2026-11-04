import unittest
from c3_top2_research_readiness_v1 import build

A=dict(plan_id="a",ticker="271560",name="오리온",
       selection_date="2026-10-30",registered_day="2026-10-31",
       source_close="114200",watch_low="110900",watch_high="113700",
       structure_stop="109600",target1="131500",target2="141700",
       expires_after_sessions="5")
B=dict(A,plan_id="b",ticker="026960",name="동서")
M=dict(provider="provider-a",upstream="upstream-a",market_scope="REGULAR_ONLY",
       price_adjustment="ADJUSTED",timezone="Asia/Seoul",
       retrieved_at="2026-11-04T00:00:00+09:00")
N=dict(M,provider="provider-b",upstream="upstream-b")
def bar():
    return dict(low=110000,high=120000,open=116000,close=116000,volume=100)

class ReadinessTests(unittest.TestCase):
    def test_empty_data_not_ready(self):
        x=build([A,B],{},M,N)
        self.assertFalse(x["data_ready_for_certified_backtest"])
        self.assertEqual(x["coverage"]["271560"]["observed_sessions"],0)
    def test_five_sessions_only(self):
        bars={("271560",f"2026-11-{i:02d}"):bar() for i in range(2,7)}
        x=build([A,B],bars,M,N)
        self.assertTrue(x["coverage"]["271560"]["five_session_complete"])
        self.assertFalse(x["coverage"]["271560"]["ten_session_complete"])
    def test_provenance_error_exposed(self):
        x=build([A,B],{},M,M)
        self.assertIn("SAME_PROVIDER",x["provenance"]["errors"])
    def test_metadata_consistency_not_certification(self):
        x=build([A,B],{},M,N)
        self.assertTrue(x["provenance"]["metadata_claims_consistent"])
        self.assertFalse(x["independently_verified"])
    def test_all_outputs_preserve_two(self):
        x=build([A,B],{},M,N)
        self.assertEqual(len(x["entry_opportunities"]),2)
        self.assertEqual(len(x["missed_opportunities"]),2)
        self.assertEqual(len(x["forward_observations"]),2)
    def test_no_trade_permission(self):
        x=build([A,B],{},M,N)
        self.assertFalse(x["trade_approved"])
        self.assertFalse(x["orders_enabled"])
        self.assertFalse(x["strategy_profitability_verified"])
    def test_duplicate_plan_rejected(self):
        with self.assertRaises(ValueError):
            build([A,A],{},M,N)

if __name__=="__main__":
    unittest.main()
