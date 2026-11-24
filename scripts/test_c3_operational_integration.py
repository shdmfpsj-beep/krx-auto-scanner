"""Decision coverage and real observed empty-zone regressions. No market claims."""
import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date
from c3_entry_geometry import entry_zone, executable, sanitize_archived_geometry
from c3_top5_financial_selection import select, financial_review_candidates, REVIEW_SCOPE
from c3_candidate_decisions import report, save
from c3_balanced_financials import retry_network, SnapshotCache
from datetime import datetime, timezone, timedelta
from urllib.error import URLError, HTTPError
from test_c3_top5_financial_selection import candidate, record, evidence, ASOF


class OperationalTests(unittest.TestCase):
    def test_transient_network_failure_retries_but_not_bad_evidence(self):
        calls=[]
        def transport():
            calls.append(1)
            if len(calls)<3: raise URLError('temporary')
            return 'success'
        pauses=[]
        self.assertEqual(retry_network(transport,pauses.append),'success')
        self.assertEqual(pauses,[1,2])
        def invalid(): raise ValueError('RECEIPT_MISMATCH')
        with self.assertRaises(ValueError):retry_network(invalid,pauses.append)
        def denied():raise HTTPError('redacted',403,'denied',{},None)
        with self.assertRaises(HTTPError):retry_network(denied,pauses.append)
        self.assertEqual(pauses,[1,2])

    def test_corporate_map_cache_hash_ttl_and_failure_boundaries(self):
        with TemporaryDirectory() as tmp:
            now=datetime(2026,11,24,tzinfo=timezone.utc)
            cache=SnapshotCache(tmp,clock=lambda:now)
            calls=[]
            def fetch(key):calls.append(1);return {'111111':'00000001'}
            self.assertEqual(cache.listed_corps('redacted',fetch),{'111111':'00000001'})
            self.assertEqual(cache.listed_corps('redacted',fetch),{'111111':'00000001'})
            self.assertEqual(len(calls),1)
            cache.clock=lambda:now+timedelta(days=2)
            cache.listed_corps('redacted',fetch)
            self.assertEqual(len(calls),2)
            path=Path(tmp)/'listed_corp_codes.json'
            r=json.loads(path.read_text());r['mapping']['111111']='00000002';path.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'CACHE_INTEGRITY'):
                cache.listed_corps('redacted',fetch)

    def test_observed_noncurrent_loan_bond_tags_include_current_bonds_once(self):
        import c3_balanced_financials as m
        from test_c3_balanced_financials import statement
        p=statement()
        for r in p['list']:
            if r['account_id'] in m.DEBT_IDS[2]:r['account_id']='ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived'
            if r['account_id'] in m.DEBT_IDS[3]:r['account_id']='ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued'
        self.assertIsNone(m.statement_metrics(p)['interest_bearing_debt_excluding_leases'])
        p['list'].append(dict(sj_div='BS',account_id='dart_CurrentPortionOfBonds',account_nm='유동성사채',thstrm_amount='5'))
        self.assertEqual(m.statement_metrics(p)['interest_bearing_debt_excluding_leases'],45)

    def test_uncertain_bond_overlap_and_other_borrowing_lines_stay_unverified(self):
        import c3_balanced_financials as m
        from test_c3_balanced_financials import statement
        p=statement();p['list'].append(dict(sj_div='BS',account_id='dart_CurrentPortionOfBonds',account_nm='유동성사채',thstrm_amount='5'))
        self.assertIsNone(m.statement_metrics(p)['interest_bearing_debt_excluding_leases'])
        p=statement()
        for r in p['list']:
            if r['account_id'] in m.DEBT_IDS[0]:r.update(account_id='-표준계정코드 미사용-',account_nm='단기차입금')
        p['list'].append(dict(sj_div='BS',account_id='-표준계정코드 미사용-',account_nm='자산유동화차입금',thstrm_amount='7'))
        result=m.statement_metrics(p)
        self.assertIsNone(result['interest_bearing_debt_excluding_leases'])
        self.assertEqual(result['unresolved_debt_accounts'][0]['account_name'],'자산유동화차입금')

    def test_malformed_document_notes_recover_without_certifying_xbrl(self):
        import io,zipfile
        from c3_dart_document_evidence import inspect_archive
        raw='<DOCUMENT><SECTION-2><TITLE>3. 연결재무제표 주석</TITLE><TABLE><TR><TD>이자비용<br>100</TD></TR></TABLE></SECTION-2></DOCUMENT>'
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('report.xml',raw)
        r=inspect_archive(stream.getvalue(),'CFS')
        self.assertEqual(r['state'],'SCOPED_NOTE_TABLES_LOCATED_REVIEW_REQUIRED')
        self.assertFalse(r['automatic_financial_promotion'])
        self.assertFalse(r['tables'][0]['unit_and_period_validated'])
        self.assertIn('report.xml',r['recovered_document_files'])

    def test_financial_sector_is_reviewed_before_generic_income_metrics(self):
        from c3_balanced_financials import collect_balanced
        from test_c3_balanced_financials import request
        calls=[]
        def transport(endpoint,params,key):
            calls.append(endpoint)
            if endpoint=='company.json':return dict(status='000',stock_code='111111',induty_code='651')
            if endpoint=='list.json':return request(endpoint,params,key)
            raise AssertionError('GENERAL_COMPANY_STATEMENTS_MUST_NOT_CLASSIFY_INSURER')
        with TemporaryDirectory() as tmp:
            r=collect_balanced(date(2026,11,20),[dict(ticker='111111',name='보험 검증용')],
                'a'*40,date(2026,11,20),SnapshotCache(tmp),request=transport,get_corps=lambda k:{'111111':'00000001'})
        row=r['excluded'][0]
        self.assertEqual(row['financial_verdict'],'REVIEW_REQUIRED')
        self.assertEqual(row['sector_profile'],'FINANCIAL_SPECIAL_MODEL_REQUIRED')
        self.assertEqual(row['risk_assessment']['mandatory_missing'],['SECTOR_MODEL_REQUIRED'])
        self.assertNotIn('fnlttSinglAcntAll.json',calls)

    def test_actual_airline_support_conflicts_with_ceiling(self):
        # Observed 11/23 rounded bounds: 30,350 > 30,200 and 8,180 > 8,110.
        for support, ma20, atr in ((30350, 29856, 1571.43), (8180, 8004, 460)):
            zone=entry_zone(support, ma20, atr)
            self.assertEqual(zone['rejection_reason'], 'EMPTY_ENTRY_INTERSECTION')
            self.assertIsNone(zone['entry_low'])
            self.assertIsNone(zone['entry_high'])
            self.assertGreater(zone['attempted_low'], zone['attempted_high'])
            self.assertEqual(zone['raw_stop'], support-.5*atr)

    def test_rounding_cannot_create_a_tradable_interval(self):
        zone=entry_zone(2000, 2000, 1)
        self.assertEqual(zone['rejection_reason'], 'NO_EXECUTABLE_TICK_INTERVAL')
        self.assertIsNone(zone['entry_high'])

    def test_directional_ticks_at_price_bands(self):
        for price, up, down in ((1999.1,2000,1999), (4999,5000,4995),
                                 (19999,20000,19990), (49999,50000,49950)):
            self.assertEqual(executable(price,'up'),up)
            self.assertEqual(executable(price,'down'),down)

    def test_nonpositive_stop_is_rejected_without_aborting_other_candidates(self):
        self.assertIsNone(entry_zone(100, 150, 300)['structural_stop'])

    def test_actual_workflow_requests_watch_finance_and_preserves_legacy_scope(self):
        from test_c3_top5_pipeline import PipelineTests
        t=PipelineTests(); t.setUp()
        try:
            t.write('entry_geometry_audit.json',dict(asof=ASOF,candidates=[candidate(),
                candidate('222222','WATCH',close=10300),candidate('333333',geometry_validated=False)]))
            t.write('qualified_chart_pool.json',dict(candidates=[]))
            (t.cwd/'receipts/c3_top5_daily').mkdir(parents=True)
            (t.cwd/'reports/c3_paper').mkdir(parents=True)
            ledger=t.cwd/'reports/c3_paper/paper_ledger.json';ledger.write_text('{"positions":{}}')
            t.env['C3_FINANCIAL_MODEL']='balanced'
            name='Evaluate dated OpenDART evidence for selected TOP5 (research only)'
            p=t.execute(name)
            self.assertEqual(p.returncode,0,p.stderr)
            x=json.loads((t.root/'financial_pool_input.json').read_text())
            self.assertEqual(len(x['candidates']),3)
            self.assertEqual(x['request_scope'],REVIEW_SCOPE)
            self.assertEqual(ledger.read_text(),'{"positions":{}}')
            t.env['C3_FINANCIAL_MODEL']='legacy'
            self.assertEqual(t.execute(name).returncode,0)
            x=json.loads((t.root/'financial_pool_input.json').read_text())
            self.assertEqual(len(x['candidates']),1)
            self.assertEqual(x['request_scope'],'EXECUTABLE_ENTRIES')
        finally:
            t.doCleanups()

    def test_valid_zone_preserves_existing_formula(self):
        z=entry_zone(9800, 10000, 400)
        self.assertEqual((z['entry_low'],z['entry_high'],z['structural_stop']), (9800,10040,9600))

    def test_archived_inversion_never_survives_as_buy_prices(self):
        c=candidate(entry_low=30350,entry_high=30200,risk_pct=1.99)
        r=sanitize_archived_geometry(c)
        self.assertIsNone(r['entry_low']); self.assertIsNone(r['risk_pct'])
        self.assertEqual(r['attempted_entry_low'],30350)
        self.assertEqual(c['entry_low'],30350)  # source remains immutable

    def test_watch_and_invalid_entries_receive_financial_review(self):
        g=dict(asof=ASOF,candidates=[candidate(),candidate('222222',geometry_validated=False),
                candidate('333333','WATCH',close=10300)])
        self.assertEqual(len(financial_review_candidates(g)),3)
        f=evidence(*(record(c['code']) for c in g['candidates']))
        f['request_scope']=REVIEW_SCOPE
        x=select(g,f)
        self.assertEqual(x['financial_requested_count'],3)
        self.assertEqual(x['financial_pass_count'],3)
        self.assertEqual(x['selected_count'],1)
        self.assertEqual(x['operational_status'],'TOP5_READY')

    def test_all_watch_pass_is_normal_cash_without_promotion(self):
        g=dict(asof=ASOF,candidates=[candidate('111111','WATCH',close=10300)])
        f=evidence(record()); f['request_scope']=REVIEW_SCOPE
        x=select(g,f)
        self.assertEqual(x['decision'],'CASH')
        self.assertEqual(x['operational_status'],'CASH_NO_ELIGIBLE')
        self.assertEqual(x['watch_count'],1)

    def test_missing_watch_evidence_is_not_empty_normal_cash(self):
        g=dict(asof=ASOF,candidates=[candidate('111111','WATCH',close=10300)])
        f=evidence(status='NO_CANDIDATES'); f['request_scope']=REVIEW_SCOPE
        x=select(g,f)
        self.assertEqual(x['decision'],'ERROR')
        self.assertEqual(x['financial_unreviewed_candidate_count'],1)

    def test_broad_review_does_not_bypass_five_percent_risk(self):
        g=dict(asof=ASOF,candidates=[candidate(stop_ref=9400,risk_pct=6,geometry_validated=False,
            rejection_reasons=['RISK_ABOVE_5PCT'])])
        f=evidence(record()); f['request_scope']=REVIEW_SCOPE
        x=select(g,f)
        self.assertEqual(x['financial_verdicts']['111111'],'PASS')
        self.assertEqual(x['selected_count'],0)

    def test_broad_review_keeps_api_budget_and_actionable_priority(self):
        g=dict(candidates=[candidate(str(100000+i),'WATCH',close=10300,opportunity_score=100)
                          for i in range(32)]+[candidate('999999')])
        pool=financial_review_candidates(g)
        self.assertEqual(len(pool),30)
        self.assertEqual(pool[0]['code'],'999999')

    def test_unreviewed_interest_budget_prevents_claim_of_complete_top5(self):
        g=dict(asof=ASOF,candidates=[candidate(str(100000+i)) for i in range(31)])
        f=evidence(*(record(c['code']) for c in financial_review_candidates(g)));f['request_scope']=REVIEW_SCOPE
        x=select(g,f)
        self.assertEqual(x['operational_status'],'HOLD_FINANCIAL_UNVERIFIED')
        self.assertEqual(x['selected_count'],0)
        self.assertEqual(x['financial_unreviewed_candidate_count'],1)

    def test_balanced_review_and_api_error_have_distinct_outcomes(self):
        g=dict(asof=ASOF,candidates=[candidate()])
        for verdict, expected in [('REVIEW_REQUIRED','HOLD_FINANCIAL_UNVERIFIED'),('ERROR','ERROR')]:
            f=evidence(record(financial_model='BALANCED_QUALITY_TIMING_V1',financial_verdict=verdict),
                       status='REVIEW_REQUIRED' if verdict=='REVIEW_REQUIRED' else 'ERROR')
            f.update(model='BALANCED_QUALITY_TIMING_V1',request_scope=REVIEW_SCOPE)
            self.assertEqual(select(g,f)['operational_status'],expected)

    def test_report_separates_finance_from_entry_and_persists_reasons(self):
        c=candidate(geometry_validated=False,rejection_reasons=['RISK_ABOVE_5PCT'],risk_pct=6)
        g=dict(asof=ASOF,candidates=[c]); f=evidence(record()); f['request_scope']=REVIEW_SCOPE
        x=select(g,f)
        r=report(dict(source_integrity={}),g,x,f)
        self.assertEqual(r['summary']['financial_decisions']['PASS'],1)
        self.assertEqual(r['summary']['risk_above_5pct'],1)
        self.assertEqual(r['candidates'][0]['status'],'REJECTED')
        self.assertIsNone(r['candidates'][0]['entry_low'])
        with TemporaryDirectory() as tmp:
            save(Path(tmp),r)
            self.assertEqual(json.loads((Path(tmp)/'candidate_decisions.json').read_text()),r)
            self.assertIn('RISK_ABOVE_5PCT',(Path(tmp)/'candidate_decisions.csv').read_text('utf-8-sig'))


def positive_fixture(out):
    """Retain the existing real renderer/manifest/no-network delivery test outputs.

    All input prices and financial statements below are SYNTHETIC fixtures.
    """
    from unittest.mock import patch
    from test_c3_top5_pipeline import PipelineTests
    from test_c3_balanced_financials import request
    from c3_balanced_financials import collect_balanced, SnapshotCache, MODEL
    from c3_balanced_validation import run, verify_images, write
    t=PipelineTests(); t.setUp()
    try:
        pool,_=t.prepare(count=5)
        pool['fixture_kind']='SYNTHETIC_NOT_MARKET_SELECTION'
        t.write('qualified_chart_pool.json',pool)
        with TemporaryDirectory() as cache:
            f=collect_balanced(date(2026,11,20),[{'ticker':'111111','name':'합성 검증용'}],
                'a'*40,date(2026,11,20),SnapshotCache(cache),request=request,get_corps=lambda k:{'111111':'00000001'})
            item=f['researched'][0]
            f['researched']=[{**copy.deepcopy(item),'ticker':c['code']} for c in pool['candidates']]
            f.update(model=MODEL,request_scope=REVIEW_SCOPE,fixture_kind='SYNTHETIC_NOT_MARKET_SELECTION')
            geometry=dict(asof=ASOF,entry_valid_until=pool['entry_valid_until'],
                          candidates=[candidate(c['code'],name='검증용') for c in pool['candidates']])
            t.write('entry_geometry_audit.json',geometry)
            with patch('c3_balanced_validation.collect_balanced',return_value=f):
                result=run(out,Path(cache),source=t.root)
        assert result['status']=='COMPLETE' and len(result['selected_codes'])==5,result
        assert result['input_kind']=='SYNTHETIC_NOT_MARKET_SELECTION' and not result['live_dart_observation']
        assert result['delivery_status']=='DRY_RUN' and result['telegram_photos_sent']==0
        r=json.loads((out/'all_candidate_report/manifest.json').read_text())
        assert verify_images(out,r)==5
        assert not (out/'delivery_boundary/receipts').exists()
        write(out/'positive_fixture_result.json',dict(status='PASS',input_kind='SYNTHETIC_NOT_MARKET_SELECTION',
            model=MODEL,selected=5,png=5,png_hash_and_metadata_verified=True,csv_json_png_values_verified=True,
            telegram_status='DRY_RUN',telegram_photos_sent=0,receipts_created=False))
    finally:
        t.doCleanups()


if __name__ == '__main__':
    import sys
    if len(sys.argv)==3 and sys.argv[1]=='--write-positive-fixture':
        positive_fixture(Path(sys.argv[2]))
    else:
        unittest.main()
