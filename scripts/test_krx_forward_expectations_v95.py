#!/usr/bin/env python3
"""No-network tests for v9.5 point-in-time research safety gates."""
from __future__ import annotations
import sys,unittest,tempfile,csv,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import exchange_calendars as xcals
import krx_forward_expectations_v95 as v

SHA='a'*64

def F(receipt='20250310000001', filing='2025-03-10', value='100', metric='FORECAST_OPERATING_PROFIT_KRW',
      period='FY2025', fs='CFS', entity='ISSUER', amendment='False', evidence=v.GOOD_EVIDENCE):
    return {'ticker':'083450','receipt_no':receipt,'filing_date':filing,'metric':metric,
            'fiscal_period':period,'fs_div':fs,'entity_scope':entity,'value_krw':value,
            'original_archive_sha256':SHA,'evidence_status':evidence,'is_amendment':amendment,
            'source_url':f'https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}'}

class Tests(unittest.TestCase):
 def setUp(self):self.cal=xcals.get_calendar('XKRX')
 def e(self,rcp,filing,signal,**other):
    return dict(ticker='083450',receipt_no=rcp,filing_date=filing,
                signal_date=signal,report_name=other.get('report_name','영업실적등에대한전망'),
                event_type=other.get('event_type','EARNINGS_PREVIEW'),
                first_usable_session=other.get('first_usable_session',''),is_amendment=other.get('is_amendment','False'))
 def test_receipt_filing_after_market_used_next_session(self):
    self.assertEqual(v.next_krx_session('2025-03-10',self.cal),'2025-03-11')
 def test_weekend_filing_monday(self):
    self.assertEqual(v.next_krx_session('2025-03-08',self.cal),'2025-03-10')
 def test_legacy_forecast_label_corrected(self):
    self.assertEqual(v.event_type({'report_name':'영업실적등에대한전망(공정공시)','event_type':'EARNINGS_PREVIEW'}),'FORECAST_DISCLOSURE')
 def test_future_filing_not_asof(self):
    e=self.e('20250310000001','2025-03-10','2025-03-10')
    out=v.inspect_events([e],{('083450','2025-03-10')},self.cal)
    self.assertEqual(out[0]['asof_eligible'],'False')
 def test_supplied_earlier_session_does_not_backdate(self):
    e=self.e('20250310000001','2025-03-10','2025-03-11',first_usable_session='2025-03-10')
    out=v.inspect_events([e],{('083450','2025-03-11')},self.cal)
    self.assertEqual(out[0]['usable_session'],'2025-03-11')
 def test_nonmatching_receipt_date_discarded(self):
    self.assertEqual(v.inspect_events([self.e('20250311000001','2025-03-10','2025-03-11')],{('083450','2025-03-11')},self.cal),[])
 def test_old_amendment_never_fresh(self):
    e=self.e('20250310000001','2025-03-10','2025-03-11',report_name='[기재정정]영업실적등에대한전망')
    out=v.inspect_events([e],{('083450','2025-03-11')},self.cal)
    self.assertEqual(out[0]['fresh_0_10'],'False')
 def test_duplicate_event_dedup(self):
    e=self.e('20250310000001','2025-03-10','2025-03-11')
    self.assertEqual(len(v.inspect_events([e,e],{('083450','2025-03-11')},self.cal)),1)
 def test_raw_amount_missing_evidence_rejected(self):
    good=F(evidence='RAW_UNVERIFIED_AMOUNT_CANDIDATE')
    rows,rejected=v.inspect_forecasts([good],self.cal)
    self.assertEqual(len(rows),0);self.assertIn('ORIGINAL_PERIOD_AMOUNT_NOT_EVIDENCED',rejected[0]['reason'])
 def test_scope_rejected_if_unknown(self):
    rows,rejected=v.inspect_forecasts([F(entity='UNKNOWN')],self.cal)
    self.assertEqual(len(rows),0);self.assertIn('ENTITY_SCOPE_UNKNOWN',rejected[0]['reason'])
 def test_receipt_and_fiscal_period_rejected(self):
    rows,rejected=v.inspect_forecasts([F(receipt='20250311000001',period='???')],self.cal)
    self.assertEqual(len(rows),0);self.assertIn('RECEIPT_DATE_MISMATCH',rejected[0]['reason'])
 def test_company_guidance_revision_up(self):
    a=F(value='100');b=F(receipt='20250410000001',filing='2025-04-10',value='125')
    rows,rej=v.inspect_forecasts([a,b],self.cal)
    result=v.compute_revisions(rows,{('083450','2025-04-11')},self.cal)
    self.assertEqual(len(result),1);self.assertEqual(result[0]['change_pct'],25.0)
    self.assertEqual(result[0]['direction'],'UP')
    self.assertEqual(result[0]['strict_pit_approved'],'False')
    self.assertIn('NOT_ANALYST_CONSENSUS',result[0]['source_type'])
 def test_future_revision_is_not_visible_to_old_signal(self):
    rows,_=v.inspect_forecasts([F(),F(receipt='20250410000001',filing='2025-04-10',value='125')],self.cal)
    self.assertEqual(v.compute_revisions(rows,{('083450','2025-03-18')},self.cal),[])
 def test_no_cross_fiscal_year(self):
    rows,_=v.inspect_forecasts([F(period='FY2025'),F(receipt='20250410000001',filing='2025-04-10',period='FY2026',value='125')],self.cal)
    self.assertEqual(v.compute_revisions(rows,{('083450','2025-04-11')},self.cal),[])
 def test_no_mix_subsidiary_or_cfs(self):
    a=F(entity='ISSUER');b=F(receipt='20250410000001',filing='2025-04-10',entity='SUBSIDIARY',value='125')
    rows,_=v.inspect_forecasts([a,b],self.cal)
    self.assertEqual(v.compute_revisions(rows,{('083450','2025-04-11')},self.cal),[])
 def test_no_expired_forecast_on_later_signal(self):
    rows,_=v.inspect_forecasts([F(period='2025Q1'),F(receipt='20250312000001',filing='2025-03-12',period='2025Q1')],self.cal)
    self.assertEqual(v.compute_revisions(rows,{('083450','2025-04-11')},self.cal),[])
 def test_profit_turnaround_not_arbitrary_percentage(self):
    cat,pct=v.direction_change(-100,20,'FORECAST_OPERATING_PROFIT_KRW')
    self.assertEqual(cat,'LOSS_TO_PROFIT');self.assertIsNone(pct)
 def test_loss_narrowing_not_growth_percent(self):
    cat,pct=v.direction_change(-100,-40,'FORECAST_OPERATING_PROFIT_KRW')
    self.assertEqual(cat,'LOSS_NARROWING');self.assertIsNone(pct)
 def test_amendment_new_not_fresh_revision(self):
    rows,_=v.inspect_forecasts([F(),F(receipt='20250410000001',filing='2025-04-10',value='125',amendment='True')],self.cal)
    self.assertEqual(v.compute_revisions(rows,{('083450','2025-04-11')},self.cal),[])
 def test_same_session_not_comparable(self):
    rows,_=v.inspect_forecasts([F(receipt='20250310000001'),F(receipt='20250310000002',value='125')],self.cal)
    self.assertEqual(v.compute_revisions(rows,{('083450','2025-03-11')},self.cal),[])
 def test_sparse_stale_event_no_revision(self):
    with tempfile.TemporaryDirectory() as d:
      path=Path(d)
      v.write_csv(path/'candidate.csv',[{'ticker':'083450','signal_date':'2025-05-01','signal_score':'70'}],['ticker','signal_date','signal_score'])
      ev=self.e('20250310000001','2025-03-10','2025-05-01')
      v.write_csv(path/'events.csv',[ev],list(ev.keys()))
      result=v.run(path/'candidate.csv',path/'events.csv',path/'no-amount',path/'no-forecast',path/'out')
      self.assertEqual(result['candidate_signals'],1)
      self.assertEqual(result['fresh_nonamend_events'],0)
      self.assertEqual(result['company_guidance_revision_pairs_provisional'],0)
      self.assertFalse(result['strict_pit_approved'])
 def test_empty_event_successful_nonzero_candidates(self):
    with tempfile.TemporaryDirectory() as d:
      path=Path(d);p=path/'candidates.csv'
      v.write_csv(p,[{'ticker':'083450','signal_date':'2025-03-11','signal_score':'99'}],['ticker','signal_date','signal_score'])
      result=v.run(p,path/'noevents',path/'noamounts',path/'noforecasts',path/'reports')
      self.assertEqual(result['candidate_signals'],1)
      self.assertEqual(result['events_with_usable_asof'],0)
      self.assertTrue((path/'reports/v95_candidate_expectation_audit.csv').exists())

if __name__=='__main__':unittest.main(verbosity=2)
