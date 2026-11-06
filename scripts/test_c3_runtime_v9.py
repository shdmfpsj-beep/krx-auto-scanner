import copy,unittest
from datetime import datetime,timezone
from c3_runtime_v9 import REPOSITORY,BRANCH,invocation,collection_plan,already_current,handoff,registration_window


class RuntimeV9Tests(unittest.TestCase):
    def test_research_smoke_is_not_an_automatic_daily_run(self):
        r=invocation(REPOSITORY,'refs/heads/'+BRANCH,'push','research_smoke','a'*40)
        self.assertFalse(r['automatic_event_observed'])
    def test_successful_main_scanner_event_allowed_after_deployment(self):
        u=dict(name='KRX daily candidate scan',head_branch='main',conclusion='success',repository=REPOSITORY)
        self.assertTrue(invocation(REPOSITORY,'refs/heads/main','workflow_run','approved_daily','a'*40,u)['automatic_event_observed'])
        for key,value in [('head_branch','untrusted'),('conclusion','failure'),('repository','other/repo')]:
            bad=dict(u);bad[key]=value
            with self.assertRaisesRegex(ValueError,'UPSTREAM'):invocation(REPOSITORY,'refs/heads/main','workflow_run','approved_daily','a'*40,bad)
    def test_unapproved_refs_and_unpinned_code_rejected(self):
        for repo,ref,event,mode,sha in [(REPOSITORY,'refs/heads/feature','push','research_direct','a'*40),('other/repo','refs/heads/main','schedule','approved_daily','a'*40),(REPOSITORY,'refs/heads/main','schedule','approved_daily','main')]:
            with self.assertRaises(ValueError):invocation(repo,ref,event,mode,sha)
    def test_before_close_never_requests_todays_eod(self):
        p=collection_plan(datetime(2026,11,5,19,tzinfo=timezone.utc),['2026-11-04','2026-11-05','2026-11-06'],[])
        self.assertEqual(p['expected_completed_session'],'2026-11-05');self.assertNotIn('2026-11-06',p['requested_dates'])
    def test_after_close_and_request_budget(self):
        p=collection_plan(datetime(2026,11,6,7,tzinfo=timezone.utc),['2026-11-04','2026-11-05','2026-11-06'],['2026-11-05'])
        self.assertEqual(p['requested_dates'],['2026-11-06'])
    def test_same_source_session_skips_only_clean_unchanged_model(self):
        r=dict(source_price_asof='2026-11-06',errors=[],source_hashes=dict(pipeline_code='abc'))
        self.assertTrue(already_current(r,'2026-11-06','abc'));self.assertFalse(already_current(dict(r,errors=['MISSING']),'2026-11-06','abc'));self.assertFalse(already_current(r,'2026-11-06','new'))
    def test_report_reader_does_not_claim_real_alarm_delivery(self):
        s=dict(generated_at='2026-11-06T00:00:00Z',source_run_id='123',source_price_asof=None,preview_price_asof='2026-11-04',new_registered_signals=0,research_top2_is_registered_today=False,performance={},errors=['EMPTY'],current_action='CASH',orders_enabled=False)
        r=handoff(s,'CASH 기준 신규 가상매매');self.assertTrue(r['files_read']);self.assertFalse(r['automatic_chatgpt_delivery_observed'])
        s['new_registered_signals']=1
        with self.assertRaisesRegex(ValueError,'WITHOUT_FRESH'):handoff(s,'CASH 기준 신규 가상매매')

    def test_delayed_publication_window_never_extends_past_possible_open(self):
        self.assertEqual(registration_window('2026-11-05',datetime(2026,11,5,23,tzinfo=timezone.utc)),'SOURCE_BEFORE_FORWARD_START')
        self.assertEqual(registration_window('2026-11-06',datetime(2026,11,7,3,tzinfo=timezone.utc)),'DELAYED_BEFORE_NEXT_POSSIBLE_OPEN')
        self.assertEqual(registration_window('2026-11-06',datetime(2026,11,9,0,tzinfo=timezone.utc)),'PAST_NEXT_POSSIBLE_OPEN')
        self.assertEqual(registration_window('2026-11-06',datetime(2026,11,6,7,tzinfo=timezone.utc)),'SAME_COMPLETED_SESSION')

    def late_fixture(self,now):
        from test_c3_forward_ledger_v8 import market,batch
        m=market(0);b,_=batch(m);actual=now[:10]
        b.update(schema='C3_FORWARD_DECISION_V9',decision_date=actual,known_at=now,allow_delayed_preopen=True)
        for rows in b['models'].values():
            for r in rows:r.update(decision_date=actual,source_price_asof=m['asof'],registered_at=now)
        return m,b

    def test_late_decision_preserves_real_clock_and_source_clock(self):
        import tempfile
        from pathlib import Path
        from c3_forward_ledger_v8 import freeze_market,register,advance
        from test_c3_forward_ledger_v8 import market,dates
        now='2026-11-07T03:00:00Z';m,b=self.late_fixture(now)
        with tempfile.TemporaryDirectory(prefix='synthetic-late-only-') as tmp:
            freeze_market(tmp,m,now);saved,new=register(tmp,b,now);self.assertTrue(new)
            self.assertEqual(saved['decision_date'],'2026-11-07');self.assertEqual(saved['price_asof'],'2026-11-06');self.assertTrue((Path(tmp)/'decisions/2026-11-06.json').exists())
            freeze_market(tmp,market(1),'2026-11-09T07:01:00Z');rows,_=advance(tmp,'2026-11-09T07:02:00Z','SYNTHETIC_LATE')
            self.assertEqual(rows[0]['source_price_asof'],'2026-11-06');self.assertEqual(rows[0]['decision_date'],'2026-11-07');self.assertEqual(rows[0]['paper']['A_SUPPORT_LIMIT']['5']['entry']['date'],dates()[1])

    def test_repeat_after_weekend_keeps_original_decision_not_new_record(self):
        import tempfile
        from pathlib import Path
        from c3_forward_ledger_v8 import freeze_market,register
        now='2026-11-07T03:00:00Z';m,b=self.late_fixture(now)
        with tempfile.TemporaryDirectory() as tmp:
            freeze_market(tmp,m,now);saved,_=register(tmp,b,now);p=Path(tmp)/'decisions/2026-11-06.json';before=p.read_bytes()
            later='2026-11-08T23:30:00Z';_,repeated=self.late_fixture(later);repeated['decision_date']='2026-11-09'
            for rows in repeated['models'].values():
                for r in rows:r['decision_date']='2026-11-09'
            old,new=register(tmp,repeated,later);self.assertFalse(new);self.assertEqual(old['decision_date'],'2026-11-07');self.assertEqual(p.read_bytes(),before);self.assertEqual(len(list(p.parent.glob('*.json'))),1)

    def test_late_price_cannot_create_retroactive_entry_after_open(self):
        import tempfile
        from c3_forward_ledger_v8 import freeze_market,register
        now='2026-11-09T00:01:00Z';m,b=self.late_fixture(now)
        with tempfile.TemporaryDirectory() as tmp:
            freeze_market(tmp,m,now)
            with self.assertRaisesRegex(ValueError,'OUTSIDE_PROSPECTIVE_WINDOW'):register(tmp,b,now)

    def test_registration_uses_analysis_completion_instead_of_collection_start(self):
        from c3_daily_research_v8 import finalize_decision_time
        from test_c3_forward_ledger_v8 import market,batch,register
        import tempfile
        b,started=batch(market(0));completed='2026-11-06T07:01:05Z';b,timing,eligible=finalize_decision_time(b,completed)
        self.assertTrue(eligible);self.assertNotEqual(b['known_at'],started);self.assertEqual(b['known_at'],completed)
        with tempfile.TemporaryDirectory() as tmp:
            saved,new=register(tmp,b,completed);self.assertTrue(new);self.assertEqual(saved['registered_at'],completed)

    def test_analysis_crossing_next_open_deadline_cannot_use_earlier_clock(self):
        from c3_daily_research_v8 import finalize_decision_time
        from test_c3_forward_ledger_v8 import market,batch
        b,_=batch(market(0));b,timing,eligible=finalize_decision_time(b,'2026-11-09T00:00:00Z')
        self.assertFalse(eligible);self.assertEqual(timing,'PAST_NEXT_POSSIBLE_OPEN');self.assertEqual(b['known_at'],'2026-11-09T00:00:00Z')


if __name__=='__main__':unittest.main()
