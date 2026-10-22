"""Offline provenance regression tests, no network or trading API."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from krx_session_probe import capture_window,check_bars,new_snapshot,compare

KST=ZoneInfo("Asia/Seoul")
def dt(h,m,day=23):
    return datetime(2026,10,day,h,m,tzinfo=KST)
def dataset(close=102):
    return {f"{i:06d}":dict(Open=100,High=105,Low=98,Close=close,
              Volume=1000,TurnoverKRW=102000) for i in range(1,111)}

class SessionProbeTests(unittest.TestCase):
    def test_reg_window_is_exact_and_market_hours_are_not_assumed(self):
        self.assertEqual(capture_window("regular",dt(15,45)),"REGULAR_WINDOW")
        self.assertEqual(capture_window("regular",dt(16,1)),"MISSED_REGULAR_WINDOW")
        self.assertEqual(capture_window("after",dt(20,25)),"AFTER_CLOSE_WINDOW")
        self.assertEqual(capture_window("after",dt(19,59)),"MISSED_AFTER_CLOSE_WINDOW")

    def test_coherent_reference_vs_session_difference_is_diagnostic_only(self):
        first=dataset()
        later=dataset()
        later["000001"]["Close"]=110   # outside unchanged regular range
        x=new_snapshot("regular",dt(15,45),{"KOSPI":first})
        y=new_snapshot("after",dt(20,25),{"KOSPI":later})
        out=compare(x,y)
        self.assertEqual(out["status"],"PAIRED_SOURCE_OBSERVATIONS_READY")
        self.assertEqual(out["changed_close_count"],1)
        self.assertEqual(out["changed_close_unchanged_highlow_count"],1)
        self.assertEqual(out["matching_tickers"],110)
        self.assertEqual(out["late_quality"]["above_high"],1)
        self.assertFalse(out["price_correction_permitted"])
        self.assertFalse(out["authorizes_sector_rank"])
        self.assertEqual(out["decision"],"CASH")

    def test_late_regular_capture_not_accepted_as_independent_price(self):
        x=new_snapshot("regular",dt(16,15),{"KOSPI":dataset()})
        y=new_snapshot("after",dt(20,25),{"KOSPI":dataset()})
        out=compare(x,y)
        self.assertEqual(out["status"],"PAIR_NOT_VERIFIED")
        self.assertIn("REGULAR_CAPTURE_LATE_OR_MISSING",out["blockers"])

    def test_cross_session_dates_do_not_become_a_pair(self):
        x=new_snapshot("regular",dt(15,45,22),{"KOSPI":dataset()})
        y=new_snapshot("after",dt(20,25,23),{"KOSPI":dataset()})
        self.assertIn("ASOF_MISMATCH",compare(x,y)["blockers"])

    def test_missing_artifact_stays_missing_not_zero_differences(self):
        r=compare({},new_snapshot("after",dt(20,25),{"KOSPI":dataset()}))
        self.assertIn("MISSING_SNAPSHOT",r["blockers"])
        self.assertEqual(r["status"],"PAIR_NOT_VERIFIED")

    def test_low_high_price_mismatch_does_not_autocorrect(self):
        bars=dataset()
        bars["000001"]["Close"]=97
        result=check_bars(bars)
        self.assertEqual(result["below_low"],1)
        self.assertEqual(result["invalid"],1)
        self.assertEqual(bars["000001"]["Close"],97)

if __name__=="__main__":unittest.main()
