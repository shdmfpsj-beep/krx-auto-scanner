import unittest
from c3_selection_diagnostic_v5 import outcome,metrics,attribute


def fixture():
    days=['2026-05-'+str(i).zfill(2) for i in range(1,12)]
    rows=[dict(date=d,open=100+i,close=100+i,high=102+i,low=98+i,tradable=True,invalid_data=False,segment=0) for i,d in enumerate(days)]
    market={d:100+i*.5 for i,d in enumerate(days)}
    return days,rows,market


class SelectionDiagnosticTests(unittest.TestCase):
    def test_selection_uses_exact_fifth_later_close(self):
        days,rows,m=fixture();r=outcome('A',days[0],rows,days,5,m)
        self.assertEqual(r['evaluation_date'],days[5]);self.assertAlmostEqual(r['price_move_pct'],5)
        self.assertAlmostEqual(r['excess_pct'],2.5)

    def test_costed_reference_never_buys_signal_close(self):
        days,rows,m=fixture();rows[1]['open']=120;r=outcome('A',days[0],rows,days,5,m)
        self.assertEqual(r['reference_entry_date'],days[1]);self.assertEqual(r['reference_exit_date'],days[6])
        self.assertLess(r['reference_net_pct'],-10)

    def test_later_winner_cannot_change_an_earlier_horizon(self):
        days,rows,m=fixture();a=outcome('A',days[0],rows,days,5,m)
        rows[7]['close']=100000;self.assertEqual(a,outcome('A',days[0],rows,days,5,m))

    def test_action_boundary_is_unknown_not_zero_return(self):
        days,rows,m=fixture();rows[3]['segment']=1;r=outcome('A',days[0],rows,days,5,m)
        self.assertEqual(r['status'],'CENSORED_REFERENCE_OR_HISTORY_RESET');self.assertNotIn('excess_pct',r)

    def test_missing_and_halted_paths_are_not_silently_dropped(self):
        days,rows,m=fixture();rows[3]['tradable']=False;r=outcome('A',days[0],rows,days,5,m);a=metrics([r])
        self.assertEqual(a['selected'],1);self.assertEqual(a['completed'],0);self.assertIsNone(a['mean_excess_pct'])

    def test_future_window_is_pending_not_zero_profit(self):
        days,rows,m=fixture();r=outcome('A',days[0],rows,days,20,m)
        self.assertEqual(r['status'],'INCOMPLETE_WINDOW');self.assertIsNone(metrics([r])['mean_costed_next_open_reference_pct'])

    def test_correct_selection_missed_limit_and_losing_trade_are_distinct(self):
        p=dict(ticker='A',decision_date='2026-05-01',high=90,reference_close=100,net_r1_rr=.5)
        orders=[dict(plan=p,status='DAY_EXPIRED_NO_TOUCH')]
        ref=lambda p:dict(status='COMPLETE',price_move_pct=10,excess_pct=5)
        a,_=attribute(orders,[],ref);self.assertEqual(a['counts'],dict(OUTPERFORMER_NOT_FILLED=1))
        orders[0]['status']='MODEL_ENTRY';trades=[dict(ticker='A',decision_date=p['decision_date'],net_pct=-3,mature=True)]
        b,_=attribute(orders,trades,ref);self.assertEqual(b['counts'],dict(OUTPERFORMER_BUT_TRADE_LOST=1))

    def test_market_underperformance_is_not_blame_assigned_to_the_limit(self):
        p=dict(ticker='A',decision_date='2026-05-01',high=90,reference_close=100,net_r1_rr=-.2)
        a,_=attribute([dict(plan=p,status='DAY_EXPIRED_NO_TOUCH')],[],lambda p:dict(status='COMPLETE',price_move_pct=5,excess_pct=-2))
        self.assertEqual(a['counts'],dict(SELECTION_DID_NOT_OUTPERFORM=1));self.assertEqual(a['r1_costed_reward_nonpositive_orders'],1)


if __name__=='__main__':unittest.main()
