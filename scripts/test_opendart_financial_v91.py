#!/usr/bin/env python3
"""Offline unit tests. Never requires an OpenDART API key or network."""
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parent))
import krx_opendart_financial_v91 as v


def make_zip():
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        z.writestr('CORPCODE.xml','<result><list><corp_code>00000001</corp_code><stock_code>083450</stock_code><corp_name>GST</corp_name></list></result>')
    return b.getvalue()


def financial_rows(receipt='20250815000001', fs='CFS', year=2025, quarter='11012'):
    def row(section,aid,name,cur,prev,bs=False):
        if bs:
            return {'sj_div':'BS','account_id':aid,'account_nm':name,'thstrm_amount':str(cur),
                    'frmtrm_amount':str(prev),'rcept_no':receipt,'currency':'KRW'}
        return {'sj_div':'IS','account_id':aid,'account_nm':name,
                'thstrm_add_amount':str(cur),'frmtrm_add_amount':str(prev),
                'thstrm_amount':'999','frmtrm_q_amount':'888',
                'rcept_no':receipt,'currency':'KRW'}
    return [row('is','ifrs-full_Revenue','매출액',1200,1000),
            row('is','dart_OperatingIncomeLoss','영업이익',180,100),
            row('bs','ifrs-full_Liabilities','부채총계',400,300,True),
            row('bs','ifrs-full_Equity','자본총계',800,700,True)]


class TestDartV91(unittest.TestCase):
    def test_next_day_excludes_same_day(self):
        self.assertEqual(v.next_calendar_day('2025-08-15'),'2025-08-16')

    def test_currency_cash(self):
        self.assertEqual(v.cash('1,200'),1200)
        self.assertEqual(v.cash('(50)'),-50)
        self.assertIsNone(v.cash('-'))

    def test_corp_zip(self):
        self.assertEqual(v.get_corp_codes('x'*40,fetch=lambda *a:make_zip())['083450'],'00000001')

    def test_original_no_amendment_and_year(self):
        rows=[{'report_nm':'[기재정정]반기보고서 (2025.06)','rcept_no':'20250901000001','rcept_dt':'20250901'},
              {'report_nm':'반기보고서 (2025.06)','rcept_no':'20250815000001','rcept_dt':'20250815'},
              {'report_nm':'반기보고서 (2024.06)','rcept_no':'20250815000002','rcept_dt':'20250815'}]
        self.assertEqual(v.parse_original_filings(rows,2025)[0]['receipt_no'],'20250815000001')

    def test_financial_ytd_and_debt(self):
        metrics,status=v.build_metrics(financial_rows(),2025,'11012','CFS',None)
        self.assertEqual(status,'OK')
        self.assertEqual(metrics['revenue_yoy_pct'],20.0)
        self.assertEqual(metrics['op_profit_yoy_pct'],80.0)
        self.assertEqual(metrics['debt_ratio_pct'],50.0)
        self.assertEqual(metrics['op_margin_pct'],15.0)

    def test_ytd_not_three_month(self):
        x=financial_rows()
        metrics,status=v.build_metrics(x,2025,'11012','CFS',None)
        self.assertEqual(metrics['revenue_amount_krw'],1200)

    def test_missing_profit_hard_blocks(self):
        x=[r for r in financial_rows() if r['account_nm']!='영업이익']
        self.assertEqual(v.build_metrics(x,2025,'11012','CFS',None)[1],'MISSING_ACCOUNT')

    def test_negative_prior_profit_blocks(self):
        x=financial_rows();x[1]['frmtrm_add_amount']='-5'
        self.assertEqual(v.build_metrics(x,2025,'11012','CFS',None)[1],'NONCOMPARABLE_PREVIOUS_YEAR')

    def test_q1_fallback_to_three_month(self):
        rows=financial_rows()
        rows[0]['thstrm_add_amount']=''
        rows[0]['frmtrm_add_amount']=''
        rows[0]['thstrm_amount']='1200'
        rows[0]['frmtrm_q_amount']='1000'
        rows[1]['thstrm_add_amount']=''
        rows[1]['frmtrm_add_amount']=''
        rows[1]['thstrm_amount']='180'
        rows[1]['frmtrm_q_amount']='100'
        metrics,status=v.build_metrics(rows,2025,'11013','CFS',None)
        self.assertEqual(status,'OK')
        self.assertEqual(metrics['revenue_yoy_pct'],20.0)

    def test_annual_comparison(self):
        rows=financial_rows()
        for row in rows[:2]:
            row['thstrm_amount']=row['thstrm_add_amount']
            row['frmtrm_amount']=row['frmtrm_add_amount']
        metrics,status=v.build_metrics(rows,2025,'11011','CFS',None)
        self.assertEqual(status,'OK')
        self.assertEqual(metrics['revenue_yoy_pct'],20.0)

    def test_no_api_key_for_dry_run(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'cache').mkdir();Path(d,'cache','083450.csv').touch()
            a=Namespace(cache_dir=str(Path(d,'cache')),outdir=d,years=[2025],refresh_days=28,max_tickers=2,tickers=None,dry_run=True)
            with patch.dict(os.environ,{'OPENDART_API_KEY':''}):r=v.collect(a)
            self.assertEqual(r['selected_tickers'],['083450'])
            self.assertFalse(r['strict_pit_approved'])

    def test_complete_mock_run_provisional_only(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'cache').mkdir();Path(d,'cache','083450.csv').touch()
            a=Namespace(cache_dir=str(Path(d,'cache')),outdir=d,years=[2025],refresh_days=28,max_tickers=2,tickers=None,dry_run=False)
            def mock_fetch(endpoint,args):
                if endpoint=='corpCode.xml':return make_zip()
                if endpoint=='list.json':return {'status':'000','total_page':1,'list':[{'report_nm':'반기보고서 (2025.06)',
                    'rcept_no':'20250815000001','rcept_dt':'20250815'}]}
                if endpoint=='fnlttSinglAcntAll.json':
                    return {'status':'000','list':financial_rows()} if args['fs_div']=='CFS' else {'status':'013'}
                raise AssertionError(endpoint)
            with patch.dict(os.environ,{'OPENDART_API_KEY':'x'*40}):
                r=v.collect(a,fetch=mock_fetch)
            self.assertEqual(r['total_provisional_rows'],1)
            self.assertFalse(r['strict_pit_approved'])
            self.assertTrue(Path(d,'v91_financial_pit_provisional.csv').exists())
            self.assertFalse(Path(d,'v90_financial_pit.csv').exists())
            rows=v.read_csv(Path(d,'v91_financial_pit_provisional.csv'))
            self.assertEqual(rows[0]['available_date'],'2025-08-16')
            self.assertEqual(rows[0]['receipt_no'],'20250815000001')
            # Rerun doesn't re-fetch completed companies.
            with patch.dict(os.environ,{'OPENDART_API_KEY':'x'*40}):
                r2=v.collect(a,fetch=mock_fetch)
            self.assertEqual(r2['selected_tickers'],[])

    def test_receipt_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'cache').mkdir();Path(d,'cache','083450.csv').touch()
            a=Namespace(cache_dir=str(Path(d,'cache')),outdir=d,years=[2025],refresh_days=28,max_tickers=1,tickers=None,dry_run=False)
            def mock_fetch(endpoint,args):
                if endpoint=='corpCode.xml':return make_zip()
                if endpoint=='list.json':return {'status':'000','total_page':1,'list':[{'report_nm':'반기보고서 (2025.06)',
                    'rcept_no':'20250815000001','rcept_dt':'20250815'}]}
                if endpoint=='fnlttSinglAcntAll.json':return {'status':'000','list':financial_rows(receipt='20250901000001')}
                raise AssertionError(endpoint)
            with patch.dict(os.environ,{'OPENDART_API_KEY':'x'*40}):
                r=v.collect(a,fetch=mock_fetch)
            self.assertEqual(r['total_provisional_rows'],0)
            self.assertTrue(any(x['status']=='RECEIPT_MISMATCH' for x in v.read_csv(Path(d,'v91_financial_collection_audit.csv'))))

if __name__=='__main__':unittest.main(verbosity=2)
