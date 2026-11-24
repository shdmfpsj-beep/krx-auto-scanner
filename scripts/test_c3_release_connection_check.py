import io
import json
import unittest
import urllib.error
from pathlib import Path

from c3_release_connection_check import (RELEASE_TITLE, RESERVATION, TEST_TEXT,
                                         check_connection, production_checks)


class Response(io.BytesIO):
    def __init__(self, status, body):
        super().__init__(json.dumps(body).encode()); self.status = status


class ReleaseConnectionTests(unittest.TestCase):
    def setUp(self):
        self.env = dict(GITHUB_EVENT_NAME='push', GITHUB_REF='refs/heads/main',
                        GITHUB_REPOSITORY='shdmfpsj-beep/krx-auto-scanner',
                        GITHUB_RUN_ATTEMPT='1', GITHUB_RUN_ID='test', GITHUB_SHA='abc',
                        TELEGRAM_BOT_TOKEN='never-print-token', TELEGRAM_CHAT_ID='-12345',
                        GH_TOKEN='never-print-gh')
        self.event = dict(head_commit=dict(message=RELEASE_TITLE + '\n\nMerge PR #202'))

    def test_production_balanced_and_protected_files_unchanged(self):
        self.assertEqual(production_checks(Path(__file__).resolve().parents[1])['model'], 'balanced')

    def test_send_is_one_test_after_create_only_separate_reservation(self):
        calls = []
        def opener(request, timeout):
            calls.append(request)
            return Response(201, {}) if len(calls) == 1 else Response(200, dict(
                ok=True, result=dict(message_id=42, chat=dict(id=-12345))))
        result = check_connection(self.env, self.event, opener)
        self.assertEqual((result['status'], result['test_messages_sent'], result['message_id']), ('SENT', 1, 42))
        self.assertTrue(calls[0].full_url.endswith(RESERVATION))
        self.assertNotIn('sha', json.loads(calls[0].data))  # create-only, never overwrite
        self.assertEqual(json.loads(calls[1].data)['text'], TEST_TEXT)
        self.assertNotIn('never-print', json.dumps(result))
        self.assertEqual(result['stock_signals_sent'], 0)

    def test_duplicate_or_permission_failure_never_calls_telegram(self):
        calls = []
        def opener(request, timeout):
            calls.append(request)
            raise urllib.error.HTTPError(request.full_url, 422, 'exists', {}, None)
        result = check_connection(self.env, self.event, opener)
        self.assertEqual(result['status'], 'BLOCKED'); self.assertEqual(len(calls), 1)

    def test_unapproved_branch_event_title_and_retry_are_blocked(self):
        def forbidden(*args, **kwargs):
            self.fail('Network must not be called')
        for field, value in [('GITHUB_EVENT_NAME', 'schedule'), ('GITHUB_REF', 'refs/heads/feature'),
                             ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_REPOSITORY', 'other/repo')]:
            self.assertEqual(check_connection({**self.env, field: value}, self.event, forbidden)['status'], 'BLOCKED')
        self.assertEqual(check_connection(self.env, {}, forbidden)['status'], 'BLOCKED')

    def test_uncertain_send_is_not_retried_and_does_not_leak_token(self):
        calls = []
        def opener(request, timeout):
            calls.append(request)
            if len(calls) == 1: return Response(201, {})
            raise TimeoutError(request.full_url)
        result = check_connection(self.env, self.event, opener)
        self.assertEqual(result['status'], 'ERROR'); self.assertEqual(len(calls), 2)
        self.assertNotIn('never-print', json.dumps(result))

    def test_http_ok_without_message_id_or_matching_chat_is_not_success(self):
        for message in [dict(chat=dict(id=-12345)), dict(message_id=7, chat=dict(id=-999))]:
            calls = []
            def opener(request, timeout):
                calls.append(request)
                return Response(201, {}) if len(calls) == 1 else Response(200, dict(ok=True, result=message))
            self.assertEqual(check_connection(self.env, self.event, opener)['status'], 'ERROR')


if __name__ == '__main__':
    unittest.main()
