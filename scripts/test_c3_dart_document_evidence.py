"""Official note discovery is scoped evidence, never an automatic risk waiver."""
import io
import json
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from c3_dart_document_evidence import inspect_archive, probe, xbrl_facts
from xml.etree import ElementTree as ET


def zipped(xml):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive:archive.writestr('filing.xml',xml)
    return buffer.getvalue()


XML='''<DOCUMENT><SECTION-2><TITLE>3. 연결재무제표 주석</TITLE>
<TABLE><TR><TH>단기차입금</TH><TH>당기</TH></TR><TR><TD>은행</TD><TD>100</TD></TR></TABLE>
</SECTION-2><SECTION-2><TITLE>5. 재무제표 주석</TITLE>
<TABLE><TR><TH>단기차입금</TH><TH>당기</TH></TR><TR><TD>은행</TD><TD>999</TD></TR></TABLE>
</SECTION-2></DOCUMENT>'''


def xbrl_example(member='ConsolidatedMember',year=2025,entity='00111111',unit='KRW'):
    return ET.fromstring(f'''<x:xbrl xmlns:x="http://www.xbrl.org/2003/instance"
        xmlns:d="http://xbrl.org/2006/xbrldi" xmlns:f="http://example.test/ifrs-full">
      <x:unit id="money"><x:measure>iso4217:{unit}</x:measure></x:unit>
      <x:context id="now"><x:entity><x:identifier>{entity}</x:identifier><x:segment>
        <d:explicitMember dimension="ifrs-full:ConsolidatedAndSeparateFinancialStatementsAxis">ifrs-full:{member}</d:explicitMember>
      </x:segment></x:entity><x:period><x:instant>{year}-12-31</x:instant></x:period></x:context>
      <f:Assets contextRef="now" unitRef="money">250</f:Assets>
      <f:Liabilities contextRef="now" unitRef="money">100</f:Liabilities>
      <f:Equity contextRef="now" unitRef="money">150</f:Equity>
      <f:CashAndCashEquivalents contextRef="now" unitRef="money">40</f:CashAndCashEquivalents>
      <f:OtherBorrowings contextRef="now" unitRef="money">40</f:OtherBorrowings>
      <f:BondsIssued contextRef="now" unitRef="money">60</f:BondsIssued>
    </x:xbrl>''')


REFERENCES={'Assets':250,'Liabilities':100,'Equity':150}


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

    def test_api_limit_is_error_not_missing_optional_document(self):
        self.assertEqual(inspect_archive(b'<result><status>020</status></result>','CFS')['state'],'ERROR')

    def test_xbrl_exact_scope_period_currency_and_reference_anchors(self):
        r=xbrl_facts(xbrl_example(),'CFS',2025,'00111111',REFERENCES)
        self.assertTrue(r['reference_balance_matches'])
        self.assertEqual(r['disclosed_totals']['loans_plus_bonds'],100)
        self.assertEqual(r['disclosed_totals']['loans_plus_bonds_less_cash'],60)
        self.assertFalse(r['formal_is_interest_expense_verified'])
        self.assertFalse(r['automatic_financial_promotion'])

    def test_xbrl_other_year_entity_division_or_currency_cannot_fill_facts(self):
        for changes in [dict(year=2024),dict(entity='00999999'),dict(member='SeparateMember'),dict(unit='USD')]:
            r=xbrl_facts(xbrl_example(**changes),'CFS',2025,'00111111',REFERENCES)
            self.assertFalse(r['reference_balance_matches'])
            self.assertEqual(r['disclosed_totals'],{})

    def test_xbrl_mismatching_reference_balance_does_not_promote_notes(self):
        r=xbrl_facts(xbrl_example(),'CFS',2025,'00111111',{**REFERENCES,'Equity':151})
        self.assertFalse(r['reference_balance_matches'])
        self.assertEqual(r['disclosed_totals'],{})

    def test_xbrl_additional_dimensions_are_not_summed_into_company_debt(self):
        root=xbrl_example()
        segment=root.find('.//{http://www.xbrl.org/2003/instance}segment')
        member=ET.SubElement(segment,'{http://xbrl.org/2006/xbrldi}explicitMember',dimension='entity:BusinessSegmentAxis')
        member.text='entity:OneSubsidiaryMember'
        r=xbrl_facts(root,'CFS',2025,'00111111',REFERENCES)
        self.assertFalse(r['reference_balance_matches'])
        self.assertEqual(r['disclosed_totals'],{})

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
