#!/usr/bin/env python3
import unittest, tempfile, sys, io, zipfile, pathlib, json, csv
from datetime import date
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import exchange_calendars as xcals
import krx_forward_pit_v94 as f


def mock_document():
    return '''<DOCUMENT><TABLE-GROUP ACLASS="{XBRL}IS1"><TABLE>
    <TR><TD>연결 포괄손익계산서 (단위 : 원)</TD><TD> </TD></TR>
    <TR><TD>수익(매출액)</TD><TD>10</TD><TD>100</TD><TD>20</TD><TD>80</TD></TR>
    <TR><TD>영업이익(손실)</TD><TD>5</TD><TD>30</TD><TD>4</TD><TD>20</TD></TR>
    </TABLE></TABLE-GROUP><TABLE-GROUP ACLASS="{XBRL}BS"><TABLE>
    <TR><TD>연결 재무상태표 (단위 : 원)</TD><TD> </TD></TR>
    <TR><TD>부채총계</TD><TD>200</TD><TD>180</TD></TR>
    <TR><TD>자본총계</TD><TD>300</TD><TD>270</TD></TR>
    </TABLE></TABLE-GROUP></DOCUMENT>'''.encode()


def archive(xml, receipt='20230512000202'):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:z.writestr(receipt+'.xml',xml)
    return buf.getvalue()

class V94(unittest.TestCase):
    def setUp(self):self.cal=xcals.get_calendar('XKRX')
    def test_pit_exact_raw_amounts(self):
        row={'ticker':'083450','receipt_no':'20230512000202','filing_date':'2023-05-12',
            'report_code':'11013','fs_div':'CFS','revenue_amount_krw':'100','op_profit_amount_krw':'30',
            'liabilities_amount_krw':'200','equity_amount_krw':'300'}
        results=f.metric_comparison(row,archive(mock_document()),self.cal)
        self.assertEqual([x['status'] for x in results],['EXACT_MATCH']*4)
        self.assertEqual(results[0]['available_date'],'2023-05-15')
    def test_numeric_mismatch_flagged(self):
        row={'ticker':'083450','receipt_no':'20230512000202','filing_date':'2023-05-12',
            'report_code':'11013','fs_div':'CFS','revenue_amount_krw':'101','op_profit_amount_krw':'30',
            'liabilities_amount_krw':'200','equity_amount_krw':'300'}
        rows=f.metric_comparison(row,archive(mock_document()),self.cal)
        self.assertEqual(rows[0]['status'],'MISMATCH');self.assertEqual(rows[0]['delta_krw'],1)
    def test_xml_is_not_strict_wellformed(self):
        vals,status=f.read_financial_table(mock_document(), 'CFS','11013')
        self.assertEqual(status,'PARSED');self.assertEqual(vals['revenue'],(100,80))
    def test_missing_xbrl_fails_closed(self):
        vals,status=f.read_financial_table('<DOC><TR><TD>매출액</TD><TD>100</TD></TR></DOC>'.encode(), 'CFS','11013')
        self.assertEqual(vals,{});self.assertIn('MISSING',status)
    def test_duplicate_account_fails_closed(self):
        doc=mock_document().replace(b'</TABLE></TABLE-GROUP>',b'<TR><TD>\xec\x88\x98\xec\x9d\xb5(\xeb\xa7\xa4\xec\xb6\x9c\xec\x95\xa1)</TD><TD>10</TD><TD>100</TD><TD>20</TD><TD>80</TD></TR></TABLE></TABLE-GROUP>',1)
        vals,status=f.read_financial_table(doc,'CFS','11013')
        self.assertIn('DUPLICATE',status)
    def test_archive_receipt_guards(self):
        self.assertEqual(f.read_original_archive(archive(mock_document(),'20230811000657'),'20230512000202')[1], 'RECEIPT_FILE_MISMATCH')
    def test_cash_negative_triangle(self):
        self.assertEqual(f.num_krw('(1,234)'),-1234)
        self.assertEqual(f.num_krw('△2,300'),-2300)
        self.assertIsNone(f.num_krw('N/A'))
    def test_candidate_asof_must_be_available(self):
        financial=[{'ticker':'123456','receipt_no':'20230512000123','filing_date':'2023-05-12','available_date':'2023-05-15'},
                   {'ticker':'123456','receipt_no':'20230630000123','filing_date':'2023-06-30','available_date':'2023-07-03'}]
        candidates=[{'ticker':'123456','signal_date':'2023-05-12','selection_status':'MISSING_ASOF_SECTOR','signal_score':'99'},
                    {'ticker':'123456','signal_date':'2023-05-16','selection_status':'MISSING_ASOF_SECTOR','signal_score':'98'},
                    {'ticker':'123456','signal_date':'2023-07-06','selection_status':'PRIOR_BREAKOUT_OR_TEST_NOT_CLEAN','signal_score':'100'}]
        got=f.recent_candidates(candidates,financial)
        self.assertEqual(len(got),1);self.assertEqual(got[0]['receipt_no'],'20230512000123')
    def test_event_after_signal_is_excluded(self):
        d={'rcept_no':'20230512000202','rcept_dt':'20230512','report_nm':'단일판매ㆍ공급계약체결'}
        self.assertEqual(f.build_event_row(d,'083450','2023-05-12',self.cal)['asof_eligible'],'False')
        self.assertEqual(f.build_event_row(d,'083450','2023-05-15',self.cal)['asof_eligible'],'True')
    def test_amendment_not_fresh_event(self):
        t,a=f.classify_event('[기재정정]단일판매ㆍ공급계약체결');self.assertEqual(t,'SUPPLY_CONTRACT');self.assertTrue(a)
    def test_no_evidence_from_plain_report_title(self):
        r=f.build_event_row({'rcept_no':'20230512000202','rcept_dt':'20230512','report_nm':'신규시설투자등'},'083450','2023-05-16',self.cal)
        self.assertIn('TITLE_ONLY',r['evidence_status']);self.assertNotIn('매출증가',r['evidence_status'])
    def test_mocked_event_collector_no_future(self):
        class Args:pass
        args=Args();args.ticker='083450';args.max_companies=4;args.asof='2023-05-15';args.lookback_days=90;args.max_pages=2
        with tempfile.TemporaryDirectory() as d:
            args.outdir=d
            fin=[{'ticker':'083450','corp_code':'00123456'}]
            def fake_client(c,p):return {'status':'000','total_page':'1','list':[
                {'rcept_no':'20230512000202','rcept_dt':'20230512','report_nm':'단일판매ㆍ공급계약체결'},
                {'rcept_no':'20230515000202','rcept_dt':'20230515','report_nm':'신규시설투자등'}]}
            s=f.collect_events(args,fin,[],self.cal,client=fake_client)
            self.assertEqual(s['listed_events'],1)
            x=f.read_csv(pathlib.Path(d)/'v94_forward_event_leads.csv')
            self.assertEqual(x[0]['filing_date'],'2023-05-12')
    def test_financial_availability_not_before_receipt(self):
        info={'ticker':'083450','receipt_no':'20230512000202','filing_date':'2023-05-12',
            'report_code':'11013','fs_div':'CFS','revenue_amount_krw':'100','op_profit_amount_krw':'30',
            'liabilities_amount_krw':'200','equity_amount_krw':'300'}
        result=f.metric_comparison(info,archive(mock_document()),self.cal)
        self.assertTrue(all(r['available_date']>r['filing_date'] for r in result))
        self.assertTrue(all(r['status']!='PIT_APPROVED' for r in result))

if __name__=='__main__':unittest.main(verbosity=2)
