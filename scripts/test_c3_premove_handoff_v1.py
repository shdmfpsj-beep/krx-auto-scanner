import gzip,json,tempfile,unittest
from pathlib import Path
import numpy as np,pandas as pd
import sys,types,importlib.util
from unittest.mock import patch
from c3_premove_handoff_v1 import PremoveObserver,CSV_NAME,HISTORY_NAME,STATUS_NAME,record_failure
from c3_premove_handoff_v1 import object_digest,validate_registered_watch,load_registered_watch,WATCH_HISTORY,WATCH_STATUS,WATCH_REGISTRY,registered_failure

def frame(n=280):
    x=np.arange(n);c=100+np.sin(x*.5)*4
    c[-10:]=[100,100,99.9,99.8,99.9,99.95,100,100.1,100.2,100.3]
    return pd.DataFrame({'시가':c-.1,'고가':c+1,'저가':c-1,'종가':c,'거래량':np.full(n,1000.)},
                        index=pd.bdate_range('2025-01-01',periods=n))

class HandoffTests(unittest.TestCase):
    def run_case(self,b,cal=None):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup);root=Path(d.name)
        days=[x.date().isoformat() for x in b.index]
        obs=PremoveObserver(days[-1],captured_at_utc='2026-10-29T00:00:00+00:00',run_context={})
        obs.observe('005930',b,'TEST_SOURCE')
        s=obs.finish(root,days[-1],days if cal is None else cal,{'status':'TEST'})
        return root,s,pd.read_csv(root/CSV_NAME,dtype={'ticker':str})
    def test_pre_move_history_survives_without_legacy_breakout_input(self):
        root,s,rows=self.run_case(frame())
        self.assertTrue(rows.price_stage_pass.iloc[0]);self.assertEqual(s['price_stage_case_count'],1)
        with gzip.open(root/HISTORY_NAME,'rt',encoding='utf-8-sig') as f:h=pd.read_csv(f,dtype={'ticker':str})
        self.assertEqual(len(h),280);self.assertEqual(set(h.ticker),{'005930'})
        self.assertFalse(s['orders_enabled']);self.assertEqual(s['company_health_verified_count'],0)
    def test_source_frame_not_mutated(self):
        b=frame();before=b.copy(deep=True);self.run_case(b);pd.testing.assert_frame_equal(b,before)
    def test_missing_session_cannot_disappear_inside_indicator_input(self):
        b=frame();cal=[x.date().isoformat() for x in b.index];b=b.drop(b.index[-10])
        root,s,rows=self.run_case(b,cal)
        self.assertEqual(s['price_valid_count'],0)
        self.assertFalse(rows.price_stage_pass.iloc[0]);self.assertIn('INSUFFICIENT',rows.reason.iloc[0])
    def test_duplicate_dates_are_not_silently_deduplicated(self):
        b=frame();b=pd.concat([b.iloc[:-1],b.iloc[-2:]])
        root,s,rows=self.run_case(b)
        self.assertEqual(s['price_valid_count'],0);self.assertFalse(rows.price_stage_pass.iloc[0])
    def test_short_annual_history_unknown_not_zero(self):
        root,s,rows=self.run_case(frame(125))
        self.assertEqual(s['price_valid_count'],1);self.assertFalse(rows.annual_context_known.iloc[0])
        self.assertTrue(pd.isna(rows.ret252.iloc[0]))
    def test_no_actual_turnover_is_fabricated_from_price_and_volume(self):
        root,s,rows=self.run_case(frame())
        self.assertEqual(s['actual_source_turnover_field_count'],0)
        self.assertTrue(pd.isna(rows.raw_reported_turnover_value.iloc[0]))
        self.assertFalse(rows.turnover_scope_certified.iloc[0])
    def test_reported_turnover_is_retained_without_regular_certification(self):
        b=frame();b['거래대금']=1234567
        root,s,rows=self.run_case(b)
        self.assertEqual(rows.raw_reported_turnover_value.iloc[0],1234567)
        self.assertEqual(s['actual_turnover_unit_and_regular_scope_certified_count'],0)
        self.assertFalse(rows.buy_approved.iloc[0])
    def test_invalid_optional_amount_does_not_erase_valid_price_observation(self):
        b=frame();b['거래대금']='1억원'
        root,s,rows=self.run_case(b)
        self.assertEqual(s['price_valid_count'],1);self.assertTrue(pd.isna(rows.raw_reported_turnover_value.iloc[0]))
    def test_unavailable_calendar_cannot_generate_accepted_stage(self):
        root,s,rows=self.run_case(frame(),[])
        self.assertFalse(s['reference_calendar_available']);self.assertEqual(s['price_stage_case_count'],0)
    def test_future_reference_calendar_cannot_generate_accepted_stage(self):
        b=frame();cal=[x.date().isoformat() for x in b.index]+['2027-01-01']
        root,s,rows=self.run_case(b,cal)
        self.assertFalse(s['reference_calendar_available']);self.assertEqual(s['price_valid_count'],0)
    def test_negative_recent_volume_quarantines_its_prefix(self):
        b=frame();b.iloc[-3,b.columns.get_loc('거래량')]=-1
        root,s,rows=self.run_case(b)
        self.assertEqual(s['price_valid_count'],0)
        self.assertEqual(s['price_tail_audits']['005930']['invalid_reason_counts'],{'INVALID_VOLUME':1})
    def test_deterministic_history_compression_and_commit_manifest(self):
        a,sa,ra=self.run_case(frame());b,sb,rb=self.run_case(frame())
        self.assertEqual((a/HISTORY_NAME).read_bytes(),(b/HISTORY_NAME).read_bytes())
        self.assertEqual(sa['output_sha256'],sb['output_sha256'])
        self.assertEqual(json.loads((a/STATUS_NAME).read_text())['approved_buy_count'],0)
    def test_failure_marker_prevents_old_outputs_being_treated_as_current(self):
        root,s,rows=self.run_case(frame());record_failure(root,'2026-10-29',RuntimeError('not done'))
        marker=json.loads((root/STATUS_NAME).read_text())
        self.assertFalse(marker['observation_audit_completed']);self.assertTrue(marker['stale_previous_outputs_not_accepted'])
    def test_missing_source_columns_are_recorded_not_repaired(self):
        root,s,rows=self.run_case(frame().drop(columns=['저가']))
        self.assertEqual(rows.observation_status.iloc[0],'SOURCE_INVALID');self.assertEqual(s['price_valid_count'],0)

class SourceRouteTests(unittest.TestCase):
    def setUp(self):
        # Source diagnostics are offline even where pykrx is unavailable.
        if importlib.util.find_spec('pykrx') is None:
            package=types.ModuleType('pykrx');package.stock=types.SimpleNamespace()
            with patch.dict(sys.modules,{'pykrx':package}):
                import run
        else:
            import run
        self.run=run;self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        paths=dict(OUT=self.root,SOURCE_LOG=self.root/'source.jsonl',RUNTIME_FILE=self.root/'runtime.json',
                   CALENDAR_FILE=self.root/'calendar.json',UNIVERSE_FILE=self.root/'universe.json')
        self.p=patch.multiple(run,**paths);self.p.start();self.addCleanup(self.p.stop)
        run.RUNTIME_FILE.write_text(json.dumps(run.runtime_evidence()))
    def provider(self,module):
        ns={'__name__':module,'answer':frame()}
        exec('def get_market_ohlcv_by_date(*args, **kwargs):\n return answer.copy()\n',ns)
        return ns['get_market_ohlcv_by_date']
    def test_actual_naver_route_and_response_times_retained(self):
        fn=self.provider('pykrx.website.naver.wrap')
        with patch.object(self.run.stock,'get_market_ohlcv_by_date',fn,create=True):b,label=self.run.fetch_ohlcv('005930')
        x=json.loads(self.run.SOURCE_LOG.read_text())
        self.assertEqual(x['route']['actual_provider_calls'][0]['module'],'pykrx.website.naver.wrap')
        self.assertLessEqual(x['fetch_started_at_utc'],x['response_received_at_utc'])
        self.assertEqual(b.to_csv(),frame().to_csv());self.assertEqual(label,'pykrx')
        self.assertFalse(x['regular_only_scope_verified']);self.assertEqual(x['request']['adjusted'],True)
    def test_krx_route_not_labelled_naver_by_package_name(self):
        with patch.object(self.run.stock,'get_market_ohlcv_by_date',self.provider('pykrx.website.krx.market.wrap'),create=True):self.run.fetch_ohlcv('005930')
        x=json.loads(self.run.SOURCE_LOG.read_text());self.assertIn('krx.market',x['route']['actual_provider_calls'][0]['module'])
    def test_profiler_restored_after_error(self):
        before=sys.getprofile()
        with self.assertRaises(RuntimeError):
            with self.run.trace_price_route():raise RuntimeError('offline')
        self.assertIs(sys.getprofile(),before)
    def test_existing_profiler_is_not_overwritten(self):
        previous=sys.getprofile();profile=lambda *args:None
        try:
            sys.setprofile(profile)
            with self.run.trace_price_route() as e:self.assertIs(sys.getprofile(),profile)
            self.assertTrue(e['trace_skipped_existing_profiler']);self.assertFalse(e['trace_completed'])
        finally:sys.setprofile(previous)
    def test_diagnostic_write_failure_does_not_switch_price_provider(self):
        self.run.SOURCE_LOG.mkdir()
        with patch.object(self.run.stock,'get_market_ohlcv_by_date',self.provider('pykrx.website.naver.wrap'),create=True):b,label=self.run.fetch_ohlcv('005930')
        self.assertEqual(label,'pykrx');self.assertIn('diagnostic_stream_write_error',b.attrs['c3_source_response'])
    def test_fallback_keeps_explicit_different_source_and_unknown_adjustment(self):
        fdr=types.ModuleType('FinanceDataReader');fdr.DataReader=lambda *args:frame().rename(columns={'시가':'Open','고가':'High','저가':'Low','종가':'Close','거래량':'Volume'})
        with patch.dict(sys.modules,{'FinanceDataReader':fdr}),patch.object(self.run.stock,'get_market_ohlcv_by_date',lambda *a,**k:pd.DataFrame(),create=True):b,label=self.run.fetch_ohlcv('005930')
        x=json.loads(self.run.SOURCE_LOG.read_text());self.assertEqual(label,'FinanceDataReader');self.assertIsNone(x['route'])
        self.assertEqual(x['request']['adjusted'],'PROVIDER_DEFAULT_UNKNOWN');self.assertFalse(x['regular_only_scope_verified'])
    def test_runtime_manifest_does_not_capture_secret_environment(self):
        with patch.dict('os.environ',{'C3_PRIVATE_SECRET':'must-not-appear'}):x=self.run.runtime_evidence()
        self.assertNotIn('must-not-appear',json.dumps(x));self.assertFalse(x['orders_enabled'])

def registry_for(b,tickers=('005930',)):
    day=b.index[-1].date().isoformat();clock=day+'T12:00:00+00:00';setups=[]
    for t in tickers:
        row=dict(ticker=t,name='TEST'+t,price_asof=day,registered_at_utc=clock,setup_id='a'*64 if t==tickers[0] else 'b'*64,
                 source_snapshot_sha256='c'*64,source_key='TEST_LINEAGE')
        row['record_id']=object_digest(row);setups.append(row)
    r=dict(schema='C3_REGISTERED_RECLAIM_COHORT_V1',baseline_price_asof=day,registered_at_utc=clock,
           registered_count=len(setups),setups=setups,baseline_exact_provider_unknown=True,orders_enabled=False,not_an_approved_buy_list=True)
    r['registry_id']=object_digest(r);return r

class RegisteredFollowupTests(unittest.TestCase):
    def capture(self,b,registry=None,observe=True,calendar=None):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name)
        days=[x.date().isoformat() for x in b.index];obs=PremoveObserver(days[-1],captured_at_utc='2026-10-30T00:00:00+00:00',run_context={},registered_watch=registry)
        if observe:obs.observe('005930',b,'TEST_SOURCE')
        s=obs.finish(root,days[-1],days if calendar is None else calendar,{'status':'TEST'})
        return root,s
    def test_registered_failure_of_price_stage_still_has_entire_history(self):
        b=frame();b.iloc[-1]=[198,202,197,200,1000]
        root,s=self.capture(b,registry_for(b));legacy=pd.read_csv(root/CSV_NAME)
        self.assertFalse(legacy.price_stage_pass.iloc[0]);self.assertEqual(s['price_stage_case_count'],0)
        follow=json.loads((root/WATCH_STATUS).read_text());self.assertEqual(follow['observed_count'],1)
        with gzip.open(root/WATCH_HISTORY,'rt',encoding='utf-8-sig') as f:h=pd.read_csv(f)
        self.assertEqual(len(h),len(b));self.assertEqual(h.close.iloc[-1],200)
    def test_unavailable_registered_issuer_is_not_dropped_or_zero_priced(self):
        b=frame();root,s=self.capture(b,registry_for(b,('005930','000660')))
        follow=json.loads((root/WATCH_STATUS).read_text());self.assertEqual(follow['registered_count'],2)
        self.assertEqual(follow['unavailable_count'],1);missing=next(x for x in follow['rows'] if x['ticker']=='000660')
        self.assertEqual(missing['state'],'REGISTERED_SOURCE_UNAVAILABLE');self.assertNotIn('close',missing)
    def test_legacy_outputs_are_byte_identical_with_or_without_registry(self):
        b=frame();a,sa=self.capture(b);c,sc=self.capture(b,registry_for(b))
        self.assertEqual((a/CSV_NAME).read_bytes(),(c/CSV_NAME).read_bytes())
        self.assertEqual((a/HISTORY_NAME).read_bytes(),(c/HISTORY_NAME).read_bytes())
    def test_duplicate_bad_history_is_preserved_for_audit_not_repaired(self):
        b=frame();r=registry_for(b);b=pd.concat([b.iloc[:-1],b.iloc[-2:]])
        root,s=self.capture(b,r);follow=json.loads((root/WATCH_STATUS).read_text())
        self.assertEqual(s['price_valid_count'],0);self.assertEqual(follow['history_rows'],len(b))
        self.assertNotEqual(follow['rows'][0]['price_tail_state'],'PRICE_ONLY_OBSERVED')
    def test_registry_tampering_and_duplicate_ticker_are_rejected(self):
        from copy import deepcopy
        r=registry_for(frame());bad=deepcopy(r);bad['setups'][0]['ticker']='000660'
        with self.assertRaisesRegex(ValueError,'DIGEST'):validate_registered_watch(bad)
        bad=deepcopy(r);bad['setups'].append(deepcopy(bad['setups'][0]));bad['registered_count']=2;bad.pop('registry_id');bad['registry_id']=object_digest(bad)
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):validate_registered_watch(bad)
    def test_capture_never_certifies_session_or_trade(self):
        b=frame();root,s=self.capture(b,registry_for(b));follow=json.loads((root/WATCH_STATUS).read_text())
        self.assertFalse(follow['regular_only_scope_verified']);self.assertEqual(follow['approved_buy_count'],0)
        self.assertFalse(follow['orders_enabled']);self.assertIsNone(follow['rows'][0]['source_response'])
    def test_failure_marker_makes_old_followup_outputs_unusable(self):
        b=frame();root,s=self.capture(b,registry_for(b));registered_failure(root,'2026-10-30',RuntimeError('not done'))
        status=json.loads((root/WATCH_STATUS).read_text());self.assertFalse(status['capture_completed']);self.assertTrue(status['stale_previous_outputs_not_accepted'])
    def test_reference_calendar_and_hashes_are_explicit(self):
        b=frame();root,s=self.capture(b,registry_for(b));follow=json.loads((root/WATCH_STATUS).read_text())
        self.assertEqual(len(follow['observed_reference_dates']),len(b));self.assertTrue(follow['reference_calendar_valid'])
        import hashlib
        for name,h in follow['output_sha256'].items():self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),h)
        self.assertEqual(load_registered_watch(root/WATCH_REGISTRY)['registered_count'],1)
    def test_invalid_reference_calendar_does_not_disappear_from_followup_status(self):
        b=frame();root,s=self.capture(b,registry_for(b),calendar=[]);follow=json.loads((root/WATCH_STATUS).read_text())
        self.assertFalse(follow['reference_calendar_valid']);self.assertTrue(follow['rows'][0]['observed'])

if __name__=='__main__':unittest.main()


