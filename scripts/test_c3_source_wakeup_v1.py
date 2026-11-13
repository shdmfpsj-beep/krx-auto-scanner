"""Completed source events are recovery wakes, never approval or date proof."""
import unittest
from datetime import datetime
from pathlib import Path
from c3_morning_source_v1 import trigger_context,prior_session,require_official_collection,SOURCE_WAKEUP_WORKFLOW,REPOSITORY


class SourceWakeupTests(unittest.TestCase):
    def fixture(self,conclusion='success'):
        env=dict(GITHUB_EVENT_NAME='workflow_run',GITHUB_REPOSITORY=REPOSITORY,GITHUB_REF='refs/heads/main',GITHUB_SHA='a'*40)
        event=dict(workflow_run=dict(id=123,name=SOURCE_WAKEUP_WORKFLOW,head_branch='main',head_repository={'full_name':REPOSITORY},
            status='completed',conclusion=conclusion,event='schedule',head_sha='b'*40,created_at='2026-11-13T03:35:42Z'))
        return env,event
    def test_success_failure_and_timeout_wake_fresh_research_without_original_registration(self):
        for outcome in ('success','failure','timed_out'):
            env,event=self.fixture(outcome);r=trigger_context(env,event)
            self.assertEqual(r['upstream_run_id'],'123');self.assertEqual(r['upstream_conclusion'],outcome)
            self.assertTrue(r['upstream_is_wakeup_not_source_validation']);self.assertFalse(r['approved_original_registration_allowed'])
    def test_fork_other_branch_other_workflow_incomplete_and_pr_upstream_are_rejected(self):
        for key,value in [('head_branch','research'),('name','untrusted'),('status','in_progress'),('event','pull_request'),('conclusion','cancelled'),('id',True)]:
            env,event=self.fixture();event['workflow_run'][key]=value
            with self.assertRaisesRegex(ValueError,'UNTRUSTED'):trigger_context(env,event)
        env,event=self.fixture();event['workflow_run']['head_repository']['full_name']='other/fork'
        with self.assertRaisesRegex(ValueError,'UNTRUSTED'):trigger_context(env,event)
    def test_only_main_schedule_and_manual_event_can_reach_existing_original_guard(self):
        for event in ('schedule','workflow_dispatch','push','pull_request'):
            env=dict(GITHUB_EVENT_NAME=event,GITHUB_REPOSITORY=REPOSITORY,GITHUB_REF='refs/heads/main')
            self.assertEqual(trigger_context(env,{'schedule':'10 23 * * 0-4'})['approved_original_registration_allowed'],event in ('schedule','workflow_dispatch'))
        env['GITHUB_EVENT_NAME']='schedule';env['GITHUB_REF']='refs/heads/research'
        self.assertFalse(trigger_context(env,{})['approved_original_registration_allowed'])
    def test_delayed_job_monday_and_holidays_keep_prior_completed_reference_day(self):
        for clock,day in [('2026-11-13T13:00:00+09:00','2026-11-12'),('2026-11-16T08:10:00+09:00','2026-11-13'),
            ('2026-10-12T08:45:00+09:00','2026-10-08'),('2026-03-03T08:45:00+09:00','2026-02-27')]:
            self.assertEqual(prior_session(datetime.fromisoformat(clock))['requested_day'],day)
    def test_http_200_does_not_replace_actual_nonempty_exact_day_rows(self):
        manifest=dict(asof='2026-11-12',official_dataset_usable=True,official_market_rows=2770)
        require_official_collection(manifest,'2026-11-12')
        for field,value in [('official_market_rows',0),('official_market_rows',True),('official_dataset_usable',False),('asof','2026-11-11')]:
            with self.assertRaisesRegex(ValueError,'EMPTY_OR_WRONG_DAY'):require_official_collection(dict(manifest,**{field:value}),'2026-11-12')
    def test_existing_schedules_are_preserved_and_fallback_is_not_original_approval(self):
        root=Path(__file__).resolve().parent.parent
        caller=(root/'.github/workflows/c3_research_daily_caller.yml').read_text()
        self.assertIn("workflows: ['"+SOURCE_WAKEUP_WORKFLOW+"']",caller)
        for cron in ('10 23 * * 0-4','20 23 * * 0-4','30 23 * * 0-4'):self.assertIn("cron: '"+cron+"'",caller)
        job=caller.split('\n  research:\n',1)[1].split('\n  morning-review:\n',1)[0]
        self.assertIn("github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'",job)
        self.assertIn("needs.source-ready.outputs.registration_trigger_allowed == 'true'",job)
        self.assertNotIn('secrets: inherit',caller)


if __name__=='__main__':unittest.main()
