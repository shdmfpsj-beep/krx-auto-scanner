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
    import shutil, subprocess, sys
    from test_c3_top5_pipeline import PipelineTests, BUILD, DELIVERY, REPO
    from test_c3_balanced_financials import request
    from c3_balanced_financials import collect_balanced, SnapshotCache, MODEL
    from c3_balanced_validation import verify_images, write
    t=PipelineTests(); t.setUp()
    try:
        pool,_=t.prepare(count=5)
        with TemporaryDirectory() as cache:
            f=collect_balanced(date(2026,11,20),[{'ticker':'111111','name':'합성 검증용'}],
                'a'*40,date(2026,11,20),SnapshotCache(cache),request=request,get_corps=lambda k:{'111111':'00000001'})
        item=f['researched'][0]
        f['researched']=[{**copy.deepcopy(item),'ticker':c['code']} for c in pool['candidates']]
        f.update(model=MODEL,request_scope=REVIEW_SCOPE,fixture_kind='SYNTHETIC_NOT_MARKET_SELECTION')
        geometry=dict(asof=ASOF,candidates=[candidate(c['code'],name='검증용') for c in pool['candidates']])
        selection=select(geometry,f)
        assert selection['selected_count']==5
        t.write('financial_pool_gate.json',f); t.write('financial_selection_research.json',selection)
        p=subprocess.run([sys.executable,str(REPO/'scripts/c3_all_candidate_report.py'),
            '--pool',str(t.root/'qualified_chart_pool.json'),'--selection',str(t.root/'financial_selection_research.json'),
            '--financial',str(t.root/'financial_pool_gate.json'),'--out',str(t.root/'all_candidate_report')],
            env=t.env,capture_output=True,text=True)
        assert p.returncode==0,p.stderr
        assert t.execute(BUILD).returncode==0
        assert t.execute(DELIVERY).returncode==0
        assert t.result()['status']=='DRY_RUN' and t.result()['telegram_photos_sent']==0
        r=json.loads((t.root/'all_candidate_report/manifest.json').read_text())
        assert verify_images(t.root,r)==5
        assert not (t.cwd/'receipts').exists()
        shutil.copytree(t.root,out,dirs_exist_ok=True)
        write(out/'positive_fixture_result.json',dict(status='PASS',input_kind='SYNTHETIC_NOT_MARKET_SELECTION',
            model=MODEL,selected=5,png=5,png_hash_and_metadata_verified=True,
            telegram_status='DRY_RUN',telegram_photos_sent=0,receipts_created=False))
    finally:
        t.doCleanups()


if __name__ == '__main__':
    import sys
    if len(sys.argv)==3 and sys.argv[1]=='--write-positive-fixture':
        positive_fixture(Path(sys.argv[2]))
    else:
        unittest.main()
