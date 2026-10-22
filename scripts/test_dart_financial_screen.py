#!/usr/bin/env python3
"""Offline annual DART statement and PIT safety regression tests."""
import io,zipfile,unittest
from datetime import date
from dart_financial_screen import (
    annual_receipt,parse_corps,extract_metric,evaluate_accounts,collect,render,
    read_stocks)

ASOF=date(2026,10,22)
TICKER=dict(ticker="005930",name="삼성전자",sector_id="SEMICON",research_proxy_index="87")
def row(kind,account,now,prev=None):
    return dict(fs_div="CFS",sj_div=kind,account_id=account,account_detail="-",
        thstrm_amount=str(now),frmtrm_amount=str(prev) if prev is not None else "")
def good_rows(revenue=100,previous=80,operating=12,previous_operating=5):
    return [row("IS","ifrs-full_Revenue",revenue,previous),
        row("IS","dart_OperatingIncomeLoss",operating,previous_operating),
        row("BS","ifrs-full_Assets",250),
        row("BS","ifrs-full_Liabilities",100),
        row("BS","ifrs-full_Equity",150)]
def filing(received="20260318",year=2025):
    return dict(status="000",list=[
        dict(report_nm=f"사업보고서 ({year}.12)",rcept_dt=received,
             rcept_no="20260318000001")])

class DartAnnualTests(unittest.TestCase):
    def test_corp_code_zip_maps_six_digit_ticker(self):
        xml=b"""<?xml version="1.0" encoding="UTF-8"?>
          <result><list><corp_code>00126380</corp_code><corp_name>Samsung</corp_name>
          <stock_code>005930</stock_code></list></result>"""
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,"w") as f:f.writestr("CORPCODE.xml",xml)
        self.assertEqual(parse_corps(stream.getvalue()),{"005930":"00126380"})
    def test_annual_filing_must_be_published_before_asof(self):
        self.assertIsNotNone(annual_receipt(filing(),"2025",ASOF))
        self.assertIsNone(annual_receipt(filing(received="20261023"),"2025",ASOF))
        self.assertIsNone(annual_receipt(filing(year=2024),"2025",ASOF))
    def test_annual_accounts_yoy_uses_same_period_and_confirms_balance_sheet(self):
        r=evaluate_accounts(dict(status="000",list=good_rows()),"CFS")
        self.assertEqual(r["status"],"DATED_ANNUAL_RESEARCH_ONLY")
        self.assertEqual(r["sales_yoy_pct"],25)
        self.assertEqual(r["operating_margin_pct"],12)
        self.assertEqual(r["accounting_identity_gap_pct"],0)
        self.assertEqual(r["financial_quality"],"ANNUAL_GROWTH_AND_MARGIN_OBSERVED")
    def test_profit_or_revenue_decline_is_caution_not_growth(self):
        r=evaluate_accounts(dict(status="000",list=good_rows(revenue=70,operating=-10)),"CFS")
        self.assertEqual(r["financial_quality"],"ANNUAL_RISK_OR_SLOWDOWN")
    def test_inconsistent_balance_sheet_blocks_quality(self):
        rows=good_rows()
        rows[-1]["thstrm_amount"]="140"
        r=evaluate_accounts(dict(status="000",list=rows),"CFS")
        self.assertEqual(r["status"],"BALANCE_SHEET_INCONSISTENT")
        self.assertEqual(r["financial_quality"],"UNVERIFIED")
    def test_duplicate_revenue_conflict_fails_closed(self):
        rows=good_rows()+[row("IS","ifrs-full_Revenue",120,80)]
        r=evaluate_accounts(dict(status="000",list=rows),"CFS")
        self.assertEqual(r["status"],"ANNUAL_METRICS_INCOMPLETE")
    def test_missing_api_key_reports_unverified_and_keeps_cash(self):
        r=collect(ASOF,[TICKER],key=None,today=ASOF)
        self.assertEqual(r["status"],"MISSING_DART_KEY")
        self.assertEqual(r["researched"],[])
        self.assertEqual(r["decision"],"CASH")
    def test_historical_replay_disallows_later_data_even_with_secret(self):
        called=[]
        def fake(*args):
            called.append(args)
            raise AssertionError("No external API should be touched")
        r=collect(date(2026,10,21),[TICKER],key="a"*40,
                  request_json=fake,get_corps=fake,today=ASOF)
        self.assertEqual(called,[])
        self.assertEqual(r["status"],"HISTORICAL_REPLAY_NO_RETROACTIVE_FINANCIALS")
    def test_cfs_first_and_ofs_only_when_cfs_has_no_complete_accounts(self):
        calls=[]
        def req(endpoint,params,key):
            calls.append((endpoint,params))
            if endpoint=="list.json":return filing()
            division=params["fs_div"]
            if division=="CFS":return dict(status="013")
            rows=[{**x,"fs_div":"OFS"} for x in good_rows()]
            return dict(status="000",list=rows)
        r=collect(ASOF,[TICKER],key="a"*40,today=ASOF,
            get_corps=lambda key:{"005930":"00126380"},request_json=req)
        self.assertEqual(r["researched"][0]["division"],"OFS")
        self.assertEqual(r["researched"][0]["status"],"DATED_ANNUAL_RESEARCH_ONLY")
        self.assertEqual(r["screen_pass_count"],1)
        self.assertFalse(r["trade_approved"])
        self.assertIn("삼성전자",render(r))
    def test_no_historical_filing_blocks_api_financial_accounts(self):
        calls=[]
        def req(endpoint,params,key):
            calls.append(endpoint)
            return dict(status="000",list=[])
        r=collect(ASOF,[TICKER],key="a"*40,today=ASOF,
             get_corps=lambda key:{"005930":"00126380"},request_json=req)
        self.assertEqual(calls,["list.json"])
        self.assertEqual(r["researched"][0]["status"],"NO_ELIGIBLE_DATED_ANNUAL_FILING")
    def test_january_uses_last_filed_annual_not_future_unpublished_year(self):
        early=date(2027,1,12)
        params_seen=[]
        def request(endpoint,params,key):
            params_seen.append(dict(params))
            if endpoint=="list.json":
                return filing(received="20260318",year=2025)
            return dict(status="000",list=good_rows())
        r=collect(early,[TICKER],key="a"*40,today=early,
                  get_corps=lambda k:{"005930":"00126380"},
                  request_json=request)
        self.assertEqual(r["researched"][0]["annual_fiscal_year"],2025)
        self.assertEqual(params_seen[-1]["bsns_year"],"2025")
        self.assertEqual(r["screen_pass_count"],1)

    def test_financial_api_error_one_stock_does_not_hide_other(self):
        two=[TICKER,{**TICKER,"ticker":"000660","name":"SK하이닉스"}]
        def req(endpoint,params,key):
            if params["corp_code"]=="00200000":raise ConnectionError()
            if endpoint=="list.json":return filing()
            return dict(status="000",list=good_rows())
        r=collect(ASOF,two,key="a"*40,today=ASOF,
          get_corps=lambda key:{"005930":"00126380","000660":"00200000"},request_json=req)
        self.assertEqual(len(r["researched"]),2)
        self.assertIn("REQUEST_FAILED",r["researched"][1]["status"])
        self.assertEqual(r["screen_pass_count"],1)

if __name__=="__main__":unittest.main()
