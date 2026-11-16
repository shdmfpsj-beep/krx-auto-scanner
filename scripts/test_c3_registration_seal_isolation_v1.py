"""Isolated source-registration seal checks; no network, ledger writes or Telegram."""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from c3_morning_registration_v1 import seal,digest,check_review
from c3_morning_source_v1 import registration_gate_blocker,trigger_context

DAY='2026-11-13'
RUN='123456'
def fixtures():
    market={'asof':DAY,'source':{'source_run_id':RUN},'rows':[{'ticker':'005930','close':70000}]}
    decision={'price_asof':DAY,'source_snapshot_hash':digest(market),'models':{'A':[{'source_run_id':RUN,'source_price_asof':DAY}],'B':[]}}
    latest={'source_price_asof':DAY,'research_top2_registered_for_source_session':True,'errors':[],'source_run_id':RUN,'source_validation_sha256':'a'*64,'new_decision_registered':False}
    return latest,decision,market

class RegistrationSealIsolation(unittest.TestCase):
    def test_valid_readonly_proof(self):
        latest,decision,market=fixtures()
        proof=seal(latest,decision,market,DAY)
        self.assertEqual(proof['mode'],'READ_ONLY_REPLAY')
        self.assertTrue(proof['original_registration_reused'])
        self.assertFalse(proof['orders_enabled'])
        self.assertFalse(proof['original_signals_modified'])
    def test_valid_approved_pipeline_proof(self):
        latest,decision,market=fixtures()
        proof=seal(latest,decision,market,DAY,caller_run_id='999')
        self.assertEqual(proof['mode'],'APPROVED_PIPELINE')
        self.assertEqual(proof['registration_run_id'],'999')
    def test_market_hash_mismatch(self):
        latest,decision,market=fixtures()
        market['rows'][0]['close']=1
        with self.assertRaisesRegex(ValueError,'REGISTERED_DECISION_MARKET_HASH_MISMATCH'):
            seal(latest,decision,market,DAY)
    def test_decision_day_mismatch(self):
        latest,decision,market=fixtures()
        decision['price_asof']='2026-11-12'
        with self.assertRaisesRegex(ValueError,'REGISTRATION_SOURCE_DAY_MISMATCH'):
            seal(latest,decision,market,DAY)
    def test_latest_day_mismatch(self):
        latest,decision,market=fixtures()
        latest['source_price_asof']='2026-11-12'
        with self.assertRaisesRegex(ValueError,'REGISTRATION_SOURCE_DAY_MISMATCH'):
            seal(latest,decision,market,DAY)
    def test_market_day_mismatch(self):
        latest,decision,market=fixtures()
        market['asof']='2026-11-12'
        with self.assertRaisesRegex(ValueError,'REGISTRATION_SOURCE_DAY_MISMATCH'):
            seal(latest,decision,market,DAY)
    def test_run_mismatch(self):
        latest,decision,market=fixtures()
        market['source']['source_run_id']='654321'
        with self.assertRaisesRegex(ValueError,'REGISTERED_MARKET_RUN_ID_MISMATCH'):
            seal(latest,decision,market,DAY)
    def test_new_registration_caller_mismatch(self):
        latest,decision,market=fixtures()
        latest['new_decision_registered']=True
        with self.assertRaisesRegex(ValueError,'NEW_REGISTRATION_CALLER_MISMATCH'):
            seal(latest,decision,market,DAY,caller_run_id='999')
    def test_after_deadline_gate(self):
        self.assertEqual(registration_gate_blocker(True,'CLOSED',True),'MORNING_REGISTRATION_WINDOW_CLOSED')
    def test_workflow_run_denied(self):
        env={'GITHUB_EVENT_NAME':'workflow_run','GITHUB_REPOSITORY':'shdmfpsj-beep/krx-auto-scanner','GITHUB_REF':'refs/heads/main'}
        event={'workflow_run':{'name':'KRX official independent daily source probe (no trading)','head_branch':'main','head_repository':{'full_name':env['GITHUB_REPOSITORY']},'status':'completed','event':'schedule','conclusion':'success','id':123}}
        context=trigger_context(env,event)
        self.assertFalse(context['approved_original_registration_allowed'])
    def test_inputs_unchanged_after_failure(self):
        latest,decision,market=fixtures()
        before=hashlib.sha256(json.dumps([latest,decision,market],sort_keys=True).encode()).hexdigest()
        market['rows'][0]['close']=1
        after_mutation=hashlib.sha256(json.dumps([latest,decision,market],sort_keys=True).encode()).hexdigest()
        with self.assertRaises(ValueError):seal(latest,decision,market,DAY)
        self.assertEqual(after_mutation,hashlib.sha256(json.dumps([latest,decision,market],sort_keys=True).encode()).hexdigest())
        self.assertNotEqual(before,after_mutation)
    def test_invalid_review_proof_rejected(self):
        latest,decision,market=fixtures()
        proof=seal(latest,decision,market,DAY,caller_run_id='999')
        with self.assertRaisesRegex(ValueError,'REGISTERED_SOURCE_HANDOFF_MISMATCH'):
            check_review(proof,'a'*40,DAY,'999')

if __name__=='__main__':unittest.main()
