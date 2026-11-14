"""Synthetic boundary faults, never market/Telegram delivery evidence."""
import copy,json,tempfile,unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock,patch
from c3_morning_source_v1 import prior_session,verify_calendar,bounded_target,compare,cache_rows,normalized_hash
from c3_company_quality_review_v1 import statement_facts,join_quality,collect,reuse_evidence
from c3_candidate_entry_review_v2 import all_geometry_reasons,usable
from c3_morning_final_v1 import packet,render,validate_image,finish_delivery,publish,prepared_image
from c3_telegram_inputs import canonical,digest


class ApprovedEngineMorningWindowTests(unittest.TestCase):
    def guard(self):
        import textwrap
        path=Path(__file__).resolve().parent.parent/'.github/workflows/c3_morning_research_adapter_v1.yml'
        script=path.read_text().split('          def require_morning_window',1)[1].split("          require_morning_window(os.environ",1)[0]
        namespace={};exec(textwrap.dedent('          def require_morning_window'+script),namespace)
        return namespace['require_morning_window']
    def test_real_adapter_window_rejects_delayed_or_current_day_registration(self):
        check=self.guard()
        self.assertEqual(check('2026-11-11',datetime.fromisoformat('2026-11-12T08:59:59+09:00')),'2026-11-11')
        for clock in ('2026-11-12T09:00:00+09:00','2026-11-12T16:00:00+09:00'):
            with self.assertRaisesRegex(ValueError,'WINDOW_MISSED'):check('2026-11-11',datetime.fromisoformat(clock))
        with self.assertRaisesRegex(ValueError,'PRIOR_COMPLETED'):check('2026-11-12',datetime.fromisoformat('2026-11-12T08:10:00+09:00'))
    def test_adapter_locks_collection_target_and_preserves_approved_event_validation(self):
        p=Path(__file__).resolve().parent.parent/'.github/workflows/c3_morning_research_adapter_v1.yml'
        s=p.read_text()
        self.assertIn("if target != os.environ['EXPECTED_MORNING_SOURCE_DAY']:raise ValueError('SOURCE_DAY_CHANGED_AFTER_PREFLIGHT')",s)
        self.assertIn("audit=invocation(os.environ['GITHUB_REPOSITORY'],os.environ['GITHUB_REF'],os.environ['GITHUB_EVENT_NAME']",s)
        self.assertNotIn("GITHUB_EVENT_NAME']='",s)
    def test_new_session_review_waits_for_registration_and_pins_its_state(self):
        path=Path(__file__).resolve().parent.parent/'.github/workflows/c3_research_daily_caller.yml'
        job=path.read_text().split('\n  new-session-review:\n',1)[1]
        self.assertIn('needs: [source-ready, research]',job)
        self.assertIn("needs.research.outputs.registered_state_sha ||",job)
        self.assertIn('/reports/c3_new_session_v1/',job)


class CalendarAndSourceTests(unittest.TestCase):
    def test_latest_prior_session_on_regular_day_monday_and_holiday(self):
        for clock,expected in [('2026-11-12T08:10:00+09:00','2026-11-11'),
            ('2026-11-16T08:10:00+09:00','2026-11-13'),
            ('2026-03-03T08:10:00+09:00','2026-02-27'),
            ('2026-10-12T08:10:00+09:00','2026-10-08')]:
            self.assertEqual(prior_session(datetime.fromisoformat(clock))['requested_day'],expected)
    def test_delayed_morning_job_never_switches_to_todays_completed_bar(self):
        r=prior_session(datetime.fromisoformat('2026-11-12T22:00:00+09:00'))
        self.assertEqual(r['requested_day'],'2026-11-11')
    def test_reference_calendar_requires_both_observed_boards(self):
        self.assertEqual(verify_calendar('2026-11-11',{'KOSPI':['2026-11-11','2026-11-12'],'KOSDAQ':['2026-11-11']},'2026-11-12')['KOSPI'],'2026-11-11')
        for observed in ({'KOSPI':['2026-11-11']},{'KOSPI':['2026-11-11'],'KOSDAQ':['2026-11-10']}):
            with self.assertRaises(ValueError):verify_calendar('2026-11-11',observed,'2026-11-12')
    def test_empty_target_is_retried_twice_without_earlier_day_substitution(self):
        collector=Mock(return_value={'asof':'2026-11-11','official_dataset_usable':False})
        pause=Mock();_,receipts=bounded_target('2026-11-11',Path('/unused'),'',collector,pause)
        self.assertEqual(collector.call_count,2);self.assertEqual(len(receipts),2)
        self.assertTrue(all(c.args[0]=='2026-11-11' for c in collector.call_args_list))
        self.assertEqual(pause.call_count,1)
    def test_success_stops_retry_and_invalid_attempt_budget_rejected(self):
        collector=Mock(return_value={'official_dataset_usable':True});bounded_target('2026-11-11','/unused','',collector)
        self.assertEqual(collector.call_count,1)
        with self.assertRaises(ValueError):bounded_target('2026-11-11','/unused','',collector,attempts=3)
    def test_name_market_date_and_every_price_field_must_match(self):
        row=dict(ticker='000001',name='SYNTHETIC',market='KOSPI',asof='2026-11-11',open=100,high=110,low=90,close=105,volume=1000,turnover_krw=100000)
        self.assertEqual(compare([row],[row],'2026-11-11')['compared_rows'],1)
        for key in ('name','market','asof','open','high','low','close','volume','turnover_krw'):
            other=dict(row);other[key]=other[key]+1 if isinstance(other[key],int) else 'DIFFERENT'
            with self.assertRaises(ValueError):compare([row],[other],'2026-11-11')
        self.assertEqual(normalized_hash([row]),normalized_hash([dict(row)]))
    def test_kosdaq_global_is_kept_konex_excluded_duplicates_rejected(self):
        header='Code,Name,Market,MarketId,Open,High,Low,Close,Volume,Amount\n'
        raw=(header+'000001,SYNTHETIC,KOSDAQ GLOBAL,KSQ,10,11,9,10,100,1000\n000002,SYNTHETIC,KONEX,KNX,10,11,9,10,100,1000\n').encode()
        rows,excluded=cache_rows(raw,'2026-11-11');self.assertEqual(len(rows),1);self.assertEqual(rows[0]['market'],'KOSDAQ');self.assertEqual(excluded,{'KONEX':1})
        with self.assertRaises(ValueError):cache_rows(raw+raw.split(b'\n')[1]+b'\n','2026-11-11')


def payload(receipt='20260814000001',division='CFS'):
    common=dict(rcept_no=receipt,bsns_year='2026',reprt_code='11012',fs_div=division,currency='KRW')
    vals=[('IS','ifrs-full_Revenue',100,80),('IS','dart_OperatingIncomeLoss',20,10),
          ('BS','ifrs-full_Assets',1000,None),('BS','ifrs-full_Liabilities',400,None),
          ('BS','ifrs-full_Equity',600,None),('CF','ifrs-full_CashFlowsFromUsedInOperatingActivities',30,None)]
    return dict(status='000',list=[dict(common,sj_div=s,account_id=k,thstrm_amount=str(v),frmtrm_q_amount=str(prev) if prev else '') for s,k,v,prev in vals])


class FinancialAndGeometryTests(unittest.TestCase):
    def test_same_date_snapshot_reuse_preserves_receipt_clock_and_rejects_other_day(self):
        import hashlib
        c={'asof':'2026-11-11','rows':[{'ticker':'000001','name':'SYNTHETIC'}]}
        q={'schema':'C3_COMPANY_QUALITY_FACTS_V1','asof':'2026-11-11','collected_at':'2026-11-12T00:27:00Z','original_document_pit_verified':False,'companies':[{'ticker':'000001','name':'SYNTHETIC'}]}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp,'facts.json');p.write_bytes(canonical(q));sha=hashlib.sha256(p.read_bytes()).hexdigest()
            r=reuse_evidence(p,sha,c);self.assertEqual(r['collected_at'],q['collected_at']);self.assertEqual(r['new_api_request_count'],0)
            with self.assertRaisesRegex(ValueError,'HASH'):reuse_evidence(p,'0'*64,c)
            c['asof']='2026-11-12'
            with self.assertRaisesRegex(ValueError,'DATE_OR_UNIVERSE'):reuse_evidence(p,sha,c)
    def test_cold_company_mapping_precedes_the_financial_budget(self):
        events=[];client=Mock(calls=0,audit=[])
        client.get.return_value={'status':'000','list':[]}
        def mapping():events.append('mapping');return {'000001':'00000001'}
        def budget(*a,**kw):events.append('financial_budget');return client
        with patch('c3_report_context.DartClient.mapping',side_effect=mapping),patch('c3_company_quality_review_v1.BudgetClient',side_effect=budget):
            result=collect({'asof':'2026-11-11','rows':[{'ticker':'000001','name':'SYNTHETIC'}]},key='SYNTHETIC')
        self.assertEqual(events,['mapping','financial_budget'])
        self.assertFalse(result['original_document_pit_verified'])
    def test_actual_period_division_currency_and_receipt_required(self):
        filing=dict(receipt_no='20260814000001',published_on='2026-08-14')
        facts=statement_facts(payload(),filing,'CFS',2026,'11012')
        self.assertEqual(facts['revenue_krw'],100);self.assertEqual(facts['operating_cashflow_ytd_krw'],30)
        for key,value in [('rcept_no','20261112000001'),('currency','USD'),('fs_div','OFS'),('bsns_year','2025'),('reprt_code','11011')]:
            p=payload();p['list'][0][key]=value
            with self.assertRaises(ValueError):statement_facts(p,filing,'CFS',2026,'11012')
    def test_snapshot_is_never_original_pit_or_buy_approval(self):
        e=dict(price_asof='2026-11-11',reviewed_technical_tickers=149,new_research_top2=[{'ticker':'000001'}])
        q=dict(asof='2026-11-11',companies=[dict(ticker='000001',status='DATED_MATCHING_RECEIPT_SNAPSHOT_NOT_PIT_VERIFIED',latest_statement={})])
        r=join_quality(e,q);self.assertEqual(r['final_top2'],[]);self.assertFalse(r['buy_approved']);self.assertIsNone(r['final_candidate_count'])
        q['asof']='2026-11-12'
        with self.assertRaises(ValueError):join_quality(e,q)
    def test_geometry_reports_all_reasons_and_preserves_original_prices(self):
        p=dict(low=59400,high=62600,stop=56100,resistance=67700,risk_pct=10.383,net_r1_rr=.6489)
        before=copy.deepcopy(p);reasons=all_geometry_reasons(p,66400)
        self.assertIn('STRUCTURE_STOP_TOO_FAR',reasons);self.assertIn('FIRST_RESISTANCE_REWARD_TOO_SMALL',reasons)
        self.assertFalse(usable(p,66400)[0]);self.assertEqual(p,before)
        p=dict(low=118000,high=122000,stop=113800,resistance=None,risk_pct=6.72,net_r1_rr=None)
        r=all_geometry_reasons(p,204000)
        self.assertIn('MISSING_FINITE_R1_OR_GEOMETRY',r);self.assertIn('STALE_ENTRY_TOO_FAR_BELOW_CLOSE',r)


class MorningStatusTests(unittest.TestCase):
    def test_research_only_png_retains_current_source_identity_without_approved_registration(self):
        source=dict(requested_day='2026-11-12',status='OFFICIAL_CACHE_MATCHED',ready=True,research_ready=True,
            source_run_id='123456',normalized_rows_sha256='a'*64)
        research=dict(source_date='2026-11-12',source_run_id='123456',source_hash='b'*64,
            normalized_rows_sha256='a'*64,buy_approved=False,selection_status='RESEARCH_ANALYSIS_COMPLETE',
            final_research_top2=[],funnel={'analysis_eligible':3,'technical':2,'practical_entry_pass':0})
        research['report_payload_sha256']=digest(canonical(research));r=packet(source,research=research)
        self.assertEqual(r['source_run_id'],'123456');self.assertIsNone(r['approved_original_source_run_id'])
        self.assertFalse(r['analysis_completed']);self.assertFalse(r['buy_approved'])
        gh=Mock()
        with tempfile.TemporaryDirectory() as root:
            path=render(r,root);validate_image(path,r)
            from PIL import Image
            with Image.open(path) as im:self.assertEqual(json.loads(im.info['source_run_id']),'123456')
            self.assertEqual(finish_delivery(r,path,gh)['status'],'DEFERRED_SOURCE_OR_REGISTRATION_NOT_READY')
        gh.assert_not_called()
    def fixture(self):
        s=dict(schema='C3_MORNING_OFFICIAL_SOURCE_V1',requested_day='2026-11-11',status='OFFICIAL_CACHE_MATCHED',ready=True,regular_only_certified=False,compared_rows=2769)
        e=dict(price_asof='2026-11-11',full_market_price_rows=2769,source_proof_sha256=digest(canonical(s)+b'\n'),original_frozen_decision_payload_sha256='a'*64,original_source_validation_sha256='b'*64,original_source_run_id='SYNTHETIC',reviewed_technical_tickers=149,analysis_eligible=1988,stock_preselector_count=149,original_b_filter_count=50,eligible_entry_feasible_tickers=0)
        return s,e
    def test_zero_research_candidates_is_not_final_zero_under_uncertified_data(self):
        s,e=self.fixture();r=packet(s,e)
        self.assertTrue(r['analysis_completed']);self.assertIsNone(r['final_candidate_count']);self.assertEqual(r['final_top2'],[])
        self.assertEqual(r['geometry_research_pass_count'],0);self.assertFalse(r['buy_approved'])
    def test_other_run_or_missing_analysis_does_not_publish_old_candidates(self):
        s,e=self.fixture();e['source_proof_sha256']='0'*64
        r=packet(s,e);self.assertFalse(r['analysis_completed']);self.assertEqual(r['scope'],{});self.assertIsNone(r['geometry_research_pass_count'])
    def test_real_png_preserves_trace_and_rejects_changed_day_before_delivery(self):
        s,e=self.fixture();r=packet(s,e)
        with tempfile.TemporaryDirectory() as tmp:
            path=render(r,tmp);validate_image(path,r)
            r['asof']='2026-11-12'
            with self.assertRaisesRegex(ValueError,'LINEAGE'):validate_image(path,r)
    def test_prepared_delivery_uses_exact_completed_image_bytes(self):
        s,e=self.fixture();r=packet(s,e)
        with tempfile.TemporaryDirectory() as tmp:
            p=render(r,Path(tmp,'render'));j=Path(tmp,'report.json');j.write_bytes(canonical(r))
            restored,target=prepared_image(s,e,None,j,p,Path(tmp,'send'))
            self.assertEqual(target.read_bytes(),p.read_bytes())
            p.write_bytes(p.read_bytes()+b'TAMPERED')
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):prepared_image(s,e,None,j,p,Path(tmp,'send2'))
    def test_existing_date_delivery_stops_before_any_telegram_request(self):
        s,e=self.fixture();r=packet(s,e);gh=Mock();bot=Mock(fingerprint='a'*16)
        with tempfile.TemporaryDirectory() as tmp:
            image=render(r,tmp)
            with patch('c3_morning_final_v1.delivery_preflight',return_value={'status':'DUPLICATE_BLOCKED','send_attempts':0}):
                answer=finish_delivery(r,image,gh,True,bot)
            self.assertEqual(answer['status'],'DUPLICATE_BLOCKED');bot.verify_group.assert_not_called();bot.send_album.assert_not_called()
    def test_publisher_only_appends_derived_morning_paths(self):
        s,e=self.fixture();gh=Mock();gh.head.return_value='a'*40
        gh.api.side_effect=[{'tree':{'sha':'b'*40}},{'sha':'c'*40},{'sha':'d'*40},{}]
        with patch('c3_report_handoff.active_research',return_value=[]):r=publish(gh,packet(s,e))
        self.assertEqual(r['status'],'PUBLISHED_DERIVED_ONLY')
        tree=gh.api.call_args_list[1].kwargs['payload']['tree']
        self.assertTrue(all(x['path'].startswith('reports/c3_morning_v1/') for x in tree))
        self.assertFalse(gh.api.call_args_list[-1].kwargs['payload']['force'])


if __name__=='__main__':unittest.main()


class QualityGateSnapshotTests(unittest.TestCase):
    def test_missing_evidence_never_becomes_company_failure(self):
        from c3_company_quality_review_v1 import quality_gate_snapshot
        result=quality_gate_snapshot({'ticker':'119500','status':'NO_CORPORATION_MAPPING'})
        self.assertEqual(result['status'],'QUALITY_UNVERIFIED')
        self.assertFalse(result['entry_quality_eligible'])
        self.assertFalse(result['buy_approved'])

    def test_positive_but_declining_company_is_not_strong(self):
        from c3_company_quality_review_v1 import quality_gate_snapshot
        facts=dict(revenue_krw=100,operating_profit_krw=5,assets_krw=200,
                   liabilities_krw=40,equity_krw=160,operating_cashflow_ytd_krw=3,
                   previous_comparable_revenue_krw=120,previous_comparable_operating_profit_krw=8)
        result=quality_gate_snapshot(dict(ticker='119500',
            status='DATED_MATCHING_RECEIPT_SNAPSHOT_NOT_PIT_VERIFIED',
            latest_statement=facts))
        self.assertEqual(result['status'],'QUALITY_DECLINING_REVIEW')
        self.assertFalse(result['entry_quality_eligible'])

    def test_growth_snapshot_still_not_buy_or_pit_certified(self):
        from c3_company_quality_review_v1 import quality_gate_snapshot
        facts=dict(revenue_krw=100,operating_profit_krw=10,assets_krw=200,
                   liabilities_krw=40,equity_krw=160,operating_cashflow_ytd_krw=7,
                   previous_comparable_revenue_krw=80,previous_comparable_operating_profit_krw=5)
        result=quality_gate_snapshot(dict(ticker='000001',
            status='DATED_MATCHING_RECEIPT_SNAPSHOT_NOT_PIT_VERIFIED',
            latest_statement=facts))
        self.assertEqual(result['status'],'QUALITY_STRONG')
        self.assertFalse(result['entry_quality_eligible'])
        self.assertFalse(result['original_document_pit_verified'])


    def test_quality_strong_is_only_descriptive_not_approved(self):
        from c3_company_quality_review_v1 import quality_gate_snapshot
        facts=dict(revenue_krw=100,operating_profit_krw=10,assets_krw=200,
                   liabilities_krw=40,equity_krw=160,operating_cashflow_ytd_krw=7,
                   previous_comparable_revenue_krw=80,previous_comparable_operating_profit_krw=5)
        result=quality_gate_snapshot(dict(ticker='000001',
            status='DATED_MATCHING_RECEIPT_SNAPSHOT_NOT_PIT_VERIFIED',
            latest_statement=facts))
        self.assertFalse(result['entry_quality_eligible'])

    def test_no_comparable_period_does_not_claim_growth(self):
        from c3_company_quality_review_v1 import quality_gate_snapshot
        facts=dict(revenue_krw=100,operating_profit_krw=10,assets_krw=200,
                   liabilities_krw=40,equity_krw=160,operating_cashflow_ytd_krw=7)
        result=quality_gate_snapshot(dict(ticker='000001',
            status='DATED_MATCHING_RECEIPT_SNAPSHOT_NOT_PIT_VERIFIED',
            latest_statement=facts))
        self.assertEqual(result['status'],'QUALITY_UNVERIFIED')
        self.assertIn('COMPARABLE_PERIOD_VALUES_MISSING',result['reason_codes'])

    def test_inconsistent_balance_sheet_is_unverified(self):
        from c3_company_quality_review_v1 import quality_gate_snapshot
        facts=dict(revenue_krw=100,operating_profit_krw=10,assets_krw=200,
                   liabilities_krw=40,equity_krw=100,operating_cashflow_ytd_krw=7)
        result=quality_gate_snapshot(dict(ticker='000001',
            status='DATED_MATCHING_RECEIPT_SNAPSHOT_NOT_PIT_VERIFIED',
            latest_statement=facts))
        self.assertEqual(result['status'],'QUALITY_UNVERIFIED')
