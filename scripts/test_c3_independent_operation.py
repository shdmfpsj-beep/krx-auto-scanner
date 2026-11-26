"""Approved issuer-level operation and separate reference transport regressions."""
import copy
import hashlib
import json
import os
import tempfile
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from c3_top5_financial_selection import (select, INDEPENDENT_POLICY, selection_approval_complete,
    validate_selection_approval)
from c3_watch5_delivery import choose, choose_reference, run, image_bytes, REVIEW_LABEL
from c3_delivery_outcome import finalize
from c3_delivery_authorization import approved_manual_delivery, INDEPENDENT_REQUEST_PREFIX, INDEPENDENT_RELEASE_PREFIX
from c3_operating_recovery import diagnose, release_independent
from c3_candidate_decisions import report as decisions
from test_c3_approval_scope import fact, financial, rejected_chart
from test_c3_top5_financial_selection import candidate, ASOF
from test_c3_watch5_delivery import fixture, write, Response, CLOCK
from test_c3_operating_recovery import FakeGitHub, manual_env


def independently(charts,*rows):
    g=dict(asof=ASOF,candidates=charts)
    f=financial(*rows);f['aggregate_policy']=INDEPENDENT_POLICY
    return select(g,f)


class IndependentSelectionTests(unittest.TestCase):
    def test_pass_and_unverified_select_only_pass_and_preserve_whole_flags(self):
        r=independently([candidate(),candidate('222222')],fact(),fact('222222','REVIEW_REQUIRED'))
        self.assertEqual([x['code'] for x in r['selected']],['111111'])
        self.assertEqual(r['operational_status'],'TOP5_READY')
        self.assertFalse(r['approval_financial_complete']);self.assertFalse(r['all_interest_financial_complete'])
        old=select(dict(asof=ASOF,candidates=[candidate(),candidate('222222')]),financial(fact(),fact('222222','REVIEW_REQUIRED')))
        self.assertEqual(r['coverage_complete'],old['coverage_complete']);self.assertTrue(selection_approval_complete(r))
        self.assertEqual(r['comparison_whole_approval_operational_status'],'HOLD_FINANCIAL_UNVERIFIED')
        self.assertEqual(r['financial_unverified_excluded_codes'],['222222'])

    def test_only_review_or_only_pass_watch_is_cash_with_disclosed_exclusions(self):
        for chart,row in [(candidate(),fact(verdict='REVIEW_REQUIRED')),
                          (candidate(status='WATCH',close=10400),fact())]:
            r=independently([chart],row)
            self.assertEqual(r['operational_status'],'CASH_NO_ELIGIBLE');self.assertFalse(r['selected'])
            self.assertTrue(selection_approval_complete(r))

    def test_pass_risk_or_empty_invalid_chart_never_promoted(self):
        for chart in (rejected_chart(),candidate(status='WATCH',close=10400)):
            r=independently([chart],fact());self.assertFalse(r['selected'])
        r=independently([candidate(entry_low=10010)],fact())
        self.assertIn(r['operational_status'],('ERROR','HOLD_DATA_INCOMPLETE'));self.assertFalse(r['selected'])

    def test_unknown_and_auth_rate_identity_integrity_errors_are_global(self):
        for changes in (dict(error='TimeoutError'),dict(error='RuntimeError'),
            dict(error='DOCUMENT_CACHE_INTEGRITY'),dict(financial_evidence_state='VALIDATION_ERROR'),
            dict(source_observations=[dict(http_status=401)]),
            dict(source_observations=[dict(api_status='020')])):
            r=independently([candidate(),candidate('222222')],fact(),fact('222222','ERROR',**changes))
            self.assertEqual(r['operational_status'],'ERROR');self.assertFalse(r['selected'])

    def test_independent_transport_failure_requires_same_endpoint_success(self):
        error=fact('222222','ERROR',error='TimeoutError',source_observations=[dict(state='ERROR',endpoint='fnlttSinglAcntAll',http_status=504)])
        good=fact(source_observations=[dict(state='FETCH',endpoint='fnlttSinglAcntAll',api_status='000')])
        r=independently([candidate(),candidate('222222')],good,error)
        self.assertEqual(r['operational_status'],'TOP5_READY');self.assertEqual(r['selected_count'],1)
        self.assertEqual(r['financial_verdicts']['222222'],'ERROR');self.assertFalse(r['unclassified_issuer_error_codes'])

    def test_future_filing_on_review_and_date_mismatch_never_downgraded(self):
        r=independently([candidate(),candidate('222222')],fact(),fact('222222','REVIEW_REQUIRED',filing_date='2099-01-01'))
        self.assertEqual(r['operational_status'],'ERROR')
        f=financial(fact());f.update(aggregate_policy=INDEPENDENT_POLICY,asof='20990101')
        self.assertEqual(select(dict(asof=ASOF,candidates=[candidate()]),f)['operational_status'],'ERROR')

    def test_selected_flags_cannot_replace_original_evidence(self):
        g=dict(asof=ASOF,candidates=[candidate()]);f=financial(fact());f['aggregate_policy']=INDEPENDENT_POLICY
        r=select(g,f);pool=copy.deepcopy(g)
        self.assertTrue(validate_selection_approval(r,g,f,pool))
        r['selected'][0]['entry_low']+=10
        with self.assertRaisesRegex(ValueError,'SOURCE_MISMATCH'):validate_selection_approval(r,g,f,pool)

    def test_missing_observation_and_uncomputed_geometry_still_block(self):
        for charts,rows in [([candidate()],[]),([candidate(geometry_validated=False)],[fact()])]:
            r=independently(charts,*rows)
            self.assertIn(r['operational_status'],('ERROR','HOLD_DATA_INCOMPLETE'));self.assertFalse(r['selected'])


class ReferencePipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'output/c3_top5'
        self.env=dict(C3_FINANCIAL_MODEL='balanced',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF_NAME='main',
            GITHUB_REPOSITORY='shdmfpsj-beep/krx-auto-scanner',GITHUB_RUN_ID='mock',
            TELEGRAM_BOT_TOKEN='never-log-token',TELEGRAM_CHAT_ID='-123',GH_TOKEN='never-log-gh',
            C3_FONT_DIR=os.environ.get('C3_FONT_DIR','/usr/share/fonts/truetype/nanum'))

    def prepare(self,refs=1):
        # Reuse the existing real classic renderer and synthetic boundary fixture.
        fixture(self.root,watches=0,top5=refs+1)
        read=lambda n:json.loads((self.root/(n+'.json')).read_text())
        g,f=read('entry_geometry_audit'),read('financial_pool_gate')
        f['aggregate_policy']=INDEPENDENT_POLICY
        rows=f['researched']+f['excluded']
        for row in rows:
            if row['ticker']!='100000':row.update(fact(row['ticker'],'REVIEW_REQUIRED'))
        s=select(g,f);receipt=read('receipt')
        for name,item in [('financial_pool_gate',f),('financial_selection_research',s),
            ('candidate_decisions',decisions(receipt,g,s,f)),
            ('watch_delivery_result',dict(status='EMPTY',selected=[],photos=[],telegram_photos_sent=0))]:write(self.root/(name+'.json'),item)
        report=read('all_candidate_report/manifest')
        for row in report['candidates']:
            row['top5']=row['code']=='100000'
            row['financial_verdict']='PASS' if row['top5'] else 'REVIEW_REQUIRED'
            row['financial_eligibility']='QUALIFIED_BASIC_FINANCIAL_RISK' if row['top5'] else 'REVIEW_INSUFFICIENT_EVIDENCE'
            if not row['top5']:row['status']='REVIEW_REQUIRED'
        # Regenerate source images and original metadata after changing finance.
        import subprocess,sys
        from test_c3_watch5_delivery import REPO
        process=subprocess.run([sys.executable,str(REPO/'scripts/c3_all_candidate_report.py'),
            '--pool',str(self.root/'qualified_chart_pool.json'),'--selection',str(self.root/'financial_selection_research.json'),
            '--financial',str(self.root/'financial_pool_gate.json'),'--out',str(self.root/'all_candidate_report')],capture_output=True,text=True)
        self.assertEqual(process.returncode,0,process.stderr)
        return read('all_candidate_report/manifest'),s,g,f

    def test_reference_is_separate_review_not_top5_or_watch(self):
        report,s,g,f=self.prepare()
        refs=choose_reference(report,s,g,f,set())
        self.assertEqual([r['code'] for r in refs],['100001'])
        self.assertFalse(choose(report,s,set()))
        self.assertEqual([r['code'] for r in s['selected']],['100000'])
        self.assertFalse(choose_reference(report,s,g,f,{'100001'}))

    def test_review_without_exact_reason_or_with_hard_risk_or_error_is_excluded(self):
        report,s,g,f=self.prepare();row=next(x for x in f['researched']+f['excluded'] if x['ticker']=='100001')
        for changes in (dict(error='TimeoutError'),dict(risk_assessment=dict(mandatory_missing=[])),
            dict(risk_assessment=dict(mandatory_missing=['X'],hard_failures=['REAL_RISK'])),dict(financial_verdict='REJECTED_FINANCIAL_RISK')):
            ff=copy.deepcopy(f);target=next(x for x in ff['researched']+ff['excluded'] if x['ticker']==row['ticker']);target.update(changes)
            self.assertFalse(choose_reference(report,s,g,ff,set()))

    def test_reference_uses_original_geometry_and_rejects_duplicate_report(self):
        report,s,g,f=self.prepare()
        for changes in (dict(stop_ref=9400,risk_pct=6),dict(entry_low=10100),dict(status='WATCH',entry_status='WATCH',close=10400)):
            gg=copy.deepcopy(g);gg['candidates'][1].update(changes)
            self.assertFalse(choose_reference(report,s,gg,f,set()))
        report['candidates'].append(copy.deepcopy(report['candidates'][1]))
        with self.assertRaisesRegex(ValueError,'DUPLICATE_CODE'):choose_reference(report,s,g,f,set())

    def test_five_reference_cap_technical_rank_and_no_duplicates(self):
        report,s,g,f=self.prepare(refs=6)
        rows=choose_reference(report,s,g,f,set());self.assertEqual(len(rows),5)
        self.assertEqual(len({r['code'] for r in rows}),5)
        self.assertNotIn('100000',[r['code'] for r in rows])

    def test_dry_run_png_exact_label_reasons_hash_and_no_source_mutation(self):
        self.prepare();before={p.name:p.read_bytes() for p in self.root.glob('*.json')}
        network=lambda *a,**k:self.fail('DRY_RUN_NETWORK')
        r=run(self.root,self.env,network,CLOCK,review=True)
        self.assertEqual(r['status'],'DRY_RUN');self.assertEqual(r['telegram_photos_sent'],0)
        item=r['selected'][0];identity=item['review_identity']
        self.assertEqual(identity['label'],REVIEW_LABEL);self.assertEqual(identity['financial_verdict'],'REVIEW_REQUIRED')
        self.assertFalse(identity['trade_approved']);self.assertEqual(identity['financial_unverified_reasons'],['BORROWING_TOTAL'])
        image_bytes(self.root,item,review=True)
        for name,binary in before.items():self.assertEqual((self.root/name).read_bytes(),binary,name)
        (self.root/'review_unverified'/item['image']).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):image_bytes(self.root,item,review=True)

    def transport(self,fail_at=None,existing=False,read_error=False):
        calls=[];sends=[]
        def opener(request,timeout):
            calls.append(request)
            if request.full_url.startswith('https://api.github.com/'):
                if request.get_method()=='GET':
                    if existing:return Response(200,dict(content='reservation'))
                    raise urllib.error.HTTPError(request.full_url,403 if read_error else 404,'not readable',{},None)
                payload=json.loads(request.data);self.assertNotIn('sha',payload)
                self.assertIn('/receipts/c3_review_daily/',request.full_url)
                return Response(201,{})
            sends.append(request)
            if len(sends)==fail_at:raise TimeoutError(request.full_url)
            return Response(200,dict(ok=True,result=dict(message_id=200+len(sends),chat=dict(id=-123))))
        return opener,calls,sends

    def test_scheduled_mock_records_separate_create_only_receipt_and_valid_ids(self):
        self.prepare();opener,calls,sends=self.transport()
        r=run(self.root,{**self.env,'GITHUB_EVENT_NAME':'schedule'},opener,CLOCK,review=True)
        self.assertEqual(r['status'],'SENT');self.assertEqual(len(sends),1)
        self.assertEqual(r['photos'][0]['telegram_message_id'],201);self.assertTrue(r['photos'][0]['destination_matches'])
        self.assertEqual(r['sent_receipt_path'],'receipts/c3_review_daily/'+ASOF+'.sent.json')
        self.assertEqual([x.get_method() for x in calls],['GET','GET','PUT','POST','PUT'])

    def test_existing_or_unreadable_reference_receipt_blocks_without_sends(self):
        self.prepare()
        for options in (dict(existing=True),dict(read_error=True)):
            opener,calls,sends=self.transport(**options)
            r=run(self.root,{**self.env,'GITHUB_EVENT_NAME':'schedule'},opener,CLOCK,review=True)
            self.assertIn(r['status'],('BLOCKED','ERROR'));self.assertFalse(sends)
            self.assertTrue(all(x.get_method()=='GET' for x in calls))

    def test_partial_uncertain_send_keeps_success_and_never_retries_or_logs_secret(self):
        self.prepare(refs=2);opener,calls,sends=self.transport(fail_at=2)
        r=run(self.root,{**self.env,'GITHUB_EVENT_NAME':'schedule'},opener,CLOCK,review=True)
        self.assertEqual(r['status'],'PARTIAL_ERROR');self.assertEqual(len(sends),2);self.assertEqual(len(r['photos']),1)
        self.assertFalse(r['automatic_retry']);self.assertNotIn('never-log-token',json.dumps(r));self.assertNotIn('sent_receipt_path',r)

    def test_expired_upstream_hold_and_pr_cannot_send(self):
        self.prepare();opener,calls,sends=self.transport()
        later=datetime(2026,11,24,8,tzinfo=ZoneInfo('Asia/Seoul'))
        r=run(self.root,{**self.env,'GITHUB_EVENT_NAME':'schedule'},opener,later,review=True)
        self.assertEqual(r['status'],'ERROR');self.assertFalse(calls)
        r=run(self.root,{**self.env,'GITHUB_EVENT_NAME':'pull_request'},opener,CLOCK,review=True)
        self.assertEqual(r['status'],'DRY_RUN');self.assertFalse(calls)
        write(self.root/'execution_outcome.json',dict(operational_status='HOLD_FINANCIAL_UNVERIFIED'))
        self.assertEqual(run(self.root,self.env,opener,CLOCK,review=True)['status'],'BLOCKED');self.assertFalse(calls)


class DeliveryAccountingTests(unittest.TestCase):
    def test_reconcile_cash_empty_and_failed_channels_without_green_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            write(root/'financial_selection_research.json',dict(operational_status='CASH_NO_ELIGIBLE',selected_count=0))
            for name in ('watch_delivery_result','review_delivery_result'):write(root/(name+'.json'),dict(status='EMPTY',selected=[],photos=[],telegram_photos_sent=0))
            write(root/'delivery_result.json',dict(status='CASH',photos=[],telegram_photos_sent=0))
            write(root/'execution_outcome.json',dict(program_status='COMPLETED',operational_status='CASH_NO_ELIGIBLE'))
            with patch('builtins.print'):self.assertEqual(finalize(root)['operational_status'],'CASH_NO_ELIGIBLE')
            write(root/'watch_delivery_result.json',dict(status='PARTIAL_ERROR',selected=[dict(code='111111')],photos=[],telegram_photos_sent=0))
            with patch('builtins.print'):r=finalize(root)
            self.assertEqual(r['operational_status'],'ERROR');self.assertIn('watch5_DELIVERY_PARTIAL_ERROR',r['delivery_reconciliation_errors'])


class ApprovedReleaseTests(unittest.TestCase):
    def env(self):return dict(GITHUB_EVENT_NAME='push',GITHUB_REF_NAME='main',GITHUB_REPOSITORY='shdmfpsj-beep/krx-auto-scanner',GITHUB_RUN_ATTEMPT='1',GITHUB_SHA='verified-main',GITHUB_RUN_ID='999')
    def event(self):return dict(head_commit=dict(message=INDEPENDENT_RELEASE_PREFIX+' (#209)'))
    def test_before_cutoff_defers_existing_schedule_without_collect_dispatch_or_send(self):
        gh=FakeGitHub();report=diagnose(gh,'20261125')
        r=release_independent(gh,self.env(),self.event(),report,datetime(2026,11,25,17,tzinfo=ZoneInfo('Asia/Seoul')))
        self.assertEqual(r['status'],'DEFERRED_TO_EXISTING_SCHEDULE');self.assertFalse(r['source_collected'])
        self.assertTrue(all(method=='GET' for _,method,_ in gh.calls))
        self.assertTrue(any('/c3_review_daily/' in path for path,_,_ in gh.calls))
    def test_approved_november26_morning_uses_existing_live_path_once(self):
        from c3_operating_recovery import MORNING_RECOVERY_PREFIX
        gh=FakeGitHub();report=diagnose(gh,'20261125')
        event=dict(head_commit=dict(message=MORNING_RECOVERY_PREFIX+' (#211)'))
        clock=datetime(2026,11,26,9,15,tzinfo=ZoneInfo('Asia/Seoul'))
        result=release_independent(gh,self.env(),event,report,clock)
        self.assertEqual(result['status'],'DISPATCH_ACCEPTED')
        inputs=next(c[2]['inputs'] for c in gh.calls if c[1]=='POST')
        env=manual_env();env.update(C3_MANUAL_ASOF='20261125',C3_APPROVAL_POLICY=INDEPENDENT_POLICY,C3_OPERATION_REQUEST_ID=inputs['operation_request_id'])
        self.assertTrue(approved_manual_delivery(env,'20261125','2026-11-26T15:30:00+09:00',clock))
    def test_morning_recovery_cannot_dispatch_after_signal_expiry(self):
        from c3_operating_recovery import MORNING_RECOVERY_PREFIX
        gh=FakeGitHub();report=diagnose(gh,'20261125')
        with self.assertRaises(ValueError):
            release_independent(gh,self.env(),dict(head_commit=dict(message=MORNING_RECOVERY_PREFIX)),report,
                datetime(2026,11,26,15,31,tzinfo=ZoneInfo('Asia/Seoul')))
        self.assertFalse(any(c[1]=='POST' for c in gh.calls))
    def test_after_cutoff_once_main_only_explicit_request_and_no_uncertain_retry(self):
        gh=FakeGitHub();report=diagnose(gh,'20261125')
        clock=datetime(2026,11,25,21,1,tzinfo=ZoneInfo('Asia/Seoul'))
        r=release_independent(gh,self.env(),self.event(),report,clock)
        self.assertEqual(r['status'],'DISPATCH_ACCEPTED')
        posts=[c for c in gh.calls if c[1]=='POST'];self.assertEqual(len(posts),1)
        inputs=posts[0][2]['inputs'];self.assertEqual(inputs['asof'],'20261125');self.assertTrue(inputs['live_delivery'])
        env=manual_env();env.update(C3_MANUAL_ASOF='20261125',C3_APPROVAL_POLICY=INDEPENDENT_POLICY,C3_OPERATION_REQUEST_ID=inputs['operation_request_id'])
        self.assertTrue(approved_manual_delivery(env,'20261125','2026-11-26T15:30:00+09:00',clock))
        with self.assertRaises(ValueError):approved_manual_delivery(env,'20261125','2026-11-26T15:30:00+09:00',datetime(2026,11,25,17,tzinfo=ZoneInfo('Asia/Seoul')))
        with self.assertRaises(ValueError):release_independent(gh,{**self.env(),'GITHUB_RUN_ATTEMPT':'2'},self.event(),report,clock)


if __name__=='__main__':unittest.main()
