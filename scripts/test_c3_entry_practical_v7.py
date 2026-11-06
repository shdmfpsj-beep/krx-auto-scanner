import copy,json,hashlib,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path
from c3_entry_practical_v7 import first_reclaim,entry_plan,costed_r1_cap,opportunity,selection_context,BUY,SELL,SLIP
from c3_selection_factors_v6 import full_session_path,review_packet
from c3_current_candidates_v7 import append_current,fresh_snapshot,bull_bear_review


def fixture(n=90):
    days=[(date(2026,5,1)+timedelta(days=i)).isoformat() for i in range(n)]
    rows=[]
    for i,d in enumerate(days):
        c=100+.5*i;rows.append(dict(date=d,name='fixture',open=c-.2,high=c+2,low=c-.1,close=c,volume=120.,turnover_krw=100000.,
            segment=0,tradable=True,invalid_data=False,ohlc_valid=True,action_boundary=False))
    rows[-1]['low']=sum(b['close'] for b in rows[-5:])/5-.1
    f=dict(structure=dict(stop=100,support=102,atr=4,pivot_date=days[-8],confirmed_on=days[-6]),
        geometry=dict(first_resistance=180,second_resistance=190),volume20=100.,prior_high20=200.,turnover20=100000.,rs20=5.)
    return days,rows,f


class EntryPracticalTests(unittest.TestCase):
    def test_reclaim_uses_a_completed_bullish_bar(self):
        days,rows,f=fixture();self.assertIsNotNone(first_reclaim(rows))
        rows[-1]['open']=rows[-1]['close']+1;self.assertIsNone(first_reclaim(rows))

    def test_recent_touch_is_not_the_first_healthy_reclaim(self):
        days,rows,f=fixture()
        for b in rows[-6:-1]:b['low']=b['close']-10
        self.assertIsNone(first_reclaim(rows))

    def test_pullback_confirmation_does_not_require_a_breakout(self):
        days,rows,f=fixture();p,why=entry_plan('A',rows,f,'B_CONFIRMED_PULLBACK','UP')
        self.assertIsNone(why);self.assertEqual(p['signal_rule'],'B_CONFIRMED_PULLBACK');self.assertEqual(p['execution_model'],'NEXT_OPEN_WITHIN_FROZEN_BUDGET')
        self.assertEqual(entry_plan('A',rows,f,'C_LIMITED_BREAKOUT','UP')[1],'BREAKOUT_NOT_CONFIRMED')

    def test_all_three_packages_keep_the_same_structural_stop(self):
        days,rows,f=fixture();f['prior_high20']=rows[-1]['close']-.2
        rows[-2]['close']=f['prior_high20']-.1;rows[-1]['open']=rows[-1]['close']-.1
        plans=[entry_plan('A',rows,f,v,'UP')[0] for v in ['A_SUPPORT_LIMIT','B_CONFIRMED_PULLBACK','C_LIMITED_BREAKOUT']]
        self.assertTrue(all(p is not None for p in plans));self.assertEqual({p['stop'] for p in plans},{100})

    def test_entry_volatility_budget_cannot_move_the_frozen_stop(self):
        days,rows,f=fixture();f['geometry']['first_resistance']=None
        a,_=entry_plan('A',rows,f,'B_CONFIRMED_PULLBACK','UP');rows[-1]['high']+=30
        b,_=entry_plan('A',rows,f,'B_CONFIRMED_PULLBACK','UP')
        self.assertEqual(a['stop'],b['stop']);self.assertGreaterEqual(b['high'],a['high'])

    def test_known_first_resistance_cap_covers_both_costs_and_slippage(self):
        r=150;cap=costed_r1_cap(r)
        self.assertLess(cap*(1+BUY)*(1+SLIP),r*(1-SELL)*(1-SLIP))
        self.assertIsNone(costed_r1_cap(None))

    def test_next_open_reclaim_never_uses_the_signal_close_or_later_low(self):
        days,rows,f=fixture();p,_=entry_plan('A',rows[:-1],f,'A_SUPPORT_LIMIT','UP')
        # Explicit toy next-open budget tests the reused fill branch, not a new rule.
        p.update(decision_date=days[0],method='BREAKOUT',low=101,high=110,stop=90)
        x=full_session_path(p,rows,days,5);self.assertNotEqual(x['entry'].get('date'),days[0])
        rows[1]['open']=120;rows[1]['low']=105
        self.assertEqual(full_session_path(p,rows,days,5)['entry']['status'],'OPEN_ABOVE_FROZEN_BUDGET')

    def test_unregistered_entry_package_is_rejected(self):
        days,rows,f=fixture()
        with self.assertRaisesRegex(ValueError,'UNREGISTERED'):entry_plan('A',rows,f,'BEST_AFTER_BACKTEST','UP')

    def test_no_setup_is_cash_but_incomplete_horizon_is_not_zero_profit(self):
        days,rows,f=fixture();cell=dict(ticker='A',decision_date=days[0],status='NO_SETUP',plan=None);idx={d:100 for d in days}
        m,_=opportunity([cell],{'A':rows},days,{'KOSPI':idx},{'A':'KOSPI'},5,'HOLDOUT')
        self.assertEqual(m['equal_opportunity_net_pct'],0);self.assertEqual(m['profitable_reference_no_setup'],1)
        pending,_=opportunity([cell],{'A':rows[:5]},days[:5],{'KOSPI':idx},{'A':'KOSPI'},20,'HOLDOUT')
        self.assertIsNone(pending['equal_opportunity_net_pct'])

    def test_censored_filled_path_is_not_a_zero_loss(self):
        days,rows,f=fixture();idx={d:100 for d in days}
        cell=dict(ticker='A',decision_date=days[0],status='PLAN_READY',plan={},paths={'5':dict(entry=dict(status='MODEL_ENTRY'),censor_date=days[3],exit=None)})
        # Nonempty means a real plan; an empty dict is intentionally not used as a signal.
        cell['plan']={'stop':90}
        m,_=opportunity([cell],{'A':rows},days,{'KOSPI':idx},{'A':'KOSPI'},5,'HOLDOUT')
        self.assertIsNone(m['equal_opportunity_net_pct']);self.assertEqual(m['counts']['EXIT_OR_ACTION_UNRESOLVED'],1)

    def test_same_date_different_markets_are_not_paired(self):
        rows=[dict(variant=v,cadence='DAILY',fold='HOLDOUT',horizon=20,status='COMPLETE',ticker=t,decision_date='2026-05-01',market_regime='DOWN',excess_pct=x,price_move_pct=-5,reference_net_pct=-6) for v,t,x in [('A','X',-2),('B','Y',3)]]
        r=selection_context(dict(outcomes=rows),{'X':'KOSPI','Y':'KOSDAQ'})['20']
        self.assertEqual(r['paired_same_day_and_market']['DOWN']['n'],0)
        self.assertGreater(r['unpaired']['B']['DOWN']['mean_excess_pct'],0);self.assertLess(r['unpaired']['B']['DOWN']['mean_net_reference_pct'],0)

    def test_fresh_source_failure_does_not_create_price_rows(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'krx_v65_collect_status.json').write_text(json.dumps(dict(krx_eod_authenticated=False,status='EMPTY',official_market_rows=0,asof='2026-11-05')))
            prices,meta=fresh_snapshot(p);self.assertIsNone(prices);self.assertEqual(meta['rows'],0)

    def test_new_bar_requires_a_matching_next_session_and_same_identity(self):
        days,rows,f=fixture();past=rows[:-1];r=dict(rows[-1],asof=days[-1],valid_daily_bar='True')
        out,reason=append_current(past,r,days[-2],days);self.assertIsNone(reason);self.assertEqual(out[-1]['date'],days[-1])
        self.assertEqual(append_current(past,r,days[-3],days)[1],'NOT_NEXT_MATCHED_SESSION')
        r['name']='different';self.assertEqual(append_current(past,r,days[-2],days)[1],'IDENTITY_CHANGED')

    def test_unresolved_price_unit_change_is_not_a_new_uptrend(self):
        days,rows,f=fixture();r=dict(rows[-1],asof=days[-1],valid_daily_bar='True',open=300,high=310,low=290,close=300)
        self.assertEqual(append_current(rows[:-1],r,days[-2],days)[1],'UNRESOLVED_PRICE_UNIT_CHANGE')

    def test_bull_bear_contract_rejects_one_sided_or_unbound_reviews(self):
        p=review_packet(dict(own_rs20=1,rs_accel5=2),'abc','2026-11-06T07:00:00Z','2026-11-09T00:00:00Z')
        h=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        r=dict(packet_sha256=h,produced_at='2026-11-06T08:00:00Z',decision='PASS',external_data_used=False,bull_evidence_keys=['own_rs20'],bear_evidence_keys=[],evidence_keys=['own_rs20'])
        with self.assertRaisesRegex(ValueError,'BOTH_BULL'):bull_bear_review(p,r,'2026-11-06T08:01:00Z')
        r.update(bear_evidence_keys=['rs_accel5'],evidence_keys=['own_rs20','rs_accel5']);self.assertTrue(bull_bear_review(p,r,'2026-11-06T08:01:00Z'))


if __name__=='__main__':unittest.main()
