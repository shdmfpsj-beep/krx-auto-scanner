import copy,unittest
from datetime import date,timedelta
import c3_execution_v638 as m
import c3_event_replay_v637 as old


def b(day,o=100.,h=103.,l=99.,c=102.,a=4.,ma=101.):
    return dict(date=day,open=o,high=h,low=l,close=c,atr14=a,ma5=ma)


class RestingExecutionTests(unittest.TestCase):
    def setUp(self):
        self.days=[str(date(2026,1,2)+timedelta(days=i)) for i in range(18)]
        self.bars={d:b(d) for d in self.days}
        self.sig=dict(asof=self.days[0],ticker='000001',signal_close=100.,stopD=94.,atr14=4.,market_trend=True)
    def run_case(self,p=None,bars=None,signals=None,days=None):
        return m.replay(days or self.days,{'000001':bars or self.bars},signals or [self.sig],p or m.Policy())
    def test_price_gap_cannot_cancel_resting_order_after_open(self):
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],110.,112.,98.,105.)
        r=self.run_case(bars=bars,days=self.days[:2]);self.assertEqual(r['open_position']['price'],99.)
    def test_gap_below_structure_is_recorded_not_silently_cancelled(self):
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],92.,96.,90.,95.)
        r=self.run_case(bars=bars);t=r['trades'][0]
        self.assertEqual(t['entry'],92.);self.assertEqual(t['exit_price'],92.)
        self.assertLess(t['pnl_krw'],0);self.assertGreater(t['planned_risk_krw'],0)
        self.assertTrue(t['unwanted_open_fill_through_structure'])
    def test_quantity_fixed_even_with_better_open(self):
        qs=[]
        for op in [95.,98.]:
            bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],op,104.,94.5,102.)
            qs.append(self.run_case(bars=bars,days=self.days[:2])['open_position']['qty'])
        self.assertEqual(qs[0],qs[1])
    def test_exact_limit_touch_does_not_fill(self):
        r=self.run_case(m.Policy(entry='REST_1D'));self.assertEqual(r['summary']['closed_trades'],0)
    def test_one_day_order_expires_before_second_day(self):
        bars=copy.deepcopy(self.bars);bars[self.days[2]]=b(self.days[2],100.,103.,97.,102.)
        r=self.run_case(m.Policy(entry='REST_1D'),bars);self.assertEqual(r['summary']['closed_trades'],0)
    def test_two_day_order_may_fill_second_day(self):
        bars=copy.deepcopy(self.bars);bars[self.days[2]]=b(self.days[2],100.,103.,97.,102.)
        r=self.run_case(m.Policy(entry='REST_2D'),bars);self.assertEqual(r['trades'][0]['entry_date'],self.days[2])
    def test_confirmation_creates_order_after_completed_d1(self):
        bars=copy.deepcopy(self.bars);bars[self.days[2]]=b(self.days[2],102.,104.,99.,103.)
        r=self.run_case(m.Policy(entry='CONFIRM_THEN_REST'),bars)
        self.assertEqual(r['trades'][0]['entry_date'],self.days[2])
        self.assertEqual(r['trades'][0]['order_decision_date'],self.days[1])
    def test_confirmation_order_is_frozen_before_d2(self):
        p=m.Policy(entry='CONFIRM_THEN_REST');r=self.run_case(p,days=self.days[:2])
        self.assertEqual(r['pending_order']['cap'],101)
        self.assertEqual(r['summary']['closed_trades'],0)
    def test_unknown_large_gap_halts_pending_history(self):
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],50.,55.,45.,53.)
        r=self.run_case(bars=bars)
        self.assertTrue(r['summary']['halted']);self.assertIsNone(r['summary']['account_roi_pct'])
    def test_missed_order_is_not_replaced_using_future_return(self):
        s=dict(self.sig,simulated_fill_allowed=False)
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],98.,120.,97.,110.)
        r=self.run_case(signals=[s],bars=bars)
        self.assertEqual(r['summary']['closed_trades'],0)
        self.assertIn('SIMULATED_MISSED_ORDER_EXPIRED',[e['event'] for e in r['events']])
    def test_intraday_entry_does_not_capture_earlier_target_high(self):
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],100.,120.,98.,105.)
        r=self.run_case(m.Policy(exit='TARGET10_D12'),bars,days=self.days[:2])
        self.assertEqual(r['summary']['open_position_count'],1)
    def test_target_after_open_entry_requires_trade_through(self):
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],98.,110.,97.,109.)
        r=self.run_case(m.Policy(exit='TARGET10_D12'),bars)
        self.assertEqual(r['trades'][0]['reason'],'TARGET_TRADED_THROUGH_PROXY')
        self.assertEqual(r['trades'][0]['exit_price'],109.)
    def test_target_exact_high_touch_unfilled(self):
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],98.,109.,97.,108.)
        r=self.run_case(m.Policy(exit='TARGET10_D12'),bars,days=self.days[:2])
        self.assertEqual(r['summary']['open_position_count'],1)
    def test_stop_has_priority_when_target_and_stop_intraday(self):
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],98.,120.,90.,110.)
        r=self.run_case(m.Policy(exit='TARGET10_D12'),bars)
        self.assertEqual(r['trades'][0]['exit_price'],94.)
    def test_later_open_target_executes_before_later_intraday_low(self):
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],98.,103.,97.,102.)
        bars[self.days[2]]=b(self.days[2],112.,114.,90.,100.)
        r=self.run_case(m.Policy(exit='TARGET10_D12'),bars)
        self.assertEqual(r['trades'][0]['exit_price'],112.)
    def test_current_high_does_not_move_close_based_trail(self):
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],98.,1000.,97.,101.)
        r=self.run_case(bars=bars,days=self.days[:2])
        self.assertFalse(r['open_position']['trail_active'])
    def test_stop_slippage_stress_lowers_gap_exit(self):
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],98.,103.,97.,102.)
        bars[self.days[2]]=b(self.days[2],90.,93.,85.,91.)
        a=self.run_case(bars=bars)['trades'][0];c=self.run_case(m.Policy(extra_stop_slippage=.003),bars)['trades'][0]
        self.assertLess(c['pnl_krw'],a['pnl_krw'])
    def test_cash_equity_and_closed_pnl_reconcile(self):
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],98.,103.,97.,102.)
        r=self.run_case(m.Policy(exit='STRUCT_D5'),bars);s=r['summary']
        self.assertAlmostEqual(s['final_equity_krw'],1e6+s['closed_pnl_krw']+s['open_liquidation_pnl_krw'])
    def test_no_future_bar_changes_prefix(self):
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],98.,103.,97.,102.)
        p=m.Policy();a=self.run_case(p,bars,days=self.days[:3]);z=self.run_case(p,bars)
        self.assertEqual(a['daily'],z['daily'][:3])
    def test_v638_does_not_mutate_v637_globals(self):
        a=old.replay(self.days,{'000001':self.bars},[self.sig])
        self.run_case();z=old.replay(self.days,{'000001':self.bars},[self.sig])
        self.assertEqual(a,z)
    def test_never_approves_actual_orders(self):
        r=self.run_case();self.assertIs(r['summary']['orders_enabled'],False)
        self.assertIs(r['summary']['trade_approved'],False)
    def test_invalid_policy_cannot_be_instantiated(self):
        with self.assertRaises(ValueError):m.Policy(entry='AFTER_SEEING_WINNER')

    def test_D0_known_cash_alternative_is_frozen_before_any_open(self):
        expensive=dict(self.sig,ticker='999999',signal_close=1e6,stopD=9e5,atr14=1e4)
        expensive['D_ranked_candidates']=[dict(expensive),dict(self.sig)]
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],98.,103.,97.,102.)
        p=m.Policy(entry='REST_1D',exit='STRUCT_D5',D0_affordability_alternative=True)
        r=m.replay(self.days,{'000001':bars},[expensive],p)
        self.assertEqual(r['trades'][0]['ticker'],'000001')
        self.assertEqual(r['trades'][0]['D0_affordability_rank'],2)
        self.assertEqual(r['events'][0]['date'],self.sig['asof'])
        self.assertEqual(r['events'][0]['ticker'],'000001')

    def test_affordable_D0_pick_cannot_be_replaced_after_unfilled_D1(self):
        sig=dict(self.sig,D_ranked_candidates=[dict(self.sig),dict(self.sig,ticker='000002')])
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],110.,112.,105.,111.)
        second=copy.deepcopy(self.bars);second[self.days[1]]=b(self.days[1],98.,103.,97.,102.)
        p=m.Policy(entry='REST_1D',D0_affordability_alternative=True)
        r=m.replay(self.days,{'000001':bars,'000002':second},[sig],p)
        self.assertEqual(r['summary']['closed_trades'],0)

    def test_future_dated_alternative_is_forbidden(self):
        sig=dict(self.sig,D_ranked_candidates=[dict(self.sig,asof=self.days[1])])
        with self.assertRaises(ValueError):
            self.run_case(m.Policy(D0_affordability_alternative=True),signals=[sig])

    def test_failed_rebound_close_exits_only_next_open(self):
        sig=dict(self.sig,signal_low=98.)
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],98.,100.,95.,95.5)
        bars[self.days[2]]=b(self.days[2],96.,100.,92.,98.)
        r=self.run_case(m.Policy(exit='STRUCT_D5',failure_close_exit=True),bars,[sig])
        t=r['trades'][0];self.assertEqual(t['exit_date'],self.days[2])
        self.assertEqual(t['exit_price'],96.)
        self.assertEqual(t['reason'],'FAILED_REBOUND_CLOSE_EXIT_NEXT_OPEN')

    def test_fixed_horizon_neighbor_is_preplanned(self):
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],98.,103.,97.,102.)
        r=self.run_case(m.Policy(exit='STRUCT_D5',fixed_exit_sessions=3),bars)
        self.assertEqual(r['trades'][0]['hold_sessions'],3)

    def test_invalid_candle_halts_instead_of_allowing_more_signals(self):
        bars=copy.deepcopy(self.bars);bars[self.days[1]]=b(self.days[1],98.,103.,97.,102.)
        bars[self.days[2]]=b(self.days[2],0.,0.,0.,0.)
        r=self.run_case(bars=bars)
        self.assertTrue(r['summary']['halted']);self.assertIsNone(r['summary']['final_equity_krw'])


class UnbrokenStructureTests(unittest.TestCase):
    def history(self,n=10):
        days=[str(date(2026,1,2)+timedelta(days=i)) for i in range(n)]
        h=[b(d) for d in days];h[3]['low']=90.;return h
    def test_confirmed_but_broken_pivot_is_rejected(self):
        h=self.history();h[-1]['low']=88.
        self.assertIsNotNone(old.confirmed_daily_stop(h,4.))
        self.assertIsNone(m.unbroken_daily_stop(h))
    def test_unbroken_pivot_has_dated_confirmation(self):
        h=self.history();r=m.unbroken_daily_stop(h)
        self.assertEqual(r['pivot_date'],h[3]['date']);self.assertEqual(r['confirmation_date'],h[5]['date'])
    def test_buffer_frozen_at_confirmation_not_later_atr(self):
        h=self.history();r=m.unbroken_daily_stop(h)
        h[-1]['atr14']=100.
        self.assertEqual(r['stop'],m.unbroken_daily_stop(h)['stop'])
    def test_later_atr_cannot_rescue_a_broken_pivot(self):
        h=self.history();h[-1]['low']=88.;h[-1]['atr14']=100.
        self.assertIsNone(m.unbroken_daily_stop(h))
    def test_two_right_bars_required(self):
        h=self.history(6);h[-1]['low']=80.;self.assertIsNone(m.unbroken_daily_stop(h))
    def test_stale_pivot_not_reused(self):
        self.assertIsNone(m.unbroken_daily_stop(self.history(40)))
    def test_no_older_pivot_fallback_after_latest_failed(self):
        h=self.history(14);h[3]['low']=80.;h[8]['low']=90.;h[-1]['low']=88.
        self.assertIsNone(m.unbroken_daily_stop(h))
    def test_unconfirmed_future_low_cannot_change_prefix(self):
        h=self.history();a=m.unbroken_daily_stop(h[:-1]);h[-1]['low']=1.
        self.assertEqual(a,m.unbroken_daily_stop(h[:-1]))


if __name__=='__main__':unittest.main()
