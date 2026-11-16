"""Fail-closed diagnostics for the existing C3 original-registration gate."""
import unittest
from c3_morning_source_v1 import registration_gate_blocker, trigger_context


class RegistrationGateDiagnosticsTest(unittest.TestCase):
    def test_approved_open_ready(self):
        self.assertIsNone(registration_gate_blocker(True, 'OPEN', True))

    def test_delayed_schedule_remains_blocked(self):
        self.assertEqual(registration_gate_blocker(True, 'CLOSED', True),
                         'MORNING_REGISTRATION_WINDOW_CLOSED')

    def test_unapproved_recovery_stays_blocked(self):
        self.assertEqual(registration_gate_blocker(False, 'OPEN', True),
                         'TRIGGER_NOT_APPROVED_FOR_ORIGINAL_REGISTRATION')

    def test_source_failure_stays_blocked(self):
        self.assertEqual(registration_gate_blocker(True, 'OPEN', False),
                         'OFFICIAL_SOURCE_NOT_READY')

    def test_trigger_provenance_is_fail_closed(self):
        base={'GITHUB_REPOSITORY':'shdmfpsj-beep/krx-auto-scanner',
              'GITHUB_REF':'refs/heads/main'}
        for event,expected in [('schedule',True),('workflow_dispatch',True),
                               ('push',False),('pull_request',False)]:
            with self.subTest(event=event):
                ctx=trigger_context(dict(base,GITHUB_EVENT_NAME=event),event={})
                self.assertIs(ctx['approved_original_registration_allowed'],expected)
        ctx=trigger_context(dict(base,GITHUB_EVENT_NAME='schedule',
                                 GITHUB_REF='refs/heads/other'),event={})
        self.assertFalse(ctx['approved_original_registration_allowed'])

    def test_wrong_repository_cannot_register(self):
        env={'GITHUB_REPOSITORY':'untrusted/fork',
             'GITHUB_REF':'refs/heads/main','GITHUB_EVENT_NAME':'schedule'}
        self.assertFalse(trigger_context(env,event={})['approved_original_registration_allowed'])

    def test_workflow_run_cannot_register_even_if_valid_wakeup(self):
        env={'GITHUB_REPOSITORY':'shdmfpsj-beep/krx-auto-scanner',
             'GITHUB_REF':'refs/heads/main','GITHUB_EVENT_NAME':'workflow_run'}
        event={'workflow_run':{'id':12345,
            'name':'KRX official independent daily source probe (no trading)',
            'head_branch':'main','head_repository':{'full_name':env['GITHUB_REPOSITORY']},
            'status':'completed','event':'schedule','conclusion':'success'}}
        self.assertFalse(trigger_context(env,event=event)['approved_original_registration_allowed'])

    def test_unknown_window_is_not_open(self):
        self.assertEqual(registration_gate_blocker(True,'UNKNOWN',True),
                         'MORNING_REGISTRATION_WINDOW_CLOSED')

    def test_missing_ready_is_not_approved(self):
        self.assertEqual(registration_gate_blocker(True,'OPEN',None),
                         'OFFICIAL_SOURCE_NOT_READY')


if __name__=='__main__':
    unittest.main()
