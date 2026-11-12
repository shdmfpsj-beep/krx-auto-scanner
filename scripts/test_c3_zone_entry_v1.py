import copy,unittest
from datetime import date,timedelta
from unittest.mock import patch
import c3_zone_entry_v1 as z
from c3_zone_execution_v1 import simulate


def fixture(n=35):
    b=[dict(date=(date(2026,1,1)+timedelta(days=i)).isoformat(),open=105,high=108,low=103,close=106,volume=10000,turnover_krw=1060000,segment=0,tradable=True) for i in range(n)]
    return b,[x['date'] for x in b],dict(high=101,low=99,stop=95,resistance=115,resistance2=125)


class ZoneMath(unittest.TestCase):
    def test_user_samsung_integer_limit_quantities(self):
        a=z.allocation(dict(high=63500,low=60700,stop=57700,resistance=65500,resistance2=None))
        self.assertEqual([x['quantity'] for x in a['legs']],[39,41]);self.assertAlmostEqual(a['weighted_average_price'],62065);self.assertLessEqual(a['costed_krw'],5000000)
    def test_single_and_two_leg_share_the_same_planned_capital(self):
        p=dict(high=101,low=99,stop=95,resistance=115,resistance2=None)
        for split in [(1,0),(.5,.5),(.5,0)]:self.assertEqual(z.allocation(p,split)['capital_krw'],5000000)
    def test_half_upper_has_uninvested_cash(self):
        a=z.allocation(dict(high=101,low=99,stop=95,resistance=115,resistance2=None),(.5,0));self.assertGreaterEqual(a['cash_unspent_krw'],2500000)
    def test_averaging_does_not_hide_absolute_risk(self):
        p=dict(high=101,low=99,stop=95,resistance=115,resistance2=None);both=z.allocation(p);half=z.allocation(p,(.5,0))
        self.assertGreater(both['full_stop_loss_krw'],half['full_stop_loss_krw'])
    def test_first_only_and_full_rr_are_separate(self):
        p=dict(high=63500,low=60700,stop=57700,resistance=65500,resistance2=None);a=z.allocation(p)
        self.assertNotEqual(a['first_only_net_r1_rr'],a['full_fill_net_r1_rr']);self.assertIsNone(a['full_fill_net_r2_rr'])
    def test_invalid_weights_rejected(self):
        with self.assertRaises(ValueError):z.allocation(dict(high=101,low=99,stop=95),(.8,.8))
    def test_pivot_zone_is_not_two_independent_supports(self):
        b,_,_=fixture(90)
        for i,x in enumerate(b):x.update(open=100+i,close=101+i,high=103+i,low=99+i)
        b[-5]['low']=180;b[-4]['low']=181;b[-3]['low']=182;b[-2]['low']=183;b[-1]['low']=184
        with patch.object(z,'confirmed_pivots',return_value=[(85,180)]),patch.object(z,'resistance_levels',return_value=[dict(price=220)]):
            p,_=z.zone_plan(b)
        self.assertTrue(p['lower_is_same_zone_not_independent_support']);self.assertEqual(p['support'],180);self.assertFalse(p['original_stop_modified'])
    def test_zone_never_uses_future_bar(self):
        b,_,_=fixture(100);p=z.zone_plan(b[:80]);b[90]['low']=1;self.assertEqual(p,z.zone_plan(b[:80]))
    def test_missing_support_has_no_invented_range(self):
        b,_,_=fixture(80)
        with patch.object(z,'confirmed_pivots',return_value=[]):self.assertIsNone(z.zone_plan(b)[0])
    def test_nominal_reported_price_scenario_is_not_broker_proof(self):
        r=z.reported_limit_mark(dict(high=63500,low=60700,stop=57700,resistance=65500,resistance2=None),66400)
        self.assertAlmostEqual(r['allocation']['weighted_average_price'],62065);self.assertFalse(r['actual_fill_verified'])


class EvidenceExport(unittest.TestCase):
    def test_csv_schema_same_with_or_without_interval(self):
        from c3_zone_study_v1 import flat_metric
        a=flat_metric(dict(n=1,descriptive_month_cluster_ci=None,market_regime={}));b=flat_metric(dict(n=30,descriptive_month_cluster_ci=[-1,2],market_regime={}))
        self.assertEqual(list(a),list(b));self.assertIsNone(a['ci95_low']);self.assertEqual(b['ci95_high'],2)
    def test_cross_envelopes_cover_independent_path_difference(self):
        from c3_zone_study_v1 import paired_delta
        o={m:{'1':{'20':dict(conservative_plan_return_pct=1,optimistic_plan_return_pct=3)}} for m in z.MODELS}
        r=paired_delta([dict(date='2026-01-01',outcomes=o)],z.MODELS[1],z.MODELS[0]);self.assertEqual(r['mean_cross_envelope_lower_pct'],-2);self.assertEqual(r['mean_cross_envelope_upper_pct'],2)


class QueuedLimitExecution(unittest.TestCase):
    def test_first_only(self):
        b,s,p=fixture();b[1].update(open=101,low=100,high=108,close=106)
        r=simulate(p,b,0,s);self.assertTrue(r['first_filled']);self.assertFalse(r['second_filled'])
    def test_both_limits_fill_on_descent(self):
        b,s,p=fixture();b[1].update(open=105,low=98,high=108,close=106)
        r=simulate(p,b,0,s);self.assertTrue(r['first_filled']);self.assertTrue(r['second_filled']);self.assertEqual([f['price'] for f in r['worst']['fills']],[101,99])
    def test_unfilled_capital_is_cash(self):
        b,s,p=fixture();r=simulate(p,b,0,s);self.assertEqual(r['conservative_plan_return_pct'],0);self.assertFalse(r['first_filled'])
    def test_open_inside_zone_only_upper_is_marketable(self):
        b,s,p=fixture();b[1].update(open=100,low=99.5,high=107,close=106)
        r=simulate(p,b,0,s);self.assertEqual(r['worst']['fills'][0]['price'],100);self.assertFalse(r['second_filled'])
    def test_gap_below_zone_fills_both_not_retro_cancel(self):
        b,s,p=fixture();b[1].update(open=98,low=97,high=103,close=102)
        r=simulate(p,b,0,s);self.assertTrue(r['second_filled']);self.assertEqual([f['price'] for f in r['worst']['fills']],[98,98])
    def test_quantity_fixed_before_better_open(self):
        b,s,p=fixture();b[1].update(open=98,low=97,high=103,close=102);r=simulate(p,b,0,s)
        self.assertEqual([f['quantity'] for f in r['worst']['fills']],[l['quantity'] for l in z.allocation(p)['legs']])
    def test_both_orders_and_stop_are_charged(self):
        b,s,p=fixture();b[1].update(open=105,low=94,high=108,close=96)
        r=simulate(p,b,0,s);self.assertTrue(r['second_filled']);self.assertTrue(r['worst']['stop_occurred']);self.assertLess(r['conservative_plan_return_pct'],0)
    def test_open_below_stop_exposes_queued_orders(self):
        b,s,p=fixture();b[1].update(open=90,low=85,high=96,close=93)
        r=simulate(p,b,0,s);self.assertTrue(r['second_filled']);self.assertTrue(r['ambiguous']);self.assertEqual(r['worst']['exit']['price'],85);self.assertIn('AUCTION_BUYS_BELOW_STOP_EXECUTION_UNCERTAIN',r['worst']['flags'])
    def test_unknown_high_low_sequence_reports_bounds(self):
        b,s,p=fixture();b[1].update(open=105,low=98,high=120,close=110)
        r=simulate(p,b,0,s);self.assertTrue(r['ambiguous']);self.assertLess(r['conservative_plan_return_pct'],r['optimistic_plan_return_pct'])
    def test_target_before_second_on_later_day_has_two_outcomes(self):
        b,s,p=fixture();b[1].update(open=101,low=100,high=108,close=106);b[2].update(open=106,low=98,high=120,close=110)
        r=simulate(p,b,0,s,validity=2);self.assertTrue(r['ambiguous']);self.assertTrue(r['second_fill_possible'])
    def test_exact_touch_not_certified_as_definite_fill(self):
        b,s,p=fixture();b[1].update(open=105,low=101,high=108,close=106)
        r=simulate(p,b,0,s);self.assertTrue(r['ambiguous']);self.assertTrue(r['first_fill_possible'])
    def test_validity_extension_allows_second_only_during_window(self):
        b,s,p=fixture();b[1].update(open=101,low=100,high=108,close=106);b[2].update(open=103,low=98,high=108,close=106)
        self.assertFalse(simulate(p,b,0,s,validity=1)['second_filled']);self.assertTrue(simulate(p,b,0,s,validity=2)['second_filled'])
    def test_trade_costs_reduce_flat_capital(self):
        b,s,p=fixture();b[1].update(open=101,low=100,high=102,close=101)
        for x in b[2:]:x.update(open=101,low=100,high=102,close=101)
        r=simulate(p,b,0,s,split=(1,0));self.assertLess(r['conservative_plan_return_pct'],0)
    def test_no_future_prices_create_a_late_fill(self):
        b,s,p=fixture();b[2].update(open=101,low=98,high=108,close=106)
        self.assertFalse(simulate(p,b,0,s,validity=1)['first_filled'])
    def test_single_and_staged_inputs_not_mutated(self):
        b,s,p=fixture();pb=copy.deepcopy(p);bb=copy.deepcopy(b);simulate(p,b,0,s);self.assertEqual(p,pb);self.assertEqual(b,bb)
    def test_missing_day_censored(self):
        b,s,p=fixture();b.pop(1);self.assertIsNone(simulate(p,b,0,s)['conservative_plan_return_pct'])
    def test_corporate_action_censored(self):
        b,s,p=fixture();b[1]['action_boundary']=True;self.assertIsNone(simulate(p,b,0,s)['conservative_plan_return_pct'])
    def test_common_maturity_censored(self):
        b,s,p=fixture(10);self.assertEqual(simulate(p,b,0,s)['status'],'CENSORED_COMMON_MATURITY')
    def test_partial_case_never_called_twenty_day_complete(self):
        b,s,p=fixture(5);r=simulate(p,b,0,s,allow_partial=True);self.assertEqual(r['status'],'PARTIAL_ASOF_NOT_MATURE')
    def test_cash_plan_is_not_data_failure(self):
        b,s,_=fixture();r=simulate(None,b,0,s);self.assertEqual(r['status'],'NO_VALID_PLAN_CASH');self.assertEqual(r['conservative_plan_return_pct'],0)
    def test_cash_from_no_plan_still_records_missed_reference_rally(self):
        b,s,_=fixture();b[3]['high']=150;r=simulate(None,b,0,s)
        self.assertGreater(r['missed_rally_mfe_pct'],10);self.assertEqual(r['quantity'],0)
    def test_gap_stop_updates_close_drawdown(self):
        b,s,p=fixture();b[1].update(open=101,low=100,high=108,close=106);b[2].update(open=90,low=85,high=95,close=91)
        self.assertLess(simulate(p,b,0,s)['worst']['max_drawdown_close_pct'],0)
    def test_hypothetical_fills_never_marked_broker_verified(self):
        b,s,p=fixture();self.assertFalse(simulate(p,b,0,s)['actual_fill_verified'])


if __name__=='__main__':unittest.main()
