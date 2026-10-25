#!/usr/bin/env python3
"""v6.15 isolated regression checks: wider opportunities, zero BUY authority."""
import unittest
from entry_opportunities_v615 import (
    SCHEMA,atr14,method_candidates,confirmed_overhead,inspect,
)

def synthetic(overhead=False):
    b=[]
    for i in range(120):
        c=100+.07*i
        b.append(dict(date="2026-10-22",open=c-.2,high=c+.45,
                      low=c-.65,close=c,volume=250000,turnover_krw=8e9))
    # A two-bar-confirmed daily swing low, not a 10-minute stop.
    b[-9]["low"]=103.5
    # Older 60-day resistance does not block a confirmed fresh 20d high.
    if overhead:b[-40]["high"]=125
    b[-1].update(date="2026-10-23",open=108.2,
                 high=110.05,low=108.2,close=109.65,volume=500000)
    return b

def m():
    return dict(relative_volume20=2.0,return_20d_pct=9.2,
        distance_from_sma20_pct=1.6,atr14_pct=1.2,
        fi_positive_session_count=3,discovery_index_100=80.2)

class FrontierTests(unittest.TestCase):
    def test_clean_breakout_without_prior_resistance_is_B_not_2R_buy(self):
        b=synthetic()
        r=inspect(b,m(),"2026-10-23","000001","테스트","KOSPI",1e10)
        self.assertTrue(any(x["method"]=="FRESH_20D_BREAKOUT" for x in r))
        q=[x for x in r if x["method"]=="FRESH_20D_BREAKOUT"][0]
        self.assertEqual(q["classification"],"B_PRICE_DISCOVERY_NO_PROVEN_TARGET_WATCH")
        self.assertEqual(q["nearby_confirmed_overhead"],"")
        self.assertEqual(q["net_R_to_ceiling"],"")
        self.assertTrue(q["scenario_target_2R_not_verified"]>q["first_limit_study"])
        self.assertIs(q["orders_enabled"],False)
        self.assertIs(q["trade_approved"],False)
        self.assertIs(q["final80_trade_score_verified"],False)
    def test_past_confirmed_swing_resistance_allows_A_research_only(self):
        b=synthetic(True)
        q=[x for x in inspect(b,m(),"2026-10-23","000001","테스트","KOSPI",1e10)
           if x["method"]=="FRESH_20D_BREAKOUT"][0]
        self.assertEqual(q["classification"],"A_CONDITIONAL_GEOMETRY_1P5R_RESEARCH")
        self.assertGreaterEqual(q["net_R_to_ceiling"],1.5)
        self.assertGreater(q["structure_stop_study"],0)
        self.assertLess(q["structure_stop_study"],q["first_limit_study"])
        self.assertIs(q["broker_order_confirmed"],False)
        self.assertIs(q["trade_approved"],False)
    def test_wrong_date_and_nonpositive_flow_are_rejected(self):
        b=synthetic(True)
        self.assertEqual(inspect(b,m(),"2026-10-24","000001","테스트","KOSPI",1),[])
        self.assertEqual(inspect(b,m(),"2026-10-23","000001","테스트","KOSPI",0),[])
    def test_chasing_and_structural_risk_do_not_create_A(self):
        b=synthetic(True);mod=m()
        mod["return_20d_pct"]=44
        q=[x for x in inspect(b,mod,"2026-10-23","000001","테스트","KOSPI",1e10)
           if x["method"]=="FRESH_20D_BREAKOUT"][0]
        self.assertEqual(q["classification"],"C_SIGNAL_NOT_READY_RISK_OR_HEADROOM")
    def test_no_past_overhead_does_not_claim_high_probability(self):
        b=synthetic()
        self.assertIsNone(confirmed_overhead(b,109.2,109.65))
        self.assertGreater(atr14(b),0)
        self.assertEqual(SCHEMA,"C3_CONDITIONAL_OPPORTUNITY_FRONTIER_V615")
    def test_asof_research_not_same_day_broker_fill(self):
        b=synthetic(True)
        q=inspect(b,m(),"2026-10-23","000001","테스트","KOSPI",1e10)[0]
        for name in ("regular_1530_price_verified","issuer_history_PIT_verified",
                     "final80_trade_score_verified","broker_order_confirmed",
                     "trade_approved","orders_enabled"):
            self.assertIs(q[name],False)

if __name__=="__main__":
    unittest.main()
