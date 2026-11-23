"""Official note discovery is scoped evidence, never an automatic risk waiver."""
import io
import json
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from c3_dart_document_evidence import inspect_archive, probe


def zipped(xml):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive:archive.writestr('filing.xml',xml)
    return buffer.getvalue()


XML='''<DOCUMENT><SECTION-2><TITLE>3. 연결재무제표 주석</TITLE>
<TABLE><TR><TH>단기차입금</TH><TH>당기</TH></TR><TR><TD>은행</TD><TD>100</TD></TR></TABLE>
</SECTION-2><SECTION-2><TITLE>5. 재무제표 주석</TITLE>
<TABLE><TR><TH>단기차입금</TH><TH>당기</TH></TR><TR><TD>은행</TD><TD>999</TD></TR></TABLE>
</SECTION-2></DOCUMENT>'''


class DocumentEvidenceTests(unittest.TestCase):
    def test_connected_and_separate_note_tables_are_never_mixed(self):
        cfs=inspect_archive(zipped(XML),'CFS');ofs=inspect_archive(zipped(XML),'OFS')
        self.assertTrue(cfs['scope_verified'])
        self.assertIn('100',json.dumps(cfs))
        self.assertNotIn('999',json.dumps(cfs))
        self.assertIn('999',json.dumps(ofs))
        self.assertFalse(cfs['automatic_financial_promotion'])
        self.assertFalse(cfs['tables'][0]['unit_and_period_validated'])

    def test_multiple_same_scope_sections_are_not_merged(self):
        # A valid document with two CFS sections is ambiguous.
        extra=XML.replace('</DOCUMENT>','<SECTION-2><TITLE>연결재무제표 주석</TITLE></SECTION-2></DOCUMENT>')
        r=inspect_archive(zipped(extra),'CFS')
        self.assertFalse(r['scope_verified'])
        self.assertEqual(r['tables'],[])

    def test_api_status_xml_is_not_a_note_archive(self):
        r=inspect_archive(b'<result><status>013</status></result>','CFS')
        self.assertEqual(r['state'],'API_UNAVAILABLE')
        self.assertEqual(r['api_status'],'013')

    def test_external_entities_are_not_processed(self):
        xml='<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><DOCUMENT>&e;</DOCUMENT>'
        r=inspect_archive(zipped(xml),'CFS')
        self.assertFalse(r['scope_verified'])
        self.assertEqual(r['tables'],[])

    def test_official_external_dtd_is_removed_without_fetching_it(self):
        xml='<!DOCTYPE DOCUMENT SYSTEM "https://example.invalid/report.dtd">'+XML
        self.assertTrue(inspect_archive(zipped(xml),'CFS')['scope_verified'])

    def test_future_receipt_blocks_download(self):
        def forbidden(*a):self.fail('network called')
        with tempfile.TemporaryDirectory() as tmp:
            r=probe('20261123000001','11011','CFS',date(2026,11,20),'a'*40,Path(tmp),forbidden)
        self.assertEqual(r['state'],'ERROR')
        self.assertEqual(r['error'],'DOCUMENT_AFTER_SIGNAL_DATE')

    def test_document_route_records_sha_and_stops_when_scoped_notes_found(self):
        calls=[]
        def download(*args):calls.append(args[0]);return zipped(XML)
        with tempfile.TemporaryDirectory() as tmp:
            r=probe('20260320000001','11011','CFS',date(2026,11,20),'a'*40,Path(tmp),download)
            self.assertTrue((Path(tmp)/r['routes'][0]['file']).is_file())
        self.assertEqual(calls,['document.xml'])
        self.assertEqual(len(r['routes'][0]['sha256']),64)
        self.assertEqual(r['state'],'EVIDENCE_LOCATED_REVIEW_REQUIRED')
        self.assertFalse(r['automatic_financial_promotion'])

    def test_transport_errors_never_expose_authenticated_url(self):
        def download(*args):raise TimeoutError('crtfc_key=PRIVATE')
        with tempfile.TemporaryDirectory() as tmp:
            r=probe('20260320000001','11011','CFS',date(2026,11,20),'a'*40,Path(tmp),download)
        self.assertNotIn('PRIVATE',json.dumps(r))
        self.assertEqual([x['state'] for x in r['routes']],['ERROR','ERROR'])


if __name__=='__main__':unittest.main()
