#!/usr/bin/env python3
"""DART direct contract filings: source-integrity, historical PIT, ZIP security."""
import io,json,unittest,zipfile
from datetime import date
from dart_contract_documents import (collect,contract_looking,dated_filings,
    zip_document,download_original,discovery_stocks,render,
    latest_preliminary_earnings)

ASOF=date(2026,10,22)
BASE=dict(asof=str(ASOF),daily_money_rank_applied=True,
          sector_top3=[dict(sector_id="POWER")],
          stock_research_top5=[dict(ticker="010120",name="LS ELECTRIC",sector_id="POWER")])
def filing(ticker="010120",corp="00123456",day="20261021",
           receipt="20261021001234",title="단일판매ㆍ공급계약체결"):
    return dict(stock_code=ticker,corp_code=corp,rcept_dt=day,
                rcept_no=receipt,report_nm=title)
def archive(xml):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("filing.xml",xml)
    return stream.getvalue()
DOC="""<?xml version="1.0" encoding="utf-8"?>
<DOCUMENT><TABLE><TR><TH>계약금액</TH><TD>50,000,000,000 원</TD></TR>
<TR><TH>계약상대</TH><TD>해외 데이터센터 발주처</TD></TR>
<TR><TH>매출액 대비</TH><TD>15%</TD></TR></TABLE></DOCUMENT>"""

class DartContractTests(unittest.TestCase):
    def test_preliminary_disclosure_withdrawal_and_later_amendment(self):
        withdrawn=filing(title="연결재무제표기준영업(잠정)실적",
                         receipt="20261021800152")
        withdrawn["rm"]="유철"
        corrected=filing(title="연결재무제표기준영업(잠정)실적",
                         receipt="20261021800153")
        corrected["rm"]="유정"
        result=latest_preliminary_earnings(
            {"status":"000","list":[withdrawn,corrected]},
            "00123456","010120",ASOF)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["receipt_no"],"20261021800153")
        self.assertTrue(result[0]["correction_flag"])
        self.assertTrue(result[0]["superseded_or_corrected"])
        self.assertFalse(result[0]["financial_figures_verified"])
    def test_preliminary_profit_fair_disclosure_is_detected_before_asof(self):
        sources=dict(status="000",list=[
            filing(title="연결재무제표기준영업(잠정)실적(공정공시)",
                   day="20261021",receipt="20261021800151"),
            filing(title="기업설명회(IR)개최(안내공시)",
                   day="20261021",receipt="20261021800160"),
            filing(title="결산실적공시 예고",day="20261020"),
            filing(ticker="005930",title="영업(잠정)실적",
                   day="20261020"),
            filing(title="연결재무제표기준영업(잠정)실적",
                   day="20261022")])
        earnings=latest_preliminary_earnings(
            sources,"00123456","010120",ASOF)
        self.assertEqual(len(earnings),1)
        self.assertEqual(earnings[0]["receipt_no"],"20261021800151")
        self.assertFalse(earnings[0]["financial_figures_verified"])
    def test_preliminary_earnings_integration_does_not_upgrade_profit(self):
        r=collect(BASE,"a"*40,today=ASOF,
           list_api=lambda *a:dict(status="000",list=[
               filing(title="연결재무제표기준영업(잠정)실적",
                      day="20261021",receipt="20261021800151")]),
           corps=lambda _:{"010120":"00123456"},
           document_reader=lambda *a:{"status":"NOT_USED"})
        issuer=r["issuer_samples"][0]
        self.assertEqual(issuer["filings"],[])
        self.assertTrue(issuer["newer_preliminary_results_require_review"])
        self.assertFalse(issuer["latest_preliminary_earnings"][0][
            "financial_figures_verified"])
        self.assertEqual(r["confirmed_positive_company_contracts"],0)
        self.assertIn("잠정실적",render(r))
    def test_title_search_is_not_automatically_positive(self):
        self.assertTrue(contract_looking("단일판매ㆍ공급계약체결"))
        self.assertTrue(contract_looking("단일판매 공급계약 해지"))
        self.assertFalse(contract_looking("반기보고서 (2026.06)"))
    def test_listing_company_and_receipt_must_match(self):
        payload=dict(status="000",list=[filing(),
            filing(ticker="005930"),
            filing(corp="99887766"),
            filing(day="20261022"),
            filing(day="20261005"),
            filing(receipt="bad")])
        f,state=dated_filings(payload,"00123456","010120",ASOF)
        self.assertEqual(len(f),1)
        self.assertEqual(f[0]["receipt_no"],"20261021001234")
        self.assertEqual(state,"RECEIPT_CANDIDATES")
    def test_amended_filing_never_automatically_positive(self):
        result,_=dated_filings(dict(status="000",list=[
            filing(title="[기재정정] 단일판매 공급계약 해지")]),
            "00123456","010120",ASOF)
        self.assertEqual(result[0]["correction_risk"],
                         "CORRECTION_OR_WITHDRAWAL")
    def test_no_future_filing_on_same_asof_date(self):
        r,_=dated_filings(dict(status="000",list=[
            filing(day="20261022")]),"00123456","010120",ASOF)
        self.assertEqual(r,[])
    def test_document_zip_table_fields_are_candidates_only(self):
        parsed=zip_document(archive(DOC))
        self.assertEqual(parsed["status"],"DART_DOCUMENT_XML_TABLES_PARSED")
        self.assertEqual(len(parsed["extracted_candidate_cells"]),3)
        self.assertFalse(parsed["amount_verified"])
        self.assertFalse(parsed["contract_effect_verified"])
    def test_prose_outside_structured_table_does_not_become_money(self):
        text="<?xml version='1.0'?><DOCUMENT><P>계약금액 500억원</P></DOCUMENT>"
        r=zip_document(archive(text))
        self.assertEqual(r["extracted_candidate_cells"],[])
    def test_real_style_non_well_formed_sgml_table_is_read_as_candidates(self):
        html="""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN">
        <HTML><BODY><TABLE><TR><TH>계약금액<TD>1,300,000,000 원
        <TR><TH>계약상대<TD>해외 고객사
        </TABLE></BODY></HTML>"""
        r=zip_document(archive(html))
        self.assertEqual(r["status"],"DART_DOCUMENT_SGML_TABLES_PARSED")
        self.assertFalse(r["amount_verified"])
    def test_original_cp949_sgml_does_not_drop_korean_table_labels(self):
        html='<HTML><META charset="euc-kr"><TABLE><TR><TH>계약금액</TH><TD>500억원</TD></TR></TABLE></HTML>'
        raw=html.encode("euc-kr")
        archive_=io.BytesIO()
        with zipfile.ZipFile(archive_,"w") as zip_:
            zip_.writestr("document.xml",raw)
        r=zip_document(archive_.getvalue())
        self.assertEqual(r["status"],"DART_DOCUMENT_SGML_TABLES_PARSED")
        self.assertTrue(any("계약금액" in x["label"] for x in r["extracted_candidate_cells"]))
        self.assertFalse(r["contract_effect_verified"])
    def test_bad_zip_and_excessive_decompressed_data_fail_closed(self):
        self.assertEqual(zip_document(b"garbage")["status"],
                         "INVALID_OR_OVERSIZE_DART_DOCUMENT")
        big=archive("<DOCUMENT><P>"+"가"*7_000_000+"</P></DOCUMENT>")
        self.assertEqual(zip_document(big)["status"],
                         "DART_DOCUMENT_TOO_LARGE")
    def test_unparseable_xml_is_no_catalyst(self):
        r=zip_document(archive("<DOCUMENT><BAD></DOCUMENT>"))
        self.assertEqual(r["status"],"DART_DOCUMENT_XML_NOT_PARSEABLE")
    def test_historical_replay_never_calls_mutable_official_api(self):
        called=[]
        def forbidden(*args,**kwargs):
            called.append(1)
            raise AssertionError("Should not look ahead")
        result=collect({**BASE,"asof":"2026-10-21"},
          "a"*40,today=ASOF,list_api=forbidden,corps=forbidden)
        self.assertEqual(called,[])
        self.assertEqual(result["status"],
                         "HISTORICAL_OR_INCOMPLETE_KRX_NO_RETROACTIVE_DART")
    def test_current_valid_filing_original_verified_as_source_not_impact(self):
        calls=[]
        def list_api(endpoint,params,key):
            calls.append((endpoint,params))
            return {"status":"000","list":[filing()]}
        def doc(receipt,key):
            return zip_document(archive(DOC))
        r=collect(BASE,"a"*40,today=ASOF,list_api=list_api,
            corps=lambda key:{"010120":"00123456"},document_reader=doc)
        self.assertEqual(r["document_attempts"],1)
        self.assertEqual(r["confirmed_positive_company_contracts"],0)
        self.assertFalse(r["trade_approved"])
        self.assertEqual(r["issuer_samples"][0]["filings"][0]["filing_contents_status"],
                        "DART_DOCUMENT_XML_TABLES_PARSED")
        self.assertIn("계약",render(r))
        self.assertEqual(calls[0][1]["end_de"],"20261021")
    def test_contract_typed_amount_and_ratio_are_only_source_observations(self):
        def req(endpoint,params,key):
            return {"status":"000","list":[filing()]}
        r=collect(BASE,"a"*40,today=ASOF,list_api=req,
            corps=lambda k:{"010120":"00123456"},
            document_reader=lambda *x:zip_document(archive(DOC)))
        row=r["issuer_samples"][0]["filings"][0]
        terms=row["structured_contract_terms"]
        self.assertEqual(terms["amount_krw"],50_000_000_000)
        self.assertEqual(terms["disclosed_sales_ratio_pct"],15)
        self.assertEqual(terms["consistency"],"RATIO_ONLY_NO_SALES_BASE")
        self.assertTrue(row["document_labeled_amount_research_only"])
        self.assertFalse(row["contract_amount_verified"])
        self.assertFalse(row["positive_catalyst_verified"])
        self.assertIn("500.00",render(r))
        self.assertEqual(r["decision"],"CASH")
    def test_correction_in_original_report_never_claims_positive_sales(self):
        r=collect(BASE,"a"*40,today=ASOF,
             list_api=lambda *a:{"status":"000","list":[
                filing(title="[정정] 단일판매 공급계약 해지")]},
             corps=lambda _:{"010120":"00123456"},
             document_reader=lambda *a:zip_document(archive(DOC)))
        x=r["issuer_samples"][0]["filings"][0]
        self.assertEqual(x["structured_contract_terms"]["status"],
                        "CORRECTION_OR_WITHDRAWAL_REVIEW")
        self.assertEqual(r["confirmed_positive_company_contracts"],0)
        self.assertIn("정정/해지",render(r))
    def test_missing_key_does_not_start_issuer_search(self):
        r=collect(BASE,None,today=ASOF)
        self.assertEqual(r["status"],"DART_SECRET_NOT_AVAILABLE")
        self.assertEqual(r["issuer_samples"],[])
    def test_many_filing_matches_limited_to_bounded_original_requests(self):
        entries=[filing(receipt=f"20261021{i:06d}",
                  title="단일판매 공급계약") for i in range(30)]
        seen=[]
        def doc(receipt,key):
            seen.append(receipt)
            return {"status":"XML_SOURCE_RECEIVED"}
        r=collect(BASE,"a"*40,today=ASOF,
           list_api=lambda *a:dict(status="000",list=entries),
           corps=lambda key:{"010120":"00123456"},document_reader=doc,
           max_downloads=1)
        self.assertEqual(len(seen),1)
        self.assertEqual(r["document_attempts"],1)
        self.assertLessEqual(len(r["issuer_samples"][0]["filings"]),2)
    def test_no_sector_stocks_or_flow_disables_all_api_access(self):
        called=[]
        def forbidden(*a):
            called.append(1)
            return {}
        r=collect({**BASE,"daily_money_rank_applied":False},
            "a"*40,today=ASOF,corps=forbidden)
        self.assertEqual(called,[])
        self.assertEqual(r["decision"],"CASH")
    def test_company_group_only_looks_up_selected_top5(self):
        r=discovery_stocks({**BASE,"stock_research_top5":[
            dict(ticker="005930",sector_id="SEMICON"),
            dict(ticker="010120",sector_id="POWER",name="LS ELECTRIC"),
            dict(ticker="222222",sector_id="POWER",name="바이오") ]})
        self.assertEqual(r,[("010120","LS ELECTRIC")])
    def test_bad_receipt_is_safe_without_network_request(self):
        self.assertEqual(download_original("notvalid","a"*40)["status"],
                         "INVALID_RECEIPT")

if __name__=="__main__":unittest.main()
