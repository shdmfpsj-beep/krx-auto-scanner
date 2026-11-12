import copy,json,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import c3_single_entry_range_v1 as e
import c3_market_context_v1 as m
from c3_range_forward_v1 import register,immutable,hash_value,update_existing
from c3_range_delivery_v1 import envelope,transport_test,safe_claim
from c3_market_range_study_v1 import financial_review,choose_watch
from test_c3_dynamic_entry_v2 import bars,trade_fixture
from c3_dynamic_entry_v2 import evaluate_trade

class RangeRisk(unittest.TestCase):
    def make(self):return e.risk_intersection(9400,10000,9000,13000,14500,10000,1000)
    def test_every_tick_and_worst_endpoint(self):
        r=self.make();self.assertTrue(r['valid']);self.assertTrue(r['all_legal_ticks_passed'])
        rows=[e.endpoint(p,9000,13000,14500,10000,1000) for p in e.legal_ticks(r['low'],r['high'])]
        self.assertEqual(r['ticks_checked'],len(rows));self.assertAlmostEqual(min(v['net_r1_rr'] for v in rows),r['min_net_r1_rr'])
        self.assertLessEqual(max(v['stop_risk_pct'] for v in rows),8)
    def test_intersection_keeps_frozen_stop_and_target(self):
        r=self.make();self.assertLess(r['high'],10000);self.assertFalse(r['anchors_modified'])
        self.assertEqual(r['structural_range'],[9400,10000])
    def test_no_target_cannot_make_range(self):self.assertFalse(e.risk_intersection(9400,10000,9000,None,None,10000,1000)['valid'])
    def test_resistance_inside_range_not_skipped(self):self.assertFalse(e.risk_intersection(9400,10000,9000,9800,14500,10000,1000)['valid'])
    def test_already_broken_high_cannot_be_current_r1(self):
        closes=[100,110,130,120,115,150,145,140,145,150];highs=[105,115,140,125,120,160,150,145,150,155]
        b=[dict(date=f'2026-10-{i+1:02d}',close=c,high=highs[i]) for i,c in enumerate(closes)]
        active,discarded=e.active_resistances(b,100,5)
        self.assertEqual([v['price'] for v in active],[160]);self.assertEqual(discarded[0]['price'],140)
    def test_future_resistance_break_cannot_change_past(self):
        b=[dict(date=f'2026-10-{i+1:02d}',close=c,high=h) for i,(c,h) in enumerate([(100,105),(110,115),(130,140),(120,125),(115,120)])]
        self.assertEqual(len(e.active_resistances(b,100,5)[0]),1)
        self.assertEqual(len(e.active_resistances(b+[dict(date='2026-10-06',close=150,high=155)],100,5)[0]),0)
    def test_deep_support_not_shifted_up(self):
        r=e.risk_intersection(5000,5200,4800,13000,14500,10000,1000);self.assertFalse(r['valid'])
        self.assertGreater(r['distance_limited_lower'],5200)
    def test_bad_rr_never_raises_resistance(self):self.assertFalse(e.risk_intersection(9500,10000,9000,10100,None,10000,1000)['valid'])
    def test_degenerate_single_tick_not_range(self):self.assertFalse(e.risk_intersection(9500,9500,9000,13000,None,10000,1000)['valid'])
    def test_bad_nan_rejected(self):self.assertFalse(e.risk_intersection(float('nan'),10000,9000,13000,None,10000,1000)['valid'])
    def test_causal_prefix_ignores_future(self):
        b=bars(125);original=e.generate_ranges(b[:110]);b[-1]['close']=1
        self.assertEqual(original,e.generate_ranges(b[:110]))
    def test_one_choice_is_one_limit_with_range_cancel_floor(self):
        p=dict(range_valid=True,range=self.make(),stop=9000,r1=13000,r2=14500)
        for choice in ('upper','middle','lower'):
            s=e.single_scenario(p,choice);self.assertEqual(s['max_purchases'],1);self.assertEqual(s['low'],p['range']['low'])
            self.assertEqual(s['high'],p['range']['endpoints'][choice]['price'])
    def test_opening_improvement_within_range_is_not_mistaken_cancel(self):
        b,s,p=trade_fixture();p.update(low=99,high=101)
        b[1].update(open=100,low=99.5,close=106)
        got=evaluate_trade(p,b,0,s,1,5);self.assertTrue(got['filled']);self.assertEqual(got['entry_price'],100)
    def test_gap_below_range_cannot_be_filled(self):
        b,s,p=trade_fixture();b[1].update(open=90,low=89)
        self.assertEqual(evaluate_trade(p,b,0,s,1,5)['status'],'CANCEL_GAP_BELOW_RANGE')
    def test_same_bar_stop_first(self):
        b,s,p=trade_fixture();b[1].update(open=101,low=90,high=130)
        got=evaluate_trade(p,b,0,s,1,5);self.assertTrue(got['status'].startswith('STOP'));self.assertLess(got['return_pct'],0)

class SourceAndSelection(unittest.TestCase):
    def test_unfinished_us_session_excluded(self):
        d,c=m.last_completed_us(datetime.fromisoformat('2026-11-12T04:00:00+09:00'));self.assertEqual(d,'2026-11-10')
    def test_us_early_close_calendar(self):
        d,c=m.last_completed_us(datetime.fromisoformat('2026-11-27T18:30:00+00:00'))
        self.assertEqual(d,'2026-11-27');self.assertEqual(datetime.fromisoformat(c).hour,18)
    def test_future_macro_observation_rejected(self):
        with self.assertRaises(ValueError):m.load_prior_macro(dict(generated_at_kst='2026-11-13T00:00:00+09:00'),datetime.fromisoformat('2026-11-12T12:00:00+09:00'))
    def test_stale_oil_is_missing_not_neutral(self):
        doc=dict(generated_at_kst='2026-11-12T12:00:00+09:00',global_etf_data={},fred_macro_data={'DCOILWTICO':dict(date='2026-11-03',value=99.64)})
        r=m.load_prior_macro(doc,datetime.fromisoformat('2026-11-12T17:00:00+09:00'))
        self.assertNotIn('DCOILWTICO',r['macro']);self.assertIn('DCOILWTICO',r['unavailable'])
    def test_later_api_snapshot_never_original_pit(self):
        q=dict(latest_statement=dict(published_on='2026-08-14',revenue_krw=10,operating_profit_krw=2,operating_cashflow_ytd_krw=1,equity_krw=6,assets_krw=10,liabilities_krw=4,balance_identity_gap_fraction=0))
        r=financial_review(q,'2026-11-11');self.assertTrue(r['observed_positive']);self.assertFalse(r['confirmed'])
    def test_future_finance_excluded(self):self.assertFalse(financial_review(dict(latest_statement=dict(published_on='2026-11-12')),'2026-11-11')['observed_positive'])
    def test_stock_watch_rank_ignores_entry_geometry(self):
        rows=[dict(ticker='000001',sector='A',momentum_pass=True,liquidity_pass=True,turnover20=20,own_rs20=3),dict(ticker='000002',sector='A',momentum_pass=True,liquidity_pass=True,turnover20=10,own_rs20=5)]
        fin={r['ticker']:dict(observed_positive=True,confirmed=False,growth_observed=True) for r in rows}
        before=[r['ticker'] for r in choose_watch(rows,fin,{})];rows[0]['range_valid']=False;rows[1]['range_valid']=True
        self.assertEqual(before,[r['ticker'] for r in choose_watch(rows,fin,{})])
    def test_negative_rs_not_promoted_by_entry(self):
        rows=[dict(ticker='000001',sector='A',momentum_pass=False,liquidity_pass=True,turnover20=20,own_rs20=-3,range_valid=True)]
        self.assertEqual(choose_watch(rows,{'000001':dict(observed_positive=True)},{}),[])
    def test_incomplete_global_not_called_bullish(self):
        r=m.combine(dict(legacy_risk_classification=dict(regime='GLOBAL_DATA_INCOMPLETE_RESEARCH_ONLY')),dict(boards={'KOSPI':dict(regime='UP'),'KOSDAQ':dict(regime='UP')}))
        self.assertEqual(r['observed_regime'],'UNVERIFIED');self.assertFalse(r['buy_approved'])

class ImmutableForward(unittest.TestCase):
    def record(self):
        return dict(source_date='2026-11-12',ticker='028050',source_run_id='test-only',source_hash='a'*64,model_version='C3_MARKET_SINGLE_ENTRY_RANGE_V1',
            created_at='2026-11-13T00:00:00+00:00',source_received_at='2026-11-12T23:30:00+00:00',reasons=['test'],market_regime='UNVERIFIED',range=None,stop=100,r1=200,r2=250,max_purchases=1,additional_purchases_allowed=False)
    def test_register_idempotence_and_stop_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.record();clock=datetime.fromisoformat(r['created_at'])
            self.assertEqual(register(td,r,clock)['status'],'CREATED');self.assertEqual(register(td,r,clock)['status'],'ALREADY_RECORDED')
            r['stop']=110
            with self.assertRaises(ValueError):register(td,r,clock)
    def test_archive_cannot_create_new_forward_record(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.record();r['source_date']='2026-11-11';clock=datetime.fromisoformat(r['created_at'])
            with self.assertRaises(ValueError):register(td,r,clock)
            self.assertEqual(register(td,r,clock,replay=True)['writes'],0)
    def test_additional_buy_policy_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.record();r['max_purchases']=2
            with self.assertRaises(ValueError):register(td,r,datetime.fromisoformat(r['created_at']))
    def test_outcome_append_not_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'a.json';self.assertEqual(immutable(p,dict(a=1)),'CREATED')
            self.assertEqual(immutable(p,dict(a=1)),'ALREADY_RECORDED')
            with self.assertRaises(ValueError):immutable(p,dict(a=2))
    def test_daily_updates_mature_5_10_20_and_are_idempotent(self):
        from datetime import date,timedelta
        days=[];day=date(2026,11,12)
        while len(days)<30:
            if day.weekday()<5:days.append(day.isoformat())
            day+=timedelta(days=1)
        bs=[dict(date=d,open=100+i,high=102+i,low=99+i,close=101+i,volume=10000,segment=0,tradable=True) for i,d in enumerate(days)]
        index={d:100+i for i,d in enumerate(days)}
        with tempfile.TemporaryDirectory() as td:
            r=self.record();register(td,r,datetime.fromisoformat(r['created_at']))
            a=update_existing(td,{'028050':bs},{'028050':index},days,days[-1]);self.assertEqual(a['results'][0]['status'],'CREATED')
            self.assertTrue(all(v['status']=='OBSERVED_PRICE_ONLY' for v in a['results'][0]['horizons'].values()))
            self.assertEqual(update_existing(td,{'028050':bs},{'028050':index},days,days[-1])['results'][0]['status'],'ALREADY_RECORDED')
    def test_tracking_missing_provider_does_not_fake_outcome(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.record();register(td,r,datetime.fromisoformat(r['created_at']))
            a=update_existing(td,{}, {},['2026-11-12'],'2026-11-12')
            self.assertEqual(a['results'][0]['status'],'UNAVAILABLE_PRICE_OR_BENCHMARK')

class SafeDelivery(unittest.TestCase):
    def test_zero_one_two_image_only_contract(self):
        with tempfile.TemporaryDirectory() as td:
            paths=[]
            for i in (0,1):
                p=Path(td)/(str(i)+'.png');Image.new('RGB',(400,600),('red','blue')[i]).save(p);paths.append(p)
            for n in (0,1,2):
                r=transport_test(paths[:max(1,n)]);self.assertEqual(r['status'],'MOCK_DELIVERED');self.assertEqual(r['actual_telegram_requests'],0)
                self.assertEqual(r['receipt']['photos'],max(1,n));self.assertFalse(r['receipt']['captions_present'])
    def test_zero_candidate_image_must_match_source_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'a.png';Image.new('RGB',(400,600),'red').save(p)
            import hashlib
            report=dict(watch_top2=[],source_date='2026-11-11',source_run_id='123',source_hash='a'*64,report_payload_sha256='b'*64)
            manifest=dict(png_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),source_run_id='123',source_hash='a'*64,report_hash='b'*64,price_asof='2026-11-11')
            self.assertEqual(envelope([p],[manifest],report)['image_count'],1)
            manifest['source_run_id']='999'
            with self.assertRaises(ValueError):envelope([p],[manifest],report)
    def test_ambiguous_send_claim_blocks_repeat(self):
        claims={};key='research-observation-v1/2026-11-11/test'
        safe_claim(claims,key,dict(status='UNCERTAIN'));self.assertEqual(safe_claim(claims,key,{}),'DUPLICATE_BLOCKED')
    def test_production_key_cannot_be_claimed(self):
        with self.assertRaises(ValueError):safe_claim({},'final/2026-11-11',{})
    def test_error_receipt_never_true_delivery(self):
        from c3_telegram_notify import Telegram
        class Response:
            status_code=200
            def json(self):return dict(ok=False)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'a.png';Image.new('RGB',(400,600),'red').save(p)
            with patch('c3_telegram_notify.requests.post',return_value=Response()):
                with self.assertRaises(ValueError):Telegram('TEST_ONLY','-1009999999999').send_album([p])

if __name__=='__main__':unittest.main()
