import copy
import unittest
from datetime import date,timedelta

from c3_practical_top2_v3 import (tick,quote,plan_entry,locate_strict,path_model,
                                 rank_key,edge_gate,replay,INITIAL_CASH,opportunity_comparison)
from c3_entry_benchmark_v1 import net_return


def fixture(n=40):
    days=[(date(2026,5,1)+timedelta(days=i)).isoformat() for i in range(n)]
    rows=[dict(date=d,open=100.,high=102.,low=98.,close=100.,volume=1000.,tradable=True,
        ohlc_valid=True,segment=0,action_boundary=False,invalid_data=False) for d in days]
    p=dict(ticker="A",decision_date=days[0],low=98,high=103,stop=90,atr=4,
        resistance=120,breakout_support=None,segment=0,kind="LIMIT_WATCH",net_r1_rr=1.)
    return days,rows,p


def candidate(ticker,days,rows,p,decision=None):
    p=dict(p,ticker=ticker,decision_date=decision or days[0])
    return dict(ticker=ticker,decision_date=p["decision_date"],fold="HOLDOUT",plan=p,
        features=dict(turnover20=1000.,stock_rs20=2.,sector_rs20=1.,stock_vs_sector20=1.,regime="UP"),
        paths={str(h):path_model(p,rows,days,h) for h in (5,10,20)})


class PracticalTop2Tests(unittest.TestCase):
    def test_tick_boundaries_and_rounding(self):
        self.assertEqual([tick(p) for p in (1999,2000,4999,5000,19999,20000,49999,50000,199999,200000,499999,500000)],
                         [1,5,5,10,10,50,50,100,100,500,500,1000])
        self.assertEqual(quote(1999.8,True),2000);self.assertEqual(quote(4999.8),4995)
        self.assertEqual(quote(5000.1,True),5010)

    def test_costed_cap_changes_entry_not_structural_stop(self):
        days,rows,p=fixture();f=dict(fresh_support=94)
        out,reason=plan_entry(p,f,"COSTED_LIMIT")
        self.assertIsNone(reason);self.assertEqual(out["stop"],90)
        self.assertGreaterEqual(out["net_r1_rr"],1)
        self.assertEqual(p["high"],103)

    def test_no_fixed_eight_percent_stop_or_risk_rule(self):
        days,rows,p=fixture();p.update(stop=50,low=80,high=90,resistance=160)
        out,reason=plan_entry(p,dict(fresh_support=75),"COSTED_LIMIT")
        self.assertIsNone(reason);self.assertGreater(out["planned_risk_pct"],8)
        self.assertEqual(out["stop"],50)

    def test_unavailable_resistance_is_not_invented(self):
        days,rows,p=fixture();p["resistance"]=None
        out,reason=plan_entry(p,dict(fresh_support=94),"COSTED_LIMIT")
        self.assertIsNone(out);self.assertEqual(reason,"FIRST_RESISTANCE_UNKNOWN")

    def test_exact_limit_print_waits_for_trade_through(self):
        days,rows,p=fixture();p["high"]=100
        rows[1].update(open=105.,high=108.,low=100.,close=104.)
        rows[2].update(open=104.,high=108.,low=99.,close=104.)
        e=locate_strict(p,{b["date"]:b for b in rows},days)
        self.assertEqual(e["date"],days[2]);self.assertEqual(e["touches"],days[1:3])

    def test_same_bar_entry_and_stop_is_retained_as_uncertain(self):
        days,rows,p=fixture();rows[1].update(open=105.,low=85.,high=108.)
        e=locate_strict(p,{b["date"]:b for b in rows},days)
        self.assertEqual(e["status"],"MODEL_ENTRY");self.assertTrue(e["order_unknown"])

    def test_touch_before_incomplete_window_is_not_deleted(self):
        days,rows,p=fixture(3)
        out=path_model(p,rows,days,20)
        self.assertEqual(out["entry"]["status"],"MODEL_ENTRY");self.assertIsNone(out["maturity_date"])

    def test_close_stop_uses_next_open_with_gap(self):
        days,rows,p=fixture();rows[1]["close"]=88.;rows[2]["open"]=80.
        out=path_model(p,rows,days,5)
        self.assertEqual(out["exit"]["date"],days[2]);self.assertEqual(out["exit"]["price"],80.)

    def test_time_exit_queues_during_halt(self):
        days,rows,p=fixture();rows[6]["tradable"]=False
        out=path_model(p,rows,days,5)
        self.assertEqual(out["exit"]["date"],days[7])

    def test_r1_stop_raise_is_not_retroactive(self):
        days,rows,p=fixture();p["resistance"]=110
        rows[1].update(close=112.,high=115.,low=98.)
        rows[2]["close"]=99.;rows[3]["open"]=95.
        out=path_model(p,rows,days,5,"R1_RAISE")
        self.assertEqual(out["exit"]["date"],days[3]);self.assertEqual(out["exit"]["price"],95.)

    def test_rank_ignores_future_returns_and_fill(self):
        days,rows,p=fixture();c=candidate("A",days,rows,p)
        original=rank_key(c,"SECTOR_LEADER")
        c["paths"]={"future_return":1000000};self.assertEqual(original,rank_key(c,"SECTOR_LEADER"))

    def test_unknown_sector_not_ranked_as_healthy(self):
        days,rows,p=fixture();c=candidate("A",days,rows,p);c["features"]["sector_rs20"]=None
        self.assertIsNone(rank_key(c,"SECTOR_LEADER"))

    def test_edge_waits_for_same_maturity_for_early_stopped_trades(self):
        candidates=[]
        for i in range(20):
            path=dict(maturity_date="2026-06-01",exit=dict(date="2026-05-01",net_pct=2.),censor_date=None)
            candidates.append(dict(ticker=str(i%10),paths={"20":path}))
        self.assertEqual(edge_gate(candidates,"2026-05-20",20)["n"],0)
        self.assertTrue(edge_gate(candidates,"2026-06-02",20)["allowed"])

    def test_edge_is_rejected_when_recent_expectancy_is_negative(self):
        candidates=[dict(ticker=str(i%10),paths={"20":dict(maturity_date="2026-05-10",exit=dict(date="2026-05-09",net_pct=-2.),censor_date=None)}) for i in range(20)]
        self.assertFalse(edge_gate(candidates,"2026-05-20",20)["allowed"])

    def test_future_no_fill_does_not_release_a_slot_early(self):
        days,rows,p=fixture();candidates=[]
        for t in ("A","B"):
            c=candidate(t,days,rows,p)
            for path in c["paths"].values():path["entry"]=dict(status="NO_TRADE_THROUGH",terminal=days[5],touches=[])
            candidates.append(c)
        candidates.append(candidate("C",days,rows,p,days[1]))
        result=replay(candidates,{t:rows for t in ("A","B","C")},days,"TURNOVER20",5,"HOLDOUT")
        self.assertEqual([o["ticker"] for o in result["orders"]],["A","B"])
        self.assertEqual(result["metrics"]["portfolio_return_pct"],0)
        self.assertIsNone(result["metrics"]["mean_net_pct"])

    def test_two_slots_integer_shares_and_single_cost_accounting(self):
        days,rows,p=fixture();candidates=[candidate(t,days,rows,p) for t in ("A","B","C")]
        out=replay(candidates,{t:rows for t in ("A","B","C")},days,"TURNOVER20",5,"HOLDOUT")
        self.assertEqual(len(out["orders"]),2)
        self.assertTrue(all(isinstance(o["qty"],int) for o in out["orders"]))
        self.assertTrue(all(x["cash"]>=0 for x in out["equity"]))
        self.assertAlmostEqual(out["trades"][0]["net_pct"],net_return(100*1.001,100*.999))
        self.assertLess(out["metrics"]["max_drawdown_close_liquidation_pct"],0)

    def test_unresolved_action_censors_portfolio_without_future_exclusion(self):
        days,rows,p=fixture();rows[3]["action_boundary"]=True;c=candidate("A",days,rows,p)
        out=replay([c],{"A":rows},days,"TURNOVER20",20,"HOLDOUT")
        self.assertEqual(len(out["orders"]),1);self.assertEqual(out["metrics"]["censored"]["date"],days[3])
        self.assertIsNone(out["metrics"]["portfolio_return_pct"])
        self.assertIsNone(out["metrics"]["max_drawdown_close_liquidation_pct"])

    def test_open_immature_loss_is_in_nav_not_hidden_by_complete_trade_filter(self):
        days,rows,p=fixture(5);rows[-1].update(close=50.,low=49.)
        c=candidate("A",days,rows,p);out=replay([c],{"A":rows},days,"TURNOVER20",20,"HOLDOUT")
        self.assertEqual(out["metrics"]["completed_trades"],0)
        self.assertEqual(out["metrics"]["open_positions_at_end"],1)
        self.assertLess(out["metrics"]["portfolio_return_pct"],-20.)

    def test_missed_baseline_winner_is_counted_and_no_order_is_cash(self):
        days,rows,p=fixture();c=candidate("A",days,rows,p)
        c["paths"]["5"]["exit"]["net_pct"]=10.
        result=opportunity_comparison(dict(C3_STRUCTURE=[c],COSTED_LIMIT=[],FRESH_COSTED_LIMIT=[]),days,"HOLDOUT",5)
        self.assertEqual(result["methods"]["COSTED_LIMIT"]["baseline_winners_missed"],1)
        self.assertEqual(result["methods"]["COSTED_LIMIT"]["mean_net_per_anchor_including_cash"],0.)

    def test_partial_common_window_and_unknown_exit_are_not_zero_profit(self):
        days,rows,p=fixture(10);c=candidate("A",days,rows,p)
        result=opportunity_comparison(dict(C3_STRUCTURE=[c],COSTED_LIMIT=[],FRESH_COSTED_LIMIT=[]),days,"HOLDOUT",5)
        self.assertEqual(result["shared_fully_observed_anchors"],0)
        days,rows,p=fixture();c=candidate("A",days,rows,p);c["paths"]["5"]["exit"]=None
        result=opportunity_comparison(dict(C3_STRUCTURE=[c],COSTED_LIMIT=[],FRESH_COSTED_LIMIT=[]),days,"HOLDOUT",5)
        self.assertEqual(result["common_censored_anchors"],1)
        self.assertIsNone(result["methods"]["C3_STRUCTURE"]["mean_net_per_anchor_including_cash"])


if __name__=="__main__":unittest.main()
