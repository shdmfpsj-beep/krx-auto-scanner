"""Deterministic no-network KRX official API and 15:30 non-certification tests."""
from __future__ import annotations
import copy,csv,json,tempfile,unittest
from pathlib import Path
from urllib.error import HTTPError
from krx_official_eod_v65 import (
    SCHEMA,COLLECT_SCHEMA,normalize_payload,collect,compare,
    official_rows,fetch_official,price,write_csv,COMPARISON_FIELDS)

DAY="2026-10-23"
KEY="FAKE_TEST_ONLY_NEVER_REAL"
MARKETS={"KOSPI":[("005930",100),("000660",202),("050090",0)],
         "KOSDAQ":[("003780",300),("089890",405)]}

def payload(market):
    return {"OutBlock_1":[dict(BAS_DD="20261023",ISU_CD=t,
        ISU_NM=t,TDD_CLSPRC=f"{v:,}",TDD_OPNPRC=f"{v:,}",
        TDD_HGPRC=f"{v+5:,}" if v else "-",
        TDD_LWPRC=f"{v-5:,}" if v else "-",
        ACC_TRDVOL="1,000" if v else "0",
        ACC_TRDVAL="200,000" if v else "0") for t,v in MARKETS[market]]}

class Response:
    def __init__(self,content):self.content=content
    def __enter__(self):return self
    def __exit__(self,*_):return False
    def read(self,n=-1):return self.content

def factory(override=None):
    def mock(req,timeout=20):
        assert req.get_method()=="GET"
        assert "basDd=20261023" in req.full_url
        assert req.get_header("Auth_key")==KEY
        market="KOSPI" if "/stk_bydd_trd?" in req.full_url else "KOSDAQ"
        body=override.get(market) if override else None
        return Response(json.dumps(body if body is not None else payload(market)).encode())
    return mock

def v64():
    values=[
       ("005930",100,105,"CLOSE_CONFLICT_SESSION_UNKNOWN"),
       ("000660",200,202,"CLOSE_CONFLICT_SESSION_UNKNOWN"),
       ("003780",300,300,"CLOSE_AGREED_SESSION_UNCERTIFIED"),
       ("089890",400,410,"CLOSE_CONFLICT_SESSION_UNKNOWN"),
       ("050090",50,50,"RECOVERY_OHLC_INVALID")
    ]
    rows=[dict(asof=DAY,ticker=t,name=t,market=("KOSPI" if i in (0,1,4) else "KOSDAQ"),
        recovery_close=str(a),v18_close=str(b),classification=cls,
        is_frozen_signal="True" if i<2 else "False",
        trade_approved="False",orders_enabled="False",
        independent_regular_close_certified="False") for i,(t,a,b,cls) in enumerate(values)]
    status=dict(schema="C3_K100_SOURCE_CONSENSUS_V64",asof=DAY,
        trade_approved=False,orders_enabled=False,
        kst_regular_session_0900_1530_independently_certified=False,
        candidate_count=len(rows),valid_close_conflicts=3,
        manifest_sha256="TEST_COINCIDENT_SHA")
    return status,rows

class V65Test(unittest.TestCase):
    def test_missing_krx_auth_is_pending_not_an_authenticated_price(self):
        with tempfile.TemporaryDirectory() as t:
            result=collect(DAY,Path(t),auth_key=None)
            self.assertEqual(result["status"],"AUTH_KEY_NOT_CONNECTED")
            self.assertEqual(result["official_market_rows"],0)
            self.assertFalse(result["krx_eod_authenticated"])
            self.assertFalse((Path(t)/"KOSPI_official.csv").exists())
            result2,allrows=compare(*v64(),result,Path(t))
            self.assertEqual(result2["official_api_connected"],False)
            self.assertEqual(result2["candidates_evaluated"],5)
            self.assertEqual(result2["official_evidence_classes"],
                 {"KRX_AUTH_OR_SERVICE_NOT_CONNECTED":5})
            self.assertFalse(any(x["source_price_ready_for_trading"] for x in allrows))

    def test_authenticated_eod_two_markets_reconcile_but_regular_flag_false(self):
        with tempfile.TemporaryDirectory() as t:
            manifest=collect(DAY,Path(t),KEY,factory())
            self.assertEqual(manifest["status"],"OFFICIAL_EOD_AVAILABLE_SESSION_SCOPE_UNCERTIFIED")
            self.assertEqual(manifest["official_market_rows"],5)
            self.assertTrue(manifest["krx_eod_authenticated"])
            self.assertFalse(manifest["independent_1530_regular_session_certified"])
            self.assertNotIn(KEY,json.dumps(manifest))
            report,rows=compare(*v64(),manifest,Path(t))
            self.assertEqual(report["schema"],SCHEMA)
            self.assertEqual(report["official_eod_matches_only_recovery"],1)
            self.assertEqual(report["official_eod_matches_only_v18"],1)
            self.assertEqual(report["official_eod_matches_both"],1)
            self.assertEqual(report["official_evidence_classes"]["OFFICIAL_EOD_DIFFERS_FROM_BOTH"],1)
            self.assertEqual(report["official_evidence_classes"]["OFFICIAL_BAR_INVALID_OR_SUSPENDED"],1)
            self.assertEqual(report["decision"],"CASH")
            self.assertFalse(report["official_1530_close_eligible_for_signal"])
            self.assertTrue(all(x["trade_approved"] is False for x in rows))
            self.assertTrue(all(x["krx_1530_regular_session_certified"] is False for x in rows))
            self.assertEqual(rows[0]["krx_eod_turnover_krw"],200000)

    def test_no_isin_suffix_trimming_without_official_short_code(self):
        p=payload("KOSPI")
        p["OutBlock_1"].append(dict(ISU_CD="KR7005930003",BAS_DD="20261023"))
        items,n=normalize_payload(p,DAY,"KOSPI")
        self.assertEqual(n,1)
        self.assertEqual(len(items),3)
        self.assertNotIn("005930",[r["ticker"] for r in items if r["name"]=="KR7005930003"])

    def test_no_authorization_secret_in_csv_or_manifest(self):
        with tempfile.TemporaryDirectory() as t:
            collect(DAY,Path(t),KEY,factory())
            self.assertNotIn(KEY,"".join(p.read_text(encoding="utf-8-sig")
                for p in Path(t).iterdir()))

    def test_wrong_date_or_duplicate_security_fails_closed(self):
        p=payload("KOSPI")
        p["OutBlock_1"][1]["BAS_DD"]="20261022"
        with self.assertRaisesRegex(ValueError,"DATE_MISMATCH"):
            normalize_payload(p,DAY,"KOSPI")
        p=payload("KOSPI")
        p["OutBlock_1"][1]["ISU_CD"]=p["OutBlock_1"][0]["ISU_CD"]
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            normalize_payload(p,DAY,"KOSPI")

    def test_empty_or_malformed_official_json_never_considered_prices(self):
        for p in ({},{"OutBlock_1":[]},{"OutBlock_1":"foo"}):
            with self.assertRaisesRegex(ValueError,"OUTBLOCK"):
                normalize_payload(p,DAY,"KOSPI")

    def test_one_market_fails_entire_collection_atomically(self):
        bad=payload("KOSDAQ")
        bad["OutBlock_1"][0]["BAS_DD"]="2026-10-22"
        with tempfile.TemporaryDirectory() as t:
            status=collect(DAY,Path(t),KEY,factory({"KOSDAQ":bad}))
            self.assertFalse(status["official_dataset_usable"])
            self.assertFalse((Path(t)/"KOSPI_official.csv").exists())
            self.assertFalse((Path(t)/"KOSDAQ_official.csv").exists())
            self.assertEqual(status["official_market_rows"],0)
            self.assertIn("DATE_MISMATCH",status["status"])

    def test_auth_approval_not_configured_does_not_leak_headers(self):
        def reject(req,timeout):
            raise HTTPError(req.full_url,403,"forbidden",{},None)
        with tempfile.TemporaryDirectory() as t:
            status=collect(DAY,Path(t),KEY,reject)
            self.assertEqual(status["status"],"KRX_AUTH_OR_SERVICE_APPROVAL_MISSING")
            self.assertFalse(status["krx_eod_authenticated"])
            self.assertNotIn(KEY,json.dumps(status))

    def test_tamper_with_official_csv_is_fatal(self):
        with tempfile.TemporaryDirectory() as t:
            status=collect(DAY,Path(t),KEY,factory())
            with (Path(t)/"KOSPI_official.csv").open("a") as f:f.write("TAMPER")
            with self.assertRaisesRegex(ValueError,"OFFICIAL_FILE_SHA256_MISMATCH"):
                compare(*v64(),status,Path(t))

    def test_tampering_with_market_date_or_count_is_fatal(self):
        with tempfile.TemporaryDirectory() as t:
            status=collect(DAY,Path(t),KEY,factory())
            altered=copy.deepcopy(status);altered["asof"]="2026-10-22"
            with self.assertRaisesRegex(ValueError,"ASOF_POLICY"):
                compare(*v64(),altered,Path(t))
            altered=copy.deepcopy(status);altered["official_market_rows"]=999
            with self.assertRaisesRegex(ValueError,"OFFICIAL_MARKET_TOTAL_INVALID"):
                compare(*v64(),altered,Path(t))

    def test_forged_regular_session_certified_true_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            status=collect(DAY,Path(t),KEY,factory())
            status["independent_1530_regular_session_certified"]=True
            with self.assertRaisesRegex(ValueError,"ASOF_POLICY"):
                compare(*v64(),status,Path(t))

    def test_v64_incomplete_or_approved_previous_rows_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            manifest=collect(DAY,Path(t),None)
            previous,rows=v64()
            with self.assertRaisesRegex(ValueError,"COMPLETE_ROWS_INVALID"):
                compare(previous,rows[:-1],manifest,Path(t))
            rows[0]["trade_approved"]="True"
            with self.assertRaisesRegex(ValueError,"V64_AUDIT_DUPLICATE"):
                compare(previous,rows,manifest,Path(t))

    def test_unparsed_non_numeric_prices_treated_as_invalid_not_imputed(self):
        self.assertIsNone(price("－"))
        self.assertIsNone(price("--"))
        self.assertEqual(price("1,234"),1234)
        p=payload("KOSPI")
        p["OutBlock_1"][0]["TDD_CLSPRC"]="-"
        bar,count=normalize_payload(p,DAY,"KOSPI")
        self.assertFalse(bar[0]["valid_daily_bar"])
        self.assertIsNone(bar[0]["close"])

    def test_cannot_invent_official_api_success_when_response_absent(self):
        with tempfile.TemporaryDirectory() as t:
            manifest=collect(DAY,Path(t),None)
            altered=copy.deepcopy(manifest)
            altered["official_dataset_usable"]=True
            altered["official_market_rows"]=9
            with self.assertRaisesRegex(ValueError,"OFFICIAL_FILE_SHA256_MISMATCH"):
                compare(*v64(),altered,Path(t))

if __name__=="__main__":unittest.main()
