import datetime
import unittest
from unittest.mock import patch
from scripts import c3_quality_context as q

class ContextTests(unittest.TestCase):
    def test_accounting_and_improvement(self):
        rows=[]
        def row(k,id,section,cur,prev=None):
            rows.append({"account_id":id,"sj_div":section,"thstrm_amount":str(cur),
                "frmtrm_amount":str(prev) if prev is not None else "-"})
        row("","ifrs-full_Equity","BS",60)
        row("","ifrs-full_Assets","BS",100)
        row("","ifrs-full_Liabilities","BS",40)
        row("","ifrs-full_Revenue","IS",150,100)
        row("","dart_OperatingIncomeLoss","IS",20,10)
        filing={"rcept_dt":"20260320","rcept_no":"20260320000001",
                "report_nm":"사업보고서 (2025.12)"}
        def fake(path,params,key):
            if path=="list.json":return {"status":"000","list":[filing]}
            return {"status":"000","list":rows}
        with patch.object(q,"get_json",side_effect=fake):
            values,filings,status=q.annual_asof("12345678","x",datetime.date(2026,11,18))
        self.assertEqual(status,"VERIFIED_ANNUAL")
        self.assertEqual(values["profit_prev"],10)
        self.assertEqual(values["equity"],60)
    def test_future_filing_not_used(self):
        with patch.object(q,"get_json",return_value={"status":"000","list":[
            {"rcept_dt":"20261119","report_nm":"사업보고서 (2025.12)"}]}):
            values,_,status=q.annual_asof("12345678","x",datetime.date(2026,11,18))
        self.assertIsNone(values)
        self.assertEqual(status,"NO_FILED_ANNUAL")
    def test_missing_key_neutral(self):
        candidates=[{"code":"123456","name":"Example","geometry_validated":True,
                     "opportunity_score":70,"entry_status":"ENTRY_READY"}]
        result,audit=q.enrich(candidates,"20261118","")
        self.assertEqual(audit["status"],"DART_KEY_MISSING_OR_INVALID")
        self.assertEqual(result,candidates)
    def test_negative_equity_risk(self):
        data={"equity":-1,"assets":100,"liabilities":101,"sales":100,
              "sales_prev":90,"profit":2,"profit_prev":1,
              "filing_date":"20260320","fiscal_year":2025}
        candidate={"code":"123456","name":"Example","geometry_validated":True,
                   "opportunity_score":70,"entry_status":"ENTRY_READY"}
        with patch.object(q,"corps",return_value={"123456":"12345678"}),\
             patch.object(q,"annual_asof",return_value=(data,[],"VERIFIED_ANNUAL")),\
             patch.object(q.datetime,"datetime",FrozenDatetime):
            result,audit=q.enrich([candidate],"20261118","a"*40)
        self.assertTrue(result[0]["quality_risk_flag"])
        self.assertEqual(result[0]["context_status"],"NONPOSITIVE_EQUITY")

if __name__=="__main__":unittest.main()
