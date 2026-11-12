"""Fault tests; fixtures are SYNTHETIC, never current market/receipt evidence."""
import copy,json,tempfile,unittest
from datetime import date,datetime,timedelta
from pathlib import Path
from unittest.mock import Mock,patch
from zoneinfo import ZoneInfo
from PIL import Image
from c3_chart_warmup_v1 import extend_bars,attach_locked_warmup
from c3_classic_theme import create_cards,chart_geometry,moving_average,audit_averages,source_labels
from c3_telegram_notify import report_error,expected_session,Telegram,deliver
from c3_telegram_inputs import canonical,digest
from c3_report_handoff import packet
from test_c3_telegram_notify import fixture,MemoryStore,FakeBot
import test_c3_telegram_notify as notify_tests


def sample():
    days=[];d=date(2026,5,1)
    while len(days)<130:
        if d.weekday()<5:days.append(d.isoformat())
        d+=timedelta(days=1)
    panel=[dict(ticker='000001',name='SYNTHETIC',date=d,open=100+i,high=106+i,low=96+i,
                close=102+i,volume=1000,turnover_krw=(102+i)*1000) for i,d in enumerate(days)]
    frozen=[dict({k:b[k] for k in ('date','name','open','high','low','close','volume','turnover_krw')},segment=0) for b in panel[-90:]]
    row={'ticker':'000001','name':'SYNTHETIC','chart_bars':frozen,'close':frozen[-1]['close']}
    return row,panel,days,{'reference_rebase_candidates':[]}


class WarmupTests(unittest.TestCase):
    def test_exact_overlap_preserves_all_ninety_original_bars_and_plans(self):
        row,panel,days,audit=sample();before=copy.deepcopy(row)
        bars,e=extend_bars(row,panel,days,audit)
        self.assertEqual(row,before);self.assertEqual(bars[-90:],row['chart_bars'])
        self.assertEqual(len(bars),119);self.assertEqual(e['added_prefix_rows'],29)
        g,av=chart_geometry(bars,row,None)
        self.assertEqual(len(g['paths']['60']),60)
        self.assertEqual(g['paths']['60'][0]['date'],bars[-60]['date'])
        self.assertEqual(source_labels({},row,bars)['ma60_visible_points'],60)
        audit_averages(bars,av)
    def test_not_enough_history_cannot_be_called_full_ma60(self):
        row,panel,days,audit=sample()
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT'):extend_bars(row,panel[-110:],days,audit)
        self.assertEqual(source_labels({},row,row['chart_bars'])['ma60_visible_points'],31)
    def test_overlap_cannot_silently_replace_any_original_ohlcv_value(self):
        for key in ('open','high','low','close','volume','turnover_krw'):
            row,panel,days,audit=sample();panel[-1][key]+=1
            with self.assertRaisesRegex(ValueError,'OVERLAP_MISMATCH'):extend_bars(row,panel,days,audit)
    def test_prefix_gap_halt_name_change_and_action_boundary_fail_closed(self):
        for kind in ('gap','halt','name','action','jump'):
            row,panel,days,audit=sample()
            if kind=='gap':panel.pop(15)
            if kind=='halt':panel[15]['volume']=0
            if kind=='name':panel[15]['name']='ANOTHER_COMPANY'
            if kind=='action':audit['reference_rebase_candidates']=[{'ticker':'000001','date':panel[15]['date']}]
            if kind=='jump':
                for k in ('open','high','low','close'):panel[15][k]*=2
            with self.assertRaises(ValueError):extend_bars(row,panel,days,audit)
    def test_unpinned_archive_never_reaches_renderer(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp,'untrusted.zip');p.write_bytes(b'SYNTHETIC_UNPINNED')
            with self.assertRaisesRegex(ValueError,'HASH'):attach_locked_warmup({'research_top2':[{'ticker':'000001'}]},p)


class OriginalDecisionTests(unittest.TestCase):
    def test_unverified_source_is_not_zero_candidates(self):
        r,s,clock=fixture();r['research_top2']=[];r['source_regular_only_certified']=False
        self.assertEqual(report_error(r,s,clock),'REGULAR_SESSION_SOURCE_UNCERTIFIED')
        with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(ValueError,'NOT_VERIFIED'):create_cards(r,tmp)
    def test_real_original_counts_zero_one_two_pass_count_gate(self):
        for n in (0,1,2):
            r,s,clock=fixture();r['research_top2']=r['research_top2'][:n]
            self.assertIsNone(report_error(r,s,clock))
    def test_false_certificate_and_changed_public_count_never_change_sealed_decision(self):
        helper=notify_tests.FrozenDecisionTests();r,record=helper.sample()
        r['source_regular_only_certified']=True
        with self.assertRaisesRegex(ValueError,'REGULAR_SESSION_UNCERTIFIED'):helper.load(r,record)
        r,record=helper.sample();r['research_top2']=[]
        with self.assertRaisesRegex(ValueError,'COUNT_OR_ORDER'):helper.load(r,record)
    def test_after_midnight_friday_recovery_keeps_same_source_date(self):
        for stamp in ('2026-11-12T00:05:00+09:00','2026-11-14T00:50:00+09:00'):
            clock=datetime.fromisoformat(stamp)
            expected='2026-11-11' if clock.weekday()==3 else '2026-11-13'
            self.assertEqual(expected_session(clock),expected)
    def test_analysis_must_complete_after_receipt_before_publication(self):
        r,s,clock=fixture();r['analysis_completed_at']='2026-11-06T13:28:00Z'
        self.assertEqual(report_error(r,s,clock),'ANALYSIS_COMPLETION_TIME_MISMATCH')


class VariablePhotoTests(unittest.TestCase):
    def test_image_hash_error_stops_before_any_telegram_client_or_claim(self):
        import c3_telegram_notify as notify
        r,s,clock=fixture()
        for row in r['research_top2']:row['chart_bars']=[{}]*119
        def broken_image(report,out):
            paths=[];cards=[]
            for i,row in enumerate(report['research_top2']):
                p=Path(out,row['ticker']+'_integrated.png');Image.new('RGB',(4,4),('white','black')[i]).save(p);paths.append(p)
                cards.append(dict(ticker=row['ticker'],asof=report['source_price_asof'],sha256='0'*64))
            Path(out,'render_diagnostics.json').write_text(json.dumps({'cards':cards}))
            return paths
        with tempfile.TemporaryDirectory() as tmp,patch.object(notify,'GitHub',return_value=Mock(sources=[])),patch.object(notify,'report_pair',return_value=(r,s,'a'*40)),patch.object(notify,'frozen_live_bars',side_effect=lambda g,r,ref:r),patch.object(notify,'now_kst',return_value=clock),patch('c3_report_context.attach_context',side_effect=lambda r,*a:r),patch('c3_classic_theme.create_cards',side_effect=broken_image),patch.object(notify,'Telegram') as bot,patch.object(notify,'ReceiptStore') as store,patch('sys.argv',['notify','--mode','live','--outdir',tmp]):
            self.assertEqual(notify.main(),1)
            bot.assert_not_called();store.assert_not_called()
    def test_zero_original_candidates_render_one_cash_png_with_no_stock_or_price(self):
        r,s,clock=fixture();r['research_top2']=[]
        r['input_provenance']={'decision_payload_sha256':'a'*64}
        with tempfile.TemporaryDirectory() as tmp:
            paths=create_cards(r,tmp);self.assertEqual(len(paths),1)
            x=packet(r,'a'*40,{'status':'DRY_RUN_VALIDATED_NO_DELIVERY'},clock,tmp,True,True)
            self.assertEqual(x['research_top2'],[]);self.assertEqual(x['images'][0]['ticker'],'CASH')
            diag=json.loads(Path(tmp,'render_diagnostics.json').read_text())
            self.assertEqual(diag['cards'][0]['source_rows'],0)
    def test_one_photo_payload_has_no_caption_no_text_and_exact_recipient(self):
        bot=Telegram('SYNTHETIC','-1001234567890')
        reply={'ok':True,'result':{'message_id':21,'photo':[{'file_id':'synthetic'}],'chat':{'id':-1001234567890}}}
        response=Mock(status_code=200);response.json.return_value=reply
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp,'synthetic.png');Image.new('RGB',(4,4)).save(p)
            with patch('c3_telegram_notify.requests.post',return_value=response) as post:
                result=bot.send_album([p]);args=post.call_args
                self.assertTrue(args.args[0].endswith('/sendPhoto'))
                self.assertEqual(set(args.kwargs['data']),{'chat_id'})
                self.assertEqual(args.kwargs['files'][0][0],'photo');self.assertFalse(args.kwargs['allow_redirects'])
                self.assertEqual(result['message_ids'],[21]);self.assertFalse(result['human_read_confirmed'])
            for changes in ({'caption':'bad'},{'chat':{'id':-1009999999999}},{'message_id':0}):
                bad=copy.deepcopy(reply);bad['result'].update(changes);response.json.return_value=bad
                with patch('c3_telegram_notify.requests.post',return_value=response),self.assertRaises(ValueError):bot.send_album([p])
    def test_cash_and_single_stock_keep_same_date_claim_and_no_uncertain_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp,'synthetic.png');Image.new('RGB',(4,4)).save(p)
            for count in (0,1):
                report={'source_price_asof':'2026-11-11','research_top2':[{}]*count,'source_run_id':'SYNTHETIC'}
                store=MemoryStore();bot=FakeBot(fail=True)
                first=deliver([p],report,store,bot);again=deliver([p],report,store,bot)
                self.assertEqual(first['status'],'REVIEW_REQUIRED_NO_AUTOMATIC_RESEND')
                self.assertEqual(again['status'],'DUPLICATE_BLOCKED');self.assertEqual(bot.calls,1)
    def test_lineage_mismatch_blocks_packet_even_when_image_hash_is_valid(self):
        r,s,clock=fixture();row,panel,days,audit=sample();bars,_=extend_bars(row,panel,days,audit)
        row.update(chart_bars=bars,chart_price_basis='KRX_UNADJUSTED_AS_TRADED')
        r['source_price_asof']=bars[-1]['date'];r['research_top2']=[row]
        r['input_provenance']={'decision_payload_sha256':'a'*64}
        with tempfile.TemporaryDirectory() as tmp:
            create_cards(r,tmp);p=Path(tmp,'render_diagnostics.json');d=json.loads(p.read_text())
            d['cards'][0]['source_run_id']='OTHER_RUN';p.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,'LINEAGE_MISMATCH'):packet(r,'a'*40,{'status':'DELIVERED'},clock,tmp,False,True)


if __name__=='__main__':unittest.main()
