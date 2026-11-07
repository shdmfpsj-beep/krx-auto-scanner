"""Adversarial no-lookahead tests for C3 V3 causal profit protection."""
import unittest

from c3_exit_v3_close_confirmed import exit_strategy, net_pct, aggregation
from c3_entry_v2_preopen import entry,exit_model

P=dict(ticker="TEST",decision_date="2026-11-05",method="PULLBACK",
       segment=0,low=95,high=102,stop=90,reference_close=100,
       resistance=110,resistance2=122,atr=4)

def B(date,o,h,l,c):
    return dict(date=date,open=o,high=h,low=l,close=c,volume=100_000,
                tradable=True,invalid_data=False,action_boundary=False,segment=0)

D=["2026-11-06","2026-11-09","2026-11-10","2026-11-11",
   "2026-11-12","2026-11-13","2026-11-16","2026-11-17"]

def E(x=100,allocation=1,unsafe=False):
    return dict(status="MODEL_ENTRY_RESEARCH_ONLY",filled=True,price=x,
                allocations_filled=allocation,open_at_or_below_stop=unsafe)

class CausalExitV3Tests(unittest.TestCase):
    def test_full_hold_matches_frozen_v2_stop_next_open(self):
        bars=[B(D[0],100,105,94,88), B(D[1],85,90,80,87)]
        by={b["date"]:b for b in bars}
        x=exit_strategy(P,D[0],E(),by,D,5,"BASELINE")
        y=exit_model(P,D[0],E(),by,D,5)
        self.assertEqual((x["status"],x["exit_date"]),(y["status"],y["exit_date"]))
        self.assertAlmostEqual(x["net_pct"],y["net_pct"],places=6)
        self.assertEqual(x["exit_reason"],"CLOSE_BELOW_FROZEN_STOP_NEXT_OPEN")

    def test_next_open_partial_not_magic_r1_fill(self):
        candles=[
           B(D[0],100,115,98,111),
           B(D[1],107,115,105,109),
           B(D[2],109,118,106,112),
           B(D[3],112,119,110,115),
           B(D[4],115,121,112,118),
           B(D[5],118,125,117,120),
           B(D[6],121,125,119,122)]
        result=exit_strategy(P,D[0],E(),{b["date"]:b for b in candles},D,5,"HALF_R1")
        self.assertEqual(result["status"],"COMPLETE")
        self.assertEqual(result["realized_parts"][0]["date"],D[1])
        self.assertEqual(result["realized_parts"][0]["price"],107)
        self.assertEqual(result["realized_parts"][0]["weight"],.5)
        self.assertEqual(result["realized_parts"][1]["date"],D[6])
        self.assertEqual(result["realized_parts"][1]["weight"],.5)
        expected=(net_pct(100,107)+net_pct(100,121))/2
        self.assertAlmostEqual(result["net_pct"],expected,places=6)

    def test_high_above_target_but_close_below_does_not_trigger(self):
        p=dict(P,resistance=110)
        bars=[B(D[0],100,120,95,105),B(D[1],105,108,99,104),
              B(D[2],104,106,99,101),B(D[3],101,109,99,105),
              B(D[4],105,108,101,102),B(D[5],102,108,99,105),
              B(D[6],105,109,99,106)]
        r=exit_strategy(p,D[0],E(),{x["date"]:x for x in bars},D,5,"HALF_R1")
        self.assertEqual(len(r["realized_parts"]),1)
        self.assertEqual(r["realized_parts"][0]["reason"],"HORIZON_NEXT_OPEN")
        self.assertEqual(r["partial_execution_count"],0)

    def test_stop_priority_over_target_high(self):
        bars=[B(D[0],100,125,85,88),B(D[1],80,92,78,81)]
        r=exit_strategy(P,D[0],E(),{x["date"]:x for x in bars},D,5,"HALF_R1")
        self.assertEqual(r["exit_date"],D[1])
        self.assertEqual(r["exit_reason"],"CLOSE_BELOW_FROZEN_STOP_NEXT_OPEN")
        self.assertEqual(len(r["realized_parts"]),1)

    def test_close_trail_activated_next_session_only(self):
        bars=[B(D[0],100,111,98,108),
              B(D[1],105,108,100,101),
              B(D[2],96,100,93,95)]
        r=exit_strategy(P,D[0],E(),{x["date"]:x for x in bars},D,5,"TRAIL_7_ATR")
        self.assertEqual(r["trail_activated_at"],D[0])
        self.assertEqual(r["exit_reason"],"TRAIL_CLOSE_BREAK_NEXT_OPEN")
        self.assertEqual(r["exit_open"],96)
        self.assertEqual(r["exit_date"],D[2])

    def test_no_future_data_if_next_open_exit(self):
        bars=[B(D[0],100,112,88,89),B(D[1],85,500,40,490)]
        r=exit_strategy(P,D[0],E(),{x["date"]:x for x in bars},D,5,"BASELINE")
        self.assertEqual(r["exit_open"],85)
        self.assertEqual(r["net_pct"],round(net_pct(100,85),6))

    def test_missing_first_resistance_is_baseline(self):
        p=dict(P,resistance=None)
        bars=[B(D[0],100,120,90,105),B(D[1],105,118,99,112),
              B(D[2],111,113,99,101),B(D[3],101,106,98,100),
              B(D[4],100,109,99,108),B(D[5],108,115,106,110),
              B(D[6],110,118,106,115)]
        by={x["date"]:x for x in bars}
        a=exit_strategy(p,D[0],E(),by,D,5,"HALF_R1")
        b=exit_strategy(p,D[0],E(),by,D,5,"BASELINE")
        self.assertEqual(a["net_pct"],b["net_pct"])
        self.assertEqual(len(a["realized_parts"]),1)

    def test_combined_half_then_trail_can_exit_rest(self):
        bars=[B(D[0],100,115,95,112),B(D[1],111,115,108,111),
              B(D[2],109,112,101,102),B(D[3],99,105,95,98)]
        r=exit_strategy(P,D[0],E(),{x["date"]:x for x in bars},D,5,"HALF_R1_TRAIL")
        self.assertEqual(len(r["realized_parts"]),2)
        self.assertEqual(r["realized_parts"][0]["date"],D[1])
        self.assertEqual(r["realized_parts"][1]["date"],D[3])
        self.assertEqual(r["realized_parts"][0]["weight"],.5)
        self.assertEqual(r["realized_parts"][1]["weight"],.5)

    def test_partial_budget_not_incorrect_full_cash_exposure(self):
        bars=[B(D[0],100,115,96,112),B(D[1],111,115,108,111),
              B(D[2],108,114,102,113),B(D[3],110,115,106,112),
              B(D[4],115,119,109,118),B(D[5],119,125,112,120),
              B(D[6],120,126,117,121)]
        r=exit_strategy(P,D[0],E(allocation=.5),{x["date"]:x for x in bars},D,5,"HALF_R1")
        self.assertAlmostEqual(r["opportunity_cash_adjusted_pct"],r["net_pct"]*.5,places=5)

    def test_below_stop_open_is_not_retroactively_cancelled(self):
        p=dict(P,low=95,high=102,stop=90)
        open_gap=B(D[0],88,95,82,85)
        rest=B(D[1],84,90,82,83)
        r=exit_strategy(p,D[0],E(x=88,unsafe=True),
                        {D[0]:open_gap,D[1]:rest},D,5,"BASELINE")
        self.assertEqual(r["status"],"COMPLETE")
        self.assertTrue(r["unsafe_unconditional_preopen_fill"])
        self.assertLess(r["net_pct"],0)

    def test_insufficient_followup_censored_not_zero_return(self):
        r=exit_strategy(P,D[0],E(),{D[0]:B(D[0],100,111,95,108)},D,5,"TRAIL_7_ATR")
        self.assertEqual(r["status"],"CENSORED_MISSING_OR_INVALID_BAR")
        self.assertIsNone(r["net_pct"])

    def test_no_entry_cash_is_separate_from_actual_trade(self):
        r=exit_strategy(P,D[0],dict(filled=False),{},D,5,"BASELINE")
        self.assertEqual(r["status"],"NO_ENTRY")
        a=aggregation([r])
        self.assertEqual(a["no_entry"],1)
        self.assertEqual(a["opportunity_mean_with_cash_pct"],0)
        self.assertIsNone(a["conditional_mean_net_pct"])

    def test_trailing_does_not_activate_on_intraday_high_alone(self):
        bars=[B(D[0],100,130,98,105),B(D[1],106,108,101,102),
              B(D[2],102,104,97,103),B(D[3],103,105,97,100),
              B(D[4],100,104,98,102),B(D[5],102,109,99,107),
              B(D[6],106,108,103,106)]
        out=exit_strategy(P,D[0],E(),{x["date"]:x for x in bars},D,5,"TRAIL_7_ATR")
        self.assertIsNone(out["trail_activated_at"])
        self.assertEqual(out["exit_reason"],"HORIZON_NEXT_OPEN")

if __name__=="__main__":
    unittest.main(verbosity=2)
