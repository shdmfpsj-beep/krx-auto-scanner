"""Functional state/provenance tests only. No return, MFE/MAE or backtest."""
import copy,json,tempfile,unittest,importlib.util
from pathlib import Path
from datetime import date,timedelta
from c3_entry_window_v1 import classify,setup_key,price_signature,select_entry_fit,report_order,calendar_grid,add_sessions,research_history,sha

PROTOCOL=dict(max_distance_pct=8.,max_distance_atr=1.)
GRID=['2026-11-05','2026-11-06','2026-11-09','2026-11-10','2026-11-11','2026-11-12','2026-11-13','2026-11-16','2026-11-17','2026-11-18']

def bars(close=110,day='2026-11-13'):
    end=date.fromisoformat(day)
    return [dict(date=str(end-timedelta(days=129-i)),open=close-(129-i)*.8-1,high=close-(129-i)*.8+2,low=close-(129-i)*.8-2,close=close-(129-i)*.8,volume=1000,turnover_krw=100000,segment=0,tradable=True) for i in range(130)]

def plan(anchor_day='2026-11-09',low=98,high=102):
    return dict(method='CONFIRMED_PIVOT',structure_type='CONFIRMED_PIVOT',invalidation_low=97,
        evidence=dict(low_date=anchor_day),support_known_on='2026-11-11',stop=95,r1=120,r2=130,atr14=10,
        default_validity_sessions=1,range_valid=True,structural_low=low,structural_high=high,
        stop_reliability=dict(research_eligible=True,status='STRUCTURAL_STOP_CONFIRMED',original_low=97),
        range=dict(valid=True,low=low,high=high,width_atr=.4,min_net_r1_rr=2.,all_legal_ticks_passed=True,
            endpoints=dict(upper=dict(stop_risk_pct=100*(high-95)/high))))

def row(t='000001',close=110,p=None):
    p=plan() if p is None else p
    return dict(ticker=t,name='Synthetic '+t,close=close,financial=dict(required_metrics_complete=True,observed_positive=True),
        momentum_pass=True,liquidity_pass=True,history_rows=130,range_review=dict(best=p,plans=[p]))

def previous():return dict(ticker='000001',name='Synthetic',source_date='2026-11-06',low=80,high=90,stop=70,r1=105,r2=125,validity_sessions=1,plan_sha256='original',immutable_original=True)

class WindowTests(unittest.TestCase):
    def check(self,r,prior=(),history=(),day='2026-11-13'):
        return classify(r,bars(r['close'],day),day,GRID,prior,history,PROTOCOL)
    def test_inside_range_is_research_ready_but_never_buy_approved(self):
        w=self.check(row(close=100));self.assertEqual(w['status'],'ENTRY_READY');self.assertTrue(w['research_fit_eligible'])
        self.assertEqual(w['approval_status'],'DATA_HOLD');self.assertFalse(w['buy_approved'])
    def test_near_range_is_not_an_inside_range_or_immediate_buy(self):
        w=self.check(row());self.assertEqual(w['status'],'NEAR_ENTRY');self.assertAlmostEqual(w['distance_to_upper_atr'],.8)
        self.assertEqual(w['valid_until_session'],'2026-11-16')
    def test_first_observation_and_expiry_cannot_reset_on_a_repeated_support(self):
        r=row();p=r['range_review']['best'];h=[dict(setup_key=setup_key(r['ticker'],p),first_observed_on='2026-11-11',frozen_price_signature=price_signature(p))]
        w=self.check(r,history=h);self.assertEqual(w['status'],'MISSED_ENTRY');self.assertEqual(w['valid_until_session'],'2026-11-12')
        self.assertFalse(w['research_fit_eligible'])
    def test_same_support_price_raise_is_not_a_new_setup(self):
        r=row();p=r['range_review']['best'];old=price_signature(p);old['high']=101
        h=[dict(setup_key=setup_key(r['ticker'],p),first_observed_on='2026-11-13',frozen_price_signature=old)]
        before=copy.deepcopy(r);w=self.check(r,history=h);self.assertEqual(w['status'],'INVALID_SETUP')
        self.assertIn('SAME_SUPPORT_REPRICING_IS_NOT_A_NEW_ENTRY',w['reason_codes']);self.assertEqual(r,before)
    def test_old_support_cannot_restart_an_expired_original_window(self):
        r=row();old=previous();old['source_date']='2026-11-11';w=self.check(r,[old])
        self.assertEqual(w['status'],'MISSED_ENTRY');self.assertIn('OLD_SUPPORT_CANNOT_RESTART_AN_EXPIRED_ENTRY_WINDOW',w['reason_codes'])
    def test_actual_new_support_event_can_create_a_separate_window(self):
        r=row(p=plan('2026-11-12'));old=previous();old['source_date']='2026-11-11';before=copy.deepcopy(old)
        w=self.check(r,[old]);self.assertEqual(w['status'],'NEAR_ENTRY');self.assertTrue(w['new_support_after_original']);self.assertEqual(old,before)
    def test_future_support_confirmation_cannot_be_a_current_entry(self):
        r=row();r['range_review']['best']['support_known_on']='2026-11-16'
        w=self.check(r);self.assertEqual(w['status'],'INVALID_SETUP');self.assertFalse(w['research_fit_eligible'])
        self.assertIn('SUPPORT_CONFIRMATION_NOT_YET_KNOWN',w['reason_codes'])
    def test_original_r1_reached_without_new_valid_support_is_missed(self):
        r=row();r['range_review']['best']=None
        w=self.check(r,[previous()]);self.assertEqual(w['status'],'MISSED_ENTRY');self.assertFalse(w['research_fit_eligible'])
    def test_far_confirmed_support_and_expansion_are_excluded_without_moving_prices(self):
        p=plan(low=58,high=60);p['range_valid']=False;r=row(p=p);r['range_review']['best']=None
        before=copy.deepcopy(r);w=self.check(r);self.assertEqual(w['status'],'OVEREXTENDED');self.assertEqual(r,before)
    def test_ma20_expansion_alone_does_not_reject_a_valid_nearby_zone(self):
        self.assertGreater((110-sum(b['close'] for b in bars()[-20:])/20),0)
        self.assertEqual(self.check(row())['status'],'NEAR_ENTRY')
    def test_confirmed_but_not_valid_zone_waits_without_a_forced_entry(self):
        p=plan();p['structural_high']=108;p['range_valid']=False;r=row(p=p);r['range_review']['best']=None
        self.assertEqual(self.check(r)['status'],'WAIT_PULLBACK')
    def test_invalid_support_is_pass_and_missing_data_is_hold(self):
        r=row(close=60);r['range_review']['best']=None;w=self.check(r,[previous()]);self.assertEqual(w['status'],'INVALID_SETUP')
        r=row();r['financial']['required_metrics_complete']=False;w=self.check(r);self.assertEqual(w['status'],'DATA_HOLD')
        self.assertIn('FINANCIAL_DATA_MISSING_NOT_COMPANY_FAILURE',w['reason_codes'])
    def test_negative_known_financials_are_not_mislabeled_missing_data(self):
        r=row();r['financial']['observed_positive']=False;w=self.check(r)
        self.assertEqual(w['status'],'NEAR_ENTRY');self.assertFalse(w['research_fit_eligible'])
        self.assertIn('EXISTING_COMPANY_MOMENTUM_OR_LIQUIDITY_GATE_FAIL',w['reason_codes'])
    def test_date_or_close_mismatch_cannot_be_an_entry(self):
        r=row();w=classify(r,bars(109),'2026-11-13',GRID,protocol=PROTOCOL);self.assertEqual(w['status'],'DATA_HOLD')
        w=classify(r,bars(day='2026-11-14'),'2026-11-14',GRID,protocol=PROTOCOL)
        self.assertEqual(w['status'],'DATA_HOLD');self.assertFalse(w['research_fit_eligible'])
        self.assertIn('NEXT_REFERENCE_SESSION_UNAVAILABLE',w['reason_codes'])
    def test_entire_pool_is_competed_not_just_watch_top_two(self):
        pool=[row(f'{i:06}') for i in range(1,19)];by={r['ticker']:r for r in pool};windows={r['ticker']:self.check(r) for r in pool}
        for r in pool:windows[r['ticker']]['research_fit_eligible']=r['ticker']=='000017'
        fit=select_entry_fit(pool,by,windows);self.assertEqual([r['ticker'] for r in fit],['000017'])
    def test_current_eligibility_status_is_required_even_if_other_flag_is_true(self):
        r=row();w=self.check(r);w.update(status='OVEREXTENDED',research_fit_eligible=True)
        self.assertEqual(select_entry_fit([r],{r['ticker']:r},{r['ticker']:w}),[])
    def test_entry_first_manifest_deduplicates_a_watch_overlap(self):
        entry=[dict(ticker='000017',png='entry.png')];watch=[dict(ticker='000001',png='watch.png'),dict(ticker='000017',png='same.png')]
        r=report_order(entry,watch,dict(source_date='2026-11-13',source_run_id='X',source_hash='H',report_payload_sha256='R'))
        self.assertEqual([x['png'] for x in r['ordered_images']],['entry.png','watch.png']);self.assertEqual(r['primary_section'],'ENTRY_FIT')
    def test_original_window_uses_one_session_not_three_or_calendar_days(self):
        self.assertEqual(add_sessions('2026-11-06',1,GRID),'2026-11-09')
        self.assertEqual(add_sessions('2026-11-13',1,GRID),'2026-11-16')
    def test_frozen_research_review_hash_is_required(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'reports/c3_new_session_v1/reviews/2026-11-13/a.json';p.parent.mkdir(parents=True)
            r=dict(source_date='2026-11-13',final_research_top2=[dict(ticker='000001',display_plan=plan())]);r['report_payload_sha256']=sha(r);p.write_text(json.dumps(r))
            h=research_history(root,'2026-11-13');self.assertEqual(h['000001'][0]['first_observed_on'],'2026-11-13')
            r['source_date']='2026-11-12';p.write_text(json.dumps(r))
            with self.assertRaises(ValueError):research_history(root,'2026-11-13')
    @unittest.skipUnless(importlib.util.find_spec('exchange_calendars'),'reference calendar installed in Actions')
    def test_actual_monday_reference_calendar_does_not_use_a_weekend(self):
        self.assertEqual(calendar_grid('2026-11-13',['2026-11-12','2026-11-13'])[:3],['2026-11-12','2026-11-13','2026-11-16'])

if __name__=='__main__':unittest.main()
