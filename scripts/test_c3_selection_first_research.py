import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_selection_first_research import eligible,research,selection_outcome,candidate
def bars():
 return [{"ticker":"000001","date":f"2026-{1+i//28:02d}-{1+i%28:02d}",
          "open":100+i*.3,"high":103+i*.3,"low":98+i*.3,
          "close":101+i*.3,"volume":1000+i*2} for i in range(85)]
def finance(day):
 return {"schema":"opendart_annual_research_v1","asof":day,"researched":[{
 "ticker":"000001","status":"DATED_ANNUAL_RESEARCH_ONLY","financial_screen_pass":True,
 "annual_plus_interim_growth_pass":True,"recent_financial_weakening_veto":False,
 "sector_id":"IT","receipt_date":"2026-01-01","latest_periodic_receipt_date":"2026-01-15"}]}
class SelectionTests(unittest.TestCase):
 def test_financial_asof_gate(self):
  b=bars();d=b[80]["date"];self.assertEqual(len(eligible(finance(d),d)),1)
  self.assertEqual(len(eligible(finance(d),b[79]["date"])),0)
 def test_future_receipt_rejected(self):
  b=bars();d=b[80]["date"];f=finance(d);f["researched"][0]["receipt_date"]="2027-01-01"
  self.assertEqual(len(eligible(f,d)),0)
 def test_future_price_not_used_for_ranking(self):
  b=bars();d=b[80]["date"];r1=research(b,finance(d),d)
  b[82]["high"]*=2;b[82]["close"]*=2
  r2=research(b,finance(d),d)
  self.assertEqual([(x["ticker"],x["research_proxy"],x["entry1_range"]) for x in r1["top2_research"]],
                   [(x["ticker"],x["research_proxy"],x["entry1_range"]) for x in r2["top2_research"]])
 def test_selection_outcome_censored(self):
  self.assertEqual(selection_outcome(bars(),80)["20"]["status"],"CENSORED")
 def test_missing_financials_fail_cash(self):
  b=bars();d=b[80]["date"];r=research(b,{},d)
  self.assertEqual(r["top2_research"],[]);self.assertEqual(r["decision"],"CASH")
 def test_benchmark_future_window_blocked(self):
  b=bars()
  with self.assertRaises(ValueError):
   candidate(b,80,{},[100.0]*22)
if __name__=="__main__":unittest.main()
