import unittest
from c3_watch_touch_cohort_audit_v1 import summarize

class CohortTests(unittest.TestCase):
    def test_pending_not_counted_as_completed(self):
        event=dict(date="2026-11-02",status="WATCH_TOUCH_ONLY",verified_fill=False,outcomes=[
            dict(horizon_sessions=5,complete=False,future_stop_touch_days=1,future_target_touch_days=1),
            dict(horizon_sessions=10,complete=True,future_stop_touch_days=1,future_target_touch_days=0)])
        r=summarize(dict(schema="C3_WATCH_TOUCH_FORWARD_OUTCOMES_V1",results=[dict(events=[event])]))
        self.assertEqual(r["horizons"]["5"]["pending"],1)
        self.assertEqual(r["horizons"]["5"]["stop_touch_events"],0)
        self.assertEqual(r["horizons"]["10"]["stop_touch_events"],1)
        self.assertEqual(r["verified_fills"],0)
    def test_repeated_touch_dates_not_independent(self):
        events=[dict(date="2026-11-02",status="WATCH_TOUCH_ONLY",verified_fill=False,outcomes=[]),
                dict(date="2026-11-03",status="WATCH_TOUCH_ONLY",verified_fill=False,outcomes=[])]
        r=summarize(dict(schema="C3_WATCH_TOUCH_FORWARD_OUTCOMES_V1",results=[dict(events=events)]))
        self.assertEqual(r["plans_with_touch"],1)
        self.assertEqual(r["first_touch_status_counts"]["WATCH_TOUCH_ONLY"],1)
        self.assertEqual(r["clustered_plans"],1)
        self.assertEqual(r["clustered_events"],2)
        self.assertFalse(r["independent_event_sample_size_verified"])
    def test_duplicate_dates_rejected(self):
        e=dict(date="2026-11-02",status="WATCH_TOUCH_ONLY",verified_fill=False,outcomes=[])
        with self.assertRaisesRegex(ValueError,"DUPLICATE_TOUCH_DATE"):
            summarize(dict(schema="C3_WATCH_TOUCH_FORWARD_OUTCOMES_V1",results=[dict(events=[e,e])]))
    def test_verified_fill_rejected(self):
        with self.assertRaisesRegex(ValueError,"UNEXPECTED_VERIFIED_FILL"):
            summarize(dict(schema="C3_WATCH_TOUCH_FORWARD_OUTCOMES_V1",
                           results=[dict(events=[dict(date="2026-11-02",status="WATCH_TOUCH_ONLY",verified_fill=True,outcomes=[])])]))
if __name__=="__main__":unittest.main()
