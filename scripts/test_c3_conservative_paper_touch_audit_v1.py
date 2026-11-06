import unittest
from c3_conservative_paper_touch_audit_v1 import audit

PLAN=dict(ticker="271560",plan_id="test",registered_day="2026-11-01",
          watch_low="100",watch_high="105",structure_stop="95",expires_after_sessions="5")
class ConservativeTouchTests(unittest.TestCase):
    def test_same_day_touch_does_not_claim_fill(self):
        prices={("271560","2026-11-02"):dict(open=103,high=108,low=94,close=99)}
        r=audit(PLAN,prices)
        self.assertEqual(r["watch_touch_days"],1)
        self.assertEqual(r["same_bar_entry_stop_ambiguities"],1)
        self.assertEqual(r["verified_fills"],0)
        self.assertIsNone(r["strategy_return_pct"])
        self.assertFalse(r["trade_approved"])
    def test_no_touch(self):
        prices={("271560","2026-11-02"):dict(open=110,high=115,low=109,close=112)}
        r=audit(PLAN,prices)
        self.assertEqual(r["watch_touch_days"],0)
        self.assertEqual(r["same_bar_entry_stop_ambiguities"],0)
    def test_gap_below_stop_is_not_intraday_order_ambiguity(self):
        prices={("271560","2026-11-02"):dict(open=90,high=102,low=89,close=101)}
        r=audit(PLAN,prices)
        self.assertEqual(r["gap_below_stop_days"],1)
        self.assertEqual(r["same_bar_entry_stop_ambiguities"],0)
        self.assertEqual(r["observations"][0]["status"],"GAP_BELOW_STOP")
    def test_watch_touch_without_stop(self):
        prices={("271560","2026-11-02"):dict(open=108,high=109,low=102,close=104)}
        r=audit(PLAN,prices)
        self.assertEqual(r["watch_touch_without_stop_days"],1)
        self.assertEqual(r["verified_fills"],0)
    def test_nonfinite_plan_rejected(self):
        with self.assertRaisesRegex(ValueError,"INVALID_PLAN_GEOMETRY"):
            audit(dict(PLAN,watch_low="nan"),{})
    def test_bad_plan_fails(self):
        with self.assertRaisesRegex(ValueError,"INVALID_PLAN_GEOMETRY"):
            audit(dict(PLAN,structure_stop="101"),{})
if __name__=="__main__":unittest.main()
