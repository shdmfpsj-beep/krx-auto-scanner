import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_financial_entry_cohort import cohort
def base():
 return {"schema":"opendart_annual_research_v1","asof":"2026-11-10","researched":[
 {"ticker":"000001","receipt_date":"2026-05-01","status":"DATED_ANNUAL_RESEARCH_ONLY",
 "financial_quality":"ANNUAL_GROWTH_AND_MARGIN_OBSERVED","financial_screen_pass":True,
 "annual_plus_interim_growth_pass":True,"recent_financial_weakening_veto":False,"sector_id":"IT"}]}
class FinancialCohortTests(unittest.TestCase):
 def test_valid_research_only(self):
  r=cohort(base(),"2026-11-10")
  self.assertEqual(len(r["eligible"]),1)
  self.assertEqual(len(r["models"]),3)
  self.assertFalse(r["trade_approved"])
  self.assertFalse(r["historical_returns_certified"])
 def test_future_filing_excluded(self):
  b=base();b["researched"][0]["receipt_date"]="2026-11-11"
  self.assertEqual(len(cohort(b,"2026-11-10")["eligible"]),0)
 def test_weak_interim_veto(self):
  b=base();b["researched"][0]["recent_financial_weakening_veto"]=True
  self.assertEqual(len(cohort(b,"2026-11-10")["eligible"]),0)
 def test_asof_mismatch_fails_closed(self):
  self.assertEqual(cohort(base(),"2026-11-09")["status"],"FINANCIAL_SOURCE_DATE_OR_SCHEMA_MISMATCH")
if __name__=="__main__":unittest.main()
