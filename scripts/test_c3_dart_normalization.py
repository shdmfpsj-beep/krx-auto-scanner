"""Source identity, exact units, observation isolation and financial recovery."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from c3_balanced_financials import SnapshotCache
from c3_balanced_source_probe import DocumentCache
from datetime import date
from c3_balanced_financials import annual_statement_version, validate_payload
from c3_dart_normalization import amount, financing_debt, note_interest, normalize_notes, audit_note, original_document
from test_c3_dart_document_evidence import zipped, xbrl_example, REFERENCES
from xml.etree import ElementTree as ET

DAY=date(2026,11,23)
IDENTITY=dict(ticker='111111',corp_code='00111111',receipt_no='20260320000001',fiscal_year=2025,division='CFS')


def filing(receipt='20260320000001',name='사업보고서 (2025.12)',**values):
    return dict(rcept_no=receipt,rcept_dt=receipt[:8],report_nm=name,corp_code='00111111',stock_code='111111',**values)


def document(notes,year=2025,corp='00111111',division='CFS',other=''):
    title='연결재무제표 주석' if division=='CFS' else '재무제표 주석'
    return zipped(f'''<DOCUMENT><DOCUMENT-NAME>사업보고서</DOCUMENT-NAME><COMPANY-NAME AREGCIK="{corp}">검증</COMPANY-NAME>
    <COVER><TU AUNIT="PERIODFROM" AUNITVALUE="{year}0101"/><TU AUNIT="PERIODTO" AUNITVALUE="{year}1231"/></COVER>
    <SECTION-2><TITLE>{title}</TITLE>{notes}</SECTION-2>{other}</DOCUMENT>''')


def raw_document(notes,**kwargs):
    # Original endpoint archives are named by their actual filing receipt.
    src=document(notes,**kwargs);out=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(src)) as z:body=z.read('filing.xml')
    with zipfile.ZipFile(out,'w') as z:z.writestr(IDENTITY['receipt_no']+'.xml',body)
    return out.getvalue()


def xbrl(no_debt=True):
    root=xbrl_example()
    if no_debt:
        for node in list(root):
            if node.tag.split('}')[-1] in ('OtherBorrowings','BondsIssued'):root.remove(node)
    else:
        for node in root:
            if node.tag.split('}')[-1] in ('OtherBorrowings','BondsIssued'):node.text=str(int(node.text)*1000)
    return zipped(ET.tostring(root).decode())


FINANCING='''<P>재무활동에서 생기는 부채의 조정내용</P><TABLE>
<TR><TD>(단위:천원)</TD></TR><TR><TH>구분</TH><TH>기초</TH><TH>현금흐름</TH><TH>당기말</TH></TR>
<TR><TD>리스부채</TD><TD>4</TD><TD>(1)</TD><TD>3</TD></TR>
<TR><TD>합계</TD><TD>4</TD><TD>(1)</TD><TD>3</TD></TR></TABLE>'''


class SourceRecoveryTests(unittest.TestCase):
    def test_attachment_receipt_does_not_replace_primary_financial_body(self):
        p=dict(list=[filing(),filing('20260326000491','[첨부정정]사업보고서 (2025.12)')])
        r=annual_statement_version(p,2025,DAY,'00111111','111111')
        self.assertEqual(r['financial_receipt'],'20260320000001')
        self.assertEqual(r['latest_disclosure']['rcept_no'],'20260326000491')
        self.assertTrue(r['attachment_review_required'])

    def test_body_correction_is_not_dropped_like_an_attachment(self):
        p=dict(list=[filing(),filing('20260326000491','[기재정정]사업보고서 (2025.12)')])
        self.assertEqual(annual_statement_version(p,2025,DAY)['financial_receipt'],'20260326000491')

    def test_future_amendment_is_not_used_for_asof_selection(self):
        p=dict(list=[filing(),filing('20261124000491','[기재정정]사업보고서 (2025.12)')])
        self.assertEqual(annual_statement_version(p,2025,DAY)['financial_receipt'],'20260320000001')

    def test_wrong_filing_company_and_receipt_date_are_errors(self):
        for edit in (dict(corp_code='00999999'),dict(stock_code='999999'),dict(rcept_dt='20260321')):
            row=filing();row.update(edit)
            with self.assertRaises(ValueError):annual_statement_version(dict(list=[row]),2025,DAY,'00111111','111111')

    def test_withdrawn_latest_body_cannot_fall_back_to_old_health(self):
        rows=[filing(),filing('20260326000491','[기재정정]사업보고서 (2025.12)',rm='철')]
        with self.assertRaisesRegex(ValueError,'WITHDRAWN'):annual_statement_version(dict(list=rows),2025,DAY)

    def test_audit_receipt_must_be_catalogue_verified_related_attachment(self):
        from c3_balanced_financials import related_audit_receipt
        version=annual_statement_version(dict(list=[filing(),filing('20260326000491','[첨부정정]사업보고서 (2025.12)')]),2025,DAY)
        payload=dict(status='000',list=[dict(rcept_no='20260326000491')])
        self.assertEqual(related_audit_receipt(payload,version),'20260326000491')
        self.assertTrue(version['attachment_review_required'])
        payload['list'][0]['rcept_no']='20260326009999'
        with self.assertRaisesRegex(ValueError,'AUDIT_RECEIPT_MISMATCH'):related_audit_receipt(payload,version)

    def test_issuer_source_failure_does_not_abort_other_company_review(self):
        from test_c3_balanced_financials import request
        from c3_balanced_financials import collect_balanced
        def responses(endpoint,params,key):
            if params['corp_code']=='00999999':raise ValueError('FILING_COMPANY_MISMATCH')
            return request(endpoint,params,key)
        with tempfile.TemporaryDirectory() as tmp:
            result=collect_balanced(DAY,[dict(ticker='999999',name='잘못된 원본'),dict(ticker='111111',name='검증 기업')],
                'a'*40,DAY,SnapshotCache(tmp),responses,lambda key:dict([('999999','00999999'),('111111','00111111')]))
            self.assertEqual(result['excluded'][0]['financial_decision'],'ERROR')
            self.assertEqual(result['researched'][0]['financial_decision'],'PASS')

    def test_current_audit_rowspan_scope_and_explicit_uncertainty(self):
        root=ET.fromstring('''<DOCUMENT><TABLE><TR><TH>사업연도</TH><TH>구분</TH><TH>감사의견</TH>
            <TH>계속기업 불확실성</TH><TH>강조사항</TH></TR>
            <TR><TD ROWSPAN="2">당기</TD><TD>감사보고서</TD><TD>적정</TD><TD>-</TD><TD>-</TD></TR>
            <TR><TD>연결감사보고서</TD><TD>적정</TD><TD>존속능력 불확실</TD><TD>-</TD></TR>
            <TR><TD>전기</TD><TD>연결감사보고서</TD><TD>적정</TD><TD>-</TD><TD>-</TD></TR>
            </TABLE></DOCUMENT>''')
        self.assertEqual(audit_note(root,'OFS')['state'],'PASS')
        self.assertEqual(audit_note(root,'CFS')['state'],'REVIEW_REQUIRED')

    def test_latest_insurance_unpublished_capital_is_not_previous_year_ratio(self):
        from c3_dart_normalization import insurance_capital_disclosure
        binary=raw_document('''<P>지급여력</P><TABLE><TR><TH>구분</TH><TH>2025년</TH><TH>2024년</TH></TR>
            <TR><TD>지급여력비율</TD><TD>산출 중</TD><TD>159.48</TD></TR></TABLE>''')
        r=insurance_capital_disclosure(binary,{**IDENTITY,'report_code':'11011'})
        self.assertEqual(r['reason'],'CURRENT_KICS_NOT_PUBLISHED')
        self.assertIsNone(r['disclosures'][0]['current_value'])
        self.assertEqual(r['disclosures'][0]['prior_raw'],['159.48'])
        self.assertFalse(r['manufacturing_model_applied'])

    def test_statement_company_identifier_is_verified(self):
        from test_c3_balanced_financials import statement
        p=statement()
        with self.assertRaisesRegex(ValueError,'COMPANY_MISMATCH'):
            validate_payload(p,'CFS',2025,'11011','20260320000001',DAY,'00999999')

    def test_numbers_preserve_sign_and_dash_never_means_missing_account_zero(self):
        self.assertEqual(amount('(1,234)'),-1234)
        self.assertIsNone(amount('-'));self.assertEqual(amount('-',dash=True),0)
        self.assertIsNone(amount(''));self.assertIsNone(amount('산출 중'))

    def test_exhaustive_reconciled_note_supports_zero_borrowings(self):
        r=normalize_notes(raw_document(FINANCING),xbrl(),IDENTITY,REFERENCES)
        fact=r['metrics']['interest_bearing_debt_excluding_leases']
        self.assertEqual(fact['value'],0)
        self.assertEqual(fact['provenance']['unit'],'천원')
        self.assertIn('EXHAUSTIVE',fact['provenance']['reconciliation']['zero_basis'])

    def test_missing_table_total_unknown_component_or_wrong_movements_prevents_zero(self):
        variants=[FINANCING.replace('<TR><TD>합계</TD><TD>4</TD><TD>(1)</TD><TD>3</TD></TR>',''),
                  FINANCING.replace('리스부채','기타금융부채'),FINANCING.replace('<TD>(1)</TD>','<TD>(99)</TD>')]
        for text in variants:
            r=normalize_notes(raw_document(text),xbrl(),IDENTITY,REFERENCES)
            self.assertNotIn('interest_bearing_debt_excluding_leases',r['metrics'])

    def test_note_period_entity_and_consolidation_cannot_mix(self):
        for changes in (dict(year=2024),dict(corp='00999999'),dict(division='OFS')):
            r=normalize_notes(raw_document(FINANCING,**changes),xbrl(),IDENTITY,REFERENCES)
            self.assertEqual(r['state'],'REVIEW_REQUIRED');self.assertEqual(r['metrics'],{})

    def test_missing_foreign_or_conflicting_units_are_not_guessed(self):
        for unit in ('단위 없음','(단위:USD)','(단위:천원, USD)'):
            r=normalize_notes(raw_document(FINANCING.replace('(단위:천원)',unit)),xbrl(),IDENTITY,REFERENCES)
            self.assertEqual(r['metrics'],{})

    def test_prior_financing_table_is_not_current(self):
        r=normalize_notes(raw_document(FINANCING.replace('당기말','전기말')),xbrl(),IDENTITY,REFERENCES)
        self.assertEqual(r['metrics'],{})

    def test_note_debt_conflicting_with_known_xbrl_or_api_is_not_accepted(self):
        r=normalize_notes(raw_document(FINANCING),xbrl(no_debt=False),IDENTITY,REFERENCES)
        self.assertIn('NOTE_DEBT_XBRL_TOTAL_MISMATCH',r['errors'])
        r=normalize_notes(raw_document(FINANCING),xbrl(),IDENTITY,REFERENCES,known_debt_floor=1000)
        self.assertIn('NOTE_DEBT_BELOW_VERIFIED_COMPONENTS',r['errors'])

    def test_finance_costs_are_not_used_as_interest_and_cf_addbacks_are_rejected(self):
        table=dict(scale=1000,rows=[['구분','당기','전기'],['금융원가','10','9'],['외환차손','10','9']],
                   context='금융비용',metadata='단위:천원')
        self.assertIsNone(note_interest(table,10000))
        table['rows']=[['구분','당기','전기'],['이자비용','10','9']];table['context']='영업활동현금흐름 조정'
        self.assertIsNone(note_interest(table,10000))

    def test_note_interest_components_including_other_interest_reconcile_once(self):
        table=dict(scale=1000000,rows=[['','','공시금액'],['금융원가','금융원가','(33)'],
            ['금융원가','이자비용','(16)'],['금융원가','이자비용-기타','(6)'],
            ['금융원가','평가손실','(11)']],context='금융수익 및 금융비용',metadata='당기 (단위:백만원)')
        self.assertEqual(note_interest(table,33000000)['value'],22000000)
        self.assertIsNone(note_interest(table,44000000))

    def test_unexplained_other_finance_costs_cannot_understate_interest(self):
        table=dict(scale=1000,rows=[['구분','당기','전기'],['금융원가','10','9'],
            ['이자비용','3','2'],['기타금융비용','7','7']],context='금융비용',metadata='단위:천원')
        self.assertIsNone(note_interest(table,10000))

    def test_xbrl_reference_balance_conflict_blocks_note_use(self):
        r=normalize_notes(raw_document(FINANCING),xbrl(),IDENTITY,{**REFERENCES,'Equity':151})
        self.assertEqual(r['state'],'REVIEW_REQUIRED');self.assertEqual(r['metrics'],{})

    def test_issuer_error_is_hold_but_shared_auth_failure_is_system_error(self):
        from test_c3_top5_financial_selection import candidate,record,evidence,ASOF
        from c3_top5_financial_selection import select,REVIEW_SCOPE
        bad=record(financial_model='BALANCED_QUALITY_TIMING_V1',financial_verdict='ERROR')
        f=evidence(bad,status='ERROR');f.update(model='BALANCED_QUALITY_TIMING_V1',request_scope=REVIEW_SCOPE,
            aggregate_policy='ISOLATED_ISSUER_FAILURES_V1')
        g=dict(asof=ASOF,candidates=[candidate()])
        self.assertEqual(select(g,f)['operational_status'],'HOLD_FINANCIAL_UNVERIFIED')
        bad['source_observations']=[dict(api_status='010')]
        self.assertEqual(select(g,f)['operational_status'],'ERROR')

    def test_unverified_watch_never_becomes_normal_cash(self):
        from test_c3_top5_financial_selection import candidate,record,evidence,ASOF
        from c3_top5_financial_selection import select,REVIEW_SCOPE
        f=evidence(record(financial_model='BALANCED_QUALITY_TIMING_V1',financial_verdict='REVIEW_REQUIRED'),status='REVIEW_REQUIRED')
        f.update(model='BALANCED_QUALITY_TIMING_V1',request_scope=REVIEW_SCOPE,aggregate_policy='ISOLATED_ISSUER_FAILURES_V1')
        x=select(dict(asof=ASOF,candidates=[candidate('111111','WATCH',close=10300)]),f)
        self.assertEqual(x['operational_status'],'HOLD_FINANCIAL_UNVERIFIED');self.assertNotEqual(x['decision'],'CASH')

    def test_financial_hold_delivery_has_no_network_or_operating_receipts(self):
        from test_c3_top5_pipeline import PipelineTests,BUILD,DELIVERY
        t=PipelineTests();t.setUp()
        try:
            t.prepare(empty=True)
            t.write('financial_selection_research.json',dict(asof='20261120',status='REVIEW_REQUIRED',
                operational_status='HOLD_FINANCIAL_UNVERIFIED',selected=[],selected_count=0,signals=[]))
            self.assertEqual(t.execute(BUILD).returncode,0)
            p=t.execute(DELIVERY);self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(t.result()['status'],'HOLD');self.assertEqual(t.result()['telegram_photos_sent'],0)
            self.assertFalse((t.cwd/'receipts').exists())
        finally:t.doCleanups()

    def test_incomplete_krx_source_is_hold_data_not_cash(self):
        from c3_balanced_validation import run
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir()
            for name,data in [('receipt',dict(asof='20261123',source_integrity=dict(session_count=59))),
                ('entry_geometry_audit',dict(asof='20261123',candidates=[])),('qualified_chart_pool',dict(asof='20261123',candidates=[]))]:
                (source/(name+'.json')).write_text(json.dumps(data))
            result=run(root/'out',root/'cache',source)
            self.assertEqual(result['operational_status'],'HOLD_DATA_INCOMPLETE')
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
