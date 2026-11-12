"""Synthetic next-session faults, never future market or delivery evidence."""
import copy,json,unittest
from pathlib import Path
from c3_morning_registration_v1 import seal,digest,completed_handoff,check_review

class RegisteredHandoffTests(unittest.TestCase):
    def fixture(self):
        day='2026-11-12';run='900001'
        latest=dict(source_price_asof=day,source_run_id=run,research_top2_registered_for_source_session=True,errors=[],new_decision_registered=True,source_validation_sha256='a'*64)
        market=dict(asof=day,source=dict(source_run_id=run),synthetic_fixture=True)
        decision=dict(price_asof=day,models={'A':[],'B':[dict(source_run_id=run,source_price_asof=day)]},source_snapshot_hash=digest(market),synthetic_fixture=True)
        return latest,decision,market,day,run
    def test_new_session_is_dynamic_and_exact_registration_commit_is_required(self):
        a,b,c,d,r=self.fixture();p=completed_handoff(seal(a,b,c,d,r),'b'*40)
        self.assertEqual(check_review(p,'b'*40,d,r)['source_day'],'2026-11-12')
        for head,day,caller in [('c'*40,d,r),('b'*40,'2026-11-11',r),('b'*40,d,'900002')]:
            with self.assertRaisesRegex(ValueError,'HANDOFF_MISMATCH'):check_review(p,head,day,caller)
    def test_missing_or_failed_registration_never_authorizes_review(self):
        a,b,c,d,r=self.fixture()
        for key,value in [('research_top2_registered_for_source_session',False),('errors',['COLLECTOR_FAILED'])]:
            bad=dict(a,**{key:value})
            with self.assertRaisesRegex(ValueError,'REGISTERED_SOURCE_REQUIRED'):seal(bad,b,c,d,r)
    def test_previous_session_or_cross_run_signal_is_rejected(self):
        a,b,c,d,r=self.fixture()
        for target in (a,b,c):
            original=copy.deepcopy(target)
            key='source_price_asof' if target is a else 'price_asof' if target is b else 'asof'
            target[key]='2026-11-11'
            with self.assertRaisesRegex(ValueError,'DAY_MISMATCH'):seal(a,b,c,d,r)
            target.clear();target.update(original)
        b['models']['B'][0]['source_run_id']='900002'
        with self.assertRaisesRegex(ValueError,'SIGNAL_RUN'):seal(a,b,c,d,r)
    def test_original_same_session_reuse_keeps_source_id_and_does_not_reregister(self):
        a,b,c,d,r=self.fixture();a['new_decision_registered']=False
        p=seal(a,b,c,d,'900002');self.assertEqual(p['source_run_id'],r);self.assertTrue(p['original_registration_reused'])
        a['new_decision_registered']=True
        with self.assertRaisesRegex(ValueError,'CALLER_MISMATCH'):seal(a,b,c,d,'900002')
    def test_changed_decision_or_source_hash_cannot_enter_handoff(self):
        a,b,c,d,r=self.fixture();c['changed']=True
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):seal(a,b,c,d,r)
    def test_historical_replay_cannot_be_promoted_to_published_registration(self):
        a,b,c,d,r=self.fixture();p=seal(a,b,c,d)
        self.assertEqual(p['mode'],'READ_ONLY_REPLAY')
        with self.assertRaisesRegex(ValueError,'APPROVED_PIPELINE'):completed_handoff(p,'b'*40)
    def test_source_run_must_exist_and_must_match_frozen_source(self):
        a,b,c,d,r=self.fixture();c['source']['source_run_id']='900002'
        with self.assertRaisesRegex(ValueError,'MARKET_RUN'):seal(a,b,c,d,r)
    def test_caller_consumes_reusable_outputs_and_source_specific_proof(self):
        root=Path(__file__).resolve().parent.parent
        caller=(root/'.github/workflows/c3_research_daily_caller.yml').read_text()
        adapter=(root/'.github/workflows/c3_morning_research_adapter_v1.yml').read_text()
        self.assertIn('needs.research.outputs.registered_state_sha',caller)
        self.assertIn('REGISTRATION_PROOF: ${{ needs.research.outputs.registration_proof }}',caller)
        self.assertIn('--registration-proof evidence/morning_registration.json',caller)
        self.assertIn('jobs.preserve-research-only.outputs.registered_state_sha',adapter)
        self.assertLess(adapter.index('git push origin HEAD:'),adapter.index('Return the exact published registration commit'))

class ObsoleteSenderTests(unittest.TestCase):
    def test_only_observed_old_queued_sender_is_eligible(self):
        from c3_retire_obsolete_sender_v1 import eligible,TARGET,OLD_HEAD,REPO
        r=dict(id=TARGET,name='C3 TOP2 Telegram notification',event='schedule',head_sha=OLD_HEAD,head_branch='main',status='queued',repository={'full_name':REPO})
        self.assertTrue(eligible(r))
        for k,v in [('id',1),('status','in_progress'),('head_sha','a'*40),('event','workflow_run'),('head_branch','research')]:self.assertFalse(eligible(dict(r,**{k:v})))
    def test_cancel_is_confirmed_without_sender_or_receipt_calls(self):
        from c3_retire_obsolete_sender_v1 import retire,TARGET,OLD_HEAD,REPO
        from unittest.mock import Mock
        r=dict(id=TARGET,name='C3 TOP2 Telegram notification',event='schedule',head_sha=OLD_HEAD,head_branch='main',status='queued',repository={'full_name':REPO})
        call=Mock(side_effect=[r,{},dict(r,status='completed',conclusion='cancelled')]);answer=retire(call,Mock())
        self.assertEqual(answer['status'],'CANCELLED');self.assertEqual(answer['telegram_requests'],0)
        self.assertEqual(call.call_args_list[1].args,('POST','actions/runs/'+str(TARGET)+'/cancel'))
    def test_active_or_completed_execution_is_not_interrupted(self):
        from c3_retire_obsolete_sender_v1 import retire
        from unittest.mock import Mock
        for status in ('in_progress','completed'):
            call=Mock(return_value={'status':status});self.assertEqual(retire(call,Mock())['cancel_requests'],0);self.assertEqual(call.call_count,1)

if __name__=='__main__':unittest.main()
