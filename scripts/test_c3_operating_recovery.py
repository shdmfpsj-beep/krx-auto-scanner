"""User-approved manual recovery, live-send scope and actual workflow transport regression."""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
from c3_delivery_authorization import approved_manual_delivery, RECOVERY_PREFIX, REQUEST_PREFIX, REPOSITORY
from c3_operating_recovery import diagnose, recover
from test_c3_top5_pipeline import PipelineTests, DELIVERY

CLOCK=datetime(2026,11,25,9,tzinfo=ZoneInfo('Asia/Seoul'))
EXPIRY='2026-11-25T15:30:00+09:00'


def manual_env():
    return dict(GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF_NAME='main',GITHUB_REPOSITORY=REPOSITORY,
        C3_FINANCIAL_MODEL='balanced',C3_MANUAL_ASOF='20261124',C3_MANUAL_LIVE_DELIVERY='true',
        C3_OPERATION_REQUEST_ID=REQUEST_PREFIX+'123')


class AuthorizationTests(unittest.TestCase):
    def test_explicit_current_main_recovery_is_authorized(self):
        self.assertTrue(approved_manual_delivery(manual_env(),'20261124',EXPIRY,CLOCK))
    def test_default_manual_preview_is_still_dry_run(self):
        env=manual_env();env.pop('C3_MANUAL_LIVE_DELIVERY')
        self.assertFalse(approved_manual_delivery(env,'20261124',EXPIRY,CLOCK))
    def test_branch_event_repository_model_and_request_are_required(self):
        for field,value in [('GITHUB_EVENT_NAME','push'),('GITHUB_EVENT_NAME','pull_request'),
            ('GITHUB_REF_NAME','feature'),('GITHUB_REPOSITORY','other/repo'),('C3_FINANCIAL_MODEL','legacy'),
            ('C3_OPERATION_REQUEST_ID',''),('C3_MANUAL_ASOF','20261123')]:
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                approved_manual_delivery({**manual_env(),field:value},'20261124',EXPIRY,CLOCK)
    def test_other_stale_and_future_dates_never_authorize(self):
        for day in ('20261123','20261125'):
            with self.assertRaises(ValueError):approved_manual_delivery(manual_env(),day,EXPIRY,CLOCK)
        for when in (datetime(2026,11,25,15,31,tzinfo=ZoneInfo('Asia/Seoul')),
                     datetime(2026,11,26,8,tzinfo=ZoneInfo('Asia/Seoul'))):
            with self.assertRaises(ValueError):approved_manual_delivery(manual_env(),'20261124',EXPIRY,when)
    def test_timezone_free_or_missing_expiry_is_not_authority(self):
        for expiry in (None,'','2026-11-25T15:30:00'):
            with self.assertRaises(ValueError):approved_manual_delivery(manual_env(),'20261124',expiry,CLOCK)


class FakeGitHub:
    def __init__(self,state='active',running=False,reserved=False):
        self.state=state;self.calls=[];self.running=running;self.reserved=reserved
    def call(self,path,method='GET',payload=None,optional=False):
        self.calls.append((path,method,payload))
        if method=='PUT':self.state='active';return dict(http_status=204)
        if method=='POST':return dict(http_status=204)
        if path=='':return dict(default_branch='main',archived=False,disabled=False)
        if path=='git/ref/heads/main':return dict(object=dict(sha='verified-main'))
        if path.endswith('/runs?per_page=50'):
            return dict(workflow_runs=[dict(id=77,status='in_progress',event='schedule',created_at='2026-11-24T23:00:00Z')] if self.running else [])
        if path.startswith('actions/workflows/'):
            return dict(id=420918398,path='.github/workflows/c3_top5_daily_telegram.yml',state=self.state)
        if path.startswith('contents/'):
            return dict(content='existing') if self.reserved else dict(http_status=404,readable=False)
        if path=='actions/runners':return dict(total_count=0,runners=[])
        return dict(enabled=True)


class ControllerTests(unittest.TestCase):
    def env(self):return dict(GITHUB_EVENT_NAME='push',GITHUB_REF_NAME='main',GITHUB_REPOSITORY=REPOSITORY,
                              GITHUB_RUN_ATTEMPT='1',GITHUB_RUN_ID='555')
    def event(self):return dict(head_commit=dict(message=RECOVERY_PREFIX+' (#205)\nApproved recovery'))
    def test_active_no_event_is_not_invented_as_a_code_cause(self):
        gh=FakeGitHub();report=diagnose(gh)
        self.assertEqual(report['schedule_finding'],'ACTIVE_WORKFLOW_NO_EVENT_CAUSE_NOT_ESTABLISHED')
        self.assertTrue(all(method=='GET' for _,method,_ in gh.calls))
    def test_disabled_workflow_is_recorded_enabled_then_dispatched_normally(self):
        gh=FakeGitHub(state='disabled_manually');report=diagnose(gh)
        self.assertEqual(report['workflow']['state'],'disabled_manually')
        result=recover(gh,self.env(),self.event(),report,CLOCK)
        self.assertEqual(result['status'],'DISPATCH_ACCEPTED');self.assertEqual(report['workflow_after_enable']['state'],'active')
        post=[x for x in gh.calls if x[1]=='POST'];self.assertEqual(len(post),1)
        self.assertEqual(post[0][2]['inputs']['asof'],'20261124');self.assertTrue(post[0][2]['inputs']['live_delivery'])
        self.assertEqual(post[0][2]['ref'],'main')
    def test_active_workflow_is_not_disabled_or_reenabled(self):
        gh=FakeGitHub();report=diagnose(gh);recover(gh,self.env(),self.event(),report,CLOCK)
        self.assertFalse(any(method=='PUT' for _,method,_ in gh.calls))
    def test_running_schedule_is_followed_instead_of_dispatched_twice(self):
        gh=FakeGitHub(running=True);report=diagnose(gh)
        result=recover(gh,self.env(),self.event(),report,CLOCK)
        self.assertEqual(result['status'],'WAIT_EXISTING_OPERATING_RUN');self.assertEqual(result['run_ids'],[77])
        self.assertFalse(any(method!='GET' for _,method,_ in gh.calls))
    def test_existing_or_unreadable_reservation_blocks_dispatch(self):
        gh=FakeGitHub(reserved=True);report=diagnose(gh)
        self.assertEqual(recover(gh,self.env(),self.event(),report,CLOCK)['status'],'BLOCKED_EXISTING_RESERVATION_REVIEW_REQUIRED')
        gh=FakeGitHub();report=diagnose(gh);next(iter(report['receipt_observations'].values()))['http_status']=403
        with self.assertRaises(ValueError):recover(gh,self.env(),self.event(),report,CLOCK)
        self.assertFalse(any(method=='POST' for _,method,_ in gh.calls))
    def test_pr_feature_rerun_and_wrong_title_never_dispatch(self):
        gh=FakeGitHub();report=diagnose(gh)
        for changes,event in [({'GITHUB_EVENT_NAME':'pull_request'},self.event()),
            ({'GITHUB_REF_NAME':'feature'},self.event()),({'GITHUB_RUN_ATTEMPT':'2'},self.event()),({},dict())]:
            with self.assertRaises(ValueError):recover(gh,{**self.env(),**changes},event,report,CLOCK)
        self.assertFalse(any(method!='GET' for _,method,_ in gh.calls))
    def test_dispatch_http_failure_is_not_retried(self):
        gh=FakeGitHub();report=diagnose(gh);base=gh.call
        def fail(path,method='GET',**kwargs):
            if method=='POST':raise TimeoutError('uncertain request')
            return base(path,method=method,**kwargs)
        with patch.object(gh,'call',side_effect=fail) as mocked:
            with self.assertRaises(TimeoutError):recover(gh,self.env(),self.event(),report,CLOCK)
            self.assertEqual(mocked.call_count,1)


class EmbeddedDeliveryRecoveryTests(PipelineTests):
    # Inherit the existing actual embedded workflow regressions too. The main
    # suite loads only these extra methods using load_tests below.
    def test_http_timeout_does_not_leak_token_to_stderr_or_receipt(self):
        self.prepare();self.env.update(GITHUB_EVENT_NAME='schedule',GITHUB_REF_NAME='main',
            GITHUB_REPOSITORY='offline/example',GH_TOKEN='fake',TELEGRAM_BOT_TOKEN='never-print-secret',TELEGRAM_CHAT_ID='fake')
        prefix='''
import io,json,urllib.request
class Response(io.BytesIO):
    status=201
    def __init__(self):super().__init__(b'{}')
def fake(req,**kwargs):
    if '/contents/' in req.full_url:return Response()
    raise TimeoutError(req.full_url)
urllib.request.urlopen=fake
'''
        process=self.execute(DELIVERY,prefix)
        self.assertNotEqual(process.returncode,0);self.assertNotIn('never-print-secret',process.stderr)
        self.assertNotIn('never-print-secret',json.dumps(self.result()));self.assertEqual(self.result()['status'],'ERROR')
    def test_wrong_destination_is_not_sent_success_and_keeps_evidence(self):
        self.prepare();self.env.update(GITHUB_EVENT_NAME='schedule',GITHUB_REF_NAME='main',
            GITHUB_REPOSITORY='offline/example',GH_TOKEN='fake',TELEGRAM_BOT_TOKEN='fake',TELEGRAM_CHAT_ID='expected')
        prefix='''
import io,json,urllib.request
class Response(io.BytesIO):
    def __init__(self,status,payload):super().__init__(json.dumps(payload).encode());self.status=status
def fake(req,**kwargs):
    if '/contents/' in req.full_url:return Response(201,{})
    return Response(200,dict(ok=True,result=dict(message_id=88,chat=dict(id='wrong'))))
urllib.request.urlopen=fake
'''
        process=self.execute(DELIVERY,prefix)
        self.assertNotEqual(process.returncode,0);self.assertEqual(self.result()['status'],'ERROR')
        self.assertFalse(self.result()['photos'][0]['destination_matches'])
        self.assertEqual(self.result()['photos'][0]['telegram_message_id'],88)
    def test_approved_manual_mode_reaches_existing_create_only_sender(self):
        self.prepare();self.env.update(GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF_NAME='main',
            GITHUB_REPOSITORY=REPOSITORY,GH_TOKEN='fake',TELEGRAM_BOT_TOKEN='fake',TELEGRAM_CHAT_ID='fake')
        prefix='''
import io,json,urllib.request,c3_delivery_authorization
# Authorization/date policy itself is exercised above; mock only that boundary
# for this older synthetic price fixture and exercise the real sender unchanged.
c3_delivery_authorization.approved_manual_delivery=lambda *args:True
class Response(io.BytesIO):
    def __init__(self,status,payload):super().__init__(json.dumps(payload).encode());self.status=status
calls=[]
def fake(req,**kwargs):
    calls.append(req.full_url)
    if '/contents/' in req.full_url:
        assert len(calls)==1
        assert 'sha' not in json.loads(req.data)
        return Response(201,{})
    return Response(200,dict(ok=True,result=dict(message_id=89,chat=dict(id='fake'))))
urllib.request.urlopen=fake
'''
        process=self.execute(DELIVERY,prefix)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(self.result()['status'],'SENT');self.assertEqual(self.result()['execution_event'],'workflow_dispatch')
        self.assertEqual(self.result()['delivery_mode'],'MANUAL_USER_APPROVED')


def load_tests(loader, tests, pattern):
    suite=unittest.TestSuite()
    for cls in (AuthorizationTests,ControllerTests):suite.addTests(loader.loadTestsFromTestCase(cls))
    for name in ('test_http_timeout_does_not_leak_token_to_stderr_or_receipt',
                 'test_wrong_destination_is_not_sent_success_and_keeps_evidence',
                 'test_approved_manual_mode_reaches_existing_create_only_sender'):
        suite.addTest(EmbeddedDeliveryRecoveryTests(name))
    return suite


if __name__=='__main__':unittest.main()
