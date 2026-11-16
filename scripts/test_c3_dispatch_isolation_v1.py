"""Read-only mock contract tests. No HTTP calls, tokens, ledger writes or Telegram."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parent))
from c3_morning_source_v1 import registration_gate_blocker, trigger_context, require_official_collection

REPO='shdmfpsj-beep/krx-auto-scanner'
URL=f'https://api.github.com/repos/{REPO}/actions/workflows/c3_research_daily_caller.yml/dispatches'

def dispatch_request(ref='main'):
    return {'method':'POST','url':URL,'headers':{'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Authorization':'Bearer <REDACTED>'},'body':json.dumps({'ref':ref})}

def simulated_dispatch(transport):
    request=dispatch_request()
    status=transport(request)
    if status==204:return 'ACCEPTED_NOT_RUN_PROVEN'
    if status in (401,403):return 'AUTH_OR_PERMISSION_DENIED'
    if status in (429,500,502,503,504):return 'RETRYABLE_NOT_CONFIRMED'
    return 'REJECTED_NOT_CONFIRMED'

def eligible(event,window='OPEN',ready=True):
    env={'GITHUB_EVENT_NAME':event,'GITHUB_REPOSITORY':REPO,'GITHUB_REF':'refs/heads/main'}
    return registration_gate_blocker(trigger_context(env,{}).get('approved_original_registration_allowed'),window,ready)

class DispatchIsolationTests(unittest.TestCase):
    def test_request_contract(self):
        r=dispatch_request()
        self.assertEqual(r['method'],'POST')
        self.assertEqual(r['url'],URL)
        self.assertEqual(json.loads(r['body']),{'ref':'main'})
        self.assertNotIn('token',json.dumps(r).lower())
    def test_http_204_is_not_execution_proof(self):
        self.assertEqual(simulated_dispatch(Mock(return_value=204)),'ACCEPTED_NOT_RUN_PROVEN')
    def test_auth_401(self):
        self.assertEqual(simulated_dispatch(Mock(return_value=401)),'AUTH_OR_PERMISSION_DENIED')
    def test_permission_403(self):
        self.assertEqual(simulated_dispatch(Mock(return_value=403)),'AUTH_OR_PERMISSION_DENIED')
    def test_retryable_does_not_grant_registration(self):
        for status in (429,500,502,503,504):
            self.assertEqual(simulated_dispatch(Mock(return_value=status)),'RETRYABLE_NOT_CONFIRMED')
    def test_duplicate_requests_not_execution_proof(self):
        transport=Mock(side_effect=[204,204])
        self.assertEqual([simulated_dispatch(transport) for _ in range(2)],['ACCEPTED_NOT_RUN_PROVEN']*2)
        self.assertEqual(transport.call_count,2)
    def test_dispatch_open_ready(self):
        self.assertIsNone(eligible('workflow_dispatch'))
    def test_schedule_open_ready(self):
        self.assertIsNone(eligible('schedule'))
    def test_after_0900_blocked(self):
        self.assertEqual(eligible('workflow_dispatch','CLOSED'),'MORNING_REGISTRATION_WINDOW_CLOSED')
    def test_source_failure_blocked(self):
        self.assertEqual(eligible('workflow_dispatch','OPEN',False),'OFFICIAL_SOURCE_NOT_READY')
    def test_wrong_day_blocked(self):
        with self.assertRaisesRegex(ValueError,'OFFICIAL_COLLECTION_EMPTY_OR_WRONG_DAY'):
            require_official_collection({'asof':'2026-11-12','official_dataset_usable':True,'official_market_rows':2770},'2026-11-13')
    def test_workflow_run_cannot_register(self):
        self.assertEqual(registration_gate_blocker(False,'OPEN',True),'TRIGGER_NOT_APPROVED_FOR_ORIGINAL_REGISTRATION')
    def test_retroactive_closed(self):
        self.assertEqual(eligible('schedule','CLOSED',True),'MORNING_REGISTRATION_WINDOW_CLOSED')
    def test_no_side_effect_paths(self):
        # Contract test module uses only in-memory mocks and read-only imports.
        import ast
        tree=ast.parse(Path(__file__).read_text())
        calls=[node.func for node in ast.walk(tree) if isinstance(node,ast.Call)]
        self.assertFalse(any(isinstance(fn,ast.Attribute) and fn.attr in ('urlopen','post') for fn in calls))
if __name__=='__main__':unittest.main()
