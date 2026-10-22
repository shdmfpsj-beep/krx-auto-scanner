#!/usr/bin/env python3
"""Offline annual DART statement and PIT safety regression tests."""
import io,zipfile,unittest,csv,tempfile
from pathlib import Path
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
    def test_absent_account_detail_is_valid_for_normal_bs_is_rows(self):
        # OpenDART full annual statements may omit account_detail entirely.
        rows=[{k:v for k,v in x.items() if k!="account_detail"}
              for x in good_rows()]
        r=evaluate_accounts(dict(status="000",list=rows),"CFS")
        self.assertEqual(r["status"],"DATED_ANNUAL_RESEARCH_ONLY")
        self.assertEqual(r["missing_metric_keys"],[])
        self.assertEqual(r["sales_yoy_pct"],25)
    def test_cis_standard_revenue_fallback_when_is_row_unavailable(self):
        rows=good_rows()
        rows[0]["sj_div"]="CIS"
        r=evaluate_accounts(dict(status="000",list=rows),"CFS")
        self.assertEqual(r["status"],"DATED_ANNUAL_RESEARCH_ONLY")
    def test_conflicting_is_values_do_not_fall_through_to_cis(self):
        rows=good_rows()+[row("IS","ifrs-full_Revenue",125,80)]
        rows.append({**row("CIS","ifrs-full_Revenue",100,80)})
        r=evaluate_accounts(dict(status="000",list=rows),"CFS")
        self.assertEqual(r["status"],"ANNUAL_METRICS_INCOMPLETE")
        self.assertIn("revenue_krw",r["missing_metric_keys"])
    def test_missing_metric_diagnostic_does_not_include_private_key(self):
        rows=[row("BS","ifrs-full_Assets",250)]
        r=evaluate_accounts(dict(status="000",list=rows),"CFS")
        self.assertEqual(r["status"],"ANNUAL_METRICS_INCOMPLETE")
        self.assertIn("revenue_krw",r["missing_metric_keys"])
        self.assertEqual(r["available_statement_rows"],1)
    def test_research_financial_calls_balanced_across_three_sectors(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"candidate.csv"
            fields=["ticker","name","sector_id","asof","research_proxy_index"]
            rows=[]
            for i in range(20):
                rows.append(dict(ticker=f"{i+1:06d}",name=f"Semiconductor{i}",
                    sector_id="SEMICON",asof=str(ASOF),
                    research_proxy_index=str(100-i)))
            for sid,prefix in (("POWER",200),("CONSTRUCTION",300)):
                for i in range(10):
                    rows.append(dict(ticker=f"{prefix+i:06d}",name=f"{sid}{i}",
                        sector_id=sid,asof=str(ASOF),research_proxy_index=str(50-i)))
            with path.open("w",encoding="utf-8",newline="") as fp:
                w=csv.DictWriter(fp,fieldnames=fields)
                w.writeheader();w.writerows(rows)
            chosen=read_stocks(path,str(ASOF),limit=20,
                     sector_ids=["SEMICON","POWER","CONSTRUCTION"])
            counts={sid:sum(r["sector_id"]==sid for r in chosen)
                for sid in ("SEMICON","POWER","CONSTRUCTION")}
            self.assertEqual(len(chosen),20)
            self.assertEqual(counts,{"SEMICON":7,"POWER":7,"CONSTRUCTION":6})
            self.assertEqual(chosen[0]["sector_id"],"SEMICON")
    def test_financial_screen_ignores_pharma_and_outside_top3(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"candidate.csv"
            with path.open("w",encoding="utf-8",newline="") as fp:
                w=csv.DictWriter(fp,fieldnames=["ticker","name","sector_id","asof"])
                w.writeheader()
                w.writerows([
                    dict(ticker="005930",name="삼성전자",sector_id="SEMICON",asof=str(ASOF)),
                    dict(ticker="000660",name="바이오주",sector_id="SEMICON",asof=str(ASOF)),
                    dict(ticker="010120",name="엘에스",sector_id="OTHER",asof=str(ASOF))])
            result=read_stocks(path,str(ASOF),sector_ids=["SEMICON"])
            self.assertEqual([x["ticker"] for x in result],["005930"])
    def test_dart_full_statement_omits_fs_div_from_rows(self):
        # The request explicitly sets fs_div=CFS; response rows may omit it.
        rows=[{k:v for k,v in x.items() if k!="fs_div"} for x in good_rows()]
        r=evaluate_accounts({"status":"000","list":rows},"CFS")
        self.assertEqual(r["status"],"DATED_ANNUAL_RESEARCH_ONLY")
        self.assertEqual(r["payload_row_count"],len(rows))
        self.assertEqual(r["division_unlabeled_row_count"],len(rows))
        self.assertEqual(r["sales_yoy_pct"],25)
    def test_explicit_other_division_cannot_leak_into_requested_statement(self):
        rows=[{**x,"fs_div":"OFS"} for x in good_rows()]
        r=evaluate_accounts({"status":"000","list":rows},"CFS")
        self.assertEqual(r["status"],"ANNUAL_METRICS_INCOMPLETE")
        self.assertEqual(r["payload_row_count"],len(rows))
        self.assertEqual(r["available_statement_rows"],0)
    def test_financial_api_unavailable_has_safe_status_without_raw_query(self):
        r=evaluate_accounts({"status":"013"},"CFS")
        self.assertEqual(r["status"],"FINANCIAL_API_UNAVAILABLE")
        self.assertEqual(r["source_api_status"],"013")
        self.assertEqual(r["payload_row_count"],0)
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
