"""Synthetic fault tests. They are not new market or Telegram delivery evidence."""
import copy,json,tempfile,threading,unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock,patch
from zoneinfo import ZoneInfo
from PIL import Image
from c3_telegram_notify import report_error,expected_session,delivery_key,deliver,Telegram,ReceiptStore
from c3_telegram_inputs import ServiceError
from c3_classic_theme import moving_average,validate_bars,notes,TRADE_COLORS

def fixture():
    clock=datetime(2026,11,6,22,45,tzinfo=ZoneInfo('Asia/Seoul'))
    r={'source_price_asof':'2026-11-06','source_run_id':'SYNTHETIC','generated_at':'2026-11-06T13:30:00Z','source_received_at':'2026-11-06T13:29:00Z','data_quality_state':'OFFICIAL_VERIFIED','source_provider':'KRX_OFFICIAL_EOD','source_quality_gate':{'status':'QUALITY_GATE_PASSED','errors':[],'markets':{'KOSPI':{'rows':900},'KOSDAQ':{'rows':1800}}},'current_scope':{'price_rows':2700,'analysis_eligible':1800},'errors':[],'orders_enabled':False,'current_action':'CASH','research_top2_registered_for_source_session':True,'research_top2':[{'ticker':'000001'},{'ticker':'000002'}]}
    s={k:r[k] for k in ('source_price_asof','source_run_id','generated_at')};return r,s,clock

class MemoryStore:
    def __init__(self):self.claims={};self.results={};self.lock=threading.Lock();self.fail_finish=False;self.legacy=False
    def initialize(self):pass
    def exists(self,k):return k in self.claims or k in self.results
    def legacy_exists(self,d):return self.legacy
    def reserve(self,k,p):
        with self.lock:
            if k in self.claims:return False
            self.claims[k]=p;return True
    def finish(self,k,p):
        if self.fail_finish:raise OSError('SYNTHETIC_SAVE_FAILURE')
        self.results[k]=copy.deepcopy(p)

class FakeBot:
    fingerprint='a'*16
    def __init__(self,fail=False):self.calls=0;self.fail=fail
    def verify_group(self):pass
    def send_album(self,paths):
        self.calls+=1
        if self.fail:raise TimeoutError('SYNTHETIC_POSSIBLY_DELIVERED')
        return {'message_ids':[11,12],'media_group_hash':'f'*64,'photos':2,'captions_present':False,'text_present':False}

class TelegramNotifyTests(unittest.TestCase):
    def setUp(self):self.latest,self.summary,self.clock=fixture()
    def test_verified_registered_new_session(self):self.assertIsNone(report_error(self.latest,self.summary,self.clock))
    def test_yesterday_cannot_be_today(self):
        self.latest['source_price_asof']='2026-11-05';self.summary['source_price_asof']='2026-11-05'
        self.assertEqual(report_error(self.latest,self.summary,self.clock),'NO_NEW_COMPLETED_SESSION')
    def test_before_close_and_monday_morning(self):
        self.assertEqual(expected_session(datetime(2026,11,6,14,tzinfo=ZoneInfo('Asia/Seoul'))),'2026-11-05')
        self.assertEqual(expected_session(datetime(2026,11,9,9,tzinfo=ZoneInfo('Asia/Seoul'))),'2026-11-06')
    def test_regular_close_boundary(self):
        self.assertEqual(expected_session(datetime(2026,11,6,15,30,tzinfo=ZoneInfo('Asia/Seoul'))),'2026-11-06')
    def test_weekend_no_daily_send(self):self.assertIsNone(expected_session(datetime(2026,11,7,12,tzinfo=ZoneInfo('Asia/Seoul'))))
    def test_mixed_runs(self):
        self.summary['source_run_id']='OTHER';self.assertEqual(report_error(self.latest,self.summary,self.clock),'RUN_ID_MISMATCH')
    def test_mixed_report_versions(self):
        self.summary['generated_at']='2026-11-06T13:00:00Z';self.assertEqual(report_error(self.latest,self.summary,self.clock),'REPORT_VERSION_MISMATCH')
    def test_unverified_prices(self):
        self.latest['data_quality_state']='PROVISIONAL';self.assertEqual(report_error(self.latest,self.summary,self.clock),'UNVERIFIED_MARKET_DATA')
    def test_market_row_count_mismatch(self):
        self.latest['current_scope']['price_rows']=10;self.assertEqual(report_error(self.latest,self.summary,self.clock),'MARKET_ROW_COUNT_MISMATCH')
    def test_one_market_is_not_whole_market(self):
        del self.latest['source_quality_gate']['markets']['KOSDAQ'];self.assertEqual(report_error(self.latest,self.summary,self.clock),'INCOMPLETE_MARKET_COVERAGE')
    def test_buy_guard_survives_display_changes(self):
        self.latest['orders_enabled']=True;self.assertEqual(report_error(self.latest,self.summary,self.clock),'LIVE_ORDER_OR_ACTION_POLICY_VIOLATION')
    def test_old_or_future_report(self):
        for stamp in ('2026-11-04T09:00:00Z','2026-11-06T13:46:00Z'):
            self.latest['generated_at']=self.summary['generated_at']=stamp
            self.assertEqual(report_error(self.latest,self.summary,self.clock),'STALE_OR_FUTURE_REPORT')
    def test_undated_source_receipt_rejected(self):
        self.latest['source_received_at']='2026-11-06T13:29:00';self.assertEqual(report_error(self.latest,self.summary,self.clock),'INVALID_REPORT_GENERATION_TIME')
    def test_unregistered_preview_not_sent_as_live(self):
        self.latest['research_top2_registered_for_source_session']=False;self.assertEqual(report_error(self.latest,self.summary,self.clock),'UNREGISTERED_RESEARCH_PREVIEW')
    def test_one_or_duplicated_stock_does_not_fill_album(self):
        for picks in ([{'ticker':'000001'}],[{'ticker':'000001'},{'ticker':'000001'}]):
            self.latest['research_top2']=picks;self.assertEqual(report_error(self.latest,self.summary,self.clock),'EXACTLY_TWO_UNIQUE_CANDIDATES_REQUIRED')
    def test_qualified_mirror_has_separate_provenance_gate(self):
        self.latest.update(data_quality_state='RESEARCH_VALIDATED',source_provider='FINANCEDATA_KRX_CACHE')
        self.assertEqual(report_error(self.latest,self.summary,self.clock),'UNVERIFIED_ALTERNATIVE_PROOF')
        self.latest['source_validation_sha256']='a'*64;self.assertIsNone(report_error(self.latest,self.summary,self.clock))
    def test_delivery_key_is_date_scoped_and_safe(self):
        self.assertEqual(delivery_key('2026-11-06','a'*16),delivery_key('2026-11-06','a'*16))
        for bad in ('../../etc/passwd','2026-13-99'):
            with self.assertRaises(ValueError):delivery_key(bad,'a'*16)
    def test_historical_permission_does_not_enable_another_date(self):
        with self.assertRaises(ValueError):delivery_key('2026-11-06','a'*16,'past_example')
        self.assertNotEqual(delivery_key('2026-11-05','a'*16),delivery_key('2026-11-05','a'*16,'past_example'))

class DeliveryFaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.files=[]
        for i,color in enumerate(('white','black')):
            p=Path(self.tmp.name)/(str(i)+'.png');Image.new('RGB',(4,4),color).save(p);self.files.append(p)
        self.report={'source_price_asof':'2026-11-06','source_run_id':'SYNTHETIC'}
    def tearDown(self):self.tmp.cleanup()
    def test_one_photo_CASH_and_stock_share_same_daily_exclusive_claim(self):
        single=Path(self.tmp.name,'CASH_integrated.png')
        Image.new('RGB',(64,64),'white').save(single)
        result={'source_price_asof':'2026-11-06','source_run_id':'SYNTHETIC',
                'final_presentation_review':{'schema':'C3_FINAL_PRESENTATION_REVIEW_V21',
                                             'delivery_kind':'CASH_1','eligible_count':0}}
        store=MemoryStore()
        bot=FakeBot();bot.send_single=lambda path:{'message_ids':[27],'media_group_hash':None,
                         'photos':1,'captions_present':False,'text_present':False}
        x=deliver([single],result,store,bot)
        self.assertEqual(x['status'],'DELIVERED')
        self.assertEqual(x['photos'],1)
        result['final_presentation_review']['delivery_kind']='ALBUM_2'
        dup=deliver(self.files,result,store,bot)
        self.assertEqual(dup['status'],'DUPLICATE_BLOCKED')
        self.assertEqual(dup['send_attempts'],0)

    def test_one_photo_sendPhoto_has_no_text_caption_redirect_or_retry(self):
        single=self.files[0]
        bot=Telegram('SYNTHETIC_NOT_REAL_TOKEN','-1001234567890')
        reply=Mock(status_code=200)
        reply.json.return_value={'ok':True,'result':{'message_id':55,
                              'photo':[{'file_id':'abc'}],'chat':{'id':-1001234567890}}}
        with patch('c3_telegram_notify.requests.post',return_value=reply) as post:
            out=bot.send_single(single)
            self.assertEqual(out['message_ids'],[55])
            self.assertEqual(out['photos'],1)
            self.assertEqual(post.call_count,1)
            self.assertIn('sendPhoto',post.call_args.args[0])
            self.assertEqual(set(post.call_args.kwargs['data']),{'chat_id'})
            self.assertEqual(set(post.call_args.kwargs['files']),{'photo'})
            self.assertIs(post.call_args.kwargs['allow_redirects'],False)

    def test_repeat_events_and_changed_content_do_not_resend(self):
        store=MemoryStore();bot=FakeBot();a=deliver(self.files,self.report,store,bot)
        Image.new('RGB',(4,4),'red').save(self.files[0])
        b=deliver(self.files,self.report,store,bot)
        self.assertEqual(a['status'],'DELIVERED');self.assertEqual(b['status'],'DUPLICATE_BLOCKED');self.assertEqual(bot.calls,1)
    def test_concurrent_claims_have_one_winner(self):
        store=MemoryStore();bot=FakeBot()
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:deliver(self.files,self.report,store,bot),range(2)))
        self.assertEqual(bot.calls,1);self.assertEqual(sum(r['status']=='DELIVERED' for r in results),1)
    def test_uncertain_api_result_never_retries(self):
        store=MemoryStore();bot=FakeBot(fail=True);a=deliver(self.files,self.report,store,bot);b=deliver(self.files,self.report,store,bot)
        self.assertEqual(a['status'],'REVIEW_REQUIRED_NO_AUTOMATIC_RESEND');self.assertEqual(b['status'],'DUPLICATE_BLOCKED');self.assertEqual(bot.calls,1)
    def test_final_git_save_failure_keeps_the_claim(self):
        store=MemoryStore();store.fail_finish=True;bot=FakeBot();a=deliver(self.files,self.report,store,bot);b=deliver(self.files,self.report,store,bot)
        self.assertIn('receipt_write_status',a);self.assertEqual(b['status'],'DUPLICATE_BLOCKED');self.assertEqual(bot.calls,1)
    def test_claim_store_failure_never_attempts_send(self):
        store=MemoryStore();store.reserve=Mock(side_effect=OSError('SYNTHETIC_CLAIM_FAILURE'));bot=FakeBot()
        with self.assertRaises(OSError):deliver(self.files,self.report,store,bot)
        self.assertEqual(bot.calls,0)
    def test_legacy_receipt_prevents_migration_resend(self):
        store=MemoryStore();store.legacy=True;bot=FakeBot();r=deliver(self.files,self.report,store,bot)
        self.assertEqual(r['status'],'DUPLICATE_BLOCKED');self.assertEqual(bot.calls,0)
    def test_duplicate_or_non_two_images_blocked(self):
        for paths in ([self.files[0]],[self.files[0]]*2,self.files*2):
            with self.assertRaises(ValueError):deliver(paths,self.report,MemoryStore(),FakeBot())
    def test_payload_has_only_two_photos_no_caption_or_text_and_no_redirect_retry(self):
        bot=Telegram('SYNTHETIC_NOT_A_REAL_TOKEN','-1001234567890')
        result={'ok':True,'result':[{'message_id':i,'media_group_id':'SYNTHETIC_ALBUM','photo':[{'file_id':'synthetic'}],'chat':{'id':-1001234567890}} for i in (11,12)]}
        response=Mock(status_code=200);response.json.return_value=result
        with patch('c3_telegram_notify.requests.post',return_value=response) as post:
            r=bot.send_album(self.files)
            self.assertEqual(post.call_count,1);args=post.call_args.kwargs
            self.assertEqual(json.loads(args['data']['media']),[{'type':'photo','media':'attach://photo0'},{'type':'photo','media':'attach://photo1'}])
            self.assertEqual(len(args['files']),2);self.assertFalse(args['allow_redirects']);self.assertFalse(r['captions_present']);self.assertFalse(r['text_present'])
    def test_wrong_group_title_or_private_recipient_is_rejected(self):
        bot=Telegram('SYNTHETIC','-1001234567890')
        for title,kind in [('other','group'),('강현 AI','private')]:
            response=Mock(status_code=200);response.json.return_value={'ok':True,'result':{'id':-1001234567890,'title':title,'type':kind}}
            with patch('c3_telegram_notify.requests.post',return_value=response),self.assertRaises(ValueError):bot.verify_group()
    def test_caption_or_different_album_response_is_never_confirmed(self):
        bot=Telegram('SYNTHETIC','-1001234567890')
        for change in ({'caption':'unexpected'},{'media_group_id':'another'}):
            messages=[{'message_id':i,'media_group_id':'one','photo':[{'file_id':'synthetic'}],'chat':{'id':-1001234567890}} for i in (11,12)]
            messages[1].update(change);response=Mock(status_code=200);response.json.return_value={'ok':True,'result':messages}
            with patch('c3_telegram_notify.requests.post',return_value=response),self.assertRaises(ValueError):bot.send_album(self.files)
    def test_atomic_api_conflict_is_duplicate_only_if_claim_is_present(self):
        gh=Mock();gh.create.side_effect=ServiceError(409);store=ReceiptStore(gh);store.exists=Mock(return_value=True)
        self.assertFalse(store.reserve('synthetic',{}));store.exists.return_value=False
        with self.assertRaises(ServiceError):store.reserve('synthetic',{})
    def test_deleted_receipt_branch_cannot_be_recreated_and_resend(self):
        gh=Mock();gh.api.return_value=None;store=ReceiptStore(gh)
        with self.assertRaisesRegex(ValueError,'STORE_MISSING'):store.initialize()
        gh.create.assert_not_called();self.assertEqual(gh.api.call_count,1)
    def test_reset_branch_without_store_anchor_is_blocked(self):
        gh=Mock();gh.api.return_value={'object':{'sha':'a'*40}};gh.file.return_value=None
        with self.assertRaisesRegex(ValueError,'ANCHOR_MISSING'):ReceiptStore(gh).initialize()
        gh.create.assert_not_called()
    def test_original_anchored_store_remains_usable(self):
        gh=Mock();gh.api.return_value={'object':{'sha':'a'*40}};gh.file.return_value=json.dumps({'schema':'C3_TELEGRAM_RECEIPT_STORE_V1','automatic_reinitialization_allowed':False}).encode()
        ReceiptStore(gh).initialize();gh.create.assert_not_called()

class ChartTruthTests(unittest.TestCase):
    def test_unpinned_historical_csv_cannot_supply_chart_prices(self):
        from c3_telegram_inputs import build_example
        with self.assertRaisesRegex(ValueError,'CACHE_HASH'):build_example({}, {}, b'SYNTHETIC_UNTRUSTED_FEED')
    def test_moving_averages_have_exact_warmup_and_no_fake_values(self):
        bars=[{'close':i} for i in range(1,66)]
        for n,last in [(5,63),(20,55.5),(60,35.5)]:
            values=moving_average(bars,n);self.assertEqual(values[:n-1],[None]*(n-1));self.assertEqual(values[-1],last)
    def test_insufficient_history_future_date_and_close_mismatch_fail(self):
        rows=[{'date':f'2026-09-{i:02}','open':100,'high':110,'low':90,'close':100,'volume':100} for i in range(1,30)]
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT'):validate_bars(rows,'2026-11-05',100)
        from datetime import timedelta
        rows=[dict(rows[0],date=(datetime(2026,8,1)+timedelta(days=i)).date().isoformat()) for i in range(91)]
        with self.assertRaisesRegex(ValueError,'DATE'):validate_bars(rows,'2026-08-10',100)
        with self.assertRaisesRegex(ValueError,'CLOSE'):validate_bars(rows,rows[-1]['date'],101)
    def test_missing_financials_or_news_are_not_invented(self):
        sections=notes({'industry':'SYNTHETIC','market':'KOSPI'},None)
        self.assertEqual(len(sections),4);self.assertIn('판단은 보류',sections[1][1]);self.assertNotIn('흑자전환',sections[1][1])
        self.assertNotIn('미확인', ''.join(v for _,v in sections));self.assertNotIn('기관 순매수',sections[2][1])
        self.assertEqual(set(TRADE_COLORS),{'first','second','stop','r1','r2'})

class FrozenDecisionTests(unittest.TestCase):
    def sample(self):
        row={'ticker':'000001','signal_id':'SYNTHETIC','reference_close':100,'entry_plans':{'A':None},'model':'B','rank':1,'chart_bars':[{'date':'2026-11-06','close':100}]}
        payload={'price_asof':'2026-11-06','models':{'B':[row]}}
        from c3_telegram_inputs import canonical,digest
        record={'payload':payload,'sha256':digest(canonical(payload))}
        report={'source_price_asof':'2026-11-06','ledger_lane':'lanes/krx_unadjusted_v12','research_top2':[{k:v for k,v in row.items() if k!='chart_bars'}]}
        return report,record
    def load(self,report,record):
        from c3_telegram_inputs import frozen_live_bars
        import types,sys
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'c3_supply_v11.py').write_text('# SYNTHETIC ARCHIVE READER PLACEHOLDER')
            reader=types.SimpleNamespace(open_sealed=lambda *args:json.dumps(record).encode());gh=Mock();gh.api.return_value=[];gh.file.return_value=b'SYNTHETIC_CIPHERTEXT'
            with patch.dict('os.environ',{'C3_ARCHIVE_READER_PATH':tmp,'KRX_AUTH_KEY':'SYNTHETIC_NOT_REAL'}),patch.dict(sys.modules,{'c3_supply_v11':reader}):return frozen_live_bars(gh,report,'a'*40)
    def test_live_chart_comes_from_same_authenticated_frozen_decision(self):
        report,record=self.sample();r=self.load(report,record)
        self.assertEqual(r['research_top2'][0]['chart_bars'],record['payload']['models']['B'][0]['chart_bars'])
        self.assertEqual(r['research_top2'][0]['chart_price_basis'],'KRX_UNADJUSTED_AS_TRADED')
    def test_bad_hash_or_public_trade_plan_cannot_change_frozen_chart(self):
        report,record=self.sample();record['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'HASH'):self.load(report,record)
        report,record=self.sample();report['research_top2'][0]['entry_plans']={'A':'changed'}
        with self.assertRaisesRegex(ValueError,'MISMATCH'):self.load(report,record)


class FinalPresentationReviewTests(unittest.TestCase):
    """Fixed real 2026-11-10 figures, plus synthetic safe-path cases."""

    def fixed_nov10(self):
        asof='2026-11-10'
        def row(ticker,name,rank,close,low,high,stop,known_on,r1,rr):
            return {'ticker':ticker,'name':name,'rank':rank,'source_price_asof':asof,
                    'source_run_id':'42884437776','source_regular_only_certified':False,
                    'signal_id':'FROZEN_'+ticker,'reference_close':close,
                    'entry_plans':{'A_SUPPORT_LIMIT':{'plan':{'low':low,'high':high,
                     'stop':stop,'known_on':known_on,'decision_date':asof,
                     'resistance':r1,'net_r1_rr':rr}}}}
        rows=[row('028050','삼성E&A',1,64600,59400,62600,56100,'2026-11-10',65500,0.33615940389023125),
              row('180640','한진칼',2,239000,118000,122000,113800,'2026-10-27',None,None)]
        return {'source_price_asof':asof,'source_run_id':'42884437776',
                'source_validation_sha256':'4de3a1db908d6c28479d6862311e650075f7f5bcaa27bdbb990fc2a31158dd09',
                'source_regular_only_certified':False,'research_top2_registered_for_source_session':True,
                'orders_enabled':False,'current_action':'CASH','research_top2':rows}

    def test_nov10_hanjin_stale_and_samsung_rr_block_keep_original_signals(self):
        from c3_final_delivery_gate_v1 import review
        from c3_telegram_inputs import canonical,digest
        report=self.fixed_nov10();frozen=digest(canonical(report))
        result=review(report)
        self.assertEqual([x['technical_status'] for x in result['reviewed']],
                         ['RISK_REJECTED','STALE_ENTRY'])
        self.assertTrue(all(x['final_status']=='DATA_BLOCKED' for x in result['reviewed']))
        self.assertEqual(result['eligible_count'],0)
        self.assertEqual(result['candidate_pool_status'],'CANDIDATE_POOL_UNVERIFIED')
        self.assertTrue(result['sendable'])
        self.assertEqual(result['delivery_kind'],'CASH_1')
        self.assertEqual(result['decision'],'CASH')
        self.assertEqual(digest(canonical(report)),frozen)

    def synthetic_report(self,n):
        from datetime import date,timedelta
        asof='2026-11-10'
        bars=[{'date':(date(2026,11,10)-timedelta(days=89-i)).isoformat(),
               'open':100,'high':101,'low':99,'close':100,'volume':100} for i in range(90)]
        picks=[]
        for i in range(n):
            picks.append({'ticker':f'{i+1:06d}','name':'SYNTHETIC','rank':i+1,
                'signal_id':f'SYNTHETIC_{i}','source_price_asof':asof,'source_run_id':'SYNTHETIC_RUN',
                'source_regular_only_certified':True,'chart_price_basis':'KRX_UNADJUSTED_AS_TRADED',
                'chart_bars':bars,'reference_close':100,'close':100,
                'entry_plans':{'A_SUPPORT_LIMIT':{'plan':{
                'low':97,'high':99,'stop':95,'resistance':110,'net_r1_rr':2.75,
                'known_on':asof,'decision_date':asof}}}})
        return {'source_price_asof':asof,'source_run_id':'SYNTHETIC_RUN',
            'source_validation_sha256':'a'*64,'source_regular_only_certified':True,
            'research_top2_registered_for_source_session':True,
            'orders_enabled':False,'current_action':'CASH','research_top2':picks}

    def test_zero_one_two_candidates_render_and_create_no_fake_prices(self):
        from c3_final_delivery_gate_v1 import review,filtered_report_for_presentation
        from c3_classic_theme import create_final_cards
        from c3_telegram_notify import validate_photos
        for count in (0,1,2):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as tmp:
                report=self.synthetic_report(count);original=json.dumps(report,sort_keys=True)
                result=review(report)
                self.assertEqual(result['eligible_count'],count)
                self.assertTrue(result['sendable'])
                self.assertEqual(result['delivery_kind'],{0:'CASH_1',1:'STOCK_1',2:'ALBUM_2'}[count])
                output=filtered_report_for_presentation(report,result)
                self.assertEqual(len(output['research_top2']),count)
                self.assertEqual(json.dumps(report,sort_keys=True),original)
                paths=create_final_cards(output,tmp)
                self.assertEqual(len(paths),1 if count<2 else 2)
                self.assertEqual(len(validate_photos(paths,allow_single=True)),len(paths))
                if count==0:
                    self.assertEqual(paths[0].name,'CASH_integrated.png')
                else:
                    diag=json.loads(Path(tmp,'render_diagnostics.json').read_text())
                    self.assertTrue(all(x['visible_rows']==60 for x in diag['cards']))

    def test_only_authenticated_frozen_B_ranked_pool_can_promote_rank_three(self):
        from c3_final_delivery_gate_v1 import review,filtered_report_for_presentation
        from c3_telegram_inputs import canonical,digest
        report=self.synthetic_report(2)
        for row in report['research_top2']:row['model']='B'
        report['research_top2'][1]['entry_plans']['A_SUPPORT_LIMIT']['plan']['resistance']=100
        pool=copy.deepcopy(report['research_top2'])
        third=copy.deepcopy(pool[0]);third.update(ticker='000003',name='SYNTHETIC3',rank=3,signal_id='THIRD')
        pool.append(third)
        proof={'schema':'C3_IMMUTABLE_B_POOL_V21',
            'origin':'AUTHENTICATED_FROZEN_C3_B_DECISION',
            'frozen_decision_sha256':'e'*64,'frozen_research_commit':'d'*40,
            'source_run_id':report['source_run_id'],'asof':report['source_price_asof'],
            'source_validation_sha256':report['source_validation_sha256'],
            'pool_sha256':digest(canonical(pool))}
        allowed=review(report,pool,proof)
        self.assertEqual(allowed['candidate_pool_status'],'AUTHENTICATED_SAME_MODEL_B_POOL')
        self.assertEqual([x['ticker'] for x in allowed['eligible']],['000001','000003'])
        self.assertEqual(allowed['replacement_count'],1)
        new=filtered_report_for_presentation(report,allowed,pool)
        self.assertEqual([x['rank'] for x in new['research_top2']],[1,3])
        self.assertEqual([x['rank'] for x in report['research_top2']],[1,2])
        forged=copy.deepcopy(proof);forged['pool_sha256']='0'*64
        rejected=review(report,pool,forged)
        self.assertEqual(rejected['candidate_pool_status'],'CANDIDATE_POOL_UNVERIFIED')
        self.assertEqual([x['ticker'] for x in rejected['eligible']],['000001'])

    def test_unverified_alternate_pool_never_invents_a_third_pick(self):
        from c3_final_delivery_gate_v1 import review
        report=self.fixed_nov10()
        fake={'ticker':'999999','source_price_asof':'2026-11-10','rank':3}
        out=review(report,frozen_ranked_pool=[fake],pool_proof={'verified':True})
        self.assertEqual(out['replacement_count'],0)
        self.assertFalse(out['substitutes_invented'])
        self.assertEqual([x['ticker'] for x in out['reviewed']],['028050','180640'])

    def test_live_gate_dry_run_cash_never_constructs_telegram(self):
        import c3_telegram_notify as notify
        clock=datetime(2026,11,10,22,45,tzinfo=ZoneInfo('Asia/Seoul'))
        report=self.fixed_nov10()
        report.update(generated_at='2026-11-10T13:42:00Z',
                      source_received_at='2026-11-10T13:30:00Z')
        summary={k:report[k] for k in ('source_price_asof','source_run_id','generated_at')}
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(notify,'GitHub'),patch.object(notify,'Telegram') as bot, \
             patch.object(notify,'ReceiptStore') as receipts, \
             patch.object(notify,'report_pair',return_value=(report,summary,'a'*40)), \
             patch.object(notify,'report_error',return_value=None), \
             patch.object(notify,'frozen_live_bars',side_effect=lambda gh,r,ref:r), \
             patch.object(notify,'now_kst',return_value=clock), \
             patch('c3_report_context.attach_context',side_effect=lambda r,*args:r), \
             patch.dict('os.environ',{'C3_FINAL_GATE_ENABLED':'1'}), \
             patch('sys.argv',['notify','--mode','live','--dry-run','--outdir',tmp]):
            self.assertEqual(notify.main(),0)
            bot.assert_not_called();receipts.assert_not_called()
            d=json.loads(Path(tmp,'delivery_status.json').read_text())
            self.assertEqual(d['status'],'DRY_RUN_VALIDATED_NO_DELIVERY')
            self.assertEqual(d['photos'],1)
            self.assertEqual(d['send_attempts'],0)
            self.assertTrue(Path(tmp,'CASH_integrated.png').exists())
            audit=json.loads(Path(tmp,'delivery_review.json').read_text())
            self.assertEqual(audit['eligible_count'],0)
            handoff=json.loads(Path(tmp,'presentation.json').read_text())
            self.assertEqual(handoff['images'][0]['ticker'],'CASH')
            self.assertFalse(handoff['chatgpt_delivery_verified'])


if __name__=='__main__':unittest.main()
