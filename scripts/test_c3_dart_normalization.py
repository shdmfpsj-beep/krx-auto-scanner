"""Source identity, exact units, observation isolation and financial recovery."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from c3_balanced_financials import SnapshotCache
from c3_balanced_source_probe import DocumentCache


class SourceRecoveryTests(unittest.TestCase):
    def test_live_catalogue_observations_are_reused_only_in_same_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=SnapshotCache(tmp);cache.session_id='run-a';calls=[]
            def request(*args):calls.append(1);return dict(status='000',list=[])
            cache.request('list.json',{'corp_code':'12345678'},'private-secret',request)
            cache.observed_or_request('list.json',{'corp_code':'12345678'},'private-secret',request)
            self.assertEqual(len(calls),1)
            other=SnapshotCache(tmp);other.session_id='run-b'
            other.observed_or_request('list.json',{'corp_code':'12345678'},'private-secret',request)
            self.assertEqual(len(calls),2)
            for file in Path(tmp).rglob('*.json'):self.assertNotIn('private-secret',file.read_text())

    def test_same_run_observation_tampering_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=SnapshotCache(tmp)
            cache.request('company.json',{},'key',lambda *a:dict(status='000'))
            file=next((Path(tmp)/'observations').rglob('*.json'))
            r=json.loads(file.read_text());r['payload']['status']='999';file.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'OBSERVATION_INTEGRITY'):
                cache.observed_or_request('company.json',{},'key',lambda *a:self.fail('network'))

    def test_document_unavailable_is_not_cached_as_a_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=DocumentCache(tmp);calls=[]
            def fetch(*a):calls.append(1);return b'<result><status>014</status></result>'
            for _ in range(2):cache.get('document.xml','20260318000849','11011','key',fetch)
            self.assertEqual(len(calls),2)
            self.assertEqual(list(Path(tmp).glob('*.json')),[])

    def test_document_cache_hash_and_receipt_are_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=DocumentCache(tmp);buf=io.BytesIO()
            with zipfile.ZipFile(buf,'w') as z:z.writestr('report.xml','<DOCUMENT/>')
            cache.get('document.xml','20260318000849','11011','key',lambda *a:buf.getvalue())
            cached=cache.get('document.xml','20260318000849','11011','key',lambda *a:self.fail('network'))
            self.assertEqual(cached,buf.getvalue())
            next(Path(tmp).glob('*.zip')).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'CACHE_INTEGRITY'):
                cache.get('document.xml','20260318000849','11011','key')


if __name__=='__main__':unittest.main()
