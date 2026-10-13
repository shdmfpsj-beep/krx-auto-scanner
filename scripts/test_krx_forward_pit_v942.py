#!/usr/bin/env python3
"""Offline regression tests: no DART credentials or network required."""
import io, json, tempfile, unittest, zipfile
from pathlib import Path
from types import SimpleNamespace
from datetime import date
import exchange_calendars as xcals
import krx_forward_pit_v942 as x

RECEIPT='20251114002947'


def fixture_xml(fs='CFS',duplicate=False,missing_unit=False,wrong_columns=False):
    if fs=='CFS': isclass,bsclass='{XBRL}IS_C1','{XBRL}BS_C'
    else: isclass,bsclass='{XBRL}IS_S1','{XBRL}BS_S'
    dunit='' if missing_unit else '<tr><td>(단위 : 원)</td></tr>'
    duplicated=(f'<table-group aclass="{isclass}">x</table-group>' if duplicate else '')
    revvals='<td>100</td><td>100</td><td>80</td><td>80</td>' if not wrong_columns else '<td>100</td><td>80</td>'
    profvals='<td>20</td><td>20</td><td>5</td><td>5</td>' if not wrong_columns else '<td>20</td><td>5</td>'
    return (f'<document><table-group aclass="{isclass}"><table>{dunit}'
            f'<tr><td>수익(매출액)</td>{revvals}</tr><tr><td>영업이익(손실)</td>{profvals}</tr>'
            f'</table></table-group>{duplicated}<table-group aclass="{bsclass}"><table>{dunit}'
            '<tr><td>부채총계</td><td>300</td><td>200</td></tr>'
            '<tr><td>자본총계</td><td>600</td><td>500</td></tr>'
            '</table></table-group></document>').encode()


def archive(xml,receipt=RECEIPT):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr(receipt+'.xml',xml)
    return b.getvalue()


class TestV942(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.cal=xcals.get_calendar('XKRX')

    def test_bounded_dart_request_never_logs_key(self):
        from unittest.mock import patch
        import urllib.error
        import io
        seen=[]
        def timeout_open(req,timeout=None):
            seen.append(timeout)
            raise urllib.error.URLError('simulated_network_issue')
        with patch.object(x.urllib.request,'urlopen',side_effect=timeout_open), patch.object(x.time,'sleep'):
            with self.assertRaises(urllib.error.URLError):
                x.bounded_dart_list('f'*40,{'corp_code':'00000001','bgn_de':'20260101'},socket_timeout=5,retries=2)
        self.assertEqual(seen,[5,5])

    def test_bounded_dart_json_success(self):
        from unittest.mock import patch
        import io
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):return b'{"status":"000","total_page":1,"list":[]}'
        with patch.object(x.urllib.request,'urlopen',return_value=Response()) as mock_urlopen:
            result=x.bounded_dart_list('f'*40,{'corp_code':'00000001'},socket_timeout=3,retries=1)
        self.assertEqual(result['status'],'000')
        self.assertEqual(mock_urlopen.call_args.kwargs['timeout'],3)

    def test_exact_class_CFS(self):
        fields,status,diag=x.original_numeric(fixture_xml(), 'CFS','11013')
        self.assertEqual(status,'PARSED')
        self.assertEqual(fields['revenue'][0],100)
        self.assertEqual(fields['op_profit'][0],20)
        self.assertEqual(fields['liabilities'][0],300)
        self.assertEqual(fields['equity'][0],600)
        self.assertEqual(len(diag['mapped']),2)

    def test_exact_class_OFS(self):
        fields,status,diag=x.original_numeric(fixture_xml('OFS'), 'OFS','11013')
        self.assertEqual(status,'PARSED')
        self.assertEqual(fields['revenue'][0],100)
        self.assertIn('balance',diag['mapped'])

    def test_reject_ambiguous_table(self):
        fields,status,_=x.original_numeric(fixture_xml(duplicate=True),'CFS','11013')
        self.assertNotEqual(status,'PARSED');self.assertEqual(fields,{})

    def test_reject_two_known_statement_aliases(self):
        xml=fixture_xml().replace(b'</table></table-group><table-group aclass="{XBRL}BS_C">',
            b'</table></table-group><table-group aclass="{XBRL}IS1"><table><tr><td>dummy</td></tr></table></table-group><table-group aclass="{XBRL}BS_C">')
        fields,status,_=x.original_numeric(xml,'CFS','11013')
        self.assertEqual(fields,{})
        self.assertEqual(status,'AMBIGUOUS_INCOME_XBRL_GROUP')

    def test_reject_missing_units(self):
        fields,status,_=x.original_numeric(fixture_xml(missing_unit=True),'CFS','11013')
        self.assertTrue(status.startswith('AMBIGUOUS_UNIT'));self.assertEqual(fields,{})

    def test_reject_wrong_columns(self):
        fields,status,_=x.original_numeric(fixture_xml(wrong_columns=True),'CFS','11013')
        self.assertIn('AMBIGUOUS_INCOME_COLUMNS',status)

    def test_bad_scope(self):
        self.assertEqual(x.original_numeric(fixture_xml(),'MIXED','11013')[1],'BAD_FS_DIV')

    def test_numeric_receipt_full_match(self):
        row=dict(ticker='083450',receipt_no=RECEIPT,filing_date='2025-11-14',fs_div='CFS',report_code='11013',
                revenue_amount_krw='100',op_profit_amount_krw='20',liabilities_amount_krw='300',equity_amount_krw='600')
        result,diag=x.compare_archive(row,archive(fixture_xml()),self.cal)
        self.assertEqual([r['status'] for r in result],['EXACT_MATCH']*4)
        self.assertTrue(x.prev.receipt_verified(result,RECEIPT))
        self.assertEqual(result[0]['available_date'],'2025-11-17')

    def test_numeric_mismatch_not_approved(self):
        row=dict(ticker='083450',receipt_no=RECEIPT,filing_date='2025-11-14',fs_div='CFS',report_code='11013',
                revenue_amount_krw='101',op_profit_amount_krw='20',liabilities_amount_krw='300',equity_amount_krw='600')
        result,_=x.compare_archive(row,archive(fixture_xml()),self.cal)
        self.assertIn('MISMATCH',[r['status'] for r in result])
        self.assertFalse(x.prev.receipt_verified(result,RECEIPT))

    def test_classify_supply_termination(self):
        kind,pol,amend,sub=x.classify_event('단일판매ㆍ공급계약해지')
        self.assertEqual((kind,pol,amend),('SUPPLY_TERMINATION','NEGATIVE_EVENT',False))

    def test_classify_amended_contract_termination(self):
        kind,pol,amend,sub=x.classify_event('[기재정정]단일판매ㆍ공급계약해지')
        self.assertEqual(kind,'SUPPLY_TERMINATION');self.assertTrue(amend);self.assertEqual(pol,'AMENDMENT_NOT_NEW_CATALYST')

    def test_classify_normal_contract_not_positive_confirmed(self):
        kind,pol,amend,sub=x.classify_event('단일판매ㆍ공급계약체결')
        self.assertEqual(kind,'SUPPLY_CONTRACT');self.assertEqual(pol,'UNCERTAIN_UNTIL_ORIGINAL')

    def test_amendment_not_fresh(self):
        e=dict(ticker='067080',signal_date='2026-09-29',receipt_no='20260915800002',report_name='[기재정정]단일판매ㆍ공급계약해지',
               filing_date='2026-09-15',first_usable_session='2026-09-16')
        r=x.normalize_event(e,self.cal)
        self.assertEqual(r['possible_growth_catalyst'],'False');self.assertEqual(r['is_cancellation'],'True')
        self.assertEqual(r['research_signal_approved'],'False')

    def test_negative_contract_not_growth(self):
        e=dict(ticker='067080',signal_date='2026-09-29',receipt_no='20260915800002',report_name='단일판매ㆍ공급계약해지',
               filing_date='2026-09-15',first_usable_session='2026-09-16')
        r=x.normalize_event(e,self.cal)
        self.assertEqual(r['freshness'],'NEGATIVE_EVENT_NOT_GROWTH')
        self.assertEqual(r['possible_growth_catalyst'],'False')

    def test_future_filing_not_eligible(self):
        e=dict(ticker='083450',signal_date='2025-11-12',receipt_no='20251114800123',report_name='단일판매ㆍ공급계약체결',
               filing_date='2025-11-14',first_usable_session='2025-11-17')
        r=x.normalize_event(e,self.cal)
        self.assertEqual(r['asof_eligible'],'False');self.assertEqual(r['possible_growth_catalyst'],'False')

    def test_retryable_pagination_and_legacy_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            x.write_csv(out/'v941_forward_event_leads.csv',[],x.prev.EV_COLS)
            x.write_json(out/'v941_event_collection_state.json',{'attempts':[
              {'ticker':'083450','signal_date':'2025-11-21','status':'SUCCESS','attempt_count':1}]})
            fin=[{'ticker':'083450','corp_code':'00012345'},{'ticker':'006800','corp_code':'00034567'}]
            candidates=[{'ticker':'083450','signal_date':'2025-11-21'},{'ticker':'006800','signal_date':'2025-11-21'}]
            calls=[]
            def client(cc,params):
                calls.append((cc,params['page_no']))
                return {'status':'000','total_page':2,'list':[{'rcept_no':'20251113800001','rcept_dt':'20251113',
                                   'report_nm':'단일판매ㆍ공급계약해지'}]}
            args=SimpleNamespace(outdir=tmp,ticker='',asof='',max_retries=2,max_companies=1,
                                 max_pages=1,lookback_days=180,delay_seconds=0)
            first=x.events(args,fin,candidates,self.cal,client)
            self.assertEqual(first['queried'],1)
            self.assertEqual(first['successful_queries'],0)
            self.assertEqual(first['warnings'][0]['issue'],'INCOMPLETE_PAGINATION')
            self.assertEqual(len(calls),1)
            # A second run must retry failed query, not requery successful legacy one.
            second=x.events(args,fin,candidates,self.cal,client)
            self.assertEqual(second['queried'],1);self.assertEqual(len(calls),2)
            self.assertEqual(second['canceled_or_terminated'],1)
            self.assertEqual(second['numeric_growth_signals_approved'],0)

    def test_raw_chart_signals_without_receipt_number_do_not_crash(self):
        # Reproduces the exact production schema that caused KeyError: receipt_no.
        with tempfile.TemporaryDirectory() as tmp:
            fin=[dict(ticker='083450',receipt_no=RECEIPT,available_date='2025-11-17',
                      filing_date='2025-11-14',fs_div='CFS',report_code='11013',
                      revenue_amount_krw='100',op_profit_amount_krw='20',
                      liabilities_amount_krw='300',equity_amount_krw='600')]
            cand=[dict(ticker='083450',signal_date='2025-11-21',signal_score='80',
                       selection_status='MISSING_ASOF_SECTOR')]
            args=SimpleNamespace(outdir=tmp,ticker='',max_retries=2,max_documents=1,
                                 archive_bundle='',delay_seconds=0)
            # No network: an exact original is supplied by an archive fixture.
            from unittest.mock import patch
            with patch.object(x.old,'get_archive',return_value=archive(fixture_xml())), \
                 patch.dict('os.environ',{'OPENDART_API_KEY':'a'*40}):
                result=x.verify(args,fin,cand,self.cal)
            self.assertEqual(result['attempted'],1)
            self.assertEqual(result['verified_four_this_run'],1)

    def test_future_financial_receipt_is_never_picked_for_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            fin=[dict(ticker='083450',receipt_no=RECEIPT,
                      available_date='2025-11-17',filing_date='2025-11-14',
                      fs_div='CFS',report_code='11013')]
            cand=[dict(ticker='083450',signal_date='2025-11-10',signal_score='80',
                       selection_status='MISSING_ASOF_SECTOR',receipt_no=RECEIPT)]
            args=SimpleNamespace(outdir=tmp,ticker='',max_retries=2,max_documents=1,
                                 archive_bundle='',delay_seconds=0)
            result=x.verify(args,fin,cand,self.cal)
            self.assertEqual(result['attempted'],0)
            self.assertEqual(result['verified_four_this_run'],0)

    def test_event_query_works_with_raw_chart_candidate_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            fin=[dict(ticker='083450',corp_code='00012345',receipt_no=RECEIPT,
                      available_date='2025-11-17',filing_date='2025-11-14',
                      fs_div='CFS',report_code='11013')]
            cand=[dict(ticker='083450',signal_date='2025-11-21',signal_score='80',
                       selection_status='MISSING_ASOF_SECTOR')]
            args=SimpleNamespace(outdir=tmp,ticker='',asof='',max_retries=2,
                max_companies=1,max_pages=1,lookback_days=180,delay_seconds=0)
            calls=[]
            def stub(cc,params):
                calls.append((cc,params['page_no']))
                return {'status':'013'}
            result=x.events(args,fin,cand,self.cal,client=stub)
            self.assertEqual(result['queried'],1)
            self.assertEqual(result['successful_queries'],1)
            self.assertEqual(calls,[('00012345','1')])



if __name__=='__main__':unittest.main(verbosity=2)
