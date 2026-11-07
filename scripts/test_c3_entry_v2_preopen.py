"""Regression cases: historical C3 Nov 6 bars and adversarial pre-open limits."""
import unittest
from c3_entry_v2_preopen import entry,exit_model,direct_case

def make_plan(ticker,lo,hi,stop,close):
    return dict(ticker=ticker,decision_date="2026-11-05",
                method="PULLBACK",segment=0,low=lo,high=hi,
                stop=stop,reference_close=close)

def bar(ticker,o,h,l,c,d="2026-11-06"):
    return dict(ticker=ticker,date=d,open=o,high=h,low=l,close=c,
                volume=500000,tradable=True,invalid_data=False,
                action_boundary=False,segment=0)

S=make_plan("028050",60700,63500,57700,64300)
W=make_plan("030530",22100,23500,20600,26950)
SB=bar("028050",59600,62300,58300,60500)
WB=bar("030530",23450,29200,23450,28300)

class ReadOnlyPreopenEntryTests(unittest.TestCase):
    def test_samsung_legacy_gap_veto(self):
        x=entry(S,SB,"LEGACY_GAP_VETO")
        self.assertFalse(x["filled"])
        self.assertEqual(x["status"],"OPEN_BELOW_BUDGET")

    def test_samsung_single_resting_preopen_fills_at_better_open(self):
        x=entry(S,SB,"RESTING_ONE")
        self.assertTrue(x["filled"])
        self.assertEqual(x["price"],59600)
        self.assertTrue(x["open_below_plan_low"])
        self.assertFalse(x["open_at_or_below_stop"])
        self.assertEqual(x["allocations_filled"],1.)

    def test_samsung_two_independent_preopen_orders_both_fill_at_open(self):
        x=entry(S,SB,"RESTING_TWO")
        self.assertEqual(x["fill_count"],2)
        self.assertEqual([z["price"] for z in x["individual_fills"]],[59600,59600])
        self.assertAlmostEqual(x["price"],59600)

    def test_wonik_one_preopen_limit_open_fill_but_second_not(self):
        x=entry(W,WB,"RESTING_TWO")
        self.assertEqual(x["fill_count"],1)
        self.assertEqual(x["allocations_filled"],.5)
        self.assertEqual(x["price"],23450)
        self.assertEqual(entry(W,WB,"LEGACY_GAP_VETO")["price"],23450)

    def test_very_bad_gap_cannot_be_retroactively_cancelled(self):
        b=bar("030530",20500,21300,20400,20700)
        x=entry(W,b,"RESTING_ONE")
        self.assertTrue(x["filled"])
        self.assertEqual(x["status"],"FILLED_BELOW_STOP_RISK")
        by={"2026-11-06":b}
        self.assertEqual(exit_model(W,"2026-11-06",x,by,["2026-11-06"],5)["status"],
                         "UNSAFE_AT_OPEN_NO_APPROVED_TRADE")
        self.assertEqual(entry(W,b,"LEGACY_GAP_VETO")["status"],"OPEN_BELOW_BUDGET")

    def test_touch_without_trade_through_does_not_claim_fill(self):
        b=bar("028050",64800,64900,63450,64700)
        self.assertEqual(entry(S,b,"RESTING_ONE")["status"],"DAY_EXPIRED_NO_FILL")
        b["low"]=63300
        x=entry(S,b,"RESTING_ONE")
        self.assertTrue(x["filled"])
        self.assertEqual(x["price"],63500)

    def test_post_open_confirmation_not_estimated_from_daily_bar(self):
        x=entry(W,WB,"POST_OPEN_REVIEW")
        self.assertEqual(x["status"],"INTRADAY_SEQUENCE_UNOBSERVED")
        self.assertFalse(x["filled"])

    def test_single_fill_cost_adjusted_exit_on_next_open_after_close_stop(self):
        e=entry(S,SB,"RESTING_ONE")
        self.assertTrue(e["filled"])
        dates=["2026-11-06","2026-11-09","2026-11-10"]
        r=bar("028050",59600,62300,56500,57000)
        r["date"]=dates[0]
        r2=bar("028050",56100,57300,56000,56600,dates[1])
        out=exit_model(S,dates[0],e,{dates[0]:r,dates[1]:r2},dates,5)
        self.assertEqual(out["status"],"COMPLETE")
        self.assertEqual(out["exit_date"],"2026-11-09")
        self.assertTrue(out["net_pct"]<0)
        self.assertEqual(out["exit_reason"],"CLOSE_BELOW_FROZEN_STOP_NEXT_OPEN")

    def test_exit_at_open_ignores_later_high_low_on_exit_day(self):
        e=entry(S,SB,"RESTING_ONE")
        a=bar("028050",59600,62000,56000,57000,"2026-11-06")
        # The next session contains a giant rally AFTER the model exited at
        # its open. It MUST NOT inflate the holding period MFE.
        b=bar("028050",56100,99900,50000,90000,"2026-11-09")
        out=exit_model(S,a["date"],e,{a["date"]:a,b["date"]:b},
                       [a["date"],b["date"]],5)
        self.assertEqual(out["status"],"COMPLETE")
        self.assertEqual(out["exit_open"],56100)
        self.assertAlmostEqual(out["mfe_pct"],100*(62000/59600-1),places=4)
        self.assertAlmostEqual(out["mae_pct"],100*(56000/59600-1),places=4)

    def test_first_partial_budget_cannot_count_full_amount(self):
        x=entry(W,WB,"RESTING_TWO")
        rows=[bar("030530",23450,29200,23450,28300,d) for d in
              ["2026-11-06","2026-11-09","2026-11-10","2026-11-11","2026-11-12","2026-11-13","2026-11-16"]]
        z=exit_model(W,rows[0]["date"],x,{r["date"]:r for r in rows},[r["date"] for r in rows],5)
        self.assertEqual(z["status"],"COMPLETE")
        self.assertAlmostEqual(z["net_pct"]/2,z["opportunity_cash_adjusted_pct"],places=4)

    def test_frozen_plan_invalid_rejected(self):
        p=dict(S,stop=63000)
        with self.assertRaises(ValueError):entry(p,SB,"RESTING_ONE")

    def test_no_real_broker_fill_asserted(self):
        for p,b in [(S,SB),(W,WB)]:
            for v in ("RESTING_ONE","RESTING_TWO"):
                x=direct_case(p,b)["variants"][v]
                self.assertFalse(x["actual_broker_fill_verified"])
                self.assertTrue(x["model_only_no_order_routing"])

if __name__=="__main__":
    unittest.main(verbosity=2)
