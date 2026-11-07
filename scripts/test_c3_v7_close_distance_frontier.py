"""V7 frozen-close limit and geometry invariants; fully synthetic prices only."""
import copy
import unittest

from c3_v7_close_distance_frontier import (
    POLICIES, prior_distance_diagnostics, make_prior_close_plans,
    execute_frozen, RISK_STOP_MAX_PCT, MIN_R1_RR, MIN_NET_R1_REWARD_PCT
)
from c3_entry_v2_preopen import entry as v2_entry

P=dict(ticker="000001",decision_date="2026-11-05",low=98.,high=100.,
       stop=96.,reference_close=110.,atr=20.,resistance=150.,resistance2=170.)
PRIOR=dict(ticker="000001",decision_date="2026-11-05")
def bar(o=105,h=115,l=102,c=109):
    return dict(date="2026-11-06",open=o,high=h,low=l,close=c,volume=100000,
                tradable=True,invalid_data=False,action_boundary=False)

class V7Tests(unittest.TestCase):
    def test_fixed_hypothesis_not_optimized_for_hindsight(self):
        self.assertEqual(POLICIES,("V2_HIGH","V7_CLOSE_UPLIFT_UNGUARDED",
                      "V7_CLOSE_R1_GUARDED"))
        self.assertEqual((RISK_STOP_MAX_PCT,MIN_R1_RR,
                          MIN_NET_R1_REWARD_PCT),(12.,1.,1.))

    def test_preclose_high_distance_is_positive(self):
        d=prior_distance_diagnostics(P,PRIOR)
        self.assertEqual(d["high_to_prior_close_gap_pct"],10.)
        self.assertEqual(d["high_to_prior_close_gap_atr"],.5)
        self.assertEqual(d["gap_bucket"],"ABOVE_HIGH_5_TO_10")

    def test_rounding_bins_dont_depend_on_next_bar(self):
        for close,tag in [(99,"CLOSE_AT_OR_BELOW_HIGH"),
                          (102,"ABOVE_HIGH_0_TO_2"),
                          (105,"ABOVE_HIGH_2_TO_5"),
                          (109,"ABOVE_HIGH_5_TO_10"),
                          (115,"ABOVE_HIGH_OVER_10")]:
            d=prior_distance_diagnostics(dict(P,reference_close=close),PRIOR)
            self.assertEqual(d["gap_bucket"],tag)

    def test_guarded_cap_is_constrained_before_open(self):
        d,plans=make_prior_close_plans(P,PRIOR)
        self.assertEqual(plans["V2_HIGH"]["limit"],100.)
        self.assertEqual(plans["V7_CLOSE_UPLIFT_UNGUARDED"]["limit"],110.)
        guarded=plans["V7_CLOSE_R1_GUARDED"]
        self.assertTrue(guarded["uplifted"])
        self.assertLessEqual(guarded["limit"],110.)
        g=guarded["net_r1_geometry_at_raised_cap"]
        self.assertLessEqual(g["raw_stop_distance_pct"],12.+1e-6)
        self.assertGreaterEqual(g["net_first_resistance_rr"],1.-1e-6)
        self.assertGreaterEqual(g["net_first_resistance_reward_pct"],1.-1e-6)

    def test_low_r1_no_extraneous_risky_raise(self):
        _,plans=make_prior_close_plans(dict(P,resistance=104.),PRIOR)
        g=plans["V7_CLOSE_R1_GUARDED"]
        self.assertFalse(g["uplifted"])
        self.assertEqual(g["limit"],P["high"])

    def test_missing_r1_remains_original_high_only(self):
        _,plans=make_prior_close_plans(dict(P,resistance=None),PRIOR)
        self.assertFalse(plans["V7_CLOSE_R1_GUARDED"]["uplifted"])
        self.assertEqual(plans["V7_CLOSE_R1_GUARDED"]["limit"],100.)

    def test_prior_close_not_above_band_keeps_exact_v2(self):
        q=dict(P,reference_close=99.)
        _,p=make_prior_close_plans(q,PRIOR)
        self.assertFalse(p[POLICIES[1]]["uplifted"])
        self.assertEqual(p[POLICIES[1]]["limit"],100.)
        self.assertEqual(p[POLICIES[2]]["limit"],100.)

    def test_when_half_atr_only_two_points_up_refuse_further(self):
        q=dict(P,reference_close=130.,atr=4.)
        _,p=make_prior_close_plans(q,PRIOR)
        self.assertEqual(p[POLICIES[1]]["limit"],102.)

    def test_frozen_original_v2_replay_exact(self):
        _,plans=make_prior_close_plans(P,PRIOR)
        self.assertEqual(execute_frozen(P,plans["V2_HIGH"],bar()),
                         dict(v2_entry(P,bar(),"RESTING_ONE"),
                              v7_policy="V2_HIGH",preclose_limit=100.,
                              model_only=True))

    def test_new_higher_bid_has_distinct_model_fill_not_broker_proof(self):
        _,plans=make_prior_close_plans(P,PRIOR)
        old=execute_frozen(P,plans["V2_HIGH"],bar(o=105,l=102))
        new=execute_frozen(P,plans[POLICIES[1]],bar(o=105,l=102))
        self.assertFalse(old["filled"])
        self.assertTrue(new["filled"])
        self.assertEqual(new["price"],105.)
        self.assertFalse(new["actual_broker_fill_verified"])

    def test_gap_below_stop_mechanically_fills_without_retro_veto(self):
        _,plans=make_prior_close_plans(P,PRIOR)
        x=execute_frozen(P,plans[POLICIES[2]],bar(o=89,l=80,c=100))
        self.assertTrue(x["filled"])
        self.assertTrue(x["open_at_or_below_stop"])

    def test_invalid_identity_fails_closed(self):
        d,p=make_prior_close_plans(P,dict(PRIOR,ticker="WRONG"))
        self.assertFalse(d["eligible"])
        self.assertFalse(p["V2_HIGH"]["submitted"])
        self.assertFalse(p[POLICIES[2]]["submitted"])

    def test_no_original_plan_remains_no_order(self):
        d,p=make_prior_close_plans(None,PRIOR)
        self.assertFalse(d["eligible"])
        self.assertTrue(all(not z["submitted"] for z in p.values()))

    def test_source_plans_immutable(self):
        original=copy.deepcopy(P);prior=copy.deepcopy(PRIOR)
        make_prior_close_plans(P,PRIOR)
        self.assertEqual(P,original);self.assertEqual(PRIOR,prior)

    def test_stress_variant_must_not_be_misrepresented_as_safe(self):
        _,plans=make_prior_close_plans(dict(P,stop=97.),
                                      PRIOR)
        self.assertTrue(plans[POLICIES[1]]["uplifted"])
        self.assertNotIn("net_r1_geometry_at_raised_cap",plans[POLICIES[1]])

if __name__=="__main__":unittest.main(verbosity=2)
