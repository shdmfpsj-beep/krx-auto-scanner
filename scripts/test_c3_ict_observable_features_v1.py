import unittest
from c3_ict_observable_features_v1 import features
from c3_ict_sequence_research_v1 import detect
from c3_ict_cohort_compare_v1 import compare

def b(day,o,h,l,c):
    return dict(date=day,open=o,high=h,low=l,close=c)

class ICTFeatureTests(unittest.TestCase):
    def test_sweep_reclaim_uses_only_prior_bars(self):
        bars=[b(str(i),100,110,90,100) for i in range(10)]
        bars.append(b("10",91,105,89,95))
        x=features(bars)[-1]
        self.assertTrue(x["sweep_reclaim"])
        self.assertFalse(x["bullish_structure_break"])
        self.assertFalse(x["bullish_fvg"])
        # Future bar cannot change the historical signal.
        bars.append(b("11",100,200,50,150))
        self.assertEqual(features(bars)[10],x)

    def test_breakout_and_fvg(self):
        bars=[b(str(i),100,110,90,100) for i in range(10)]
        bars.append(b("10",112,121,111,119))
        x=features(bars)[-1]
        self.assertTrue(x["bullish_structure_break"])
        self.assertTrue(x["bullish_fvg"])
        self.assertFalse(x["sweep_reclaim"])

    def test_sequence_waits_for_break_then_later_retest(self):
        bars=[b(str(i),100,110,90,100) for i in range(10)]
        bars.append(b("10",94,105,89,95))
        self.assertEqual(detect(bars),[])
        bars.append(b("11",112,125,111,123))
        self.assertEqual(detect(bars)[0]["event"],"DISPLACED_STRUCTURE_BREAK")
        bars.append(b("12",115,117,110.5,114))
        self.assertEqual(detect(bars)[-1]["event"],"FVG_RETEST_WATCH")
        self.assertFalse(detect(bars)[-1]["trade_approved"])
    def test_retest_after_sweep_invalidation_is_rejected(self):
        bars=[b(str(i),100,110,90,100) for i in range(10)]
        bars.append(b("10",94,105,89,95))
        bars.append(b("11",112,125,111,123))
        bars.append(b("12",88,112,85,87))
        bars.append(b("13",110,115,110,112))
        events=detect(bars)
        self.assertEqual([e["event"] for e in events],["DISPLACED_STRUCTURE_BREAK"])
    def test_sweep_invalidated_before_break(self):
        bars=[b(str(i),100,110,90,100) for i in range(10)]
        bars.append(b("10",94,105,89,95))
        bars.append(b("11",87,100,85,86))
        bars.append(b("12",112,125,111,123))
        self.assertFalse(any(e["event"]=="DISPLACED_STRUCTURE_BREAK" for e in detect(bars)))
    def test_cohort_no_touch_no_approval(self):
        plan=dict(plan_id="ict_fixture",ticker="TEST",registered_day="2026-01-01",
                  watch_low=20,watch_high=21,structure_stop=19,target1=25,
                  expires_after_sessions=2)
        prices={("TEST","2026-01-02"):dict(open=30,high=31,low=29,close=30),
                ("TEST","2026-01-03"):dict(open=30,high=31,low=29,close=30)}
        report=compare([plan],prices)
        self.assertEqual(report["rows"],[])
        self.assertEqual(report["ict_filter_retention"]["total_plans"],1)
        self.assertEqual(report["ict_filter_retention"]["no_touch_plans"],1)
        self.assertFalse(report["trade_approved"])
        self.assertEqual(report["horizon_counts"]["5"]["prior_ict"]["completed_horizons"],0)
    def test_cohort_first_touch_only(self):
        plan=dict(plan_id="repeat_fixture",ticker="TEST",registered_day="2026-01-01",
                  watch_low=20,watch_high=21,structure_stop=19,target1=25,
                  expires_after_sessions=2)
        prices={("TEST","2026-01-02"):dict(open=22,high=22,low=20,close=21),
                ("TEST","2026-01-03"):dict(open=22,high=22,low=20,close=21)}
        report=compare([plan],prices)
        self.assertEqual(len(report["rows"]),1)
        self.assertEqual(report["observation_unit"],"FIRST_TOUCH_PER_PLAN")
        self.assertEqual(report["independent_plan_count"],1)
        self.assertEqual(report["ict_filter_retention"]["total_plans"],1)
        self.assertEqual(report["ict_filter_retention"]["no_touch_plans"],0)
        self.assertEqual(report["ict_filter_retention"]["eligible_first_touch_plans"],1)
        self.assertEqual(report["ict_filter_retention"]["retained_with_prior_ict"],0)
        self.assertEqual(report["ict_filter_retention"]["excluded_without_prior_ict"],1)
        self.assertIsNone(report["horizon_counts"]["5"]["no_prior_ict"]["mean_mfe_pct"])
    def test_missing_ticker_price_history_fails_closed(self):
        plan=dict(plan_id="missing_fixture",ticker="ABSENT",registered_day="2026-01-01",
                  watch_low=20,watch_high=21,structure_stop=19,target1=25,
                  expires_after_sessions=2)
        with self.assertRaisesRegex(ValueError,"MISSING_TICKER_PRICE_HISTORY"):
            compare([plan],{("OTHER","2026-01-02"):dict(open=30,high=31,low=29,close=30)})
    def test_stale_gap_window_rejected(self):
        bars=[b(str(i),100,110,90,100) for i in range(10)]
        bars.extend([b("10",94,105,89,95),b("11",112,125,111,123)])
        bars.extend(b(str(i),120,126,115,121) for i in range(12,16))
        bars.append(b("16",115,117,110.5,114))
        self.assertFalse(any(e["event"]=="FVG_RETEST_WATCH" for e in detect(bars,max_fvg_age=3)))
        self.assertTrue(any(e["event"]=="FVG_RETEST_WATCH" for e in detect(bars,max_fvg_age=5)))
    def test_ict_signal_invalidated_between_retest_and_touch(self):
        bars=[b(str(i).zfill(2),100,110,90,100) for i in range(10)]
        bars.extend([b("10",94,105,89,95),b("11",112,125,111,123),
                     b("12",115,117,110.5,114),b("13",86,90,84,85),
                     b("14",100,110,96,100)])
        plan=dict(plan_id="invalidate_fixture",ticker="TEST",registered_day="13",
                  watch_low=96,watch_high=97,structure_stop=80,target1=130,
                  expires_after_sessions=2)
        prices={("TEST",x["date"]):{k:x[k] for k in ("open","high","low","close")}
                for x in bars}
        report=compare([plan],prices)
        self.assertEqual(len(report["rows"]),1)
        self.assertFalse(report["rows"][0]["ict_prior_signal"])
    def test_warmup_and_lookback(self):
        bars=[b(str(i),100,110,90,100) for i in range(10)]
        self.assertFalse(any(x["sweep_reclaim"] for x in features(bars)))
        with self.assertRaises(ValueError):
            features(bars,lookback=2)

if __name__=="__main__":
    unittest.main()
