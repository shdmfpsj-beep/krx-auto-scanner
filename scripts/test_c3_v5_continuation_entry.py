"""V5 time-causal continuance/entry decision and opportunity cost guardrails."""
import copy,unittest
from c3_v5_continuation_entry import POLICIES,prior_strong,choose_plan,simulate,gate_risk
from c3_entry_v2_preopen import entry

P=dict(ticker="TEST",decision_date="2026-11-05",method="PULLBACK",
       segment=0,low=90,high=110,stop=86,atr=10,
       reference_close=107,resistance=121,resistance2=140,
       rank_turnover=4_000_000_000,rs20=22)
STRONG=dict(ticker="TEST",decision_date="2026-11-05",
       trend60=True,turnover_ratio=1.25,own_rs20=17,rs_accel5=3)
WEAK=dict(STRONG,trend60=False,turnover_ratio=.8)
def b(o=105,h=112,l=99,c=106):
    return dict(date="2026-11-06",open=o,high=h,low=l,close=c,
                volume=1_000_000,tradable=True,invalid_data=False,
                action_boundary=False,segment=0)

class V5Cases(unittest.TestCase):
    def test_research_policies_do_not_change_after_run(self):
        self.assertEqual(POLICIES,("V2_HIGH","V4_MIDPOINT","V5_TREND_GATE_HIGH",
                         "V5_TREND_ADAPTIVE","V5_RISK_AWARE"))

    def test_raw_B_acceleration_is_not_confused_with_continuation(self):
        self.assertFalse(prior_strong(WEAK)["strong"])
        self.assertTrue(prior_strong(STRONG)["strong"])

    def test_missing_prior_factors_never_guessed(self):
        x=choose_plan(P,dict(STRONG,turnover_ratio=None),"V5_TREND_ADAPTIVE")
        self.assertFalse(x["submitted"])
        self.assertEqual(x["status"],"NO_ORDER_PRIOR_FEATURES_MISSING")

    def test_strong_keeps_original_high_limit(self):
        a=choose_plan(P,STRONG,"V5_TREND_ADAPTIVE")
        self.assertEqual(a["limit"],110.)
        self.assertEqual(a["selection_basis"],"STRONG_HIGH_ELSE_MID")
        c=choose_plan(P,STRONG,"V5_TREND_GATE_HIGH")
        self.assertEqual(c["limit"],110.)

    def test_weak_adaptive_uses_mid_not_cash(self):
        x=choose_plan(P,WEAK,"V5_TREND_ADAPTIVE")
        self.assertTrue(x["submitted"])
        self.assertEqual(x["limit"],100.)
        y=choose_plan(P,WEAK,"V5_TREND_GATE_HIGH")
        self.assertFalse(y["submitted"])

    def test_midpoint_fills_only_on_trade_through(self):
        planned,ex=simulate(P,WEAK,b(o=105,h=112,l=99,c=110),"V5_TREND_ADAPTIVE")
        self.assertTrue(ex["filled"])
        self.assertEqual(ex["price"],100.)
        self.assertEqual(ex["individual_fills"][0]["when"],"INTRADAY_LIMIT_ASSUMED")
        _,unfilled=simulate(P,WEAK,b(o=105,h=112,l=100,c=108),"V5_TREND_ADAPTIVE")
        self.assertFalse(unfilled["filled"])

    def test_v2_control_execution_exact_identity(self):
        x,buy=simulate(P,STRONG,b(o=99),"V2_HIGH")
        frozen=entry(P,b(o=99),"RESTING_ONE")
        self.assertEqual(buy["price"],frozen["price"])
        self.assertEqual(buy["filled"],frozen["filled"])
        self.assertEqual(buy["status"],frozen["status"])
        self.assertEqual(x["limit"],P["high"])

    def test_unconditional_gap_below_stop_still_mechanically_fills(self):
        p,e=simulate(P,STRONG,b(o=80,h=112,l=78,c=100),"V5_TREND_GATE_HIGH")
        self.assertTrue(e["filled"])
        self.assertTrue(e["open_at_or_below_stop"])
        self.assertEqual(e["status"],"FILLED_BELOW_STOP_RISK")

    def test_risk_protection_does_not_claim_preopen_riskless_execution(self):
        good=gate_risk(P,95.)
        self.assertTrue(good["accepted"])
        bad=gate_risk(P,110.)
        self.assertFalse(bad["accepted"])

    def test_risk_policy_starts_at_mid_or_cash(self):
        # Frozen stop 89 makes midpoint risk 11%, whereas HIGH risk >12%;
        # original stop 86 would correctly reject BOTH (mid = 14% risk).
        eligible=dict(P,stop=89)
        x=choose_plan(eligible,STRONG,"V5_RISK_AWARE")
        self.assertTrue(x["submitted"])
        self.assertEqual(x["limit"],100.)
        self.assertEqual(x["selection_basis"],"RISK_APPROVED_MID")
        original=choose_plan(P,STRONG,"V5_RISK_AWARE")
        self.assertFalse(original["submitted"])
        impossible=dict(eligible,resistance=87)
        y=choose_plan(impossible,STRONG,"V5_RISK_AWARE")
        self.assertFalse(y["submitted"])

    def test_original_immutable_prior_signal_not_mutated(self):
        p=copy.deepcopy(P);f=copy.deepcopy(WEAK)
        for policy in POLICIES:
            simulate(P,WEAK,b(),policy)
        self.assertEqual(P,p)
        self.assertEqual(WEAK,f)

    def test_no_order_returns_no_entry_not_zero_trade(self):
        frozen,e=simulate(P,WEAK,b(),"V5_TREND_GATE_HIGH")
        self.assertFalse(frozen["submitted"])
        self.assertFalse(e["filled"])
        self.assertTrue(e["no_order"])

    def test_source_plan_absence_is_not_invented(self):
        z=choose_plan(None,STRONG,"V2_HIGH")
        self.assertFalse(z["submitted"])
        self.assertEqual(z["status"],"NO_ORIGINAL_SUPPORT_PLAN")

    def test_no_trade_approvals_or_data_leaks_in_plan(self):
        for policy in POLICIES:
            x=choose_plan(P,STRONG,policy)
            if x["submitted"]:
                self.assertFalse(x["generated_using_next_session_price"])
            self.assertNotIn("future_close",x)
        with self.assertRaises(ValueError):
            choose_plan(P,STRONG,"HINDSIGHT_WINNER_FILTER")

if __name__=="__main__":unittest.main(verbosity=2)
