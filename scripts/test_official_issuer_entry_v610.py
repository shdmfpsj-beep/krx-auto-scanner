"""v6.10 offline synthetic 2-market KRX base-info and risk-first veto."""
from __future__ import annotations
import csv,json,tempfile,unittest
from pathlib import Path
from test_sector_flow_v69 import setup as prep_sector
from sector_flow_v69 import evaluate as sector_evaluate,write_outputs as save_sector
from official_issuer_entry_v610 import (
    retrieve,calculate,emit,is_common,normalize_info,risk_valid,SCHEMA)

DAY="2026-10-23"
def files(tmp):
    v18,scan=prep_sector(tmp)
    report,sectors,stocks,top3,qualified=sector_evaluate(v18,scan)
    out=Path(tmp)/"flow"
    save_sector(out,report,sectors,stocks,top3,qualified)
    base=Path(tmp)/"base"
    return scan,out,base

def fake_base(endpoint,asof,key):
    assert asof==DAY and key=="SYNTHETIC_TEST_KEY"
    is_kospi=endpoint=="stk_isu_base_info"
    rows=[("010000","TEST_COMMON","보통주"),
          ("010001","TEST_PREFERRED","우선주")] if is_kospi else [
          ("020000","TEST_KOSDAQ","보통주")]
    return {"OutBlock_1":[dict(ISU_CD="KR7"+t+"000",ISU_SRT_CD=t,
        ISU_NM=name,LIST_DD="20200101",MKT_TP_NM="유가증권시장" if is_kospi else "코스닥",
        SECUGRP_NM="주권",KIND_STKCERT_TP_NM=kind,
        SECT_TP_NM="중견기업부") for t,name,kind in rows]}, "fake_response_hash"

class IssuerBase610Tests(unittest.TestCase):
    def test_valid_baseline_exact_flow_and_kospi_kosdaq_common_class(self):
        with tempfile.TemporaryDirectory() as temp:
            scan,flow,base=files(temp)
            m=retrieve(DAY,base,"SYNTHETIC_TEST_KEY",fake_base)
            self.assertTrue(m["official_base_usable"])
            self.assertEqual(sum(m["market_counts"].values()),3)
            result,rows,short=calculate(scan,flow,base)
            self.assertEqual(result["schema"],SCHEMA)
            self.assertEqual(result["input_v68_candidates"],3)
            self.assertEqual(result["strong_sector_research_shortlist_count"],1)
            self.assertEqual(result["shortlist_top20_actual_count"],1)
            self.assertEqual(short[0]["ticker"],"010000")
            self.assertFalse(result["exact_regular_1530_prices_verified"])
            self.assertEqual(result["decision"],"CASH")
            self.assertFalse(result["trade_approved"])
            kinds={r["ticker"]:r["common_share_basic_info_verified"] for r in rows}
            self.assertTrue(kinds["010000"])
            self.assertFalse(kinds["010001"])
            self.assertTrue(kinds["020000"])
            self.assertTrue(all(not x["trade_approved"] for x in rows))
            out=Path(temp)/"results";emit(out,result,rows,short)
            self.assertIn("CASH",(out/"issuer_entry_v610_mobile.md").read_text())

    def test_absent_key_does_not_fake_official_share_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            scan,flow,base=files(temp)
            m=retrieve(DAY,base,None)
            self.assertFalse(m["official_base_usable"])
            res,rows,short=calculate(scan,flow,base)
            self.assertEqual(res["candidates_basic_common_share_verified"],0)
            self.assertFalse(short[0]["official_common_share_proof"])
            self.assertTrue(all("OFFICIAL_BASE_INFO_MISSING" in r["blocking_reasons"] for r in rows))

    def test_no_both_2r_without_full_structural_price_geometry(self):
        m=dict(setup="RESEARCH_TRIGGER_CONFIRMED_ASOF",
            first_entry_reference="100",stop_reference="95",
            nearest_resistance_reference="120",
            first_net_rr="3.0",second_entry_reference="97",
            second_net_rr="2.5",structure_reference_valid="True")
        self.assertEqual(risk_valid(m)[0],True)
        self.assertEqual(risk_valid({**m,"second_net_rr":"1.2"})[0],False)
        self.assertEqual(risk_valid({**m,"stop_reference":"101"})[0],False)
        self.assertEqual(risk_valid({**m,"setup":"NO_CONFIRMED_SETUP"})[0],False)
        self.assertEqual(risk_valid({**m,"first_net_rr":"1.99"})[0],False)

    def test_isu_cd_standard_isin_must_not_be_treated_as_short_code(self):
        body,_=fake_base("stk_isu_base_info",DAY,"SYNTHETIC_TEST_KEY")
        rows=normalize_info(body,"KOSPI",DAY)
        self.assertEqual(rows[0]["ticker"],"010000")
        self.assertNotEqual(rows[0]["isin"],rows[0]["ticker"])
        self.assertTrue(is_common(rows[0]))
        self.assertFalse(is_common(rows[1]))
        self.assertEqual(rows[0]["board_section"],"중견기업부")

    def test_base_api_future_listing_date_is_rejected(self):
        body,_=fake_base("stk_isu_base_info",DAY,"SYNTHETIC_TEST_KEY")
        body["OutBlock_1"][0]["LIST_DD"]="20261026"
        with self.assertRaisesRegex(ValueError,"FUTURE_LISTING"):
            normalize_info(body,"KOSPI",DAY)

    def test_api_approval_error_safe_and_atomic(self):
        with tempfile.TemporaryDirectory() as temp:
            scan,flow,base=files(temp)
            def denied(endpoint,asof,key):
                if endpoint=="ksq_isu_base_info":raise ValueError("KRX_AUTH_OR_SERVICE_APPROVAL_MISSING")
                return fake_base(endpoint,asof,key)
            m=retrieve(DAY,base,"SYNTHETIC_TEST_KEY",denied)
            self.assertFalse(m["official_base_usable"])
            self.assertEqual(m["error"],"KRX_AUTH_OR_SERVICE_APPROVAL_MISSING")
            self.assertFalse((base/"KOSPI_basic_v610.csv").exists())
            result,rows,_=calculate(scan,flow,base)
            self.assertEqual(result["decision"],"CASH")
            self.assertTrue(all(not r["common_share_basic_info_verified"] for r in rows))

    def test_tampered_basic_file_sha_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            scan,flow,base=files(temp)
            retrieve(DAY,base,"SYNTHETIC_TEST_KEY",fake_base)
            with (base/"KOSPI_basic_v610.csv").open("a") as f:f.write("BAD")
            with self.assertRaisesRegex(ValueError,"OFFICIAL_BASIC_FILE_SHA256"):
                calculate(scan,flow,base)

    def test_tamper_v68_52_candidate_file_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            scan,flow,base=files(temp)
            retrieve(DAY,base,"SYNTHETIC_TEST_KEY",fake_base)
            with (scan/"full_market_v68_method_research.csv").open("a") as f:f.write("BAD")
            with self.assertRaisesRegex(ValueError,"V610_FULLMARKET_SOURCE_FILE_SHA256"):
                calculate(scan,flow,base)

    def test_3rd_sector_not_manufactured_in_strong_top20(self):
        with tempfile.TemporaryDirectory() as temp:
            scan,flow,base=files(temp)
            retrieve(DAY,base,"SYNTHETIC_TEST_KEY",fake_base)
            report,rows,short=calculate(scan,flow,base)
            self.assertEqual(report["strong_proxy_sectors"],["CONSTRUCTION","INSURANCE"])
            self.assertTrue(all("CONTENT" not in r["sector"] for r in short))
            self.assertEqual(report["in_strong_sector_with_common_2R"],0)

    def test_source_dates_are_immutable_between_reports(self):
        with tempfile.TemporaryDirectory() as temp:
            scan,flow,base=files(temp)
            retrieve(DAY,base,"SYNTHETIC_TEST_KEY",fake_base)
            meta=base/"krx_basic_v610_status.json"
            m=json.loads(meta.read_text());m["asof"]="2026-10-22";meta.write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError,"V610_BASIC_SOURCE_DATE"):
                calculate(scan,flow,base)

if __name__=="__main__":unittest.main()
