import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from krx_regular_after_layers import window,capture,split,REGULAR,AFTER

KST=ZoneInfo("Asia/Seoul")
def at(h,m,day=23):return datetime(2026,10,day,h,m,tzinfo=KST)
def data(close=100):
    return {f"{i:06d}":{"Open":98,"High":104,"Low":96,"Close":close,
         "Volume":1000,"TurnoverKRW":100000} for i in range(1,121)}
class TestRegularAfterIsolation(unittest.TestCase):
    def test_narrow_capture_after_1530_before_offhours(self):
        self.assertEqual(window("regular",at(15,35)),"POST_REGULAR_PRE_OFFHOURS")
        self.assertEqual(window("regular",at(15,44)),"MISSED_REGULAR_ISOLATION_WINDOW")
        self.assertEqual(window("regular",at(16,10)),"MISSED_REGULAR_ISOLATION_WINDOW")
        self.assertEqual(window("after",at(20,25)),"AFTERMARKET_FINISHED")
        self.assertEqual(window("after",at(18,30)),"MISSED_AFTERMARKET_FINAL_WINDOW")
    def test_early_pykrx_time_stamp_is_not_proof_of_regular_only_ohlcv(self):
        snap=capture("regular",at(15,35),{"KOSPI":data()})
        self.assertEqual(snap["trade_session"],REGULAR)
        self.assertFalse(snap["regular_strategy_eligible"])
        self.assertFalse(snap["provider_session_scope_verified"])
        self.assertIn("PROVIDER_REGULAR_SESSION_SCOPE_NOT_ATTESTED",snap["separation_blockers"])
        self.assertFalse(snap["trade_approved"])
    def test_late_capture_must_not_be_accepted_as_regular(self):
        snap=capture("regular",at(15,45),{"KOSPI":data()})
        self.assertIn("CAPTURE_WINDOW_NOT_VERIFIED",snap["separation_blockers"])
    def test_regular_query_starts_in_time_but_finishes_after_1540(self):
        snap=capture("regular",at(15,35),{"KOSPI":data()},
                     completed_at=at(15,42))
        self.assertEqual(snap["capture_window"],"POST_REGULAR_PRE_OFFHOURS")
        self.assertIn("CAPTURE_FINISHED_OUTSIDE_SESSION_WINDOW",snap["separation_blockers"])
        self.assertFalse(snap["regular_strategy_eligible"])

    def test_after_snapshot_cannot_overwrite_regular_stops(self):
        early=capture("regular",at(15,35),{"KOSPI":data()})
        d=data()
        d["000001"]["Close"]=106
        late=capture("after",at(20,25),{"KOSPI":d})
        out=split(early,late)
        self.assertEqual(early["stocks"]["000001"]["Close"],100)
        self.assertEqual(late["stocks"]["000001"]["Close"],106)
        self.assertEqual(out["comparison"]["changed_snapshot_close_count"],1)
        self.assertIn("PROVIDER_REGULAR_SESSION_SCOPE_NOT_ATTESTED",out["blockers"])
        self.assertFalse(out["source_regular_strategy_ready"])
        self.assertEqual(out["final_buy_approvals"],0)
    def test_compare_anomalous_but_separate_time_stamped_sources(self):
        early=capture("regular",at(15,35),{"KOSPI":data()})
        bad=data()
        bad["000001"]["Close"]=110
        late=capture("after",at(20,25),{"KOSPI":bad})
        out=split(early,late)
        self.assertTrue(out["comparison"]["eligible_for_observational_comparison"])
        self.assertEqual(out["comparison"]["changed_snapshot_close_count"],1)
        self.assertEqual(out["comparison"]["invalid_after_price_vs_high_low_count"],1)
        self.assertFalse(out["source_regular_strategy_ready"])
        self.assertFalse(out["regular_ohlcv_certified"])

    def test_late_completed_aftermarket_snapshot_does_not_form_a_pair(self):
        early=capture("regular",at(15,35),{"KOSPI":data()})
        late=capture("after",at(20,25),{"KOSPI":data()},
                     completed_at=at(22,1))
        out=split(early,late)
        self.assertIn("AFTER_CAPTURE_FINISHED_OUTSIDE_WINDOW",out["blockers"])
        self.assertFalse(out["comparison"]["eligible_for_observational_comparison"])

    def test_cannot_relabel_unscoped_api_as_certified(self):
        with self.assertRaisesRegex(ValueError,"UNSCOPED_SOURCE"):
            capture("regular",at(15,35),{"KOSPI":data()},True)
    def test_mismatched_dates_cannot_form_session_pair(self):
        a=capture("regular",at(15,35,22),{"KOSPI":data()})
        b=capture("after",at(20,25,23),{"KOSPI":data()})
        result=split(a,b)
        self.assertIn("DATE_PAIR_MISMATCH",result["blockers"])
        self.assertEqual(result["decision"],"CASH")
    def test_no_regular_snapshot_is_not_zero_stock_candidates(self):
        b=capture("after",at(20,25),{"KOSPI":data()})
        out=split({},b)
        self.assertIn("REGULAR_SNAPSHOT_MISSING",out["blockers"])
        self.assertFalse(out["source_regular_strategy_ready"])
if __name__=="__main__":unittest.main()
