import copy,csv,hashlib,json,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path
from c3_selection_factors_v6 import (causal_factors,factor_pass,nonoverlap,choose,build_pool,load_indices,
    full_session_path,review_packet,validate_review,paired_dates)


def bars(n=90):
    days=[(date(2026,5,1)+timedelta(days=i)).isoformat() for i in range(n)]
    rows=[dict(date=d,name='fixture',open=100+i,close=100+i,high=102+i,low=98+i,volume=1000+i,turnover_krw=100000+i*100,
        segment=0,tradable=True,invalid_data=False,ohlc_valid=True,action_boundary=False) for i,d in enumerate(days)]
    return days,rows,{d:100+i*.1 for i,d in enumerate(days)}


class SelectionFactorTests(unittest.TestCase):
    def test_relative_strength_is_against_the_own_board_index(self):
        days,rows,index=bars();f=causal_factors(rows,index)
        expected=100*(rows[-1]['close']/rows[-21]['close']-1)-100*(index[days[-1]]/index[days[-21]]-1)
        self.assertAlmostEqual(f['own_rs20'],expected)

    def test_acceleration_uses_an_already_known_five_session_lag(self):
        days,rows,index=bars();f=causal_factors(rows,index)
        old=100*(rows[-6]['close']/rows[-26]['close']-1)-100*(index[days[-6]]/index[days[-26]]-1)
        self.assertAlmostEqual(f['rs_accel5'],f['own_rs20']-old)

    def test_252_high_is_unknown_without_the_full_window(self):
        days,rows,index=bars();r=causal_factors(rows,index)
        self.assertIsNone(r['high252_ratio']);self.assertFalse(factor_pass(r,'HIGH252'))
        self.assertFalse(factor_pass(r,'HIGH252_AVAILABLE'));self.assertTrue(factor_pass(r,'A'))

    def test_complete_252_high_does_not_substitute_a_short_window(self):
        days,rows,index=bars(260);rows[-252]['high']=10000
        self.assertLess(causal_factors(rows,index)['high252_ratio'],.8)

    def test_b_cannot_qualify_a_weak_or_decelerating_stock(self):
        self.assertFalse(factor_pass(dict(own_rs20=-1,rs_accel5=3),'B'))
        self.assertFalse(factor_pass(dict(own_rs20=3,rs_accel5=-1),'B'))
        self.assertTrue(factor_pass(dict(own_rs20=3,rs_accel5=1),'B'))

    def test_unregistered_filter_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'UNREGISTERED'):factor_pass({},'BEST_AFTER_LOOKING')

    def test_nonoverlap_is_reserved_before_observing_future_returns(self):
        days,rows,index=bars();events=[dict(ticker='A',decision_date=days[i],future_profit=v) for i,v in [(0,-10),(1,1000),(19,1000),(20,-10)]]
        got=nonoverlap(events,days)
        self.assertEqual([r['decision_date'] for r in got],[days[0],days[20]])

    def test_different_stocks_have_separate_nonoverlap_clocks(self):
        days,_,_=bars();events=[dict(ticker=t,decision_date=days[0]) for t in ['A','B']]
        self.assertEqual(len(nonoverlap(events,days)),2)

    def test_paired_comparison_does_not_make_missing_model_dates_zero(self):
        rows=[dict(variant='A',status='COMPLETE',decision_date='2026-05-01',excess_pct=-2),dict(variant='B',status='COMPLETE',decision_date='2026-05-01',excess_pct=1),dict(variant='B',status='COMPLETE',decision_date='2026-05-02',excess_pct=100)]
        p=paired_dates(rows);self.assertEqual(p['common_decision_dates'],1);self.assertEqual(p['only_B_dates'],1);self.assertEqual(p['mean_B_minus_A_excess_pct'],3)

    def test_fixed26_clock_also_covers_unselected_proposals(self):
        days,_,_=bars();pool={}
        for i in [0,1]:pool[days[i]]=[dict(ticker=t,decision_date=days[i],fold='HOLDOUT',cohort_regime='UP',turnover20=v,legacy_rs20=1) for t,v in [('A',3),('B',2),('C',1)]]
        self.assertEqual(len(choose(pool,days,'A','FIXED26','HOLDOUT')),2)
        self.assertEqual(len(choose(pool,days,'A','DAILY','HOLDOUT')),4)

    def test_future_winner_cannot_displace_the_ranked_two(self):
        days,_,_=bars();pool={days[0]:[dict(ticker=t,decision_date=days[0],fold='HOLDOUT',cohort_regime='UP',turnover20=v,legacy_rs20=1,future_profit=10000 if t=='C' else -100) for t,v in [('A',3),('B',2),('C',1)]]}
        self.assertEqual([r['ticker'] for r in choose(pool,days,'A','DAILY','HOLDOUT')],['A','B'])

    def test_future_bars_cannot_change_an_earlier_feature_packet(self):
        days,rows,index=bars();proxy={d:100. for d in days};turns={('A',b['date']):b['turnover_krw'] for b in rows}
        first=build_pool({'A':copy.deepcopy(rows)},days,{'KOSPI':index},turns,{'A':'KOSPI'},proxy)
        changed=copy.deepcopy(rows);changed[-1].update(close=100000,high=100001)
        second=build_pool({'A':changed},days,{'KOSPI':index},turns,{'A':'KOSPI'},proxy)
        self.assertEqual(first[days[-10]],second[days[-10]])

    def test_reference_path_uses_five_full_entry_sessions(self):
        days,rows,index=bars();p=dict(ticker='A',decision_date=days[0],method='BREAKOUT',segment=0,low=90,high=110,stop=80,resistance=150)
        path=full_session_path(p,rows,days,5)
        self.assertEqual(path['entry']['date'],days[1]);self.assertEqual(path['exit']['date'],days[6])
        self.assertEqual(path['maturity_date'],days[6])

    def test_index_hash_and_session_grid_are_required(self):
        days,_,_=bars(3)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);meta=dict(series={})
            for market in ['KOSPI','KOSDAQ']:
                path=p/(market+'_index.csv')
                with path.open('w',newline='') as f:
                    w=csv.DictWriter(f,fieldnames=['date','market','open','high','low','close']);w.writeheader()
                    for day in days:w.writerow(dict(date=day,market=market,open=100,high=101,low=99,close=100))
                meta['series'][market]=dict(csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            (p/'index_manifest.json').write_text(json.dumps(meta));load_indices(p,days)
            with self.assertRaisesRegex(ValueError,'GRID'):load_indices(p,days[:-1])
            (p/'KOSPI_index.csv').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'HASH'):load_indices(p,days)

    def test_ai_packet_whitelist_excludes_identity_and_future_results(self):
        row=dict(own_rs20=1,rs_accel5=1,ticker='WINNER',name='Known future winner',future_return=1000,outcome='WIN')
        packet=review_packet(row,'abc','2026-11-06T07:00:00Z','2026-11-09T00:00:00Z')
        self.assertEqual(set(packet['features']),{'own_rs20','rs_accel5'})
        self.assertNotIn('WINNER',json.dumps(packet))

    def review_fixture(self):
        p=review_packet(dict(own_rs20=2),'abc','2026-11-06T07:00:00Z','2026-11-09T00:00:00Z')
        h=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        r=dict(packet_sha256=h,produced_at='2026-11-06T08:00:00Z',external_data_used=False,evidence_keys=['own_rs20'],decision='ABSTAIN')
        return p,r

    def test_genuine_review_can_be_recorded_before_execution(self):
        p,r=self.review_fixture();self.assertTrue(validate_review(p,r,'2026-11-06T08:01:00Z'))

    def test_ai_cannot_change_the_packet_or_add_unknown_news(self):
        p,r=self.review_fixture();r['packet_sha256']='other'
        with self.assertRaisesRegex(ValueError,'HASH'):validate_review(p,r,'2026-11-06T08:01:00Z')
        p,r=self.review_fixture();r['evidence_keys']=['next_earnings_surprise']
        with self.assertRaisesRegex(ValueError,'UNGROUNDED'):validate_review(p,r,'2026-11-06T08:01:00Z')

    def test_ai_review_after_execution_is_not_a_valid_backtest(self):
        p,r=self.review_fixture()
        with self.assertRaisesRegex(ValueError,'AFTER_EXECUTION'):validate_review(p,r,'2026-11-09T00:00:01Z')


if __name__=='__main__':unittest.main()
