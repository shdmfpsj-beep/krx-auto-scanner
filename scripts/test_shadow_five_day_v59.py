"""Offline backtest safety: causality, gap risk, ambiguous order, 2nd alternative."""
import tempfile,unittest,csv
from pathlib import Path
from datetime import date,timedelta
from unittest.mock import patch
from shadow_five_day_v59 import (
    ENTRY_DAYS,HOLD_DAYS,simulate,commission_exit,stats,
    historical_shadow,signal_rows_for_historic_selected_universe,
    build_report,markdown)
from entry_strategy_v58 import METHODS

BASE=date(2026,10,1)
def bar(i,open=100,high=105,low=95,close=101):
    return dict(date=BASE+timedelta(days=i),
        open=float(open),high=float(high),low=float(low),
        close=float(close),volume=1000,source="pykrx")
def future(n=7):
    return [bar(i) for i in range(n)]
def plan(first=100,second=94,stop=90,target=120):
    return dict(asof="2026-09-30",ticker="005930",name="TEST",
        method=METHODS[2],asof_close_research=105,
        first_entry_reference=first,second_entry_reference=second,
        stop_reference=stop,nearest_resistance_reference=target,
        first_net_rr=2.0,second_net_rr=3.0)

class FiveDayShadowTests(unittest.TestCase):
    def test_next_day_limit_never_pre_fills_on_signal_day(self):
        f=future();f[0]=bar(0,open=130,high=131,low=121,close=128)
        f[1]=bar(1,open=120,high=121,low=100,close=110)
        r=simulate(plan(),f)
        self.assertEqual(r["entry_date"],str(BASE+timedelta(days=1)))
        self.assertEqual(r["entry_price"],100)
        self.assertTrue(r["hypothetical_only"])
        self.assertFalse(r["trade_approved"])

    def test_same_entry_candle_stop_target_assume_stop(self):
        f=future()
        f[0]=bar(0,open=110,high=125,low=85,close=119)
        r=simulate(plan(),f)
        self.assertEqual(r["exit_reason"],"STOP")
        self.assertEqual(r["exit_price"],90)
        self.assertIn("ASSUME_STOP",r["path_ambiguity"])
        self.assertEqual(r["outcome"],"NET_LOSS")

    def test_after_limit_touch_high_same_bar_not_provably_after_entry(self):
        f=future()
        f[0]=bar(0,open=110,high=125,low=99,close=118)
        f[1]=bar(1,open=110,high=115,low=104,close=111)
        r=simulate(plan(),f)
        self.assertEqual(r["entry_price"],100)
        self.assertNotEqual(r["exit_date"],str(BASE))
        self.assertEqual(r["exit_reason"],"TIME_EXIT_5TH_SESSION")
        self.assertIn("DEFERRED",r["path_ambiguity"])

    def test_entry_at_open_better_price_and_target_allowed(self):
        f=future()
        f[0]=bar(0,open=97,high=121,low=96,close=115)
        r=simulate(plan(),f)
        self.assertEqual(r["entry_price"],97)
        self.assertEqual(r["exit_reason"],"TARGET")
        self.assertEqual(r["exit_price"],120)

    def test_gap_below_stop_cancels_entry_instead_of_fantasy_fill(self):
        f=future();f[0]=bar(0,open=80,high=95,low=75,close=88)
        r=simulate(plan(),f)
        self.assertEqual(r["outcome"],"CANCEL_OPENED_BELOW_STOP")
        self.assertIsNone(r["entry_price"])

    def test_stop_gap_uses_worse_open_loss_not_stop(self):
        f=future()
        f[0]=bar(0,open=99,high=108,low=98,close=106)
        f[1]=bar(1,open=80,high=88,low=70,close=75)
        r=simulate(plan(),f)
        self.assertEqual(r["exit_reason"],"STOP_GAP_BELOW_STOP")
        self.assertEqual(r["exit_price"],80)
        self.assertLess(r["net_r"],-1)

    def test_target_gap_is_capped_at_limit_target(self):
        f=future()
        f[0]=bar(0,open=99,high=105,low=98,close=104)
        f[1]=bar(1,open=150,high=160,low=145,close=151)
        r=simulate(plan(),f)
        self.assertEqual(r["exit_reason"],"TARGET_GAP_CAPPED")
        self.assertEqual(r["exit_price"],120)

    def test_never_fill_limit_beyond_two_sessions(self):
        f=future()
        for i in range(2):f[i]=bar(i,open=126,high=130,low=122,close=125)
        f[2]=bar(2,open=98,high=107,low=97,close=100)
        r=simulate(plan(),f)
        self.assertEqual(r["outcome"],"NOT_FILLED_WITHIN_2_SESSIONS")
        self.assertIsNone(r["entry_price"])

    def test_partial_future_not_counted_even_if_apparent_winner(self):
        f=future(6);f[0]=bar(0,open=99,high=130,low=98,close=125)
        r=simulate(plan(),f)
        self.assertEqual(r["outcome"],"PENDING_FULL_FORWARD_HORIZON")
        self.assertIsNone(r["exit_price"])

    def test_second_is_independent_and_never_auto_average(self):
        f=future()
        f[0]=bar(0,open=110,high=113,low=97,close=108)
        f[1]=bar(1,open=110,high=112,low=100,close=104)
        first=simulate(plan(),f,"FIRST")
        second=simulate(plan(),f,"SECOND")
        self.assertEqual(first["entry_price"],100)
        self.assertEqual(second["outcome"],"NOT_FILLED_WITHIN_2_SESSIONS")
        self.assertIsNone(second["entry_price"])

    def test_missing_second_is_invalid_not_defaulted(self):
        x=plan(second=None)
        r=simulate(x,future(),"SECOND")
        self.assertEqual(r["outcome"],"INVALID_ENTRY_GEOMETRY")

    def test_held_fifth_candle_closes_position(self):
        f=future()
        f[0]=bar(0,open=98,high=110,low=97,close=103)
        r=simulate(plan(),f)
        self.assertEqual(r["sessions_held"],5)
        self.assertEqual(r["exit_date"],str(BASE+timedelta(days=4)))
        self.assertEqual(r["exit_reason"],"TIME_EXIT_5TH_SESSION")

    def test_target_hit_can_still_be_net_loss_after_fees(self):
        x=plan(first=100,stop=90,target=100.2)
        b=future()
        b[0]=bar(0,open=99,high=101,low=98,close=100.3)
        result=simulate(x,b)
        self.assertEqual(result["exit_reason"],"TARGET")
        self.assertEqual(result["outcome"],"NET_LOSS")
        self.assertTrue(result["target_hit_but_net_loss"])
        diag=stats([result],"FIRST",METHODS[2])
        self.assertEqual(diag["targets_that_lost_after_cost"],1)
        self.assertEqual(diag["wins"],0)

    def test_two_r_shadow_cohort_requires_risk_and_limit_distance(self):
        from shadow_five_day_v59 import geometric_two_r_gate
        p=plan()
        p.update(first_net_rr=2.5,second_net_rr=2.9,
                 first_stop_risk_pct=6,second_stop_risk_pct=3,
                 first_entry_below_close_atr=.5)
        self.assertTrue(geometric_two_r_gate(p,"FIRST"))
        self.assertTrue(geometric_two_r_gate(p,"SECOND"))
        p["first_entry_below_close_atr"]=2
        self.assertFalse(geometric_two_r_gate(p,"FIRST"))
        self.assertTrue(geometric_two_r_gate(p,"SECOND"))
        p["second_net_rr"]=1.5
        self.assertFalse(geometric_two_r_gate(p,"SECOND"))
        p["second_net_rr"]=2.5
        p["second_stop_risk_pct"]=15
        self.assertFalse(geometric_two_r_gate(p,"SECOND"))

    def test_strict_subcohort_has_no_false_live_approval(self):
        p=plan()
        p.update(first_net_rr=2.5,second_net_rr=2.5,
                 first_stop_risk_pct=6,second_stop_risk_pct=4,
                 first_entry_below_close_atr=.5)
        b=future()
        b[0]=bar(0,open=99,high=121,low=98,close=120)
        f=simulate(p,b)
        q=build_report([],{},date(2026,10,23),[f],
                       dict(historical_signal_days=1,
                            trigger_counts={METHODS[2]:1}))
        self.assertEqual(q["only_geometric_2r_scenarios"],1)
        self.assertEqual(q["geometric_2r_only_stats"][METHODS[2]]["FIRST"]["filled"],1)
        self.assertFalse(q["geometric_2r_group_is_validated_win_probability"])
        self.assertEqual(q["validated_live_strategy_trade_count"],0)
        self.assertEqual(q["decision"],"CASH")

    def test_fee_calculation_uses_both_buy_and_sell_and_stop_risk(self):
        net,r=commission_exit(100,90,120)
        paid=100*1.0025;proceeds=120*.9975;stop=90*.9975
        self.assertAlmostEqual(net,100*(proceeds/paid-1),places=4)
        self.assertAlmostEqual(r,(proceeds-paid)/(paid-stop),places=4)
        self.assertLess(commission_exit(100,90,100)[0],0)

    def test_invalid_prices_and_horizon_block(self):
        self.assertIsNone(commission_exit(100,105,120))
        self.assertEqual(simulate(plan(first=90),future())["outcome"],
                         "INVALID_ENTRY_GEOMETRY")
        with self.assertRaises(ValueError):simulate(plan(),future(),"BOTH")

    def test_invalid_archive_date_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"status.json").write_text(
                '{"market_data_date":"2026-10-22","scan_complete":true,"data_date_verified":true}')
            cs,hs,errors=signal_rows_for_historic_selected_universe(
                root,date(2026,10,23))
            self.assertEqual(cs,[])
            self.assertIn("ARCHIVED_RECOVERY_ASOF_MISMATCH",errors)

    def test_hindsight_bias_is_explicit_and_never_approved(self):
        diagnostic=dict(historical_signal_days=0,trigger_counts={})
        r=build_report([],{},date(2026,10,23),[],diagnostic)
        self.assertTrue(r["retrospective_universe_selection_bias"])
        self.assertFalse(r["point_in_time_historical_stock_universe_verified"])
        self.assertFalse(r["historical_daily_price_regular_session_certified"])
        self.assertEqual(r["validated_live_strategy_trade_count"],0)
        self.assertEqual(r["decision"],"CASH")
        self.assertFalse(r["trade_approved"])
        self.assertFalse(r["orders_enabled"])
        self.assertIn("선정편향",markdown(r))

    def test_empty_stats_never_fake_win_percentage(self):
        s=stats([],"FIRST",METHODS[0])
        self.assertIsNone(s["win_rate_pct"])
        self.assertIsNone(s["mean_net_return_pct"])
        self.assertFalse(s["return_is_a_valid_strategy_win_probability"])

    def test_strictly_historical_signal_window_not_23_oct_future(self):
        all_bars=[]
        start=date(2026,4,27)
        for i in range(120):
            d=start+timedelta(days=i)
            cl=100+i*.1
            all_bars.append(dict(date=d,open=cl-.5,high=cl+2,
                low=cl-2,close=cl,volume=1000,source="pykrx"))
        c=dict(ticker="005930",name="TEST",instrument_type="UNKNOWN",
               turnover_source="ESTIMATED_CLOSE_X_VOLUME",
               data_source="pykrx")
        count=[]
        def fake(mock,prefix,snapshot,method,paired=None):
            count.append((snapshot,len(prefix),method))
            return dict(asof=str(snapshot),ticker="005930",
                method=method,setup="NO_CONFIRMED_SETUP")
        with patch("shadow_five_day_v59.evaluate",side_effect=fake):
            r,d=historical_shadow([c],{"005930":all_bars},all_bars[-1]["date"])
        self.assertEqual(r,[])
        self.assertTrue(all(n>=81 and snapshot==all_bars[n-1]["date"]
                            for snapshot,n,m in count))
        self.assertTrue(all(n+7<len(all_bars)+1 for snapshot,n,m in count))
        self.assertFalse(any(snapshot==all_bars[-1]["date"] for snapshot,n,m in count))

if __name__=="__main__":
    unittest.main()
