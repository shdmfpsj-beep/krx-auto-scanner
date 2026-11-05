import copy
import unittest
from datetime import date,timedelta
from c3_daily_top2_v4 import structure,features,make_plan,next_day_entry,model_path,replay


def fixture(n=80):
    days=[(date(2026,5,1)+timedelta(days=i)).isoformat() for i in range(n)]
    rows=[dict(date=d,open=100.,high=102.,low=98.,close=100.,volume=1000.,turnover_krw=100000.,
               tradable=True,ohlc_valid=True,invalid_data=False,action_boundary=False,segment=0) for d in days]
    p=dict(ticker="A",decision_date=days[0],method="PULLBACK",signal_key="A:anchor1",segment=0,
        low=98,high=103,stop=90,atr=4,support=92,support_date="2026-04-28",known_on=days[0],
        reference_close=100,resistance=120,resistance2=130,rank_turnover=100000,rs20=2,regime="UP")
    return days,rows,p


def candidate(p,rows,days,day=None,key=None):
    p=dict(p,decision_date=day or p["decision_date"],signal_key=key or p["signal_key"])
    return dict(plan=p,fold="HOLDOUT",paths={str(h):model_path(p,rows,days,h) for h in (5,10,20)})


class DailyTop2Tests(unittest.TestCase):
    def rising_with_pivot(self):
        days,rows,p=fixture(70)
        for i,b in enumerate(rows):
            close=100+i*.2;b.update(open=close-.3,high=close+2,low=close-2,close=close)
        rows[65]["low"]=100.
        return days,rows,p

    def test_pivot_requires_two_completed_confirmation_bars(self):
        days,rows,p=self.rising_with_pivot()
        self.assertIsNone(structure(rows[:67]))
        s=structure(rows[:68]);self.assertEqual(s["pivot_date"],days[65]);self.assertEqual(s["confirmed_on"],days[67])

    def test_atr_buffer_freezes_at_confirmation_not_current_volatility(self):
        days,rows,p=self.rising_with_pivot();a=structure(rows)
        future=dict(rows[-1],date="2026-07-10",high=250.,low=112.,close=114.,open=113.)
        b=structure(rows+[future]);self.assertEqual(a["stop"],b["stop"]);self.assertEqual(a["atr"],b["atr"])

    def test_broken_structure_cannot_revive_without_new_confirmed_pivot(self):
        days,rows,p=self.rising_with_pivot();s=structure(rows)
        rows[-1].update(close=s["stop"]-1,low=s["stop"]-2)
        self.assertIsNone(structure(rows))

    def test_exact_limit_touch_is_not_filled_on_a_later_day(self):
        days,rows,p=fixture();p["high"]=100
        rows[1].update(open=105.,high=108.,low=100.,close=104.)
        rows[2].update(open=104.,high=108.,low=99.,close=104.)
        e=next_day_entry(p,rows,days)
        self.assertEqual(e["status"],"TOUCH_WITHOUT_TRADE_THROUGH");self.assertEqual(e["terminal"],days[1])

    def test_confirmed_breakout_buys_only_next_open_within_budget(self):
        days,rows,p=fixture();p["method"]="BREAKOUT";rows[1]["open"]=101.
        e=next_day_entry(p,rows,days)
        self.assertEqual(e["price"],101.);self.assertNotEqual(e["date"],p["decision_date"])
        rows[1]["open"]=104.
        self.assertEqual(next_day_entry(p,rows,days)["status"],"OPEN_ABOVE_FROZEN_BUDGET")

    def test_breakout_confirmation_and_pullback_use_same_structural_stop(self):
        days,rows,p=fixture();rows[-2]["close"]=109.;rows[-1].update(open=111.,close=112.,high=114.,low=110.,volume=120.)
        f=dict(structure=dict(pivot_date=days[-5],confirmed_on=days[-3],support=100.,atr=4.,stop=95),
            geometry=dict(first_resistance=130.,second_resistance=140.),prior_high20=110.,volume20=100.,rs20=2.,turnover20=1000.)
        a,ra=make_plan("A",rows,f,"PULLBACK","UP");b,rb=make_plan("A",rows,f,"BREAKOUT","UP")
        self.assertIsNone(ra);self.assertIsNone(rb);self.assertEqual(a["stop"],b["stop"])
        rows[-1]["volume"]=119.
        self.assertEqual(make_plan("A",rows,f,"BREAKOUT","UP")[1],"BREAKOUT_NOT_CONFIRMED")

    def test_same_bar_entry_and_stop_is_retained_as_uncertainty(self):
        days,rows,p=fixture();rows[1].update(open=105.,low=85.,high=110.)
        e=next_day_entry(p,rows,days)
        self.assertEqual(e["status"],"MODEL_ENTRY");self.assertTrue(e["order_unknown"])

    def test_gap_after_close_stop_is_not_filled_at_stop_price(self):
        days,rows,p=fixture();rows[1]["close"]=88.;rows[2]["open"]=80.
        x=model_path(p,rows,days,20)["exit"]
        self.assertEqual(x["price"],80.);self.assertLess(x["net_pct"],-20.)

    def test_daily_reoffers_unfilled_structure_and_fixed26_does_not(self):
        days,rows,p=fixture();rows[1].update(open=105.,low=104.,high=106.,close=105.)
        plans=[candidate(p,rows,days),candidate(p,rows,days,days[1])]
        a=replay(plans,{"A":rows},days,5,"HOLDOUT","DAILY")
        b=replay(plans,{"A":rows},days,5,"HOLDOUT","FIXED26")
        self.assertEqual(a["metrics"]["orders"],2);self.assertEqual(a["metrics"]["model_entries"],1)
        self.assertEqual(b["metrics"]["orders"],1);self.assertEqual(b["metrics"]["model_entries"],0)

    def test_entered_structure_is_consumed_but_new_structure_can_trade(self):
        days,rows,p=fixture()
        a=candidate(p,rows,days);same=candidate(p,rows,days,days[8]);new=candidate(p,rows,days,days[9],"A:anchor2")
        r=replay([a,same,new],{"A":rows},days,5,"HOLDOUT","DAILY")
        self.assertEqual(r["metrics"]["model_entries"],2)
        self.assertEqual(r["metrics"]["counts"]["already_entered_structure"],1)

    def test_daily_can_trade_new_structure_inside_26_sessions(self):
        days,rows,p=fixture();plans=[candidate(p,rows,days),candidate(p,rows,days,days[8],"A:new")]
        self.assertEqual(replay(plans,{"A":rows},days,5,"HOLDOUT","DAILY")["metrics"]["model_entries"],2)
        self.assertEqual(replay(plans,{"A":rows},days,5,"HOLDOUT","FIXED26")["metrics"]["model_entries"],1)

    def test_future_winner_cannot_replace_the_two_selected_orders(self):
        days,rows,p=fixture();plans=[];panel={}
        for t in ("A","B","C"):
            q=dict(p,ticker=t,signal_key=t+":anchor");c=candidate(q,rows,days);plans.append(c);panel[t]=rows
        plans[2]["paths"]["5"]["exit"]["net_pct"]=100000.
        r=replay(plans,panel,days,5,"HOLDOUT","DAILY")
        self.assertEqual([o["plan"]["ticker"] for o in r["orders"]],["A","B"])

    def test_no_unseen_window_is_not_zero_return_success(self):
        days,rows,p=fixture();r=replay([],{"A":rows},days,20,"UNSEEN","DAILY")
        self.assertEqual(r["metrics"]["completed"],0);self.assertIsNone(r["metrics"]["mean_net_pct"])
        self.assertIsNone(r["metrics"]["portfolio_return_pct"]);self.assertIsNone(r["metrics"]["max_drawdown_close_pct"])

    def test_open_immature_loss_still_reduces_equity(self):
        days,rows,p=fixture(5);rows[-1].update(close=50.,low=49.)
        r=replay([candidate(p,rows,days)],{"A":rows},days,20,"HOLDOUT","DAILY")
        self.assertEqual(r["metrics"]["completed"],0);self.assertLess(r["metrics"]["portfolio_return_pct"],-20.)

    def test_unresolved_action_does_not_turn_into_a_zero_loss(self):
        days,rows,p=fixture();rows[3]["action_boundary"]=True
        r=replay([candidate(p,rows,days)],{"A":rows},days,20,"HOLDOUT","DAILY")
        self.assertIsNotNone(r["metrics"]["censored"]);self.assertIsNone(r["metrics"]["portfolio_return_pct"])


if __name__=="__main__":unittest.main()
