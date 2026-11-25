"""Unapproved independent-scope comparison cannot write operating outcomes or send."""
import copy
import os
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
from c3_financial_policy_comparison import compare
from test_c3_approval_scope import financial, fact
from test_c3_top5_financial_selection import candidate, ASOF


def inputs(charts=None, facts=None):
    charts=charts or [candidate(),candidate('222222')]
    facts=facts or [fact(),fact('222222',verdict='REVIEW_REQUIRED')]
    geometry=dict(asof=ASOF,candidates=charts)
    pool=dict(asof=ASOF,entry_valid_until='2026-11-23T15:30:00+09:00',candidates=copy.deepcopy(charts))
    bycode={f['ticker']:f for f in facts}
    report=dict(asof=ASOF,candidates=[dict(c,asof_close=c['close'],composite_score=70,top5=False,
        financial_verdict='PASS' if bycode[c['code']]['financial_verdict']=='QUALIFIED' else bycode[c['code']]['financial_verdict']) for c in charts])
    return geometry,pool,financial(*facts),report


class PolicyComparisonTests(unittest.TestCase):
    def run_comparison(self,args=None,blocked=None):return compare(*(args or inputs()),blocked or set())

    def test_verified_company_is_only_hypothetical_selection_and_original_stays_hold(self):
        r=self.run_comparison()
        self.assertEqual(r['policy_a']['operational_status'],'HOLD_FINANCIAL_UNVERIFIED')
        self.assertEqual(r['policy_b']['top5'],1);self.assertEqual(r['policy_b']['selected'][0]['code'],'111111')
        self.assertEqual(r['policy_b']['excluded_financial_verdicts'],{'222222':'REVIEW_REQUIRED'})
        self.assertFalse(r['main_policy_changed']);self.assertFalse(r['delivery_authorized'])
        self.assertFalse(r['all_interest_financial_complete'])

    def test_watch_is_separate_and_original_risk_limit_and_sorting_are_used(self):
        charts=[candidate(),candidate('222222','WATCH',close=10400),candidate('333333')]
        rows=[fact(),fact('222222'),fact('333333',verdict='REVIEW_REQUIRED')]
        r=self.run_comparison(inputs(charts,rows))
        self.assertEqual(r['policy_b']['top5'],1);self.assertEqual(r['policy_b']['watch5'],1)
        self.assertEqual(r['policy_b']['watch'][0]['code'],'222222')

    def test_common_authentication_failure_blocks_all_other_verified_stocks(self):
        args=inputs(facts=[fact(),fact('222222',verdict='ERROR',source_observations=[dict(http_status=401)])])
        r=self.run_comparison(args)
        self.assertTrue(r['policy_b']['system_wide_block']);self.assertEqual(r['policy_b']['top5'],0)

    def test_isolated_company_transport_error_is_excluded_and_never_promoted(self):
        args=inputs(facts=[fact(),fact('222222',verdict='ERROR',error='TimeoutError')])
        r=self.run_comparison(args)
        self.assertEqual(r['policy_b']['top5'],1)
        self.assertEqual(r['policy_b']['excluded_financial_verdicts']['222222'],'ERROR')

    def test_unproven_geometry_is_common_data_hold(self):
        args=inputs(charts=[candidate(geometry_validated=False),candidate('222222')])
        r=self.run_comparison(args);self.assertTrue(r['policy_b']['system_wide_block'])
        self.assertEqual(r['policy_b']['top5'],0);self.assertEqual(r['policy_b']['watch5'],0)

    def test_unverified_filing_identity_blocks_entire_comparison(self):
        args=inputs(facts=[fact(),fact('222222',verdict='ERROR',error='DOCUMENT_COMPANY_MISMATCH')])
        r=self.run_comparison(args);self.assertTrue(r['policy_b']['system_wide_block'])
        self.assertEqual(r['policy_b']['top5'],0)

    def test_risk_above_five_percent_is_not_repaired_or_selected(self):
        c=candidate(status='WATCH',entry_status='WATCH',geometry_validated=False,stop_ref=None,
            rejected_structural_stop_ref=9400,risk_pct=6,rejection_reasons=['RISK_ABOVE_5PCT'])
        args=inputs(charts=[c,candidate('222222')],facts=[fact(),fact('222222',verdict='REVIEW_REQUIRED')])
        r=self.run_comparison(args);self.assertEqual(r['policy_b']['top5'],0);self.assertEqual(r['policy_b']['watch5'],0)

    def test_history_block_survives_subset_approval(self):
        r=self.run_comparison(blocked={'111111'})
        self.assertEqual(r['policy_b']['top5'],0)

    def test_maximum_five_and_no_forced_fill(self):
        charts=[candidate(str(100000+i)) for i in range(7)]
        r=self.run_comparison(inputs(charts,[fact(c['code']) for c in charts]))
        self.assertEqual(r['policy_b']['top5'],5)

    def test_expired_signal_never_transmits_even_with_live_environment(self):
        with patch.dict(os.environ,{'C3_MANUAL_LIVE_DELIVERY':'true','GITHUB_EVENT_NAME':'schedule','TELEGRAM_BOT_TOKEN':'TEST'}), \
                patch('urllib.request.urlopen',side_effect=AssertionError('NETWORK_FORBIDDEN')):
            r=self.run_comparison()
        self.assertTrue(r['signal_expired']);self.assertFalse(r['delivery_authorized'])
        self.assertEqual(r['telegram_photos_sent'],0);self.assertFalse(r['operating_receipts_created'])

    def test_source_objects_and_original_verdicts_are_unchanged(self):
        args=inputs();before=copy.deepcopy(args);self.run_comparison(args)
        self.assertEqual(args,before)

    def test_asof_mismatch_is_not_silently_fixed(self):
        args=inputs();args[1]['asof']='20261119'
        with self.assertRaisesRegex(ValueError,'DATE_MISMATCH'):self.run_comparison(args)

    def test_comparison_is_not_connected_to_production_or_live_permissions(self):
        root=Path(__file__).resolve().parents[1]
        daily=(root/'.github/workflows/c3_top5_daily_telegram.yml').read_text()
        self.assertNotIn('c3_financial_policy_comparison',daily)
        workflow=(root/'.github/workflows/c3_financial_policy_review.yml').read_text()
        for forbidden in ('TELEGRAM_BOT_TOKEN','actions: write','contents: write','schedule:','workflow_dispatch:'):
            self.assertNotIn(forbidden,workflow)


if __name__=='__main__':unittest.main()
