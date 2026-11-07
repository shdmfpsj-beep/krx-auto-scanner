"""V4 pre-open risk/reward cap and per-trade adverse gap tests; NO broker calls."""
import unittest
from c3_entry_v4_geometry import (
    VARIANTS,PREDEFINED,executable_cap,model_entry,score_geometry,
    actual_net_r1_rr,BUY_FACTOR,SELL_FACTOR)
from c3_entry_v2_preopen import entry

P=dict(ticker="TEST",decision_date="2026-11-05",method="PULLBACK",
       segment=0,low=90,high=110,stop=86,atr=10,
       reference_close=107,resistance=121,resistance2=140,
       rank_turnover=4_000_000_000,rs20=22)
def B(o=100,h=112,l=90,c=103):
    return dict(date="2026-11-06",open=o,high=h,low=l,close=c,
                volume=500_000,tradable=True,invalid_data=False,
                action_boundary=False,segment=0)

class FrozenEntryV4Tests(unittest.TestCase):
    def test_frozen_variants_stable_order(self):
        self.assertEqual(VARIANTS,("V2_HIGH","V4_BALANCED","V4_DEFENSIVE","V4_MIDPOINT"))

    def test_v2_high_exact_identity_and_fill(self):
        x=executable_cap(P,"V2_HIGH")
        self.assertEqual(x["limit"],110)
        a,_=model_entry(P,B(o=109),"V2_HIGH")
        b=entry(P,B(o=109),"RESTING_ONE")
        self.assertEqual(a["price"],b["price"])
        self.assertEqual(a["status"],b["status"])

    def test_balanced_cap_obeys_risk_rr_cost(self):
        x=executable_cap(P,"V4_BALANCED")
        self.assertEqual(x["status"],"PLAN_READY")
        self.assertLess(x["limit"],P["high"])
        self.assertLessEqual(x["raw_stop_distance_pct"],12)
        self.assertGreaterEqual(x["net_first_resistance_rr"],1)
        self.assertGreaterEqual(x["net_first_resistance_reward_pct"],1)
        self.assertLessEqual(x["limit"],P["high"])

    def test_defensive_stricter_cap_than_balanced_or_no_trade(self):
        a=executable_cap(P,"V4_BALANCED")
        d=executable_cap(P,"V4_DEFENSIVE")
        self.assertEqual(a["status"],"PLAN_READY")
        if d["status"]=="PLAN_READY":
            self.assertLessEqual(d["limit"],a["limit"])
            self.assertLessEqual(d["raw_stop_distance_pct"],8)
            self.assertGreaterEqual(d["net_first_resistance_rr"],1.5)
        else:
            self.assertIn(d["status"],("CAP_TOO_FAR_BELOW_FROZEN_BAND",
                         "CAP_BELOW_STOP","QUOTE_OR_COST_CONSTRAINT_FAILED"))

    def test_high_price_near_r1_not_eligible_without_lower_entry(self):
        p=dict(P,resistance=87)
        d=executable_cap(p,"V4_DEFENSIVE")
        self.assertNotEqual(d["status"],"PLAN_READY")

    def test_unknown_r1_does_not_pretend_reward_budget(self):
        p=dict(P,resistance=None)
        self.assertEqual(executable_cap(p,"V4_BALANCED")["status"],"UNKNOWN_OR_INVALID_R1")
        self.assertEqual(executable_cap(p,"V4_DEFENSIVE")["status"],"UNKNOWN_OR_INVALID_R1")
        self.assertEqual(executable_cap(p,"V2_HIGH")["status"],"PLAN_READY")

    def test_budget_calculated_before_next_bar_and_does_not_change_on_gap(self):
        a,_=model_entry(P,B(o=100),"V4_BALANCED")
        b,_=model_entry(P,B(o=80,h=112,l=70,c=100),"V4_BALANCED")
        self.assertEqual(a["preopen_frozen_limit"],b["preopen_frozen_limit"])
        self.assertTrue(b["filled"])
        self.assertTrue(b["open_at_or_below_stop"])
        self.assertEqual(b["status"],"FILLED_BELOW_STOP_RISK")
        self.assertFalse(b["actual_broker_fill_verified"])

    def test_above_limit_is_no_fill_without_looking_at_close(self):
        plan=executable_cap(P,"V4_BALANCED")
        x,_=model_entry(P,B(o=120,h=130,l=plan["limit"]-1,c=121),"V4_BALANCED")
        self.assertTrue(x["filled"])
        self.assertEqual(x["price"],plan["limit"])
        y,_=model_entry(P,B(o=120,h=130,l=plan["limit"],c=121),"V4_BALANCED")
        self.assertFalse(y["filled"])
        self.assertEqual(y["status"],"DAY_EXPIRED_NO_FILL")

    def test_original_band_not_mutated(self):
        old=dict(P)
        for v in VARIANTS:model_entry(P,B(o=91),"{}".format(v))
        self.assertEqual(P,old)

    def test_zero_cost_or_bad_geometry_rejected(self):
        bad=dict(P,stop=P["low"])
        self.assertEqual(executable_cap(bad,"V4_DEFENSIVE")["status"],"BAD_FROZEN_GEOMETRY")
        with self.assertRaises(ValueError):executable_cap(P,"PEEK_NEXT_BAR")

    def test_reward_and_stop_including_costs(self):
        cap=100.
        self.assertAlmostEqual(actual_net_r1_rr(cap,86.,121.),
             (121*SELL_FACTOR-100*BUY_FACTOR)/(100*BUY_FACTOR-86*SELL_FACTOR))
        self.assertAlmostEqual(score_geometry(cap,86,121)["raw_stop_distance_pct"],14.)

    def test_midpoint_cap_is_preclose_limit_not_next_low(self):
        x=executable_cap(P,"V4_MIDPOINT")
        self.assertEqual(x["limit"],100.)
        a,_=model_entry(P,B(o=105,h=112,l=99,c=110),"V4_MIDPOINT")
        self.assertTrue(a["filled"])
        self.assertEqual(a["price"],100.)
        b,_=model_entry(P,B(o=105,h=112,l=100,c=104),"V4_MIDPOINT")
        self.assertFalse(b["filled"])

if __name__=="__main__":unittest.main(verbosity=2)
