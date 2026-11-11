"""Adversarial end-to-end report tests. No real Telegram or ledger writes."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import c3_telegram_notify as notify
from c3_classic_theme import source_labels
from c3_entry_geometry_gate import assess
from c3_final_delivery_gate_v1 import review
import test_c3_telegram_notify as cases


class NightlyPreflightTests(unittest.TestCase):
    def test_dated_cache_checks_market_counts_and_do_not_certify_session(self):
        from c3_nightly_preflight_v1 import audit_cache
        raw=b'Code,Name,MarketId,Market,Open,High,Low,Close,Volume,Amount\n000001,ONE,STK,KOSPI,100,110,90,105,10,1050\n000002,TWO,KSQ,KOSDAQ,0,0,0,100,0,0\n'
        result=audit_cache(raw,'2026-11-11',raw)
        self.assertEqual(result['market_rows'],{'KOSPI':1,'KOSDAQ':1})
        self.assertEqual(result['issues'],[]);self.assertFalse(result['regular_only_certified'])
        self.assertEqual(result['zero_volume_rows'],1)

    def test_cache_corrupt_numbers_duplicates_and_name_mismatches_fail_closed(self):
        from c3_nightly_preflight_v1 import audit_cache
        header='Code,Name,MarketId,Market,Open,High,Low,Close,Volume,Amount\n'
        for row in ('000001,ONE,STK,KOSPI,100,90,80,105,10,1050\n',
                    '000001,,STK,KOSPI,100,110,90,105,10,1050\n',
                    '000001,ONE,STK,KOSPI,100,110,90,105,nan,1050\n'):
            result=audit_cache((header+row+row).encode(),'2026-11-11')
            self.assertEqual(result['status'],'INTERNAL_QUALITY_FAILED')

    def test_final_zero_one_two_pass_actual_input_gate_only_when_enabled(self):
        report, summary, clock = cases.fixture()
        for n in (0, 1, 2):
            current=copy.deepcopy(report);current['research_top2']=current['research_top2'][:n]
            with self.subTest(n=n), patch.dict(os.environ, {'C3_FINAL_GATE_ENABLED':'1'}):
                self.assertIsNone(notify.report_error(current,summary,clock))
            if n<2:
                with patch.dict(os.environ, {'C3_FINAL_GATE_ENABLED':'0'}):
                    self.assertEqual(notify.report_error(current,summary,clock),'EXACTLY_TWO_UNIQUE_CANDIDATES_REQUIRED')

    def test_missing_candidate_field_is_never_authenticated_empty_decision(self):
        r,s,c=cases.fixture();del r['research_top2']
        with patch.dict(os.environ, {'C3_FINAL_GATE_ENABLED':'1'}):
            self.assertEqual(notify.report_error(r,s,c),'FINAL_CANDIDATE_COUNT_OR_IDENTITY_INVALID')

    def test_missing_future_and_preclose_analysis_are_rejected(self):
        for value in (None,'2026-11-06T13:31:00Z','2026-11-06T06:29:00Z'):
            r,s,c=cases.fixture()
            if value is None:del r['analysis_completed_at']
            else:r['analysis_completed_at']=value
            self.assertIsNotNone(notify.report_error(r,s,c))

    def test_later_read_of_same_frozen_decision_is_valid(self):
        r,s,c=cases.fixture();r['source_received_at']='2026-11-06T13:29:45Z'
        self.assertIsNone(notify.report_error(r,s,c))

    def test_incomplete_source_does_not_become_zero_candidates(self):
        r,s,c=cases.fixture();r['research_top2']=[];r['research_top2_registered_for_source_session']=False
        with patch.dict(os.environ, {'C3_FINAL_GATE_ENABLED':'1'}):
            self.assertEqual(notify.report_error(r,s,c),'UNREGISTERED_RESEARCH_PREVIEW')
        r,s,c=cases.fixture();r['research_top2']=[];r['source_price_asof']='2026-11-05'
        self.assertEqual(notify.report_error(r,s,c),'NO_NEW_COMPLETED_SESSION')

    def test_zero_one_two_end_to_end_dryrun_never_constructs_sender_or_store(self):
        for n in (0,1,2):
            sample=cases.FinalPresentationReviewTests().synthetic_report(n)
            r,s,c=cases.fixture();r.update(sample)
            r['source_price_asof']='2026-11-06'
            # Use the dated synthetic bars as a separate session, then a valid
            # report clock for that exact session. Never substitute real prices.
            from datetime import datetime
            from zoneinfo import ZoneInfo
            r['source_price_asof']='2026-11-10'
            r.update(generated_at='2026-11-10T13:30:00Z',source_received_at='2026-11-10T13:29:00Z',analysis_completed_at='2026-11-10T13:29:30Z')
            for row in r['research_top2']:
                row.update(decision_date='2026-11-10',order_validity_sessions=1)
            s={k:r[k] for k in ('source_price_asof','source_run_id','generated_at')}
            c=datetime(2026,11,10,22,45,tzinfo=ZoneInfo('Asia/Seoul'))
            original=json.dumps(r,sort_keys=True)
            with self.subTest(n=n),tempfile.TemporaryDirectory() as tmp, \
                 patch.object(notify,'GitHub',return_value=Mock(sources=[])), \
                 patch.object(notify,'report_pair',return_value=(copy.deepcopy(r),s,'a'*40)), \
                 patch.object(notify,'frozen_live_bars',side_effect=lambda gh,r,ref:r), \
                 patch.object(notify,'now_kst',return_value=c), \
                 patch.object(notify,'Telegram') as sender,patch.object(notify,'ReceiptStore') as store, \
                 patch('c3_report_context.attach_context',side_effect=lambda r,*args:r), \
                 patch.dict(os.environ,{'C3_FINAL_GATE_ENABLED':'1'}), \
                 patch('sys.argv',['notify','--mode','live','--dry-run','--outdir',tmp]):
                self.assertEqual(notify.main(),0)
                sender.assert_not_called();store.assert_not_called()
                status=json.loads(Path(tmp,'delivery_status.json').read_text())
                self.assertEqual(status['photos'],max(1,n));self.assertEqual(status['send_attempts'],0)
                self.assertEqual(json.dumps(r,sort_keys=True),original)

    def test_frozen_decision_count_and_name_are_not_silently_discarded(self):
        helper=cases.FrozenDecisionTests()
        for mode in ('dropped','name'):
            r,record=helper.sample()
            if mode=='dropped':r['research_top2']=[]
            else:r['research_top2'][0]['name']='ALTERED'
            with self.assertRaisesRegex(ValueError,'MISMATCH'):helper.load(r,record)

    def test_invalid_prices_fail_closed_without_arithmetic_crash(self):
        for changes in ({'high':0},{'stop':99},{'low':float('nan')},{'resistance':float('inf')}):
            row={'reference_close':100,'entry_plans':{'A_SUPPORT_LIMIT':{'plan':dict(low=97,high=99,stop=95,resistance=110,**{})}}}
            row['entry_plans']['A_SUPPORT_LIMIT']['plan'].update(changes)
            self.assertFalse(assess(row)['eligible'])

    def test_warmup_is_measured_and_expiry_is_original_only(self):
        r=cases.FinalPresentationReviewTests().synthetic_report(1);row=r['research_top2'][0]
        row.update(order_validity_sessions=1,decision_date='2026-11-10',source_received_at='2026-11-10T13:00:00Z')
        labels=source_labels(r,row,row['chart_bars'])
        self.assertEqual(labels['ma60_visible_points'],31)
        self.assertFalse(labels['ma60_full_visible_window'])
        self.assertEqual(labels['required_rows_for_full_ma60_window'],119)
        self.assertIn('PASS',labels['validity'])
        del row['order_validity_sessions']
        self.assertIn('미확정',source_labels(r,row,row['chart_bars'])['validity'])

    def test_cash_distinguishes_data_blocker_from_no_entry(self):
        r=cases.FinalPresentationReviewTests().synthetic_report(1)
        r['source_regular_only_certified']=False
        self.assertEqual(review(r)['cash_reason'],'SOURCE_VALIDATION_BLOCKED')


if __name__=='__main__':unittest.main()
