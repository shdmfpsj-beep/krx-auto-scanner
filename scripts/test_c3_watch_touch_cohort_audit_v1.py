import unittest
from c3_watch_touch_cohort_audit_v1 import summarize

class CohortTests(unittest.TestCase):
    def test_pending_not_counted_as_completed(self):
        event=dict(date="2026-11-02",status="WATCH_TOUCH_ONLY",verified_fill=False,outcomes=[
            dict(horizon_sessions=5,observed_future_sessions=2,complete=False,future_stop_touch_days=1,future_target_touch_days=1),
            dict(horizon_sessions=10,observed_future_sessions=10,complete=True,future_stop_touch_days=1,future_target_touch_days=0)])
        r=summarize(dict(schema="C3_WATCH_TOUCH_FORWARD_OUTCOMES_V1",results=[dict(plan_id="p1",events=[event])]))
        self.assertEqual(r["horizons"]["5"]["pending"],1)
        self.assertEqual(r["horizons"]["5"]["stop_touch_events"],0)
        self.assertEqual(r["horizons"]["10"]["stop_touch_events"],1)
        self.assertEqual(r["verified_fills"],0)
    def test_repeated_touch_dates_not_independent(self):
        events=[dict(date="2026-11-02",status="WATCH_TOUCH_ONLY",verified_fill=False,outcomes=[]),
                dict(date="2026-11-03",status="WATCH_TOUCH_ONLY",verified_fill=False,outcomes=[])]
        r=summarize(dict(schema="C3_WATCH_TOUCH_FORWARD_OUTCOMES_V1",results=[dict(plan_id="p1",events=events)]))
        self.assertEqual(r["plans_with_touch"],1)
        self.assertEqual(r["first_touch_status_counts"]["WATCH_TOUCH_ONLY"],1)
        self.assertEqual(r["clustered_plans"],1)
        self.assertEqual(r["clustered_events"],2)
        self.assertEqual(r["first_touch_horizons"],{})
        self.assertFalse(r["independent_event_sample_size_verified"])
    def test_duplicate_dates_rejected(self):
        e=dict(date="2026-11-02",status="WATCH_TOUCH_ONLY",verified_fill=False,outcomes=[])
        with self.assertRaisesRegex(ValueError,"DUPLICATE_TOUCH_DATE"):
            summarize(dict(schema="C3_WATCH_TOUCH_FORWARD_OUTCOMES_V1",results=[dict(plan_id="p1",events=[e,e])]))
    def test_first_touch_only_horizon_count(self):
        a=dict(horizon_sessions=5,observed_future_sessions=5,complete=True,future_stop_touch_days=0,future_target_touch_days=1)
        events=[dict(date="2026-11-02",status="WATCH_TOUCH_ONLY",verified_fill=False,outcomes=[a]),
                dict(date="2026-11-03",status="WATCH_TOUCH_ONLY",verified_fill=False,outcomes=[a])]
        r=summarize(dict(schema="C3_WATCH_TOUCH_FORWARD_OUTCOMES_V1",results=[dict(plan_id="p1",events=events)]))
        self.assertEqual(r["horizons"]["5"]["complete"],2)
        self.assertEqual(r["first_touch_horizons"]["5"]["complete"],1)
        self.assertEqual(r["first_touch_per_plan"][0]["forward_progress"][0]["remaining_sessions"],0)
    def test_first_touch_only_order_counts_and_ambiguity(self):
        h=lambda order: dict(horizon_sessions=5,observed_future_sessions=5,complete=True,
                             future_stop_touch_days=1,future_target_touch_days=1,
                             stop_target_touch_order=order)
        events=[dict(date="2026-11-02",status="SAME_BAR_STOP_AMBIGUOUS",
                     touch_day_execution_ambiguous=True,verified_fill=False,
                     outcomes=[h("STOP_FIRST")]),
                dict(date="2026-11-03",status="WATCH_TOUCH_ONLY",
                     touch_day_execution_ambiguous=False,verified_fill=False,
                     outcomes=[h("TARGET_FIRST")])]
        r=summarize(dict(schema="C3_WATCH_TOUCH_FORWARD_OUTCOMES_V1",
                         results=[dict(plan_id="p1",events=events)]))
        self.assertEqual(r["first_touch_order_counts"]["5"],{"STOP_FIRST":1})
        self.assertEqual(r["first_touch_same_day_collision_count"],1)
    def test_completed_first_touch_post_stop_rebound_counted_once(self):
        h=lambda rebound: dict(horizon_sessions=5,observed_future_sessions=5,
            complete=True,future_stop_touch_days=1,future_target_touch_days=0,
            first_future_stop_touch_date="2026-11-03",
            post_stop_rebound_observed=rebound,stop_target_touch_order="STOP_FIRST")
        events=[dict(date="2026-11-02",status="WATCH_TOUCH_ONLY",verified_fill=False,
                     outcomes=[h(True)]),
                dict(date="2026-11-03",status="WATCH_TOUCH_ONLY",verified_fill=False,
                     outcomes=[h(False)])]
        r=summarize(dict(schema="C3_WATCH_TOUCH_FORWARD_OUTCOMES_V1",
                         results=[dict(plan_id="p1",events=events)]))
        self.assertEqual(r["first_touch_rebound_counts"]["5"],
                         {"stop_then_rebound":1,"stop_no_rebound":0,"no_stop":0})
    def test_duplicate_plan_ids_rejected(self):
        e=dict(date="2026-11-02",status="WATCH_TOUCH_ONLY",
               verified_fill=False,outcomes=[])
        with self.assertRaisesRegex(ValueError,"DUPLICATE_PLAN_ID"):
            summarize(dict(schema="C3_WATCH_TOUCH_FORWARD_OUTCOMES_V1",
                           results=[dict(plan_id="p1",events=[e]),
                                    dict(plan_id="p1",events=[e])]))
    def test_verified_fill_rejected(self):
        with self.assertRaisesRegex(ValueError,"UNEXPECTED_VERIFIED_FILL"):
            summarize(dict(schema="C3_WATCH_TOUCH_FORWARD_OUTCOMES_V1",
                           results=[dict(plan_id="p1",events=[dict(date="2026-11-02",status="WATCH_TOUCH_ONLY",verified_fill=True,outcomes=[])])]))
if __name__=="__main__":unittest.main()
