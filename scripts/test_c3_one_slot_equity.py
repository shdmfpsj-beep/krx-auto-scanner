#!/usr/bin/env python3
"""Offline C3 account realism tests: one-slot, capital, stop budget, MDD."""
import unittest
from c3_one_slot_equity import simulate,choose_one_per_day,render

DATES=["2026-10-22","2026-10-23","2026-10-26","2026-10-27",
       "2026-10-28","2026-10-29","2026-10-30","2026-11-02"]
def sig(day="2026-10-22",ticker="005930",rank=90,entry=100,stop=90,
        cap=110,resistance=130):
    return dict(signal_date=day,ticker=ticker,sector_id="SEMICON",
        signal_close=entry,signal_atr14=8,
        stop_reference=stop,no_chase_reference=cap,
        prior_high=resistance,research_proxy_index=rank,
        plan_version="next_open_5d_v1")
def bar(day,op=100,hi=105,lo=95,cl=102):
    return dict(date=day,open=op,high=hi,low=lo,close=cl)

class OneSlotTests(unittest.TestCase):
    def test_one_share_cash_gate_blocks_expensive_stock(self):
        s=sig(entry=300000,stop=280000,cap=330000,resistance=380000)
        records={"005930":[bar(DATES[1],op=300000,hi=360000,lo=290000,cl=320000)]}
        out=simulate([s],records,DATES,initial_cash=250000)
        self.assertEqual(out["traded_positions"],0)
        self.assertEqual(out["skips"][0]["reason"],"CAPITAL_GATE_LESS_THAN_ONE_SHARE")
        self.assertEqual(out["realised_return_pct"],0)
    def test_buy_integer_shares_with_structure_risk_cap(self):
        r={"005930":[bar(DATES[1],hi=125,lo=95)]}
        out=simulate([sig()],r,DATES,initial_cash=1000000,risk_budget_pct=2)
        self.assertEqual(out["traded_positions"],1)
        pos=out["trades"][0]
        self.assertIsInstance(pos["shares"],int)
        self.assertLessEqual(pos["planned_risk_krw"],20000.01)
        self.assertGreater(pos["realized_pnl_krw"],0)
        self.assertEqual(pos["exit_date"],DATES[1])
        self.assertIn("가상",render(out))
    def test_stronger_premarket_rank_picked_without_future_reselection(self):
        a=sig(ticker="000660",rank=95,cap=105)
        b=sig(ticker="005930",rank=88)
        prices={"000660":[bar(DATES[1],op=108,hi=120,lo=95)],
                "005930":[bar(DATES[1],op=100,hi=125,lo=95)]}
        out=simulate([a,b],prices,DATES)
        self.assertEqual(out["traded_positions"],0)
        self.assertEqual(out["skips"][0]["ticker"],"000660")
        self.assertEqual(out["skips"][0]["reason"],"SKIP_GAP_UP_ABOVE_NO_CHASE")
        self.assertEqual(out["skips"][0]["rejected_alternative_signals"],1)
    def test_held_one_stock_blocks_another_signal(self):
        p1=[bar(DATES[1],hi=105,lo=95),bar(DATES[2],hi=122,lo=95)]
        p2=[bar(DATES[2],hi=125,lo=95),bar(DATES[3],hi=130,lo=95)]
        signals=[sig(),sig(DATES[1],ticker="000660",rank=99)]
        out=simulate(signals,{"005930":p1,"000660":p2},DATES)
        self.assertEqual(out["traded_positions"],1)
        self.assertEqual(out["blocked_simultaneous_candidates"],1)
        self.assertEqual(out["skips"][0]["reason"],"C3_ALREADY_HOLDING_ONE_STOCK")
    def test_signal_after_same_day_exit_can_trade_next_day(self):
        signals=[sig(),sig(DATES[1],ticker="000660",rank=92)]
        p1=[bar(DATES[1],hi=122,lo=95)]
        p2=[bar(DATES[2],hi=122,lo=95)]
        out=simulate(signals,{"005930":p1,"000660":p2},DATES)
        self.assertEqual(out["traded_positions"],2)
        self.assertEqual(out["trades"][1]["entry_date"],DATES[2])
    def test_stop_loss_reduces_cash_and_reports_mdd(self):
        out=simulate([sig()],{"005930":[bar(DATES[1],hi=110,lo=89,cl=92)]},DATES)
        self.assertEqual(out["traded_positions"],1)
        self.assertLess(out["realised_pnl_krw"],0)
        self.assertGreater(out["mark_to_market_mdd_pct"],0)
    def test_unresolved_first_trade_blocks_fabricated_new_positions(self):
        signals=[sig(),sig(DATES[1],ticker="000660")]
        prices={"005930":[bar(DATES[1],hi=105,lo=95)]}
        out=simulate(signals,prices,DATES)
        self.assertEqual(out["integrity"],"MISSING_INTERMEDIATE_SESSION_PRICE")
        self.assertFalse(out["research_valid"])
        self.assertEqual(out["traded_positions"],0)
        self.assertEqual(out["ending_realised_equity_krw"],1000000)
    def test_signal_date_not_in_market_calendar_fails_closed(self):
        out=simulate([sig("2026-10-21")],{},DATES)
        self.assertEqual(out["integrity"],"SIGNAL_DATE_NOT_IN_VALIDATED_CALENDAR")
        self.assertEqual(out["traded_positions"],0)
    def test_no_session_history_returns_no_fake_performance(self):
        out=simulate([sig()],{},[])
        self.assertFalse(out["research_valid"])
        self.assertIsNone(out["ending_realised_equity_krw"])
    def test_different_risk_budget_changes_quantity_not_structural_stop(self):
        p={"005930":[bar(DATES[1],hi=122,lo=95)]}
        low=simulate([sig()],p,DATES,risk_budget_pct=1.5)
        high=simulate([sig()],p,DATES,risk_budget_pct=3.0)
        self.assertLess(low["trades"][0]["shares"],high["trades"][0]["shares"])
        self.assertEqual(low["trades"][0]["structure_stop_krw"],90)
        self.assertEqual(high["trades"][0]["structure_stop_krw"],90)
    def test_invalid_negative_risk_or_cash_is_rejected(self):
        with self.assertRaises(ValueError):
            simulate([],{},DATES,initial_cash=-100)
        with self.assertRaises(ValueError):
            simulate([],{},DATES,risk_budget_pct=10)
    def test_deterministic_original_precomputed_rank(self):
        selected=choose_one_per_day([sig(rank=45),sig(ticker="000660",rank=94)])
        self.assertEqual(selected[0][1]["ticker"],"000660")
        self.assertEqual(selected[0][2],2)

if __name__=="__main__":
    unittest.main()
