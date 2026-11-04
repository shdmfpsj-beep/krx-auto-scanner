import unittest
from c3_watch_touch_cohort_audit_v1 import summarize

class CohortTests(unittest.TestCase):
    def test_pending_not_counted_as_completed(self):
        event=dict(status="WATCH_TOUCH_ONLY",verified_fill=False,outcomes=[
            dict(horizon_sessions=5,complete=False,future_stop_touch_days=1,future_target_touch_days=1),
            dict(horizon_sessions=10,complete=True,future_stop_touch_days=1,future_target_touch_days=0)])
        r=summarize(dict(schema="C3_WATCH_TOUCH_FORWARD_OUTCOMES_V1",results=[dict(events=[event])]))
        self.assertEqual(r["horizons"]["5"]["pending"],1)
        self.assertEqual(r["horizons"]["5"]["stop_touch_events"],0)
        self.assertEqual(r["horizons"]["10"]["stop_touch_events"],1)
        self.assertEqual(r["verified_fills"],0)
    def test_verified_fill_rejected(self):
        with self.assertRaisesRegex(ValueError,"UNEXPECTED_VERIFIED_FILL"):
            summarize(dict(schema="C3_WATCH_TOUCH_FORWARD_OUTCOMES_V1",
                           results=[dict(events=[dict(status="WATCH_TOUCH_ONLY",verified_fill=True,outcomes=[])])]))
if __name__=="__main__":unittest.main()
