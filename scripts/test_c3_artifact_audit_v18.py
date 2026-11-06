import hashlib,io,json,subprocess,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from c3_artifact_audit_v18 import Resolver,SourceUnavailable,safe_archive

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


if __name__=="__main__":unittest.main()
