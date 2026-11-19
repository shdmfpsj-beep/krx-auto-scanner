import unittest
from c3_top5_financial_selection import select, classify

G = {"asof":"20261119","candidates":[
    {"code":"111111","name":"A","status":"ENTRY_READY","risk_pct":3,"opportunity_score":70},
    {"code":"222222","name":"B","status":"NEAR_ENTRY","risk_pct":4,"opportunity_score":90},
    {"code":"333333","name":"C","status":"ENTRY_READY","risk_pct":6}]}

def record(ticker,quality="ANNUAL_POSITIVE_MIXED",interim="INTERIM_SALES_AND_PROFIT_GROWTH_OBSERVED"):
    return {"ticker":ticker,"annual_status":"DATED_ANNUAL_RESEARCH_ONLY",
            "filing_date":"2026-03-20","financial_quality":quality,
            "interim_status":"DATED_INTERIM_YTD_RESEARCH_ONLY",
            "interim_quality":interim,"interim_filing_date":"2026-11-16"}

F = {"asof":"20261119","status":"PARTIAL_OR_FAILED_FINANCIAL_GATE",
     "researched":[record("111111")],"excluded":[record("222222","ANNUAL_RISK_OR_SLOWDOWN")]}

class SelectionTests(unittest.TestCase):
    def test_risk_excluded_but_mixed_annual_can_qualify(self):
        x=select(G,F)
        self.assertEqual([v["code"] for v in x["selected"]],["111111"])
        self.assertEqual(x["financial_classifications"]["222222"],"EXCLUDED_CONFIRMED_RISK")
        self.assertFalse(x["trade_approved"])
    def test_entry_ready_precedes_near_even_with_growth_bonus(self):
        f={**F,"excluded":[record("222222","ANNUAL_GROWTH_AND_MARGIN_OBSERVED")]}
        self.assertEqual([x["code"] for x in select(G,f)["selected"]],["111111","222222"])
    def test_next_day_research_never_authorizes(self):
        x=select(G,{**F,"status":"NEXT_DAY_FINANCIAL_RESEARCH_NOT_PIT_CERTIFIED"})
        self.assertEqual(x["selected_count"],1)
        self.assertFalse(x["point_in_time_certified"])
        self.assertEqual(x["decision"],"CASH")
    def test_missing_coverage_blocks(self):
        x=select(G,{**F,"excluded":[]})
        self.assertFalse(x["coverage_complete"])
        self.assertEqual(x["selected_count"],0)
    def test_mismatched_date_blocks(self):
        self.assertEqual(select(G,{**F,"asof":"20261118"})["selected_count"],0)
    def test_missing_financial_blocks(self):
        self.assertEqual(select(G,{})["selected_count"],0)
    def test_missing_interim_is_review_not_qualified(self):
        v=record("111111")
        v["interim_quality"]=None
        self.assertEqual(classify(v),"REVIEW_INSUFFICIENT_EVIDENCE")
    def test_interim_weakening_veto(self):
        self.assertEqual(classify(record("111111",interim="INTERIM_PROFIT_OR_SALES_WEAKENING")),
                         "EXCLUDED_CONFIRMED_RISK")
if __name__=="__main__":
    unittest.main()
