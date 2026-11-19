import unittest
from c3_top5_financial_selection import select
G={"asof":"20261119","candidates":[
 {"code":"111111","name":"A","status":"ENTRY_READY","risk_pct":3},
 {"code":"222222","name":"B","status":"NEAR_ENTRY","risk_pct":4},
 {"code":"333333","name":"C","status":"ENTRY_READY","risk_pct":6}]}
F={"asof":"20261119","status":"PARTIAL_OR_FAILED_FINANCIAL_GATE",
   "researched":[{"ticker":"111111","financial_screen_pass":True},
                {"ticker":"222222","financial_screen_pass":False}]}
class SelectionTests(unittest.TestCase):
 def test_financial_gate_and_risk(self):
  x=select(G,F)
  self.assertEqual([v["code"] for v in x["selected"]],["111111"])
  self.assertFalse(x["trade_approved"])
 def test_entry_ready_precedes_near_and_scores_sort(self):
  g={"asof":"20261119","candidates":[
    {"code":"222222","status":"ENTRY_READY","risk_pct":3,"opportunity_score":20},
    {"code":"111111","status":"ENTRY_READY","risk_pct":3,"opportunity_score":90},
    {"code":"333333","status":"NEAR_ENTRY","risk_pct":3,"opportunity_score":99}]}
  f={**F,"researched":[{"ticker":x,"financial_screen_pass":True} for x in ("111111","222222","333333")]}
  self.assertEqual([x["code"] for x in select(g,f)["selected"]],["111111","222222","333333"])
 def test_next_day_research_is_visible_but_never_certified(self):
  f={**F,"status":"NEXT_DAY_FINANCIAL_RESEARCH_NOT_PIT_CERTIFIED"}
  x=select(G,f)
  self.assertEqual(x["selected_count"],1)
  self.assertTrue(x["coverage_complete"])
  self.assertFalse(x["point_in_time_certified"])
  self.assertEqual(x["decision"],"CASH")
 def test_missing_coverage_blocks(self):
  x=select(G,{**F,"researched":F["researched"][:1]})
  self.assertFalse(x["coverage_complete"])
  self.assertEqual(x["selected_count"],0)
 def test_mismatched_date_is_cash(self):
  self.assertEqual(select(G,{**F,"asof":"20261118"})["selected_count"],0)
 def test_missing_financial_is_cash(self):
  self.assertEqual(select(G,{})["selected_count"],0)
if __name__=="__main__":unittest.main()
