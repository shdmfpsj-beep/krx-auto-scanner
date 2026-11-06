import hashlib,io,json,subprocess,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from c3_artifact_audit_v18 import Resolver,SourceUnavailable,safe_archive
from c3_data_audit_v18 import comparison,census
from c3_fast_ops_v18 import cached_current,bounded_collect,optional_scanner

DAY='2026-11-06';RUN=39923708922


def row(t='000001',m='KOSPI'):
    return dict(ticker=t,market=m,asof=DAY,open=100,high=110,low=90,close=105,volume=10,turnover_krw=1000)


class ArtifactTests(unittest.TestCase):
    def resolver(self,files=None,expired=False,inventory=None,run_extra=None):
        files=files or {'status.json':json.dumps(dict(market_data_date=DAY,scan_complete=True,data_date_verified=True)).encode(),'candidates.csv':b'ticker\n000001\n','candidate_daily_history_v52.csv':b'ticker,date\n000001,2026-11-06\n'}
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            for n,data in files.items():z.writestr(n,data)
        body=b.getvalue();meta=dict(id=123,name='renamed-source-package',size_in_bytes=len(body),expired=expired,digest='sha256:'+hashlib.sha256(body).hexdigest(),workflow_run={'id':RUN})
        def reader(path):
            if '/artifacts?' in path:return dict(artifacts=inventory if inventory is not None else [meta])
            return dict(dict(id=RUN,path='.github/workflows/krx_recovery_scan.yml',status='completed',conclusion='success',head_branch='main'),**(run_extra or {}))
        return Resolver(reader,lambda i:body),files,meta

    def manifest(self,files):
        return dict(asof=DAY,source_run_ids={'recovery_run_id':str(RUN)},source_sha256={'recovery_status':hashlib.sha256(files['status.json']).hexdigest(),'recovery_history':hashlib.sha256(files['candidate_daily_history_v52.csv']).hexdigest()})

    def test_renamed_artifact_recovered_by_content_with_exact_hashes(self):
        r,f,_=self.resolver()
        with tempfile.TemporaryDirectory() as d:self.assertEqual(r.recovery(self.manifest(f),d),Path(d))
        self.assertTrue(r.events[0]['github_digest_verified'])
    def test_missing_artifact_never_downloaded(self):
        r,_,_=self.resolver(inventory=[]);r.downloader=lambda i:self.fail('must not download')
        with self.assertRaisesRegex(SourceUnavailable,'SOURCE_ARTIFACT_ABSENT'):r.download(RUN,'recovery','unused')
    def test_expired_artifact_never_downloaded(self):
        r,_,_=self.resolver(expired=True);r.downloader=lambda i:self.fail('must not download')
        with self.assertRaisesRegex(SourceUnavailable,'EXPIRED'):r.download(RUN,'recovery','unused')
    def test_wrong_run_inventory_rejected(self):
        r,_,meta=self.resolver();meta['workflow_run']['id']=RUN+1
        with self.assertRaisesRegex(ValueError,'RUN_ID_MISMATCH'):r.inventory(RUN,'recovery')
    def test_failed_source_run_rejected(self):
        r,_,_=self.resolver(run_extra={'conclusion':'failure'})
        with self.assertRaisesRegex(ValueError,'UNSUCCESSFUL'):r.inventory(RUN,'recovery')
    def test_wrong_trade_day_rejected(self):
        r,f,_=self.resolver();m=self.manifest(f);m['asof']='2026-11-05'
        with tempfile.TemporaryDirectory() as d,self.assertRaisesRegex(ValueError,'TRADE_DAY'):r.recovery(m,d)
    def test_changed_original_hash_rejected(self):
        r,f,_=self.resolver();m=self.manifest(f);m['source_sha256']['recovery_history']='0'*64
        with tempfile.TemporaryDirectory() as d,self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):r.recovery(m,d)
    def test_archive_digest_mismatch_rejected(self):
        r,_,meta=self.resolver();meta['digest']='sha256:'+'0'*64
        with tempfile.TemporaryDirectory() as d,self.assertRaisesRegex(ValueError,'DIGEST_MISMATCH'):r.download(RUN,'recovery',d)
    def test_path_traversal_rejected(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('../outside','bad')
        with self.assertRaisesRegex(ValueError,'UNSAFE'):safe_archive(b.getvalue(),{})
    def test_missing_required_member_reported(self):
        r,_,_=self.resolver(files={'unrelated.txt':b'none'})
        with tempfile.TemporaryDirectory() as d,self.assertRaisesRegex(SourceUnavailable,'REQUIRED_FILES_ABSENT'):r.download(RUN,'recovery',d)
    def test_ambiguous_inventory_not_guessed(self):
        r,_,meta=self.resolver();other=dict(meta,id=124);old=r.reader
        r.reader=lambda p:dict(artifacts=[meta,other]) if '/artifacts?' in p else old(p)
        with tempfile.TemporaryDirectory() as d,self.assertRaisesRegex(ValueError,'AMBIGUOUS_ARTIFACT_CONTENT'):r.download(RUN,'recovery',d)


class DataTests(unittest.TestCase):
    def test_matching_values_do_not_certify_regular_or_independent(self):
        q=comparison([row()],[row()],DAY)
        self.assertEqual(q['matched_rows'],1);self.assertFalse(q['regular_only_certified']);self.assertFalse(q['independent_vendor_certified'])
    def test_ohlcv_and_turnover_conflicts_remain_visible(self):
        q=comparison([row()],[dict(row(),close=106,volume=20,turnover_krw=2000)],DAY)
        self.assertEqual(q['field_mismatches'][0]['fields'],['close','volume','turnover_krw'])
    def test_wrong_price_day_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'WRONG_DATE'):comparison([row()],[dict(row(),asof='2026-11-05')],DAY)
    def test_duplicate_security_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):comparison([row(),row()],[row()],DAY)
    def test_actual_dated_census_counts_not_fixed(self):
        prices=[row(),row('000002','KOSDAQ')]
        basic=[dict(r,asof_requested=DAY,listed_date='20200101',share_kind='보통주',security_group='주권') for r in prices]
        r=census(prices,basic,DAY);self.assertTrue(r['requested_date_membership_match']);self.assertFalse(r['historical_vintage_independently_certified'])
    def test_missing_listing_exposed(self):
        basic=[dict(row(),asof_requested=DAY,listed_date='20200101',share_kind='보통주',security_group='주권')]
        self.assertEqual(census([],basic,DAY)['markets']['KOSPI']['missing'],['000001'])
    def test_future_listing_and_wrong_requested_day_rejected(self):
        basic=dict(row(),asof_requested=DAY,listed_date='20261109',share_kind='보통주',security_group='주권')
        with self.assertRaisesRegex(ValueError,'FUTURE_LISTING'):census([row()],[basic],DAY)


class FastOpsTests(unittest.TestCase):
    def test_missing_auxiliary_scanner_does_not_qualify_price_data(self):
        def absent(_):raise ValueError('NO_GENUINELY_COMPLETED_SCANNER_WITH_ARTIFACT')
        with tempfile.TemporaryDirectory() as d:
            r=optional_scanner('',d,d,absent);self.assertEqual(r['status'],'AUXILIARY_SCANNER_UNAVAILABLE')
            self.assertTrue(r['required_price_supply_not_bypassed'])
    def test_collection_deadline_records_explicit_failure(self):
        def timeout(*a,**k):raise subprocess.TimeoutExpired(a[0],k['timeout'])
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'supply.json'
            with self.assertRaisesRegex(ValueError,'BUDGET_EXCEEDED'):bounded_collect(DAY,'2026-11-05','control',d,d,p,runner=timeout)
            self.assertEqual(json.loads(Path(str(p)+'.timing.json').read_text())['status'],'PRICE_COLLECTION_BUDGET_EXCEEDED')
    def test_cached_registered_market_is_reused_without_mutation(self):
        report=dict(data_quality_state='RESEARCH_VALIDATED',source_price_asof=DAY,errors=[],source_hashes={'pipeline_code':'same'})
        records={DAY+'.json.gz':dict(asof=DAY,source={'price_basis':'UNADJUSTED_AS_TRADED'},rows={'000001':row(),'000002':row('000002','KOSDAQ')}),DAY+'.json':dict(price_asof=DAY)}
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)/'lanes/krx_unadjusted_v12'
            for folder,name in [('markets',DAY+'.json.gz'),('decisions',DAY+'.json')]:
                p=base/folder/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'unchanged')
            reader=lambda p:records[p.name]
            self.assertTrue(cached_current(report,DAY,'same',d,reader));self.assertFalse(cached_current(report,DAY,'changed',d,reader))
            records[DAY+'.json.gz']['rows']['000001']['volume']=.5
            self.assertFalse(cached_current(report,DAY,'same',d,reader))
            self.assertTrue(all(p.read_bytes()==b'unchanged' for p in base.rglob('*') if p.is_file()))


if __name__=='__main__':unittest.main()
