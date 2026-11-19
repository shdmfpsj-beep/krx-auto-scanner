import unittest
from c3_top5_financial_selection import select
G={"asof":"20261119","candidates":[
 {"code":"111111","name":"A","status":"ENTRY_READY","risk_pct":3},
 {"code":"222222","name":"B","status":"NEAR_ENTRY","risk_pct":4},
 {"code":"333333","name":"C","status":"ENTRY_READY","risk_pct":6}]}
F={"asof":"20261119","status":"PARTIAL_OR_FAILED_FINANCIAL_GATE",
   "researched":[{"ticker":"111111","financial_screen_pass":True},
                {"ticker":"222222","financial_screen_pass":False},
                {"ticker":"333333","financial_screen_pass":True}]}
class SelectionTests(unittest.TestCase):
 def test_financial_gate_and_risk(self):
  x=select(G,F)
  self.assertEqual([v["code"] for v in x["selected"]],["111111"])
  self.assertFalse(x["trade_approved"])
 def test_mismatched_date_is_cash(self):
  self.assertEqual(select(G,{**F,"asof":"20261118"})["selected_count"],0)
 def test_missing_financial_is_cash(self):
  self.assertEqual(select(G,{})["selected_count"],0)
if __name__=="__main__":unittest.main()
