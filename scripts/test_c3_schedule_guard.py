"""Missing-event recovery and delayed-primary races, without network or messages."""
import base64
import copy
import hashlib
import io
import json
import unittest
import urllib.error
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo
from c3_schedule_guard import assess, recover_missing, completed_state, verify_parent, archive_outcome, REPOSITORY
from c3_delivery_authorization import approved_manual_delivery

CLOCK=datetime(2026,11,26,7,47,tzinfo=ZoneInfo('Asia/Seoul'))


def env(**changes):
    return dict(GITHUB_EVENT_NAME='schedule',GITHUB_REF_NAME='main',GITHUB_REPOSITORY=REPOSITORY,
        GITHUB_RUN_ID='500',GITHUB_RUN_ATTEMPT='1',**changes)


def prior(**changes):
    result=dict(id=400,status='completed',event='schedule',conclusion='success',head_branch='main',
        created_at='2026-11-25T23:17:00Z',display_title='C3 TOP5 + WATCH5 latest · schedule')
    result.update(changes);return result


def bundle(state='CASH_NO_ELIGIBLE',status='CASH',count=0):
    return {'execution_outcome.json':dict(asof='20261125',program_status='COMPLETED',operational_status=state),
        'receipt.json':dict(asof='20261125'),'financial_selection_research.json':dict(asof='20261125',selected_count=count),
        'delivery_result.json':dict(asof='20261125',status=status,photos=[],telegram_photos_sent=0),
        'watch_delivery_result.json':dict(asof='20261125',status='EMPTY',selected=[],photos=[],telegram_photos_sent=0),
        'review_delivery_result.json':dict(asof='20261125',status='EMPTY',selected=[],photos=[],telegram_photos_sent=0)}


class Fake:
    token='never-log-token'
    def __init__(self,runs=None,data=None):
        self.runs=runs or [];self.data=data or bundle();self.markers={};self.calls=[];self.fail_post=False;self.denied=False;self.conflict=False
    def call(self,path,method='GET',payload=None,optional=False):
        self.calls.append((path,method,payload))
        if method=='POST':
            if self.fail_post:raise TimeoutError('uncertain '+self.token)
            return dict(http_status=204)
        if path.startswith('contents/'):
            key=path[len('contents/'):].split('?')[0]
            if method=='PUT':
                if self.conflict:raise urllib.error.HTTPError('https://api.github.com/',422,'exists',{},None)
                assert 'sha' not in payload
                self.markers[key]=json.loads(base64.b64decode(payload['content']))
                return dict(content=dict(path=key,sha='a'*40))
            if self.denied:return dict(http_status=403,readable=False)
            return dict(content=base64.b64encode(json.dumps(self.markers[key]).encode()).decode()) if key in self.markers else dict(http_status=404)
        if path.endswith('/runs?per_page=100'):return dict(workflow_runs=self.runs)
        if path.startswith('actions/runs/'):
            return dict(event='schedule',run_attempt=1,head_branch='main',path='.github/workflows/c3_operating_recovery.yml',repository=dict(full_name=REPOSITORY))
        return dict(state='active')
    def load(self,client,run):return copy.deepcopy(self.data)
    def posts(self):return [c for c in self.calls if c[1]=='POST']


class ScheduleGuardTests(unittest.TestCase):
    def test_primary_without_prior_operation_is_admitted(self):
        client=Fake();r=assess(client,env(),CLOCK,load_archive=client.load)
        self.assertTrue(r['execute']);self.assertEqual(r['asof'],'20261125');self.assertFalse(client.posts())

    def test_existing_branch_and_historical_manual_preview_remain_non_sending(self):
        client=Fake();context=env();context.update(GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF_NAME='feature',C3_MANUAL_ASOF='20261124')
        result=assess(client,context,CLOCK,load_archive=client.load)
        self.assertEqual(result['status'],'PREVIEW_ONLY');self.assertTrue(result['execute']);self.assertFalse(client.calls)

    def test_missing_primary_creates_one_dispatch_reservation_then_posts_once(self):
        client=Fake();event=dict(schedule='47 22 * * 1-5')
        r=recover_missing(client,env(),event,CLOCK,client.load)
        self.assertEqual(r['status'],'DISPATCH_ACCEPTED');self.assertEqual(len(client.posts()),1)
        self.assertEqual(client.posts()[0][2]['inputs']['asof'],'20261125');self.assertTrue(client.posts()[0][2]['inputs']['live_delivery'])
        self.assertIn('receipts/c3_dispatch_daily/20261125.json',client.markers)
        again=recover_missing(client,env(),dict(schedule='27 23 * * 1-5'),CLOCK,client.load)
        self.assertEqual(again['status'],'SKIP_EXISTING_OR_UNCERTAIN_DISPATCH');self.assertEqual(len(client.posts()),1)

    def test_running_primary_prevents_backup_and_new_daily_scan(self):
        for status in ('queued','in_progress','pending'):
            client=Fake([prior(status=status)])
            self.assertEqual(assess(client,env(),CLOCK,load_archive=client.load)['status'],'SKIP_RUNNING')
            self.assertEqual(recover_missing(client,env(),dict(schedule='47 22 * * 1-5'),CLOCK,client.load)['status'],'SKIP_RUNNING')
            self.assertFalse(client.posts());self.assertFalse(client.markers)

    def test_later_queued_operation_does_not_starve_current_primary(self):
        client=Fake([prior(id=600,status='queued')])
        self.assertTrue(assess(client,env(),CLOCK,load_archive=client.load)['execute'])

    def test_cash_empty_completion_prevents_a_second_full_scan(self):
        client=Fake([prior()])
        self.assertEqual(assess(client,env(),CLOCK,load_archive=client.load)['status'],'SKIP_COMPLETED')
        self.assertEqual(recover_missing(client,env(),dict(schedule='27 23 * * 1-5'),CLOCK,client.load)['status'],'SKIP_COMPLETED')
        self.assertFalse(client.posts())

    def test_completed_sent_evidence_blocks_delayed_primary(self):
        data=bundle('TOP5_READY','SENT',1)
        data['delivery_result.json'].update(photos=[dict(telegram_message_id=123,destination_matches=True,image_sha256='a'*64)],telegram_photos_sent=1)
        client=Fake([prior(id=600)],data)
        self.assertEqual(assess(client,env(),CLOCK,load_archive=client.load)['status'],'SKIP_COMPLETED')

    def test_partial_uncertain_hold_error_and_failed_run_never_retry(self):
        for data in (bundle('HOLD_FINANCIAL_UNVERIFIED','HOLD'),bundle('ERROR','ERROR'),bundle('TOP5_READY','PARTIAL_ERROR',1)):
            client=Fake([prior()],data)
            r=recover_missing(client,env(),dict(schedule='47 22 * * 1-5'),CLOCK,client.load)
            self.assertTrue(r['status'].startswith('BLOCKED_'));self.assertFalse(client.posts())
        client=Fake([prior(conclusion='failure')])
        self.assertEqual(assess(client,env(),CLOCK,load_archive=client.load)['status'],'BLOCKED_PREVIOUS_FAILED_RUN')

    def test_preview_without_sends_does_not_count_as_completed_live_delivery(self):
        client=Fake([prior()],bundle('TOP5_READY','DRY_RUN',1))
        self.assertTrue(assess(client,env(),CLOCK,load_archive=client.load)['execute'])

    def test_existing_send_reservation_or_unreadable_receipt_never_rescans(self):
        client=Fake();client.markers['receipts/c3_watch5_daily/20261125.json']=dict(asof='20261125',run_id='400')
        self.assertEqual(assess(client,env(),CLOCK,load_archive=client.load)['status'],'SKIP_EXISTING_DELIVERY_RESERVATION')
        client=Fake();client.denied=True
        with self.assertRaisesRegex(ValueError,'STATE_UNVERIFIED'):assess(client,env(),CLOCK,load_archive=client.load)
        self.assertFalse(client.posts())

    def test_wrong_receipt_date_and_missing_or_invalid_message_id_fail_closed(self):
        client=Fake();client.markers['receipts/c3_top5_daily/20261125.json']=dict(asof='20261124')
        with self.assertRaisesRegex(ValueError,'DATE_MISMATCH'):assess(client,env(),CLOCK,load_archive=client.load)
        data=bundle('TOP5_READY','SENT',1)
        data['delivery_result.json'].update(photos=[dict(telegram_message_id=True,destination_matches=True,image_sha256='a'*64)],telegram_photos_sent=1)
        with self.assertRaisesRegex(ValueError,'EVIDENCE_INVALID'):completed_state(data,'20261125')

    def test_uncertain_dispatch_is_not_posted_again_by_final_recovery(self):
        client=Fake();client.fail_post=True
        with self.assertRaises(TimeoutError):recover_missing(client,env(),dict(schedule='47 22 * * 1-5'),CLOCK,client.load)
        client.fail_post=False
        result=recover_missing(client,env(),dict(schedule='27 23 * * 1-5'),CLOCK,client.load)
        self.assertEqual(result['status'],'SKIP_EXISTING_OR_UNCERTAIN_DISPATCH');self.assertEqual(len(client.posts()),1)

    def test_failed_create_only_dispatch_reservation_prevents_post(self):
        client=Fake();client.conflict=True
        self.assertEqual(recover_missing(client,env(),dict(schedule='47 22 * * 1-5'),CLOCK,client.load)['status'],'SKIP_EXISTING_OR_UNCERTAIN_DISPATCH')
        self.assertFalse(client.posts())

    def test_recovery_requires_approved_cron_schedule_main_and_first_attempt(self):
        for changes in (dict(GITHUB_REF_NAME='feature'),dict(GITHUB_EVENT_NAME='pull_request'),dict(GITHUB_RUN_ATTEMPT='2')):
            client=Fake();context=env();context.update(changes)
            with self.assertRaises(ValueError):recover_missing(client,context,dict(schedule='47 22 * * 1-5'),CLOCK,client.load)
            self.assertFalse(client.posts())
        with self.assertRaises(ValueError):recover_missing(Fake(),env(),dict(schedule='0 23 * * 1-5'),CLOCK)

    def test_parent_is_verified_against_real_schedule_origin_and_separate_marker(self):
        client=Fake();recover_missing(client,env(),dict(schedule='47 22 * * 1-5'),CLOCK,client.load)
        context=dict(GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF_NAME='main',GITHUB_REPOSITORY=REPOSITORY,
            C3_FINANCIAL_MODEL='balanced',C3_APPROVAL_POLICY='INDEPENDENT_ISSUER_FINANCIAL_APPROVAL_V2',C3_MANUAL_ASOF='20261125',
            C3_MANUAL_LIVE_DELIVERY='true',C3_OPERATION_REQUEST_ID='scheduled-recovery-20261125-500')
        self.assertTrue(verify_parent(context,'20261125',client))
        with patch('c3_schedule_guard.GitHub',return_value=client):
            self.assertTrue(approved_manual_delivery(context,'20261125','2026-11-26T15:30:00+09:00',CLOCK))
        client.markers.clear()
        with self.assertRaisesRegex(ValueError,'RESERVATION_MISMATCH'):verify_parent(context,'20261125',client)

    def test_owner_default_manual_daily_admission(self):
        context=env()
        context.update(GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_ACTOR='shdmfpsj-beep',
            GITHUB_TRIGGERING_ACTOR='shdmfpsj-beep',C3_MANUAL_ASOF='',C3_OPERATION_REQUEST_ID='',
            C3_MANUAL_LIVE_DELIVERY='true',C3_FINANCIAL_MODEL='balanced',
            C3_APPROVAL_POLICY='INDEPENDENT_ISSUER_FINANCIAL_APPROVAL_V2')
        client=Fake()
        self.assertTrue(assess(client,context,CLOCK,load_archive=client.load)['execute'])
        client.markers['receipts/c3_watch5_daily/20261125.json']=dict(asof='20261125')
        self.assertEqual(assess(client,context,CLOCK,load_archive=client.load)['status'],'SKIP_EXISTING_DELIVERY_RESERVATION')
        for changes in (dict(GITHUB_ACTOR='other'),dict(GITHUB_TRIGGERING_ACTOR='other'),
                        dict(GITHUB_RUN_ATTEMPT='2'),dict(GITHUB_REF_NAME='feature'),
                        dict(C3_MANUAL_ASOF='20261125'),dict(C3_FINANCIAL_MODEL='legacy')):
            with self.assertRaises(ValueError):
                approved_manual_delivery(dict(context,**changes),'20261125','2026-11-26T15:30:00+09:00',CLOCK)
        with self.assertRaises(ValueError):
            approved_manual_delivery(context,'20261125','2026-11-26T15:30:00+09:00',
                datetime(2026,11,26,15,31,tzinfo=ZoneInfo('Asia/Seoul')))

    def test_expired_manual_signal_cannot_scan_or_dispatch(self):
        client=Fake();context=env();context.update(GITHUB_EVENT_NAME='workflow_dispatch',C3_MANUAL_ASOF='20261125',C3_MANUAL_LIVE_DELIVERY='true')
        with self.assertRaisesRegex(ValueError,'EXPIRED'):
            assess(client,context,datetime(2026,11,26,15,31,tzinfo=ZoneInfo('Asia/Seoul')),load_archive=client.load)
        self.assertFalse(client.calls)

    def test_old_date_artifact_is_not_called_today_and_prior_inputs_are_not_mutated(self):
        client=Fake([prior(created_at='2026-11-25T05:30:30Z')]);before=copy.deepcopy(client.markers)
        self.assertTrue(assess(client,env(),CLOCK,load_archive=lambda *a:self.fail('old artifact read'))['execute'])
        self.assertEqual(client.markers,before)

    def test_archive_hash_failure_cannot_be_treated_as_a_completed_day(self):
        class Client(Fake):
            def call(self,*args,**kwargs):return dict(artifacts=[dict(id=1,name='c3-top5-daily-classic-per-stock',digest='sha256:'+'a'*64)])
        response=io.BytesIO(b'not-an-authentic-archive')
        with patch('urllib.request.build_opener') as build:
            build.return_value.open.return_value=response
            with self.assertRaisesRegex(ValueError,'INTEGRITY'):archive_outcome(Client(),prior())


if __name__=='__main__':unittest.main()
