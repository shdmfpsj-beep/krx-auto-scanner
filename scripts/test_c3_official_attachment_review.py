"""Official linked sections are captured as evidence, never treated as a pass."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from c3_official_attachment_review import sections, capture

RECEIPT='20260326000001'


def viewer(receipt=RECEIPT,**changes):
    fields=dict(text='정 정 신 고 (보고)',rcpNo=receipt,dcmNo='12345678',eleId='1',offset='658',length='5120',dtd='dart4.xsd')
    fields.update(changes)
    return 'var node1 = {};'+''.join(f'node1[\'{k}\'] = "{v}";' for k,v in fields.items())+'treeData.push(node1);'


class AttachmentReviewTests(unittest.TestCase):
    def test_public_url_parameters_are_read_from_observed_filing_nodes(self):
        r=sections(viewer(),RECEIPT)
        self.assertEqual(len(r),1);self.assertEqual(r[0]['dcmNo'],'12345678')

    def test_wrong_receipt_external_schema_bad_numbers_or_duplicate_nodes_block(self):
        for body in [viewer(receipt='20260327000001'),viewer(dtd='https://outside.invalid/schema'),viewer(offset='bad'),viewer()+viewer()]:
            with self.assertRaises(ValueError):sections(body,RECEIPT)

    def test_missing_node_metadata_is_not_guessed(self):
        with self.assertRaises(ValueError):sections(viewer().replace('node1[\'eleId\'] = "1";',''),RECEIPT)

    def test_verified_source_capture_is_not_a_financial_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);source=p/'viewer.html';source.write_text(viewer());urls=[]
            def fetch(url):urls.append(url);return '<html><body>정정된 공식 첨부 내용 원문 검토용 자료입니다.</body></html>'.encode()
            r=capture(source,hashlib.sha256(source.read_bytes()).hexdigest(),RECEIPT,'20261124',p/'out',fetch)
            self.assertEqual(len(urls),1);self.assertTrue(urls[0].startswith('https://dart.fss.or.kr/report/viewer.do?'))
            self.assertFalse(r['qualification_use']);self.assertFalse(r['trade_approved'])
            row=r['sections'][0];self.assertEqual(hashlib.sha256((p/'out'/row['file']).read_bytes()).hexdigest(),row['sha256'])

    def test_source_hash_mismatch_or_future_filing_never_downloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);source=p/'viewer.html';source.write_text(viewer())
            for sha,day in [('bad','20261124'),(hashlib.sha256(source.read_bytes()).hexdigest(),'20260320')]:
                with self.assertRaises(ValueError):capture(source,sha,RECEIPT,day,p/'out',lambda url:self.fail('network called'))

    def test_error_does_not_expose_credentials_or_claim_a_valid_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);source=p/'viewer.html';source.write_text(viewer())
            def fetch(url):raise ValueError('PRIVATE_SECRET')
            r=capture(source,hashlib.sha256(source.read_bytes()).hexdigest(),RECEIPT,'20261124',p/'out',fetch)
            self.assertEqual(r['sections'][0]['state'],'ERROR');self.assertNotIn('PRIVATE_SECRET',json.dumps(r))


if __name__=='__main__':unittest.main()
