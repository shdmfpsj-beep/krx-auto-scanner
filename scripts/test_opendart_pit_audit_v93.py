#!/usr/bin/env python3
"""Offline tests for OpenDART v9.3. No API key/network required."""
import csv, io, json, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
import exchange_calendars as xcals
import krx_opendart_pit_audit_v93 as v

class V93Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.cal=xcals.get_calendar('XKRX')

    def test_holiday_and_weekend(self):
        self.assertEqual(v.krx_next_session('2026-08-14',self.cal),'2026-08-18')
        self.assertEqual(v.krx_next_session('2026-10-09',self.cal),'2026-10-12')

    def test_regular_trading_next_day(self):
        self.assertEqual(v.krx_next_session('2026-10-12',self.cal),'2026-10-13')

    def test_date_validate_retains_original_and_quarantine(self):
        base={'filing_date':'2026-08-14','available_date':'2026-08-15','receipt_no':'20260814000001'}
        row=v.date_validate(base,self.cal)
        self.assertEqual(row['available_date'],'2026-08-18')
        self.assertEqual(row['original_available_date'],'2026-08-15')
        self.assertEqual(row['date_check_status'],'XKRX_NEXT_SESSION_COMPUTED')
        broken=v.date_validate(dict(base,receipt_no='20260813000001'),self.cal)
        self.assertEqual(broken['date_check_status'],'RECEIPT_DATE_CONFLICT')
        self.assertEqual(broken['available_date'],'')

    def test_transition(self):
        self.assertEqual(v.transition(90,-10),'LOSS_TO_PROFIT')
        self.assertEqual(v.transition(-15,-25),'LOSS_NARROWING')
        self.assertEqual(v.transition(-35,-25),'LOSS_WIDENING')
        self.assertEqual(v.transition(-10,100),'PROFIT_TO_LOSS_OR_ZERO')
        self.assertEqual(v.transition(10,0),'ZERO_TO_PROFIT')

    def test_recovery_metrics_loss_to_profit(self):
        def row(sj,id,nm,cur,prior,div='CFS'):
            return {'sj_div':sj,'account_id':id,'account_nm':nm,'fs_div':div,'account_detail':'-',
                    'currency':'KRW','thstrm_add_amount':str(cur),'frmtrm_add_amount':str(prior),
                    'thstrm_amount':str(cur),'frmtrm_amount':str(prior)}
        rows=[row('IS','ifrs-full_Revenue','매출액',1_000_000,900_000),
              row('IS','dart_OperatingIncomeLoss','영업이익',100_000,-50_000),
              row('BS','ifrs-full_Liabilities','부채총계',500_000,500_000),
              row('BS','ifrs-full_Equity','자본총계',500_000,400_000)]
        m,s=v.metric_recover(rows,'11012','CFS')
        self.assertEqual(s,'OK');self.assertEqual(m['op_profit_yoy_pct'],'')
        self.assertEqual(m['earnings_transition'],'LOSS_TO_PROFIT')
        self.assertEqual(m['debt_ratio_pct'],100)
        self.assertAlmostEqual(m['revenue_yoy_pct'],11.1111)

    def test_account_absence_does_not_fabricate(self):
        self.assertEqual(v.metric_recover([], '11012','CFS')[1],'MISSING_INCOME_STATEMENT_ACCOUNTS')

    def test_wrong_currency_rejected(self):
        rows=[{'sj_div':'IS','account_id':'ifrs-full_Revenue','fs_div':'CFS','account_detail':'-',
               'currency':'USD','thstrm_add_amount':'10'},
              {'sj_div':'IS','account_id':'dart_OperatingIncomeLoss','fs_div':'CFS','account_detail':'-',
               'currency':'USD','thstrm_add_amount':'2'}]
        self.assertEqual(v.metric_recover(rows,'11012','CFS')[1],'NON_KRW')

    def test_missing_20_diagnosis_and_pit_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            rec={x:'' for x in v.BASE_FIELDS}
            rec.update(ticker='000001',receipt_no='20260814000001',filing_date='2026-08-14',
                       available_date='2026-08-15',fs_div='CFS')
            with zipfile.ZipFile(path/'fixture.zip','w') as z:
                s=io.StringIO();w=csv.DictWriter(s,fieldnames=v.BASE_FIELDS);w.writeheader();w.writerow(rec)
                z.writestr('v91_financial_pit_provisional.csv',s.getvalue())
                s=io.StringIO();w=csv.DictWriter(s,fieldnames=v.legacy.AUDIT_COLS);w.writeheader()
                w.writerow({'ticker':'000002','year':'2026','report_code':'11012','status':'NONCOMPARABLE_PREVIOUS_YEAR'})
                z.writestr('v91_financial_collection_audit.csv',s.getvalue())
                z.writestr('v91_financial_collection_state.json',json.dumps({'completed_tickers':['000001','000002']}))
            summary=v.build_report(path,path/'fixture.zip')
            self.assertFalse(summary['strict_pit_approved'])
            self.assertEqual(summary['calendar_changed_rows'],1)
            self.assertEqual(summary['zero_original_rows_codes'],['000002'])
            self.assertEqual(summary['combined_provisional_rows'],1)
            self.assertEqual(summary['original_funded_tickers'],1)
            out=v.read_csv_file(path/'v93_financial_calendar_adjusted_provisional.csv')
            self.assertEqual(out[0]['available_date'],'2026-08-18')
            self.assertEqual(out[0]['pit_numeric_status'],'UNVERIFIED_CURRENT_API_SNAPSHOT_NOT_ORIGINAL')

if __name__=='__main__':unittest.main(verbosity=2)
