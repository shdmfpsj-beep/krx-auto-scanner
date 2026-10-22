#!/usr/bin/env python3
"""Safe dated DART financial-to-stock join tests."""
import unittest
from sector_financial_join import join,render

ASOF="2026-10-22"
BASE=dict(asof=ASOF,sector_top3=[
    dict(sector_id="SEMICON"),dict(sector_id="POWER"),dict(sector_id="SHIP")],
    stock_research_top5=[dict(ticker="005930",name="삼성전자",sector_id="SEMICON",
                                proxy_index=90,final_verified_score=None)])
def research(receipt_date="2026-03-18",ticker="005930",sector="SEMICON",pass_=True):
    return dict(ticker=ticker,name="삼성전자",sector_id=sector,
        research_proxy_index="90",status="DATED_ANNUAL_RESEARCH_ONLY",
        financial_quality="ANNUAL_GROWTH_AND_MARGIN_OBSERVED" if pass_ else "ANNUAL_RISK_OR_SLOWDOWN",
        financial_screen_pass=pass_,receipt_date=receipt_date,
        annual_fiscal_year=2025,receipt_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318000001",
        sales_yoy_pct=12,operating_margin_pct=8,division="CFS")
def source(rows,asof=ASOF):
    return dict(schema="opendart_annual_research_v1",asof=asof,
        status="ANNUAL_RESEARCH_READ",researched=rows)

class FinancialJoinTests(unittest.TestCase):
    def test_annual_growth_research_is_not_trade_approval(self):
        r=join(BASE,source([research()]))
        self.assertEqual(len(r["financial_quality_watch_top5"]),1)
        self.assertTrue(r["stock_research_top5"][0]["fundamentals_filing_verified"])
        self.assertIsNone(r["stock_research_top5"][0]["final_verified_score"])
        self.assertEqual(r["decision"],"CASH")
        self.assertFalse(r["trade_approved"])
        self.assertIn("실적 검증",render(r,"# sector report"))
    def test_newer_semiannual_receipt_does_not_upgrade_annual_growth_to_quarterly(self):
        data=research()
        data["latest_periodic_receipt_date"]="2026-08-14"
        data["latest_periodic_report_name"]="반기보고서 (2026.06)"
        data["latest_periodic_financials_analyzed"]=False
        result=join(BASE,source([data]))
        top=result["stock_research_top5"][0]
        self.assertEqual(top["latest_periodic_receipt_date"],"2026-08-14")
        self.assertFalse(top["latest_periodic_financials_verified"])
        self.assertFalse(result["fundamentals_full_final_15_points_scored"])
        self.assertIn("연간 수치",render(result,"# research"))
    def test_missing_or_stale_finance_never_receives_fifteen_points(self):
        for financing in ({},source([research()],"2026-10-21")):
            r=join(BASE,financing)
            self.assertEqual(r["financial_quality_watch_top5"],[])
            self.assertFalse(r["fundamentals_full_final_15_points_scored"])
            self.assertEqual(r["stock_research_top5"][0]["financial_quality"],"NOT_VERIFIED")
    def test_out_of_asof_future_filing_is_excluded(self):
        r=join(BASE,source([research(receipt_date="2026-10-23")]))
        self.assertEqual(r["financial_quality_watch_top5"],[])
        self.assertFalse(r["stock_research_top5"][0]["fundamentals_filing_verified"])
    def test_non_top3_sector_cannot_leak_into_financial_watch(self):
        r=join(BASE,source([research(sector="OTHER")]))
        self.assertEqual(r["financial_quality_watch_top5"],[])
    def test_profit_or_revenue_caution_does_not_pass_quality_screen(self):
        r=join(BASE,source([research(pass_=False)]))
        self.assertTrue(r["stock_research_top5"][0]["fundamentals_filing_verified"])
        self.assertFalse(r["stock_research_top5"][0]["financial_screen_pass"])
        self.assertEqual(r["financial_quality_watch_top5"],[])
    def test_price_only_top5_order_remains_stable(self):
        b={**BASE,"stock_research_top5":[
            BASE["stock_research_top5"][0],
            dict(ticker="000660",name="SK하이닉스",sector_id="SEMICON",
                 proxy_index=98)]}
        f=source([research(),research(ticker="000660")])
        r=join(b,f)
        self.assertEqual([x["ticker"] for x in r["stock_research_top5"]],
                         ["005930","000660"])
        self.assertEqual(len(r["financial_quality_watch_top5"]),2)

if __name__=="__main__":unittest.main()
