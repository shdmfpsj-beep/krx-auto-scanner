"""Faults at the report/automation boundary; no messages or market simulations."""
import copy,json,tempfile,unittest,os
from pathlib import Path
from unittest.mock import patch,Mock
from c3_telegram_inputs import canonical,digest,ServiceError
from c3_report_handoff import packet,publish,recovery_plan,read_retry,ROOT,RESEARCH
from test_c3_telegram_notify import fixture


class HandoffTests(unittest.TestCase):
    def setUp(self):self.report,self.summary,self.clock=fixture()
    def test_missing_today_source_never_exposes_old_preview_as_top2(self):
        self.report.update(source_price_asof=None,attempted_price_asof='2026-11-06',errors=['UNAVAILABLE'])
        x=packet(self.report,'a'*40,{'status':'SKIPPED','reason':'NO_NEW_COMPLETED_SESSION'},self.clock,'/does/not/exist')
        self.assertEqual(x['research_top2'],[]);self.assertEqual(x['images'],[])
        self.assertEqual(x['expected_price_session'],'2026-11-06');self.assertEqual(x['status'],'NOT_READY')
    def test_failed_render_never_publishes_candidates(self):
        x=packet(self.report,'a'*40,{'status':'INTERNAL_FAILURE_NO_TEXT_SENT'},self.clock,'/does/not/exist')
        self.assertFalse(x['research_top2']);self.assertFalse(x['chatgpt_delivery_verified'])
    def test_success_packet_pins_images_and_omits_private_bars(self):
        with tempfile.TemporaryDirectory() as tmp:
            cards=[]
            for r in self.report['research_top2']:
                r['chart_bars']=[{'private_full_history':True}];r['company_context']={'quarters':[],'dart':{'do_not_publish':'full_raw_accounts'}}
                body=r['ticker'].encode();Path(tmp,r['ticker']+'_integrated.png').write_bytes(body)
                cards.append(dict(ticker=r['ticker'],asof=self.report['source_price_asof'],sha256=digest(body)))
            p=Path(tmp,'render_diagnostics.json');p.write_text(json.dumps({'example_only':False,'cards':cards}))
            x=packet(self.report,'a'*40,{'status':'DRY_RUN_VALIDATED_NO_DELIVERY','send_attempts':0},self.clock,tmp,True)
            self.assertEqual(len(x['images']),2);self.assertTrue(x['dry_run']);self.assertEqual(x['status'],'READY')
            self.assertNotIn('chart_bars',x['research_top2'][0]);self.assertNotIn('dart',x['research_top2'][0]['company_context'])
            self.assertFalse(x['chatgpt_delivery_verified'])
            cards[-1]['asof']='2026-11-05';p.write_text(json.dumps({'example_only':False,'cards':cards}))
            with self.assertRaisesRegex(ValueError,'DATE_OR_HASH'):packet(self.report,'a'*40,{'status':'DELIVERED'},self.clock,tmp)
    def test_historical_cards_cannot_be_live_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'render_diagnostics.json').write_text(json.dumps({'example_only':True}))
            with self.assertRaisesRegex(ValueError,'HISTORICAL'):packet(self.report,'a'*40,{'status':'DELIVERED'},self.clock,tmp)
    def test_live_dry_run_skips_without_telegram_construction(self):
        import c3_telegram_notify as n
        self.report['source_price_asof']=None
        with tempfile.TemporaryDirectory() as tmp,patch.object(n,'GitHub'),patch.object(n,'Telegram') as bot,patch.object(n,'report_pair',return_value=(self.report,self.summary,'a'*40)),patch.object(n,'now_kst',return_value=self.clock),patch('sys.argv',['notify','--mode','live','--dry-run','--outdir',tmp]):
            self.assertEqual(n.main(),0);bot.assert_not_called()
            x=json.loads(Path(tmp,'presentation.json').read_text());self.assertEqual(x['status'],'NOT_READY')
            self.assertEqual(json.loads(Path(tmp,'delivery_status.json').read_text())['send_attempts'],0)
    def test_successful_live_dry_run_never_claims_or_constructs_sender(self):
        import c3_telegram_notify as n
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            def render(report,out):
                files=[];cards=[]
                for i,row in enumerate(report['research_top2']):
                    path=Path(out,row['ticker']+'_integrated.png');Image.new('RGB',(4,4),('white','black')[i]).save(path);files.append(path)
                    cards.append(dict(ticker=row['ticker'],asof=report['source_price_asof'],sha256=digest(path.read_bytes())))
                Path(out,'render_diagnostics.json').write_text(json.dumps({'example_only':False,'cards':cards}));return files
            with patch.object(n,'GitHub',return_value=Mock(sources=[])),patch.object(n,'Telegram') as bot,patch.object(n,'ReceiptStore') as receipts,patch.object(n,'report_pair',return_value=(self.report,self.summary,'a'*40)),patch.object(n,'frozen_live_bars',side_effect=lambda g,r,ref:r),patch.object(n,'now_kst',return_value=self.clock),patch('c3_report_context.attach_context',side_effect=lambda r,*args:r),patch('c3_classic_theme.create_cards',side_effect=render),patch('sys.argv',['notify','--mode','live','--dry-run','--outdir',tmp]):
                self.assertEqual(n.main(),0);bot.assert_not_called();receipts.assert_not_called()
            x=json.loads(Path(tmp,'presentation.json').read_text());self.assertEqual(x['status'],'READY');self.assertEqual(len(x['images']),2)
            self.assertEqual(x['delivery']['send_attempts'],0);self.assertEqual(x['source_report_sha256'],digest(canonical(self.report)))
    def test_valid_chart_remains_available_when_delivery_is_uncertain(self):
        with tempfile.TemporaryDirectory() as tmp:
            cards=[]
            for row in self.report['research_top2']:
                body=row['ticker'].encode();Path(tmp,row['ticker']+'_integrated.png').write_bytes(body)
                cards.append(dict(ticker=row['ticker'],asof=self.report['source_price_asof'],sha256=digest(body)))
            Path(tmp,'render_diagnostics.json').write_text(json.dumps({'example_only':False,'cards':cards}))
            result={'status':'REVIEW_REQUIRED_NO_AUTOMATIC_RESEND','send_attempts':1}
            x=packet(self.report,'a'*40,result,self.clock,tmp,render_validated=True)
            self.assertEqual(x['status'],'READY');self.assertEqual(x['delivery']['status'],result['status'])
            self.assertFalse(x['chatgpt_delivery_verified'])


class RecoveryTests(unittest.TestCase):
    def setUp(self):self.r,self.s,self.clock=fixture()
    def plan(self,event='schedule',mode='live',runs=()):return recovery_plan(self.r,self.s,self.clock,event,mode,runs)
    def test_valid_source_with_zero_or_one_candidates_is_not_recollected(self):
        for n in (0,1,2):
            self.r['research_top2']=self.r['research_top2'][:n];self.assertFalse(self.plan()['recover'])
    def test_unavailable_source_requests_bounded_recovery(self):
        self.r['source_price_asof']=None;self.assertTrue(self.plan()['recover'])
    def test_no_recovery_for_completion_event_or_preview_or_push(self):
        self.r['source_price_asof']=None
        for event,mode in [('workflow_run','live'),('workflow_dispatch','preview'),('push','past_example'),('pull_request','live')]:self.assertFalse(self.plan(event,mode)['recover'])
    def test_active_research_prevents_parallel_recovery(self):
        self.r['source_price_asof']=None
        for status in ('queued','in_progress','waiting','pending','requested'):self.assertFalse(self.plan(runs=[{'status':status}])['recover'])
    def test_mismatched_source_versions_need_repair(self):
        self.s['source_run_id']='OTHER';self.assertTrue(self.plan()['recover'])


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.r,self.s,self.clock=fixture();self.manifest=packet(self.r,'a'*40,{'status':'SKIPPED'},self.clock,'/unused');self.gh=Mock()
        self.gh.head.return_value='b'*40
        self.gh.file.side_effect=lambda path,ref,missing_ok=False:canonical(self.r) if path==ROOT+'/latest.json' else None
        def api(path,method='GET',payload=None):
            if path.startswith('git/commits/') and method=='GET':return {'tree':{'sha':'c'*40}}
            return {'sha':'d'*40}
        self.gh.api.side_effect=api
    def test_atomic_publication_only_writes_derived_paths(self):
        x=publish(self.gh,self.manifest);self.assertEqual(x['status'],'PUBLISHED_RESEARCH_ONLY')
        for call in self.gh.api.call_args_list:
            if call.args[0]=='git/trees':
                entries=call.kwargs['payload']['tree'];self.assertEqual(len(entries),2)
                self.assertTrue(all(e['path'].startswith(ROOT+'/presentation/') for e in entries))
            if call.kwargs.get('method')=='PATCH':
                self.assertEqual(call.args[0],'git/refs/heads/'+RESEARCH);self.assertIs(call.kwargs['payload']['force'],False)
    def test_changed_source_aborts_without_any_write(self):
        self.r['source_run_id']='NEWER';self.assertEqual(publish(self.gh,self.manifest)['status'],'SOURCE_CHANGED_NOT_PUBLISHED')
        self.assertFalse(any(c.kwargs.get('method') in ('POST','PATCH') for c in self.gh.api.call_args_list))
    def test_save_collision_rechecks_source_and_preserves_newer_run(self):
        def api(path,method='GET',payload=None):
            if method=='PATCH':self.r['source_run_id']='NEWER';raise ServiceError(422)
            return {'tree':{'sha':'c'*40},'sha':'d'*40}
        self.gh.api.side_effect=api
        self.assertEqual(publish(self.gh,self.manifest)['status'],'SOURCE_CHANGED_NOT_PUBLISHED')
    def test_existing_archive_cannot_be_replaced(self):
        self.gh.file.side_effect=lambda path,ref,missing_ok=False:canonical(self.r) if path==ROOT+'/latest.json' else b'{}'
        with self.assertRaisesRegex(ValueError,'IMMUTABLE'):publish(self.gh,self.manifest)
    def test_transient_git_read_retries_but_permission_failure_does_not(self):
        read=Mock(side_effect=[ServiceError(502),{'verified':'actual_read'}]);pause=Mock()
        self.assertEqual(read_retry(read,pause=pause),{'verified':'actual_read'});self.assertEqual(read.call_count,2)
        read=Mock(side_effect=ServiceError(403))
        with self.assertRaises(ServiceError):read_retry(read,pause=pause)
        self.assertEqual(read.call_count,1)
    def test_uncertain_git_update_is_confirmed_without_another_write(self):
        def api(path,method='GET',payload=None):
            if method=='PATCH':
                self.gh.file.side_effect=lambda path,ref,missing_ok=False:canonical(self.manifest)
                raise ServiceError(502)
            return {'tree':{'sha':'c'*40},'sha':'d'*40}
        self.gh.api.side_effect=api
        result=publish(self.gh,self.manifest)
        self.assertTrue(result['confirmed_after_uncertain_git_response'])
        self.assertEqual(sum(c.kwargs.get('method')=='PATCH' for c in self.gh.api.call_args_list),1)
    def test_active_engine_preserves_its_research_head_lease(self):
        self.gh.api.side_effect=lambda *a,**k:{'workflow_runs':[{'id':1,'status':'in_progress'}]}
        self.assertEqual(publish(self.gh,self.manifest)['status'],'RESEARCH_ACTIVE_HANDOFF_DEFERRED')
        self.gh.head.assert_not_called();self.gh.file.assert_not_called()
        self.assertFalse(any(c.kwargs.get('method') in ('POST','PATCH') for c in self.gh.api.call_args_list))


if __name__=='__main__':unittest.main()
