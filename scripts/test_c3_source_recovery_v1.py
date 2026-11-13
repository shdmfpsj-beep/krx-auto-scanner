"""Synthetic fault boundaries; actual Nov12 data is proved by Actions artifacts."""
import copy,csv,gzip,hashlib,io,json,os,tempfile,unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from c3_morning_source_v1 import execute,normalized_hash
from c3_source_recovery_v1 import validate,cache
from c3_source_recovery_analysis_v1 import load_prices,dated_snapshot,extended_history
from c3_morning_final_v1 import packet
from c3_telegram_inputs import canonical


class SourceRecovery(unittest.TestCase):
    def rows(self):
        return [dict(ticker=t,name='SYNTHETIC',market=m,asof='2026-11-12',open=100.,high=110.,low=90.,close=105.,volume=100.,turnover_krw=10000.) for t,m in [('000001','KOSPI'),('000002','KOSDAQ')]]
    def recovery(self,approved=True,available=True,indices=True):
        def collect(day,out,attempts=1):
            out=Path(out);(out/'indices').mkdir(parents=True,exist_ok=True)
            for m in ('KOSPI','KOSDAQ'):(out/'indices'/(m+'_index.csv')).write_text('date,close\n'+day+',100\n')
            return dict(asof=day,status='OFFICIAL_VERIFIED' if approved else 'SINGLE_SOURCE_UNVERIFIED' if available else 'SOURCE_UNAVAILABLE',
                research_ready=available,approved_source_ready=approved and available,indices_ready=indices,rows=2 if available else 0,markets={'KOSPI':1,'KOSDAQ':1},
                quality={},attempts=[],comparison={'compared_rows':2} if approved else {},normalized_rows_sha256=normalized_hash(self.rows()),
                data_received_at='2026-11-13T08:10:00+09:00',cache={'ref':'a'*40,'raw_sha256':'b'*64,'excluded':{'KONEX':1}},official={'raw_response_sha256':{},'response_diagnostics':[]})
        return collect
    def run_execute(self,collector,clock='2026-11-13T08:10:00+09:00'):
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'GITHUB_RUN_ID':'123456','GITHUB_OUTPUT':root+'/outputs'}),patch('c3_morning_source_v1.prior_session',return_value=dict(requested_day='2026-11-12',report_day_kst='2026-11-13',expected_entry_session='2026-11-13')):
            r=execute(root,clock=datetime.fromisoformat(clock),recover=collector)
            output=Path(root,'outputs').read_text();saved=json.loads(Path(root,'morning_source.json').read_text())
            self.assertEqual(saved,r);return r,output
    def test_ready_source_passes_real_run_identity_to_downstream(self):
        r,o=self.run_execute(self.recovery());self.assertTrue(r['ready']);self.assertIn('run_id=123456\n',o);self.assertIn('source_day=2026-11-12',o)
    def test_valid_cache_can_be_researched_without_official_approval(self):
        r,o=self.run_execute(self.recovery(False));self.assertFalse(r['ready']);self.assertTrue(r['research_ready']);self.assertEqual(r['source_status'],'SINGLE_SOURCE_UNVERIFIED')
    def test_no_data_is_never_ready(self):
        r,o=self.run_execute(self.recovery(False,False));self.assertFalse(r['ready']);self.assertFalse(r['research_ready']);self.assertEqual(r['status'],'SOURCE_UNAVAILABLE')
    def test_missing_indices_do_not_erase_collected_prices_or_approve_them(self):
        r,o=self.run_execute(self.recovery(indices=False));self.assertFalse(r['ready']);self.assertTrue(r['research_ready']);self.assertEqual(r['collected_rows'],2)
    def test_after_open_registration_guard_is_preserved(self):
        r,o=self.run_execute(self.recovery(),clock='2026-11-13T09:15:00+09:00');self.assertEqual(r['registration_window'],'CLOSED');self.assertIn('registration_window=CLOSED',o)
    def test_variable_new_day_counts_and_halt_like_zeroes(self):
        rows=self.rows();rows.append(dict(rows[1],ticker='000003',open=0,high=0,low=0,volume=0,turnover_krw=0))
        q=validate(rows,'2026-11-12');self.assertEqual(q['markets']['KOSDAQ']['rows'],2);self.assertEqual(q['markets']['KOSDAQ']['halt_like'],1)
    def test_invalid_prices_duplicates_and_wrong_date_are_rejected(self):
        for rows in [self.rows()+[self.rows()[0]],[dict(self.rows()[0],low=200),self.rows()[1]],[dict(self.rows()[0],asof='2026-11-11'),self.rows()[1]]]:
            with self.assertRaises(ValueError):validate(rows,'2026-11-12')
    def test_source_transfer_cannot_change_prices_or_date(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root);rows=self.rows();(p/'collection.json').write_text(json.dumps(dict(asof='2026-11-12',research_ready=True,normalized_rows_sha256=normalized_hash(rows),price_basis='UNADJUSTED_AS_REPORTED')))
            (p/'normalized_market.json').write_text(json.dumps(dict(asof='2026-11-12',rows=rows)))
            self.assertEqual(len(load_prices(p)[1]),2);rows[0]['close']=106
            (p/'normalized_market.json').write_text(json.dumps(dict(asof='2026-11-12',rows=rows)))
            with self.assertRaisesRegex(ValueError,'HASH'):load_prices(p)


class NewReportBoundaries(unittest.TestCase):
    def fixture(self):
        source=dict(requested_day='2026-11-12',status='OFFICIAL_CACHE_MATCHED',ready=True,research_ready=True,source_run_id='123',normalized_rows_sha256='a'*64)
        research=dict(source_date='2026-11-12',source_run_id='123',source_hash='b'*64,normalized_rows_sha256='a'*64,buy_approved=False,
            selection_status='RESEARCH_ANALYSIS_COMPLETE',final_research_top2=[],funnel={'technical':3})
        research['report_payload_sha256']=hashlib.sha256(canonical(research)).hexdigest();return source,research
    def test_current_completed_zero_is_distinct_from_missing_analysis(self):
        s,r=self.fixture();self.assertEqual(packet(s,research=r)['display_state'],'ANALYSIS_COMPLETE_CASH')
        self.assertEqual(packet(s)['display_state'],'SELECTION_INCOMPLETE')
    def test_yesterday_original_top2_never_becomes_new_top2(self):
        s,r=self.fixture();old=dict(price_asof='2026-11-11',final_top2=[{'ticker':'028050'},{'ticker':'180640'}])
        p=packet(s,entry=old);self.assertEqual(p['display_top2'],[]);self.assertFalse(p['analysis_completed'])
    def test_old_research_wrong_run_or_tampered_hash_is_blocked(self):
        for key,value in [('source_date','2026-11-11'),('source_run_id','999'),('buy_approved',True),('normalized_rows_sha256','c'*64)]:
            s,r=self.fixture();r[key]=value;v=dict(r);v.pop('report_payload_sha256');r['report_payload_sha256']=hashlib.sha256(canonical(v)).hexdigest()
            with self.assertRaises(ValueError):packet(s,research=r)
    def test_research_entry_range_cannot_authorize_buy_or_change_approved_top2(self):
        s,r=self.fixture();r['final_research_top2']=[{'ticker':'000001'}];v=dict(r);v.pop('report_payload_sha256');r['report_payload_sha256']=hashlib.sha256(canonical(v)).hexdigest()
        p=packet(s,research=r);self.assertEqual(p['display_state'],'RESEARCH_ENTRY_RANGE_UNAPPROVED');self.assertFalse(p['buy_approved']);self.assertEqual(p['final_top2'],[])
    def test_missing_company_data_is_not_completed_cash(self):
        s,r=self.fixture();r['selection_status']='RESEARCH_ANALYSIS_INCOMPLETE_FINANCIAL';v=dict(r);v.pop('report_payload_sha256');r['report_payload_sha256']=hashlib.sha256(canonical(v)).hexdigest()
        self.assertEqual(packet(s,research=r)['display_state'],'SELECTION_INCOMPLETE_COMPANY_DATA')
    def test_baseline_date_is_retained_for_approved_history_continuity(self):
        from c3_daily_research_v8 import histories
        with tempfile.TemporaryDirectory() as root:
            p=Path(root);start=datetime(2026,6,1);days=[];d=start
            while len(days)<72:
                if d.weekday()<5:days.append(d.date().isoformat())
                d+=timedelta(days=1)
            rows=[dict(ticker='000001',name='SYNTHETIC',date=day,open=100,high=110,low=90,close=105,volume=100,turnover_krw=10000) for day in days]
            panel=p/'panel.csv.gz'
            with gzip.open(panel,'wt') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows[:-2])
            audit=dict(panel_sha256=hashlib.sha256(panel.read_bytes()).hexdigest(),reference_rebase_candidates=[]);a=p/'audit.json';a.write_text(json.dumps(audit))
            base=dict(rows[-2]);base.pop('date');snap={days[-2]:dated_snapshot({'000001':base},days[-2])}
            price=dict(rows[-1],asof=days[-1]);past,_=histories(panel,a,{'000001':price},snap,days,days[-1]);extended,_=extended_history(panel,audit,{'000001':price},snap,days,days[-1])
            self.assertEqual([r['date'] for r in past['000001']],[r['date'] for r in extended['000001']]);self.assertEqual(len(past['000001']),72)


if __name__=='__main__':unittest.main()
