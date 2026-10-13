#!/usr/bin/env python3
import csv, io, json, os, sys, tempfile, unittest, zipfile
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import exchange_calendars as xcals
import krx_forward_pit_v941 as v

class TestForwardResearch941(unittest.TestCase):
 def setUp(self):self.cal=xcals.get_calendar('XKRX')
 def raw(self,receipt,xml):
  buf=io.BytesIO()
  with zipfile.ZipFile(buf,'w') as z:z.writestr(receipt+'.xml',xml)
  return buf.getvalue()
 def test_forecast_before_actual(self):
  self.assertEqual(v.classify('영업실적등에대한전망(공정공시)')[0],'FORECAST_DISCLOSURE')
  self.assertEqual(v.classify('연결재무제표기준영업실적등에대한전망')[0],'FORECAST_DISCLOSURE')
  self.assertEqual(v.classify('매출액또는손익구조30%이상변동')[0],'EARNINGS_ACTUAL')
 def test_contract_and_amendment(self):
  typ,amend,sub=v.classify('[기재정정]단일판매ㆍ공급계약체결(자회사의 주요경영사항)')
  self.assertEqual(typ,'SUPPLY_CONTRACT');self.assertTrue(amend);self.assertTrue(sub)
 def test_asof_and_freshness(self):
  row={'ticker':'083450','signal_date':'2023-05-15','receipt_no':'20230512000202','filing_date':'2023-05-12',
  'first_usable_session':'2023-05-15','report_name':'신규시설투자등','source_url':'x'}
  normalized=v.normalize_event(row,self.cal)
  self.assertEqual(normalized['freshness'],'FRESH_0_10_SESSIONS')
  self.assertEqual(normalized['sessions_since_first_usable'],0)
  row['signal_date']='2023-05-12'
  self.assertEqual(v.normalize_event(row,self.cal)['asof_eligible'],'False')
 def test_correction_not_fresh(self):
  r={'ticker':'083450','signal_date':'2023-05-16','receipt_no':'20230512000202','filing_date':'2023-05-12',
  'first_usable_session':'2023-05-15','report_name':'[기재정정]신규시설투자등'}
  self.assertEqual(v.normalize_event(r,self.cal)['freshness'],'CORRECTION_NOT_NEW_CATALYST')
 def test_bad_receipt_day_excluded(self):
  self.assertIsNone(v.from_dart_list({'rcept_no':'20230512000202','rcept_dt':'20230515','report_nm':'신규시설투자등'},'083450','2023-05-16',self.cal))
 def test_status_migration_requires_all_four(self):
  rows=[{'receipt_no':'20230811001440','metric':x,'status':'EXACT_MATCH'} for x in [e[0] for e in v.old.METRICS]]
  self.assertTrue(v.receipt_verified(rows,'20230811001440'))
  rows[0]['status']='UNVERIFIED_MISSING_OR_MULTIPLE_XBRL_INCOME'
  self.assertFalse(v.receipt_verified(rows,'20230811001440'))
 def test_multiple_amounts_are_ambiguous(self):
  e={'ticker':'083450','signal_date':'2025-01-20','receipt_no':'20250117000001','event_type':'CAPEX','report_name':'신규시설투자','source_url':'x'}
  xml='''<doc><table><tr><td>(단위:원)</td></tr><tr><td>투자금액</td><td>1000</td></tr><tr><td>투자금액</td><td>1500</td></tr></table></doc>'''.encode()
  rows,_=v.parse_document_event_evidence(xml,e)
  self.assertEqual(rows[0]['evidence_status'],'AMBIGUOUS_VALUES_OR_UNITS')
 def test_units_required(self):
  e={'ticker':'083450','signal_date':'2025-01-20','receipt_no':'20250117000001','event_type':'SUPPLY_CONTRACT','report_name':'단일판매 공급계약','source_url':'x'}
  xml='<doc><table><tr><td>계약금액</td><td>3,500</td></tr></table></doc>'.encode()
  rows,_=v.parse_document_event_evidence(xml,e)
  self.assertEqual(rows[0]['value_krw'],'')
 def test_unit_explicit_one_candidate_unverified(self):
  e={'ticker':'083450','signal_date':'2025-01-20','receipt_no':'20250117000001','event_type':'SUPPLY_CONTRACT','report_name':'공급계약','source_url':'x'}
  xml='<doc><table><tr><td>(단위:백만원)</td></tr><tr><td>계약금액</td><td>3,500</td></tr></table></doc>'.encode()
  rows,_=v.parse_document_event_evidence(xml,e)
  self.assertEqual(rows[0]['value_krw'],3500000000)
  self.assertIn('UNVERIFIED',rows[0]['evidence_status'])
 def test_original_indexed_classes(self):
  xml='''<DOCUMENT><TABLE-GROUP ACLASS="{XBRL}IS2"><TABLE><TR><TD>포괄손익계산서 (단위:원)</TD></TR>
  <TR><TD>매출액</TD><TD>1</TD><TD>2</TD><TD>3</TD><TD>4</TD></TR>
  <TR><TD>영업이익</TD><TD>1</TD><TD>5</TD><TD>2</TD><TD>3</TD></TR></TABLE></TABLE-GROUP>
  <TABLE-GROUP ACLASS="{XBRL}BS1"><TABLE><TR><TD>재무상태표 (단위:원)</TD></TR>
  <TR><TD>부채총계</TD><TD>20</TD><TD>19</TD></TR><TR><TD>자본총계</TD><TD>40</TD><TD>35</TD></TR>
  </TABLE></TABLE-GROUP></DOCUMENT>'''.encode()
  fields,status,diag=v.read_original_numeric(xml,'CFS','11013')
  self.assertEqual(status,'PARSED_EXTENDED_CLASS')
  self.assertEqual(fields['revenue'][0],2)
 def test_duplicate_indexed_classes_not_inferred(self):
  doc='''<DOC><TABLE-GROUP ACLASS="{XBRL}IS2"><TABLE><TR><TD>(단위:원)</TD></TR><TR><TD>매출액</TD><TD>1</TD></TR><TR><TD>영업이익</TD><TD>1</TD></TR></TABLE></TABLE-GROUP></DOC>'''
  fields,status,_=v.read_original_numeric((doc+doc).encode(),'CFS','11013')
  self.assertNotEqual(status,'PARSED_EXTENDED_CLASS')
 def test_event_bulk_continuation(self):
  class Args:pass
  args=Args();args.outdir='';args.max_companies=1;args.lookback_days=100;args.max_pages=2;args.ticker='';args.asof='';args.max_retries=2;args.delay_seconds=0
  f=[{'ticker':'111111','corp_code':'00000001'},{'ticker':'222222','corp_code':'00000002'}]
  c=[{'ticker':'111111','signal_date':'2023-05-15'}, {'ticker':'222222','signal_date':'2023-05-15'}]
  def client(cc,p):return {'status':'000','total_page':'1','list':[{'rcept_no':'20230512000001','rcept_dt':'20230512','report_nm':'공급계약'}]}
  with tempfile.TemporaryDirectory() as d:
   args.outdir=d
   a=v.run_events(args,f,c,self.cal,client)
   b=v.run_events(args,f,c,self.cal,client)
   self.assertEqual((a['companies_this_run'],b['companies_this_run']),(1,1))
   self.assertEqual(b['total_distinct_ticker_signal_queries_done'],2)
   self.assertEqual(len(v.old.read_csv(Path(d)/'v941_forward_event_leads.csv')),2)
 def test_old_compared_without_numeric_evidence_is_retried(self):
  # Regression: v9.4 saved COMPARED for 0/4 fields; must NOT count as verified.
  from unittest.mock import patch
  rr={'ticker':'083450','receipt_no':'20230512000202','filing_date':'2023-05-12',
      'report_code':'11013','fs_div':'CFS','revenue_amount_krw':'100','op_profit_amount_krw':'30',
      'liabilities_amount_krw':'200','equity_amount_krw':'300'}
  xml='<DOCUMENT><TABLE-GROUP ACLASS="{XBRL}IS1"><TABLE>\n  <TR><TD>포괄손익계산서 (단위:원)</TD></TR>\n  <TR><TD>매출액</TD><TD>1</TD><TD>100</TD><TD>1</TD><TD>80</TD></TR>\n  <TR><TD>영업이익</TD><TD>1</TD><TD>30</TD><TD>1</TD><TD>20</TD></TR>\n  </TABLE></TABLE-GROUP><TABLE-GROUP ACLASS="{XBRL}BS"><TABLE>\n  <TR><TD>재무상태표 (단위:원)</TD></TR>\n  <TR><TD>부채총계</TD><TD>200</TD><TD>180</TD></TR>\n  <TR><TD>자본총계</TD><TD>300</TD><TD>270</TD></TR></TABLE></TABLE-GROUP></DOCUMENT>'
  with tempfile.TemporaryDirectory() as d:
   path=Path(d);(path/'v94_archive_attempts.json').write_text(json.dumps({'attempts':[{'receipt_no':rr['receipt_no'],'status':'COMPARED','exact_match_fields':0}]}))
   with (path/'v94_original_numeric_reconciliation.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=v.VERIFY_COLS);w.writeheader()
    for k in [m[0] for m in v.old.METRICS]:w.writerow({'receipt_no':rr['receipt_no'],'metric':k,'status':'UNVERIFIED_MISSING_OR_MULTIPLE_XBRL_INCOME'})
   class Args:pass
   a=Args();a.outdir=d;a.ticker='083450';a.archive_bundle='fixture';a.max_documents=6;a.max_retries=2;a.delay_seconds=0
   with patch.object(v.old,'choose_archives',return_value=[rr]),patch.object(v.old,'read_archives_from_bundle',return_value={rr['receipt_no']:self.raw(rr['receipt_no'],xml.encode())}):
    result=v.run_verify(a,[rr],[],self.cal)
   self.assertEqual(result['attempted_this_run'],1)
   self.assertEqual(result['new_verified_all_four'],1)
   self.assertEqual(v.read_json(path/'v941_original_attempts.json',{})['attempts'][0]['status'],'VERIFIED_ALL_FOUR')

 def test_partial_pagination_retryable(self):
  class Args:pass
  a=Args();a.outdir='';a.max_companies=1;a.lookback_days=90;a.max_pages=1;a.ticker='';a.asof='';a.max_retries=2;a.delay_seconds=0
  with tempfile.TemporaryDirectory() as d:
   a.outdir=d
   r=v.run_events(a,[{'ticker':'111111','corp_code':'00000001'}],[{'ticker':'111111','signal_date':'2023-05-15'}],self.cal,
      client=lambda cc,p:{'status':'000','total_page':'3','list':[]})
   self.assertTrue(r['warnings']);self.assertEqual(r['total_distinct_ticker_signal_queries_done'],0)
 def test_forecast_without_period_cannot_be_revision(self):
  e={'ticker':'083450','signal_date':'2025-01-20','receipt_no':'20250117000001','event_type':'FORECAST_DISCLOSURE','report_name':'영업실적 전망','source_url':'x'}
  xml='<table><tr><td>(단위:억원)</td></tr><tr><td>매출액</td><td>100</td></tr></table>'.encode()
  rows,_=v.parse_document_event_evidence(xml,e)
  self.assertEqual(rows[0]['period'],'')
  self.assertIn('no revision score',rows[0]['note'].lower())

if __name__=='__main__':unittest.main(verbosity=2)
