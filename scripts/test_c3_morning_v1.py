"""Synthetic boundary faults, never market/Telegram delivery evidence."""
import copy,json,tempfile,unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock
from c3_morning_source_v1 import prior_session,verify_calendar,bounded_target,compare,cache_rows,normalized_hash
from c3_company_quality_review_v1 import statement_facts,join_quality,collect
from c3_candidate_entry_review_v2 import all_geometry_reasons,usable


class CalendarAndSourceTests(unittest.TestCase):
    def test_latest_prior_session_on_regular_day_monday_and_holiday(self):
        for clock,expected in [('2026-11-12T08:10:00+09:00','2026-11-11'),
            ('2026-11-16T08:10:00+09:00','2026-11-13'),
            ('2026-03-03T08:10:00+09:00','2026-02-27'),
            ('2026-10-12T08:10:00+09:00','2026-10-08')]:
            self.assertEqual(prior_session(datetime.fromisoformat(clock))['requested_day'],expected)
    def test_delayed_morning_job_never_switches_to_todays_completed_bar(self):
        r=prior_session(datetime.fromisoformat('2026-11-12T22:00:00+09:00'))
        self.assertEqual(r['requested_day'],'2026-11-11')
    def test_reference_calendar_requires_both_observed_boards(self):
        self.assertEqual(verify_calendar('2026-11-11',{'KOSPI':['2026-11-11','2026-11-12'],'KOSDAQ':['2026-11-11']},'2026-11-12')['KOSPI'],'2026-11-11')
        for observed in ({'KOSPI':['2026-11-11']},{'KOSPI':['2026-11-11'],'KOSDAQ':['2026-11-10']}):
            with self.assertRaises(ValueError):verify_calendar('2026-11-11',observed,'2026-11-12')
    def test_empty_target_is_retried_twice_without_earlier_day_substitution(self):
        collector=Mock(return_value={'asof':'2026-11-11','official_dataset_usable':False})
        pause=Mock();_,receipts=bounded_target('2026-11-11',Path('/unused'),'',collector,pause)
        self.assertEqual(collector.call_count,2);self.assertEqual(len(receipts),2)
        self.assertTrue(all(c.args[0]=='2026-11-11' for c in collector.call_args_list))
        self.assertEqual(pause.call_count,1)
    def test_success_stops_retry_and_invalid_attempt_budget_rejected(self):
        collector=Mock(return_value={'official_dataset_usable':True});bounded_target('2026-11-11','/unused','',collector)
        self.assertEqual(collector.call_count,1)
        with self.assertRaises(ValueError):bounded_target('2026-11-11','/unused','',collector,attempts=3)
    def test_name_market_date_and_every_price_field_must_match(self):
        row=dict(ticker='000001',name='SYNTHETIC',market='KOSPI',asof='2026-11-11',open=100,high=110,low=90,close=105,volume=1000,turnover_krw=100000)
        self.assertEqual(compare([row],[row],'2026-11-11')['compared_rows'],1)
        for key in ('name','market','asof','open','high','low','close','volume','turnover_krw'):
            other=dict(row);other[key]=other[key]+1 if isinstance(other[key],int) else 'DIFFERENT'
            with self.assertRaises(ValueError):compare([row],[other],'2026-11-11')
        self.assertEqual(normalized_hash([row]),normalized_hash([dict(row)]))
    def test_kosdaq_global_is_kept_konex_excluded_duplicates_rejected(self):
        header='Code,Name,Market,MarketId,Open,High,Low,Close,Volume,Amount\n'
        raw=(header+'000001,SYNTHETIC,KOSDAQ GLOBAL,KSQ,10,11,9,10,100,1000\n000002,SYNTHETIC,KONEX,KNX,10,11,9,10,100,1000\n').encode()
        rows,excluded=cache_rows(raw,'2026-11-11');self.assertEqual(len(rows),1);self.assertEqual(rows[0]['market'],'KOSDAQ');self.assertEqual(excluded,{'KONEX':1})
        with self.assertRaises(ValueError):cache_rows(raw+raw.split(b'\n')[1]+b'\n','2026-11-11')


def payload(receipt='20260814000001',division='CFS'):
    common=dict(rcept_no=receipt,bsns_year='2026',reprt_code='11012',fs_div=division,currency='KRW')
    vals=[('IS','ifrs-full_Revenue',100,80),('IS','dart_OperatingIncomeLoss',20,10),
          ('BS','ifrs-full_Assets',1000,None),('BS','ifrs-full_Liabilities',400,None),
          ('BS','ifrs-full_Equity',600,None),('CF','ifrs-full_CashFlowsFromUsedInOperatingActivities',30,None)]
    return dict(status='000',list=[dict(common,sj_div=s,account_id=k,thstrm_amount=str(v),frmtrm_q_amount=str(prev) if prev else '') for s,k,v,prev in vals])


class FinancialAndGeometryTests(unittest.TestCase):
    def test_actual_period_division_currency_and_receipt_required(self):
        filing=dict(receipt_no='20260814000001',published_on='2026-08-14')
        facts=statement_facts(payload(),filing,'CFS',2026,'11012')
        self.assertEqual(facts['revenue_krw'],100);self.assertEqual(facts['operating_cashflow_ytd_krw'],30)
        for key,value in [('rcept_no','20261112000001'),('currency','USD'),('fs_div','OFS'),('bsns_year','2025'),('reprt_code','11011')]:
            p=payload();p['list'][0][key]=value
            with self.assertRaises(ValueError):statement_facts(p,filing,'CFS',2026,'11012')
    def test_snapshot_is_never_original_pit_or_buy_approval(self):
        e=dict(price_asof='2026-11-11',reviewed_technical_tickers=149,new_research_top2=[{'ticker':'000001'}])
        q=dict(asof='2026-11-11',companies=[dict(ticker='000001',status='DATED_MATCHING_RECEIPT_SNAPSHOT_NOT_PIT_VERIFIED',latest_statement={})])
        r=join_quality(e,q);self.assertEqual(r['final_top2'],[]);self.assertFalse(r['buy_approved']);self.assertIsNone(r['final_candidate_count'])
        q['asof']='2026-11-12'
        with self.assertRaises(ValueError):join_quality(e,q)
    def test_geometry_reports_all_reasons_and_preserves_original_prices(self):
        p=dict(low=59400,high=62600,stop=56100,resistance=67700,risk_pct=10.383,net_r1_rr=.6489)
        before=copy.deepcopy(p);reasons=all_geometry_reasons(p,66400)
        self.assertIn('STRUCTURE_STOP_TOO_FAR',reasons);self.assertIn('FIRST_RESISTANCE_REWARD_TOO_SMALL',reasons)
        self.assertFalse(usable(p,66400)[0]);self.assertEqual(p,before)
        p=dict(low=118000,high=122000,stop=113800,resistance=None,risk_pct=6.72,net_r1_rr=None)
        r=all_geometry_reasons(p,204000)
        self.assertIn('MISSING_FINITE_R1_OR_GEOMETRY',r);self.assertIn('STALE_ENTRY_TOO_FAR_BELOW_CLOSE',r)


if __name__=='__main__':unittest.main()
