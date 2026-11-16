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


if __name__=='__main__':
    unittest.main()
