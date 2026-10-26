import copy
import math
import unittest
from datetime import date, timedelta

import c3_event_replay_v637 as m


def bar(day, op=100., hi=103., lo=99., cl=102., atr=2., ma5=101.):
    return dict(date=day, open=op, high=hi, low=lo, close=cl, atr14=atr, ma5=ma5)


class EventReplayTests(unittest.TestCase):
    def setUp(self):
        self.days = [str(date(2026, 1, 2) + timedelta(days=i)) for i in range(16)]
        self.bars = {d: bar(d) for d in self.days}
        self.sig = dict(asof=self.days[0], ticker='000001', signal_close=100.,
                        stopD=94., atr14=4., market_trend=True)

    def run_case(self, policy=None, signals=None, prices=None, days=None):
        return m.replay(days or self.days, prices or {'000001': self.bars},
                        signals if signals is not None else [self.sig],
                        policy or m.Policy(exit='STRUCT_D5'))

    def test_iso_method_pollution_rejected(self):
        with self.assertRaises(ValueError):
            m.iso_day('<bound method Series.asof>')

    def test_iso_noncanonical_rejected(self):
        with self.assertRaises(ValueError):
            m.iso_day('20260102')

    def test_duplicate_sessions_rejected(self):
        with self.assertRaises(ValueError):
            self.run_case(days=[self.days[0], self.days[0]])

    def test_one_pick_per_day_required(self):
        with self.assertRaises(ValueError):
            self.run_case(signals=[self.sig, dict(self.sig, ticker='000002')])

    def test_unequal_prices_do_not_break_cash(self):
        for p in [99.99, 100., 102.49]:
            b=copy.deepcopy(self.bars);b[self.days[1]]=bar(self.days[1], p, 104., 99., 102.)
            r=self.run_case(prices={'000001': b})
            self.assertTrue(all(d['cash_krw'] >= 0 for d in r['daily']))

    def test_quantity_reserves_buy_fees(self):
        q=m.share_qty(1000.,100.,100.,99.9,m.Costs(.0015,.005),.03)
        self.assertEqual(q, 0)

    def test_quantity_risk_budget(self):
        q=m.share_qty(1e6,1e6,100.,94.)
        damage=q*(100.*1.0015-94.*.995)
        self.assertLessEqual(damage, 10000.)

    def test_invalid_quantities_fail_closed(self):
        for entry in [float('nan'),float('inf'),-1,True]:
            self.assertEqual(m.share_qty(100.,100.,entry,50.),0)

    def test_rr_boundary_algebra(self):
        cap=m.maximum_entry_rr2(90.,130.)
        self.assertAlmostEqual(m.net_rr(cap,90.,130.),2.)

    def test_unknown_resistance_not_infinite_reward(self):
        self.assertIsNone(m.maximum_entry_rr2(90.,None))

    def test_rr_gate_rejects_unknown(self):
        r=self.run_case(m.Policy(require_rr2=True))
        self.assertEqual(r['summary']['closed_trades'],0)
        self.assertIn('NO_DATED_RESISTANCE',[x['event'] for x in r['events']])

    def test_same_day_entry_forbidden(self):
        p,_=m.make_pending(self.sig,m.Policy(),m.BASE_COST,1e6,1e6,0)
        with self.assertRaises(ValueError):
            m.pending_step(p,self.bars[self.days[0]],0,m.Policy(),m.BASE_COST,1e6,1e6)

    def test_quantity_frozen_before_open(self):
        p=m.Policy(exit='STRUCT_D5'); q=[]
        for op in [99.,102.]:
            b=copy.deepcopy(self.bars);b[self.days[1]]=bar(self.days[1],op,104.,98.,102.)
            q.append(self.run_case(p,prices={'000001':b})['trades'][0]['qty'])
        self.assertEqual(q[0],q[1])

    def test_late_signal_not_discarded_for_missing_12_days(self):
        sig=dict(self.sig,asof=self.days[-2])
        r=self.run_case(m.Policy(),signals=[sig])
        self.assertEqual(r['summary']['open_position_count'],1)
        self.assertEqual(r['summary']['closed_trades'],0)

    def test_open_equity_reconciles_fees_and_unrealized(self):
        sig=dict(self.sig,asof=self.days[-2])
        r=self.run_case(m.Policy(),signals=[sig]);s=r['summary']
        self.assertAlmostEqual(s['final_equity_krw']-1e6,s['closed_pnl_krw']+s['open_liquidation_pnl_krw'])

    def test_no_forced_end_of_data_exit(self):
        r=self.run_case(m.Policy(),days=self.days[:3])
        self.assertEqual(r['summary']['open_position_count'],1)
        self.assertEqual(r['summary']['closed_trades'],0)

    def test_marked_drawdown_includes_open_loss(self):
        b=copy.deepcopy(self.bars);b[self.days[2]]=bar(self.days[2],100.,101.,96.,97.)
        r=self.run_case(m.Policy(),prices={'000001':b},days=self.days[:3])
        self.assertLess(r['summary']['daily_liquidation_mdd_pct'],0)
        self.assertEqual(r['summary']['closed_trades'],0)

    def test_cash_closed_ledger_reconciles(self):
        r=self.run_case();s=r['summary']
        self.assertAlmostEqual(s['final_equity_krw'],1e6+sum(t['pnl_krw'] for t in r['trades']))

    def test_gap_through_stop_uses_open(self):
        b=copy.deepcopy(self.bars);b[self.days[2]]=bar(self.days[2],90.,93.,88.,91.)
        t=self.run_case(prices={'000001':b})['trades'][0]
        self.assertEqual(t['exit_price'],90.)
        self.assertLess(t['pnl_krw'],-t['planned_risk_krw'])

    def test_current_high_cannot_create_same_day_stop(self):
        b=copy.deepcopy(self.bars);b[self.days[1]]=bar(self.days[1],100.,120.,99.,110.)
        r=self.run_case(m.Policy(exit='LEGACY_TRAIL7_D12'),prices={'000001':b},days=self.days[:2])
        self.assertEqual(r['summary']['open_position_count'],1)

    def test_new_atr_trail_waits_for_close_1r(self):
        r=self.run_case(m.Policy(),days=self.days[:2])
        self.assertFalse(r['open_position']['trail_active'])
        self.assertEqual(r['open_position']['active_stop'],94.)

    def test_atr_trail_activates_next_session(self):
        b=copy.deepcopy(self.bars);b[self.days[1]]=bar(self.days[1],100.,112.,99.,110.)
        r=self.run_case(m.Policy(),prices={'000001':b},days=self.days[:2])
        self.assertTrue(r['open_position']['trail_active'])
        self.assertEqual(r['open_position']['active_stop'],106.)

    def test_d5_close_decision_exits_d6_open(self):
        b=copy.deepcopy(self.bars)
        for d in self.days[1:6]:b[d]=bar(d,100.,103.,99.,100.,2.,102.)
        b[self.days[6]]=bar(self.days[6],101.,103.,90.,100.)
        t=self.run_case(m.Policy(),prices={'000001':b})['trades'][0]
        self.assertEqual(t['exit_date'],self.days[6])
        self.assertEqual(t['exit_price'],101.)
        self.assertEqual(t['reason'],'WEAK_D5_EXIT_D6_OPEN')

    def test_limit_exact_low_touch_unfilled(self):
        b=copy.deepcopy(self.bars)
        for d in self.days[1:3]:b[d]=bar(d,100.,103.,99.,102.)
        r=self.run_case(m.Policy(entry='RETEST_2D'),prices={'000001':b})
        self.assertEqual(r['summary']['closed_trades'],0)
        self.assertIn('EXPIRED_UNFILLED',[e['event'] for e in r['events']])

    def test_limit_trade_through_one_tick(self):
        b=copy.deepcopy(self.bars);b[self.days[1]]=bar(self.days[1],100.,103.,98.,102.)
        r=self.run_case(m.Policy(entry='RETEST_2D',exit='STRUCT_D5'),prices={'000001':b})
        self.assertEqual(r['trades'][0]['entry'],99.)

    def test_better_open_limit_fill(self):
        b=copy.deepcopy(self.bars);b[self.days[1]]=bar(self.days[1],98.5,103.,98.,102.)
        r=self.run_case(m.Policy(entry='RETEST_2D',exit='STRUCT_D5'),prices={'000001':b})
        self.assertEqual(r['trades'][0]['entry'],98.5)

    def test_gap_cancel_never_switches_to_other_stock(self):
        b=copy.deepcopy(self.bars);b[self.days[1]]=bar(self.days[1],110.,112.,108.,111.)
        r=self.run_case(prices={'000001':b,'000002':self.bars})
        self.assertEqual(r['summary']['closed_trades'],0)
        self.assertIn('GAP_CANCEL_NO_REPLACEMENT',[e['event'] for e in r['events']])

    def test_pending_order_reserves_only_slot(self):
        sig2=dict(self.sig,asof=self.days[1],ticker='000002')
        r=self.run_case(m.Policy(entry='RETEST_2D'),signals=[self.sig,sig2],
                        prices={'000001':self.bars,'000002':self.bars})
        ev=[e for e in r['events'] if e['date']==self.days[1] and e['ticker']=='000002']
        self.assertEqual(ev[0]['event'],'ONE_SLOT_BUSY_OR_RESERVED')

    def test_confirm_uses_d1_close_then_d2_open(self):
        b=copy.deepcopy(self.bars);b[self.days[1]]=bar(self.days[1],100.,103.,99.,102.)
        r=self.run_case(m.Policy(entry='CONFIRM_D2',exit='STRUCT_D5'),prices={'000001':b})
        t=r['trades'][0]
        self.assertEqual(t['entry_date'],self.days[2])
        self.assertEqual(t['order_decision_date'],self.days[1])

    def test_confirm_d2_prices_cannot_change_d1_order(self):
        p=m.Policy(entry='CONFIRM_D2');r=self.run_case(p,days=self.days[:2])
        before=r['pending_order']
        b=copy.deepcopy(self.bars);b[self.days[2]]=bar(self.days[2],100.,10000.,1.,5000.)
        after=self.run_case(p,prices={'000001':b},days=self.days[:2])['pending_order']
        self.assertEqual(before,after)

    def test_missing_bar_halts_instead_of_skipping(self):
        b=copy.deepcopy(self.bars);del b[self.days[2]]
        r=self.run_case(m.Policy(),prices={'000001':b})
        self.assertTrue(r['summary']['halted'])
        self.assertIsNone(r['summary']['account_roi_pct'])

    def test_corporate_gap_halts_without_future_reselection(self):
        b=copy.deepcopy(self.bars);b[self.days[2]]=bar(self.days[2],50.,53.,48.,51.)
        r=self.run_case(m.Policy(),prices={'000001':b})
        self.assertTrue(r['summary']['halted'])
        self.assertEqual(r['summary']['closed_trades'],0)

    def test_truncated_prefix_matches_full_run_to_that_day(self):
        p=m.Policy();full=self.run_case(p);short=self.run_case(p,days=self.days[:4])
        self.assertEqual(full['daily'][:4],short['daily'])
        self.assertEqual([e for e in full['events'] if e['date']<=self.days[3]],short['events'])

    def test_market_filter_uses_signal_day_only(self):
        s=dict(self.sig,market_trend=False)
        r=self.run_case(m.Policy(regime='BENCH_TREND'),signals=[s])
        self.assertEqual(r['summary']['closed_trades'],0)

    def test_no_same_exit_day_reselection(self):
        s=dict(self.sig,asof=self.days[5]);r=self.run_case(signals=[self.sig,s])
        self.assertEqual(r['summary']['closed_trades'],1)

    def test_never_approves_trading(self):
        r=self.run_case()
        self.assertIs(r['summary']['trade_approved'],False)
        self.assertIs(r['summary']['orders_enabled'],False)

    def test_new_signal_not_dropped_at_calendar_month_end(self):
        r=self.run_case(m.Policy(),days=self.days[:3])
        self.assertEqual(len(r['daily']),3)
        self.assertNotEqual(r['daily'][-1]['equity_krw'],1e6)

    def test_purge_removes_holding_interval_crossing_split(self):
        rows=[dict(asof='2026-01-02',exit_date='2026-06-29'),
              dict(asof='2026-06-25',exit_date='2026-07-02'),
              dict(asof='2026-07-03',exit_date='2026-07-08')]
        got=m.purge_training_intervals(rows,'2026-07-01','2026-10-23')
        self.assertEqual(got,rows[:1])

    def test_embargo_uses_session_count(self):
        rows=[dict(asof=self.days[0],exit_date=self.days[3])]
        self.assertEqual(m.purge_training_intervals(rows,self.days[5],self.days[8],2,self.days),[])

    def test_unconfirmed_pivot_not_counted(self):
        h=[bar(d,100.,101.,99.,100.) for d in self.days[:7]]
        h[-1]['high']=130.
        self.assertIsNone(m.resistance_clusters(h,105.,2.))

    def test_two_separated_confirmed_resistance_touches(self):
        h=[bar(d,100.,101.,99.,100.) for d in self.days]
        h[3]['high']=120.;h[9]['high']=120.5
        r=m.resistance_clusters(h,105.,2.)
        self.assertEqual(r['price'],120.)
        self.assertEqual(r['touches'],2)

    def test_tick_boundaries(self):
        for x in [1999.9,2000.,4999.,5000.,19999.,20000.,49999.,50000.,199999.,200000.]:
            v=m.floor_tick(x)
            self.assertLessEqual(v,x)
            self.assertEqual(v % m.tick(v),0)

    def test_confirmed_daily_pivot_waits_for_two_right_bars(self):
        h=[bar(d) for d in self.days[:7]];h[-1]['low']=80.
        self.assertIsNone(m.confirmed_daily_stop(h,2.))

    def test_confirmed_daily_stop_has_dated_evidence(self):
        h=[bar(d) for d in self.days[:8]];h[3]['low']=90.
        r=m.confirmed_daily_stop(h,2.)
        self.assertEqual(r['pivot_date'],self.days[3])
        self.assertEqual(r['confirmation_date'],self.days[5])
        self.assertLess(r['stop'],90.)

    def test_missing_confirmed_pivot_cancels_without_substitute(self):
        s=dict(self.sig,requires_confirmed_pivot=True,confirmed_pivot_evidence=None)
        r=self.run_case(signals=[s])
        self.assertEqual(r['summary']['closed_trades'],0)
        self.assertEqual(r['events'][0]['event'],'NO_CONFIRMED_DAILY_PIVOT')

    def test_invalid_policy_rejected(self):
        with self.assertRaises(ValueError):m.Policy(entry='CHOOSE_BEST_FUTURE')
        with self.assertRaises(ValueError):m.Policy(limit_penetration_ticks=0)

    def test_cost_stress_on_same_closed_fill_lowers_pnl(self):
        b=self.run_case(m.Policy(exit='STRUCT_D5'))
        s=m.replay(self.days,{'000001':self.bars},[self.sig],m.Policy(exit='STRUCT_D5'),m.STRESS_COST)
        self.assertLess(s['trades'][0]['net_pct'],b['trades'][0]['net_pct'])


if __name__=='__main__':unittest.main()
