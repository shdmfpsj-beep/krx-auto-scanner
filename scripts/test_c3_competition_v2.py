import copy
import math
import tempfile
import unittest
from datetime import date,timedelta

from c3_competition_v2 import (locate_entry,execute,observe,entry_cap,cluster_ci,
                               make_plan,signal_features,load_official)


def fixture(n=40):
    days=[(date(2026,5,1)+timedelta(days=i)).isoformat() for i in range(n)]
    bars=[dict(date=d,open=100.,high=102.,low=98.,close=100.,volume=1000.,
               tradable=True,ohlc_valid=True,segment=0,action_boundary=False,
               internal_gap=False,invalid_data=False) for d in days]
    plan=dict(ticker="000001",decision_date=days[0],low=98.,high=103.,stop=90.,atr=4.,
              kind="CONFIRMED_NEXT_OPEN",segment=0,breakout_support=None,resistance=110.)
    entry=dict(status="MODEL_ENTRY",date=days[1],price=100.,at_open=True,order_unknown=False)
    return days,bars,plan,entry


class CompetitionTests(unittest.TestCase):
    def test_confirmation_uses_next_open_not_signal_close(self):
        days,bars,p,e=fixture();bars[1]["open"]=101.
        self.assertEqual(locate_entry(p,bars,days)["price"],101.)
        self.assertNotEqual(locate_entry(p,bars,days)["date"],p["decision_date"])

    def test_next_open_budget_is_frozen(self):
        days,bars,p,e=fixture();bars[1]["open"]=110.
        self.assertEqual(locate_entry(p,bars,days)["status"],"NEXT_OPEN_OUTSIDE_FROZEN_BUDGET")

    def test_close_stop_waits_for_next_open_and_gap(self):
        days,bars,p,e=fixture();bars[1]["close"]=88.;bars[2]["open"]=80.
        out=execute(p,e,bars,days,5,slip=0)
        self.assertEqual(out["exit_date"],days[2]);self.assertEqual(out["exit_price"],80.)
        self.assertLess(out["net_pct"],-20.)

    def test_gap_intraday_stop_does_not_fill_at_stop(self):
        days,bars,p,e=fixture();bars[2]["open"]=80.;bars[2]["low"]=79.
        out=execute(p,e,bars,days,5,"STRUCTURE_INTRADAY",slip=0)
        self.assertEqual(out["exit_price"],80.);self.assertEqual(out["reason"],"GAP_STOP")

    def test_same_bar_has_two_scenarios_not_an_invented_order(self):
        days,bars,p,e=fixture();bars[2].update(low=85.,high=120.)
        a=execute(p,e,bars,days,5,"INTRADAY_TAKE10",slip=0)
        b=execute(p,e,bars,days,5,"INTRADAY_TAKE10",slip=0,optimistic=True)
        self.assertTrue(a["order_unknown"]);self.assertTrue(b["order_unknown"])
        self.assertLess(a["net_pct"],b["net_pct"])

    def test_raise_after_resistance_effective_next_session(self):
        days,bars,p,e=fixture();bars[1].update(close=112.,high=113.,low=98.)
        bars[2]["close"]=99.;bars[3]["open"]=95.
        out=execute(p,e,bars,days,5,"R1_RAISE_CLOSE",slip=0)
        self.assertEqual(out["stop_trace"][0][1],90.)
        self.assertEqual(out["stop_trace"][1][1],100.)
        self.assertEqual(out["exit_date"],days[3])

    def test_trailing_stop_never_moves_down(self):
        days,bars,p,e=fixture(60);p["decision_date"]=days[25];e["date"]=days[26]
        for b in bars[:28]:b["close"]=110.
        out=execute(p,e,bars,days,20,"MONOTONE_TRAIL_CLOSE")
        stops=[x[1] for x in out["stop_trace"]]
        self.assertEqual(stops,sorted(stops));self.assertGreater(stops[-1],stops[0])

    def test_unresolved_action_censors_without_rebasing_earlier_price(self):
        days,bars,p,e=fixture();original=copy.deepcopy(e);bars[3]["action_boundary"]=True
        self.assertEqual(execute(p,e,bars,days,5)["reason"],"UNRESOLVED_CORPORATE_ACTION")
        self.assertEqual(e,original)

    def test_action_after_actual_exit_does_not_delete_completed_loss(self):
        days,bars,p,e=fixture();bars[1]["close"]=85.;bars[4]["action_boundary"]=True
        out=execute(p,e,bars,days,5)
        self.assertTrue(out["complete"]);self.assertLess(out["net_pct"],0)

    def test_halt_does_not_execute_pending_close_stop(self):
        days,bars,p,e=fixture();bars[1]["close"]=85.;bars[2]["tradable"]=False;bars[3]["open"]=80.
        out=execute(p,e,bars,days,5)
        self.assertEqual(out["exit_date"],days[3]);self.assertEqual(out["exit_price"],80.)

    def test_invalid_data_is_not_treated_as_a_halt(self):
        days,bars,p,e=fixture();bars[2].update(invalid_data=True,tradable=False)
        self.assertEqual(execute(p,e,bars,days,5)["reason"],"INVALID_OFFICIAL_OHLC")

    def test_previously_touched_entry_survives_incomplete_watch_window(self):
        days,bars,p,e=fixture(3);p["kind"]="LIMIT_WATCH"
        self.assertEqual(locate_entry(p,bars,days)["status"],"MODEL_ENTRY")
        self.assertFalse(execute(p,e,bars,days,5)["complete"])

    def test_slippage_is_charged_both_sides(self):
        days,bars,p,e=fixture()
        a=execute(p,e,bars,days,5,slip=0);b=execute(p,e,bars,days,5,slip=.0025)
        self.assertLess(b["net_pct"],a["net_pct"])

    def test_known_open_resolves_same_day_target_stop_order(self):
        days,bars,p,e=fixture();bars[2].update(open=115.,low=85.,high=120.)
        out=execute(p,e,bars,days,5,"INTRADAY_TAKE10")
        self.assertEqual(out["reason"],"TAKE10");self.assertFalse(out["order_unknown"])

    def test_intraday_touch_preserves_uncertainty(self):
        days,bars,p,e=fixture();p["kind"]="LIMIT_WATCH";bars[1].update(open=105.,low=80.,high=110.)
        self.assertTrue(locate_entry(p,bars,days)["order_unknown"])

    def test_observation_does_not_assign_same_bar_order(self):
        days,bars,p,e=fixture();bars[2].update(low=80.,high=125.)
        out=observe(p,e,bars,days,5)
        self.assertTrue(out["target10_order_unknown"]);self.assertFalse(out["target10_before_stop"])

    def test_costed_entry_budget_and_unknown_resistance(self):
        cap=entry_cap(90,120)
        reward=120*.995*.999-cap*1.0015*1.001
        risk=cap*1.0015*1.001-90*.995*.999
        self.assertAlmostEqual(reward,risk);self.assertIsNone(entry_cap(90,None))

    def test_missing_security_bar_censors_instead_of_skipping_session(self):
        days,bars,p,e=fixture();del bars[2]
        self.assertEqual(execute(p,e,bars,days,5)["reason"],"SECURITY_GAP_OR_DISAPPEARANCE")

    def test_few_clusters_do_not_get_a_confidence_interval(self):
        self.assertIsNone(cluster_ci([]))
        self.assertIsNone(cluster_ci([("2026-05",1.)]*100))
        pairs=[(f"2026-{5+i%6:02}",float(i%5)) for i in range(60)]
        self.assertEqual(cluster_ci(pairs),cluster_ci(pairs))

    def test_future_proxy_and_bars_cannot_change_a_frozen_plan(self):
        days,bars,p,e=fixture(100)
        for i,b in enumerate(bars):
            close=100+i*.5+2*math.sin(i)
            b.update(open=close-.1,high=close+2,low=close-2,close=close)
        past=bars[:80];proxy={d:100+i*.1 for i,d in enumerate(days)}
        f=signal_features(past,{},proxy,days)
        self.assertIsNotNone(f)
        original=make_plan("TEST",past,f,"FRESH_SUPPORT_LIMIT")
        for b in bars[80:]:b.update(high=1000000,low=.01,close=.01)
        proxy.update({d:.001 for d in days[80:]})
        self.assertEqual(f,signal_features(past,{},proxy,days))
        self.assertEqual(original,make_plan("TEST",past,signal_features(past,{},proxy,days),"FRESH_SUPPORT_LIMIT"))

    def test_corrupt_input_is_rejected_before_research(self):
        import json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/"audit.json").write_text(json.dumps(dict(panel_sha256="wrong")))
            (p/"prices.gz").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError,"HASH_MISMATCH"):
                load_official(p/"prices.gz",p/"audit.json",p/"unused",p/"unused")

    def test_missed_resistance_does_not_keep_buy_watch_alive(self):
        days,bars,p,e=fixture();p["kind"]="LIMIT_WATCH"
        bars[1].update(open=108.,low=105.,high=115.,close=112.)
        self.assertEqual(locate_entry(p,bars,days)["status"],"MISSED_RESISTANCE_WITHOUT_ENTRY")

    def test_exact_decimal_target_touch_is_not_lost_to_float_rounding(self):
        days,bars,p,e=fixture();bars[2]["high"]=110.
        self.assertEqual(execute(p,e,bars,days,5,"INTRADAY_TAKE10")["reason"],"TAKE10")
        self.assertTrue(observe(p,e,bars,days,5)["target10"])


if __name__=="__main__":unittest.main()
