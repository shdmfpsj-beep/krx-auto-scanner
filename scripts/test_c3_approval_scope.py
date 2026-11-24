"""Buy approval scope never upgrades unverified finance or changes entry math."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from c3_top5_financial_selection import select, approval_scope, APPROVAL_POLICY, REVIEW_SCOPE
from c3_balanced_validation import exit_code, run
from test_c3_top5_financial_selection import candidate, record, evidence, ASOF


def financial(*rows):
    f=evidence(*rows,status='REVIEW_REQUIRED')
    f.update(model='BALANCED_QUALITY_TIMING_V1',request_scope=REVIEW_SCOPE,aggregate_policy=APPROVAL_POLICY)
    return f


def fact(code='111111',verdict='QUALIFIED',**changes):
    r=record(code,financial_model='BALANCED_QUALITY_TIMING_V1',financial_verdict=verdict,
        risk_assessment=dict(state='PASS',mandatory_missing=[]),
        quality_100=dict(score=70,comparison_signature=['safety']))
    if verdict!='QUALIFIED':r.update(financial_evidence_complete=False,financial_risk_gate_pass=False,
        risk_assessment=dict(state='REVIEW_REQUIRED',mandatory_missing=['BORROWING_TOTAL']))
    r.update(changes);return r


def rejected_chart(code='111111'):
    return candidate(code,'PASS_RISK_GEOMETRY',entry_status='WATCH',geometry_validated=False,
        stop_ref=None,rejected_structural_stop_ref=9400,risk_pct=6,rejection_reasons=['RISK_ABOVE_5PCT'])


class ApprovalScopeTests(unittest.TestCase):
    def result(self,charts,*rows):return select(dict(asof=ASOF,candidates=charts),financial(*rows))

    def test_three_financial_pass_no_entry_is_cash(self):
        charts=[rejected_chart(),candidate('222222','WATCH',close=10300),candidate('333333','WATCH',close=10400)]
        r=self.result(charts,*(fact(c['code']) for c in charts))
        self.assertEqual(r['operational_status'],'CASH_NO_ELIGIBLE');self.assertEqual(r['selected_count'],0)
        self.assertEqual(r['financial_pass_count'],3)

    def test_three_financial_pass_one_entry_selects_only_intersection(self):
        charts=[rejected_chart(),candidate('222222'),candidate('333333','WATCH',close=10400)]
        r=self.result(charts,*(fact(c['code']) for c in charts))
        self.assertEqual(r['operational_status'],'TOP5_READY')
        self.assertEqual([x['code'] for x in r['selected']],['222222'])

    def test_unverified_rejected_chart_does_not_hold_or_become_pass(self):
        r=self.result([rejected_chart()],fact(verdict='REVIEW_REQUIRED'))
        self.assertEqual(r['operational_status'],'CASH_NO_ELIGIBLE')
        self.assertEqual(r['financial_verdicts']['111111'],'REVIEW_REQUIRED')
        self.assertEqual(r['comparison_conservative_operational_status'],'HOLD_FINANCIAL_UNVERIFIED')
        self.assertTrue(r['approval_financial_complete']);self.assertFalse(r['all_interest_financial_complete'])

    def test_unverified_ready_holds_even_with_other_verified_entry(self):
        r=self.result([candidate(),candidate('222222')],fact(verdict='REVIEW_REQUIRED'),fact('222222'))
        self.assertEqual(r['operational_status'],'HOLD_FINANCIAL_UNVERIFIED');self.assertEqual(r['selected'],[])

    def test_unverified_near_holds(self):
        r=self.result([candidate(status='NEAR_ENTRY')],fact(verdict='REVIEW_REQUIRED'))
        self.assertEqual(r['operational_status'],'HOLD_FINANCIAL_UNVERIFIED')

    def test_unverified_watch_is_observation_only_and_never_promoted(self):
        r=self.result([candidate(status='WATCH',close=10400)],fact(verdict='REVIEW_REQUIRED'))
        self.assertEqual(r['operational_status'],'CASH_NO_ELIGIBLE');self.assertEqual(r['selected_count'],0)
        self.assertEqual(r['nonblocking_financial_unverified_codes'],['111111'])

    def test_authentication_is_error_even_when_chart_is_rejected(self):
        for event in (dict(api_status='010'),dict(http_status=401),dict(api_status='020')):
            r=self.result([rejected_chart()],fact(verdict='ERROR',source_observations=[event]))
            self.assertEqual(r['operational_status'],'ERROR')

    def test_original_integrity_and_future_qualified_record_remain_global_errors(self):
        for changes in (dict(financial_verdict='ERROR',financial_evidence_state='VALIDATION_ERROR'),
                        dict(filing_date='2026-11-21'),dict(error='DOCUMENT_CACHE_INTEGRITY_ERROR')):
            r=self.result([rejected_chart()],fact(**changes))
            self.assertEqual(r['operational_status'],'ERROR');self.assertEqual(r['selected_count'],0)

    def test_isolated_optional_transport_error_is_visible_without_fake_financial_pass(self):
        r=self.result([rejected_chart(),candidate('222222')],fact(verdict='ERROR',error='TimeoutError'),fact('222222'))
        self.assertEqual(r['operational_status'],'TOP5_READY')
        self.assertEqual(r['financial_verdicts']['111111'],'ERROR');self.assertEqual(r['selected_count'],1)

    def test_all_candidate_api_outage_is_global_error(self):
        r=self.result([rejected_chart()],fact(verdict='ERROR',error='TimeoutError',financial_evidence_state='API_ERROR'))
        self.assertEqual(r['operational_status'],'ERROR')

    def test_five_and_maximum_five_positive_fixture(self):
        for count in (5,6):
            charts=[candidate(str(100000+i)) for i in range(count)]
            r=self.result(charts,*(fact(c['code']) for c in charts))
            self.assertEqual(r['operational_status'],'TOP5_READY');self.assertEqual(r['selected_count'],5)

    def test_all_confirmed_technical_rejections_are_cash(self):
        charts=[rejected_chart(str(100000+i)) for i in range(3)]
        r=self.result(charts,*(fact(c['code'],verdict='REVIEW_REQUIRED') for c in charts))
        self.assertEqual(r['operational_status'],'CASH_NO_ELIGIBLE')

    def test_missing_required_financial_request_is_error_not_cash(self):
        r=self.result([candidate()])
        self.assertEqual(r['operational_status'],'ERROR')

    def test_unreviewed_actionable_budget_is_hold(self):
        from c3_top5_financial_selection import financial_review_candidates
        charts=[candidate(str(100000+i)) for i in range(31)]
        rows=[fact(c['code']) for c in financial_review_candidates(dict(candidates=charts))]
        r=self.result(charts,*rows)
        self.assertEqual(r['operational_status'],'HOLD_FINANCIAL_UNVERIFIED');self.assertEqual(r['selected'],[])

    def test_unproven_geometry_rejection_is_hold_data(self):
        for c in (candidate(geometry_validated=False),{**rejected_chart(),'rejected_structural_stop_ref':9600},
                  {**rejected_chart(),'rejected_structural_stop_ref':None}):
            r=self.result([c],fact())
            self.assertEqual(r['operational_status'],'HOLD_DATA_INCOMPLETE');self.assertEqual(r['selected'],[])

    def test_empty_interval_is_proven_but_reason_label_alone_is_not(self):
        c=rejected_chart();c.update(entry_low=None,entry_high=None,attempted_entry_low=10000,
            attempted_entry_high=9950,rejection_reasons=['EMPTY_ENTRY_INTERSECTION'])
        self.assertTrue(approval_scope(c)['verified'])
        c['attempted_entry_high']=10050
        self.assertFalse(approval_scope(c)['verified'])

    def test_five_percent_and_status_tampering_still_block_approval(self):
        for c in (candidate(stop_ref=9400,risk_pct=6),candidate(entry_low=10100),candidate(close=10500)):
            r=self.result([c],fact())
            self.assertEqual(r['selected_count'],0);self.assertEqual(r['operational_status'],'ERROR')

    def test_policy_does_not_mutate_original_financial_or_geometry(self):
        g=dict(asof=ASOF,candidates=[rejected_chart()]);f=financial(fact(verdict='REVIEW_REQUIRED'))
        before=copy.deepcopy((g,f));select(g,f);self.assertEqual((g,f),before)

    def test_operational_exit_contract_keeps_default_hold_exit_two(self):
        for state in ('HOLD_FINANCIAL_UNVERIFIED','HOLD_DATA_INCOMPLETE'):
            x=dict(status='REVIEW_REQUIRED',operational_status=state)
            self.assertEqual(exit_code(x),2);self.assertEqual(exit_code(x,True),0)
        self.assertEqual(exit_code(dict(status='ERROR',operational_status='ERROR'),True),1)
        raw=dict(status='ERROR',operational_status='HOLD_DATA_INCOMPLETE')
        self.assertEqual(exit_code(raw),1);self.assertEqual(exit_code(raw,True),0)

    def test_foreign_financial_model_cannot_use_balanced_approval_policy(self):
        r=self.result([candidate()],record())
        self.assertEqual(r['operational_status'],'ERROR');self.assertEqual(r['selected'],[])

    def test_confirmed_financial_rejection_of_executable_entry_is_cash(self):
        from test_c3_balanced_financials import BalancedFinancialTests
        t=BalancedFinancialTests();t.setUp()
        try:
            f=t.collect(t.rejected_payload);f.update(aggregate_policy=APPROVAL_POLICY,request_scope=REVIEW_SCOPE)
            r=select(dict(asof=ASOF,candidates=[candidate()]),f)
            self.assertEqual(r['operational_status'],'CASH_NO_ELIGIBLE')
            self.assertEqual(r['financial_decision_counts']['REJECTED_FINANCIAL_RISK'],1)
        finally:t.doCleanups()

    def test_data_hold_manifest_is_blocked_before_network_and_receipts(self):
        from test_c3_top5_pipeline import PipelineTests,BUILD,DELIVERY
        t=PipelineTests();t.setUp()
        try:
            t.prepare(empty=True)
            t.write('financial_selection_research.json',dict(asof=ASOF,status='REVIEW_REQUIRED',
                operational_status='HOLD_DATA_INCOMPLETE',selected=[],selected_count=0,signals=[]))
            self.assertEqual(t.execute(BUILD).returncode,0)
            result=t.execute(DELIVERY);self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(t.result()['status'],'HOLD');self.assertEqual(t.result()['telegram_photos_sent'],0)
            self.assertFalse((t.cwd/'receipts').exists())
        finally:t.doCleanups()

    def test_hold_delivery_integration_never_reserves_or_sends(self):
        from test_c3_top5_pipeline import PipelineTests
        t=PipelineTests();t.setUp()
        try:
            t.prepare()
            g=dict(asof=ASOF,candidates=[candidate(name='검증용')]);t.write('entry_geometry_audit.json',g)
            f=financial(fact(verdict='REVIEW_REQUIRED'))
            with tempfile.TemporaryDirectory() as tmp,patch('c3_balanced_validation.collect_balanced',return_value=f):
                r=run(Path(tmp)/'out',Path(tmp)/'cache',t.root)
                self.assertEqual(r['operational_status'],'HOLD_FINANCIAL_UNVERIFIED',r)
                self.assertEqual(r['delivery_status'],'HOLD');self.assertEqual(r['telegram_photos_sent'],0)
                self.assertFalse((Path(tmp)/'out/delivery_boundary/receipts').exists())
        finally:t.doCleanups()

    def test_incomplete_krx_preflight_is_hold_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir()
            for name,data in [('receipt',dict(asof=ASOF,source_integrity=dict(session_count=59))),
                ('entry_geometry_audit',dict(asof=ASOF,candidates=[])),('qualified_chart_pool',dict(asof=ASOF,candidates=[]))]:
                (source/(name+'.json')).write_text(json.dumps(data))
            self.assertEqual(run(root/'out',root/'cache',source)['operational_status'],'HOLD_DATA_INCOMPLETE')

    def test_daily_action_summary_distinguishes_cash_top5_holds_and_error(self):
        from test_c3_top5_pipeline import PipelineTests
        t=PipelineTests();t.setUp()
        try:
            for state,delivery,expected in [('CASH_NO_ELIGIBLE','CASH',0),('TOP5_READY','DRY_RUN',0),
                ('HOLD_FINANCIAL_UNVERIFIED','HOLD',0),('HOLD_DATA_INCOMPLETE','HOLD',0),('TOP5_READY','ERROR',1)]:
                t.write('financial_selection_research.json',dict(asof=ASOF,operational_status=state))
                t.write('delivery_result.json',dict(status=delivery,telegram_photos_sent=0))
                result=t.execute('Publish operational outcome without sending');self.assertEqual(result.returncode,expected,result.stderr)
                outcome=json.loads((t.root/'execution_outcome.json').read_text())
                self.assertEqual(outcome['program_status'],'ERROR' if expected else 'COMPLETED')
                self.assertFalse((t.cwd/'receipts').exists())
        finally:t.doCleanups()


class FixedAsOfReplayTests(unittest.TestCase):
    def test_fixed_collection_environment_pins_date_and_removes_send_credentials(self):
        from c3_balanced_validation import collection_environment
        with patch.dict('os.environ',dict(TELEGRAM_BOT_TOKEN='private',TELEGRAM_CHAT_ID='private',C3_MANUAL_ASOF='20990101')):
            env=collection_environment(Path('/isolated'),'20261123')
        self.assertEqual(env['C3_MANUAL_ASOF'],'20261123');self.assertEqual(env['C3_TEST_SEND_TELEGRAM'],'false')
        self.assertEqual(env['GITHUB_EVENT_NAME'],'workflow_dispatch')
        self.assertNotIn('TELEGRAM_BOT_TOKEN',env);self.assertNotIn('TELEGRAM_CHAT_ID',env)

    def test_invalid_fixed_date_fails_before_collection(self):
        from c3_balanced_validation import collection_environment
        for day in ('2026112','20261131','2026-11-23',True):
            with self.assertRaisesRegex(ValueError,'INVALID_FIXED_ASOF'):
                collection_environment(Path('/isolated'),day)

    def test_invalid_fixed_configuration_is_error_not_successful_hold(self):
        with tempfile.TemporaryDirectory() as tmp,patch('c3_balanced_validation.subprocess.run') as child:
            r=run(Path(tmp)/'out',Path(tmp)/'cache',live=True,asof='not-a-date')
            self.assertEqual(r['operational_status'],'ERROR');self.assertEqual(exit_code(r,True),1)
            child.assert_not_called()

    def test_fixed_date_cannot_silently_accept_other_source_day(self):
        from test_c3_top5_pipeline import PipelineTests
        t=PipelineTests();t.setUp()
        try:
            t.prepare(empty=True)
            t.write('entry_geometry_audit.json',dict(asof=ASOF,candidates=[]))
            with tempfile.TemporaryDirectory() as tmp,patch('c3_balanced_validation.collect_balanced') as fetch:
                r=run(Path(tmp)/'out',Path(tmp)/'cache',t.root,asof='20261119')
                self.assertEqual(r['error'],'SOURCE_FIXED_ASOF_MISMATCH');fetch.assert_not_called()
        finally:t.doCleanups()

    def test_future_or_duplicate_bar_cannot_enter_fixed_day_selection(self):
        from test_c3_top5_pipeline import PipelineTests
        t=PipelineTests();t.setUp()
        try:
            pool,_=t.prepare();pool['candidates'][0]['bars'][-1]['date']='20261121'
            t.write('qualified_chart_pool.json',pool)
            t.write('entry_geometry_audit.json',dict(asof=ASOF,candidates=[candidate(name='검증용')]))
            with tempfile.TemporaryDirectory() as tmp,patch('c3_balanced_validation.collect_balanced') as fetch:
                r=run(Path(tmp)/'out',Path(tmp)/'cache',t.root,asof=ASOF)
                self.assertEqual(r['error'],'SOURCE_BAR_DATE_MISMATCH');fetch.assert_not_called()
        finally:t.doCleanups()

    def test_fixed_asof_and_latest_switch_cannot_be_combined(self):
        from contextlib import redirect_stderr
        from io import StringIO
        from c3_balanced_validation import main
        with patch('sys.argv',['validation','--asof','20261123','--require-latest-source','--out','out','--cache','cache']), \
             redirect_stderr(StringIO()),patch('c3_balanced_validation.run') as fetch:
            with self.assertRaises(SystemExit) as raised:main()
            self.assertEqual(raised.exception.code,2);fetch.assert_not_called()

    def test_krx_original_response_capture_has_exact_hash_and_no_auth_header(self):
        import ast,os,hashlib,time,datetime,urllib.request,urllib.error,urllib.parse
        from unittest.mock import MagicMock
        from c3_balanced_validation import embedded
        node=next(n for n in ast.parse(embedded('Collect KRX sessions and render one classic image per stock')).body
                  if isinstance(n,ast.FunctionDef) and n.name=='fetch')
        scope=dict(os=os,Path=Path,json=json,hashlib=hashlib,datetime=datetime,urllib=urllib,time=time)
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<unchanged-krx-fetch-with-capture>','exec'),scope)
        raw=b'{"OutBlock_1":[{"BAS_DD":"20261123","ISU_CD":"111111"}]}'
        response=MagicMock();response.__enter__.return_value=response;response.read.return_value=raw
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,dict(KRX_AUTH_KEY='NEVER_WRITE_THIS_AUTH_KEY',C3_KRX_CAPTURE_DIR=tmp)), \
             patch('urllib.request.urlopen',return_value=response):
            self.assertEqual(len(scope['fetch']('20261123','stk_bydd_trd')),1)
            payload=Path(tmp)/'stk_bydd_trd_20261123.json';self.assertEqual(payload.read_bytes(),raw)
            meta=json.loads((Path(tmp)/'stk_bydd_trd_20261123.meta.json').read_text())
            self.assertEqual(meta['sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(meta['rows'],1)
            for file in Path(tmp).iterdir():self.assertNotIn('NEVER_WRITE_THIS_AUTH_KEY',file.read_text())


if __name__=='__main__':unittest.main()
