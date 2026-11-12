import copy,math,statistics,unittest
from unittest.mock import patch
import c3_dynamic_entry_v2 as d


def bars(n=125):
    out=[]
    for i in range(n):
        c=10000+15*i+100*math.sin(i*.5)
        out.append(dict(date=f'2026-{1+i//28:02d}-{1+i%28:02d}',open=c-10,high=c+80,low=c-80,close=c,volume=100000,turnover_krw=c*100000,segment=0,tradable=True))
    return out


def trade_fixture():
    b=bars(35)
    for x in b:x.update(open=105,high=108,low=103,close=106)
    return b,[x['date'] for x in b],dict(low=99,high=101,stop=95,resistance=115,resistance2=125)


class IndicatorsAndStructure(unittest.TestCase):
    def test_bandwidth_population_reference(self):
        a=list(range(1,30));got=d.bandwidth(a);self.assertIsNone(got[18]);self.assertAlmostEqual(got[19],4*statistics.pstdev(a[:20])/statistics.mean(a[:20]))
    def test_adx_warmup_and_uptrend(self):
        b=bars(40)
        for i,x in enumerate(b):x.update(open=100+i,high=102+i,low=99+i,close=101+i)
        a=d.adx14(b);self.assertTrue(all(x is None for x in a[:27]));self.assertAlmostEqual(a[27]['adx'],100);self.assertGreater(a[-1]['plus_di'],a[-1]['minus_di'])
    def test_adx_flat_does_not_divide_by_zero(self):
        b=bars(40)
        for x in b:x.update(open=100,high=100,low=100,close=100)
        self.assertEqual(d.adx14(b)[-1]['adx'],0)
    def test_indicator_prefix_invariant_to_future(self):
        b=bars();prefix=d.indicators(b[:100]);full=d.indicators(b)
        for k in prefix:self.assertEqual(prefix[k],full[k][:100])
    def test_plan_prefix_invariant_to_future(self):
        b=bars();self.assertEqual(d.plans(b[:100]),d.plans(b[:100],{k:v[:100] for k,v in d.indicators(b).items()}))
    def test_resistance_requires_two_completed_right_bars(self):
        b=bars(10)
        for x in b:x.update(open=100,close=100,high=102,low=99)
        b[-2]['high']=120
        self.assertEqual(d.resistance_levels(b,105,3),[])
        b.append(dict(b[-1],date='2026-01-11'))
        found=d.resistance_levels(b,105,3);self.assertEqual(found[0]['known_on'],b[-1]['date'])
    def test_stop_is_not_moved_to_pass_reward_threshold(self):
        b=bars();kw=dict(anchor=b[-1]['close']-50,invalidation=b[-1]['close']-100,support_date=b[-4]['date'],known_on=b[-2]['date'])
        with patch.object(d,'resistance_levels',return_value=[dict(price=b[-1]['close']+40)]):p=d.geometry(b,'X',**kw)
        with patch.object(d,'resistance_levels',return_value=[dict(price=b[-1]['close']+1000)]):q=d.geometry(b,'X',**kw)
        self.assertEqual((p['low'],p['high'],p['stop']),(q['low'],q['high'],q['stop']))
    def test_one_entry_does_not_require_second_support(self):
        b=bars();close=b[-1]['close']
        with patch.object(d,'confirmed_pivots',return_value=[]),patch.object(d,'resistance_levels',return_value=[dict(price=close+1500)]):
            p=d.geometry(b,'X',close-40,close-100,b[-4]['date'],b[-2]['date'])
        self.assertIsNone(p['entry2']);self.assertTrue(p['geometry_pass']);self.assertFalse(p['entry2_is_required'])
    def test_unconfirmed_setup_cannot_pass(self):
        b=bars();p=d.geometry(b,'WATCH',b[-1]['close']-20,b[-1]['close']-40,b[-4]['date'],b[-2]['date'],False)
        self.assertFalse(p['geometry_pass']);self.assertIn('SETUP_CONFIRMATION_REQUIRED',p['reasons'])
    def test_second_completed_reclaim_is_not_first_pullback(self):
        b=bars(10)
        for i,x in enumerate(b):x.update(close=[100,103,106,104,108,106,109,107,111,113][i],high=[101,104,107,105,109,107,110,108,112,114][i],low=90)
        self.assertIsNone(d.first_pullback_context(b,0,2))
    def test_short_history_excluded(self):self.assertEqual(d.plans(bars(79))[2],'INSUFFICIENT_80_BAR_CONTIGUOUS_HISTORY')
    def test_missing_pit_finance_never_certified(self):self.assertEqual(d.company_gate({'financial_stability_verified':True},'2026-11-11'),'UNKNOWN_PIT_NOT_RANKED')
    def test_future_finance_rejected(self):self.assertEqual(d.company_gate({'original_document_pit_verified':True,'published_on':'2026-11-12'},'2026-11-11'),'FUTURE_FINANCIAL_REPORT_REJECTED')
    def test_strategy_overlap_and_twenty_session_lockout(self):
        last={};rows=[{'ticker':'A','method':'HMA'},{'ticker':'A','method':'RETEST'},{'ticker':'B'}]
        chosen,skipped=d.pick_unique(rows,last,100);self.assertEqual([r['ticker'] for r in chosen],['A','B']);self.assertEqual(skipped,1)
        self.assertEqual(d.pick_unique(rows,last,120)[0],[])
        self.assertEqual(len(d.pick_unique(rows,last,121)[0]),2)
    def test_failed_later_retest_invalidates_old_contact(self):
        b=bars(6)
        for x in b:x.update(open=102,high=105,low=100,close=103)
        b[3].update(low=80,close=85);b[-1].update(low=101,close=110)
        s=d.retest_structure(b,1,100,4)
        self.assertFalse(s['support_retained_on_closes']);self.assertEqual(s['invalidation_low'],80);self.assertEqual(s['support_break_dates'],[b[3]['date']])
    def test_structural_stop_covers_low_even_if_close_reclaims(self):
        b=bars(6)
        for x in b:x.update(open=102,high=105,low=100,close=103)
        b[3].update(low=80,close=101)
        s=d.retest_structure(b,1,100,4)
        self.assertTrue(s['support_retained_on_closes']);self.assertEqual(s['invalidation_low'],80)
    def test_confirmation_day_low_cannot_be_omitted_from_stop(self):
        b=bars(6)
        for x in b:x.update(open=102,high=105,low=100,close=103)
        b[-1].update(low=90,close=104)
        self.assertEqual(d.retest_structure(b,1,100,4)['invalidation_low'],90)


class DailyExecution(unittest.TestCase):
    def test_gap_below_range_cancelled(self):
        b,s,p=trade_fixture();b[1].update(open=98,low=97,high=103,close=102)
        o=d.evaluate_trade(p,b,0,s);self.assertEqual(o['status'],'CANCEL_GAP_BELOW_RANGE');self.assertFalse(o['filled'])
    def test_open_at_resistance_cancelled(self):
        b,s,p=trade_fixture();b[1]['open']=115;self.assertEqual(d.evaluate_trade(p,b,0,s)['status'],'CANCEL_R1_ALREADY_REACHED')
    def test_expiry_range_not_reached_pass(self):
        b,s,p=trade_fixture();o=d.evaluate_trade(p,b,0,s);self.assertEqual(o['status'],'PASS_UNFILLED');self.assertEqual(o['return_pct'],0)
    def test_validity_one_two_three(self):
        b,s,p=trade_fixture();b[2].update(open=101,low=100,high=106,close=105)
        self.assertFalse(d.evaluate_trade(p,b,0,s,1)['filled']);self.assertTrue(d.evaluate_trade(p,b,0,s,2)['filled']);self.assertTrue(d.evaluate_trade(p,b,0,s,3)['filled'])
    def test_same_bar_stop_wins_target(self):
        b,s,p=trade_fixture();b[1].update(open=101,low=94,high=120,close=110)
        o=d.evaluate_trade(p,b,0,s);self.assertEqual(o['status'],'STOP_INTRADAY_CONSERVATIVE');self.assertFalse(o['r1_hit_before_stop']);self.assertLess(o['return_pct'],0)
    def test_intraday_entry_day_high_cannot_prove_target(self):
        b,s,p=trade_fixture();b[1].update(open=106,low=100,high=120,close=108)
        o=d.evaluate_trade(p,b,0,s);self.assertEqual(o['status'],'HORIZON_CLOSE');self.assertTrue(o['entry_day_target_sequence_unknown']);self.assertFalse(o['r1_hit_before_stop'])
    def test_r2_after_stop_never_credited(self):
        b,s,p=trade_fixture();b[1].update(open=101,low=94,high=105,close=96);b[2]['high']=130
        self.assertFalse(d.evaluate_trade(p,b,0,s)['r2_path_hit'])
    def test_stop_gap_exits_at_open(self):
        b,s,p=trade_fixture();b[1].update(open=101,low=100,close=104);b[2].update(open=90,low=85,high=94,close=93)
        o=d.evaluate_trade(p,b,0,s);self.assertEqual(o['status'],'STOP_GAP');self.assertEqual(o['exit_price'],90)
    def test_round_trip_costs_reduce_flat_return(self):
        b,s,p=trade_fixture();b[1].update(open=101,low=100,close=101)
        for x in b[2:]:x.update(open=101,low=100,high=103,close=101)
        o=d.evaluate_trade(p,b,0,s);f=d.DEFAULT['fees'];expected=100*((1-f['sell'])*(1-f['slippage_each_side'])/((1+f['buy'])*(1+f['slippage_each_side']))-1)
        self.assertAlmostEqual(o['return_pct'],expected);self.assertLess(o['return_pct'],0)
    def test_entry_wait_missing_price_censored(self):
        b,s,p=trade_fixture();b.pop(1);self.assertIsNone(d.evaluate_trade(p,b,0,s)['return_pct'])
    def test_unfilled_future_missing_price_censored(self):
        b,s,p=trade_fixture();b.pop(10);self.assertEqual(d.evaluate_trade(p,b,0,s)['status'],'CENSORED_PRICE_ACTION_OR_GAP')
    def test_action_boundary_after_entry_censored(self):
        b,s,p=trade_fixture();b[1].update(open=101,low=100);b[3]['action_boundary']=True
        self.assertIsNone(d.evaluate_trade(p,b,0,s)['return_pct'])
    def test_incomplete_horizon_censored(self):
        b,s,p=trade_fixture();self.assertEqual(d.evaluate_trade(p,b,20,s)['status'],'CENSORED_COMMON_CLOCK')
    def test_holdout_cutoff_cannot_leak_future(self):
        b,s,p=trade_fixture();self.assertIsNone(d.evaluate_trade(p,b,0,s,1,20,cutoff=s[22])['return_pct'])
    def test_input_plan_not_mutated(self):
        b,s,p=trade_fixture();before=copy.deepcopy(p);d.evaluate_trade(p,b,0,s);self.assertEqual(p,before)


if __name__=='__main__':unittest.main()
