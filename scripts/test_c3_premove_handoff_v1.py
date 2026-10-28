import gzip,json,tempfile,unittest
from pathlib import Path
import numpy as np,pandas as pd
from c3_premove_handoff_v1 import PremoveObserver,CSV_NAME,HISTORY_NAME,STATUS_NAME,record_failure

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

if __name__=='__main__':unittest.main()
