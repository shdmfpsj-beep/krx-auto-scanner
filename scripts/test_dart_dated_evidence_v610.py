"""v6.10.1 causal DATE_ONLY OpenDART titles, no fake publication time."""
from __future__ import annotations
import csv,json,tempfile,unittest
from pathlib import Path
from test_official_issuer_entry_v610 import files,fake_base,DAY
from test_sector_flow_v69 import write
from official_issuer_entry_v610 import retrieve,calculate as issuer_calc,emit
from dart_dated_evidence_v610 import calculate,write_outputs,SCHEMA,SOURCE_FIELDS,report_categories

def create_fixture(tmp):
    scan,flow,base=files(tmp)
    retrieve(DAY,base,"SYNTHETIC_TEST_KEY",fake_base)
    status,allrows,short=issuer_calc(scan,flow,base)
    issuer=Path(tmp)/"issuer"
    emit(issuer,status,allrows,short)
    v18=Path(tmp)/"sector_v18"
    st=v18/"diagnostics/collection_status.json"
    s=json.loads(st.read_text())
    def mk(t,day,rcp,name):
        return dict(ticker=t,corp_code="00123456",corp_name=t,
           report_name=name,receipt_no=rcp,receipt_date=day,
           url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo="+rcp,
           published_precision="DAY_ONLY_no_intraday_time",
           collected_at="2026-10-23T12:32:58+00:00",source="OPENDART_list")
    docs=[
        mk("010000","2026-10-22","20261022000001","연결재무제표기준영업(잠정)실적(공정공시)"),
        mk("010000","2026-10-23","20261023000001","공급계약체결(당일시각 불명)"),
        mk("010001","2026-10-20","20261020000001","기재정정 공시"),
        mk("010000","2026-09-10","20260910000001","구형 잠정실적"),
        mk("020000","2026-10-01","20261001000001","단일판매공급계약체결")
    ]
    s["datasets"]["dart"]=dict(status="DATE_ONLY_COMPLETE",rows=len(docs),
        exact_publication_time="UNAVAILABLE")
    st.write_text(json.dumps(s))
    path=v18/"catalysts/disclosures.csv"
    write(path,SOURCE_FIELDS,docs)
    return v18,issuer,path

class DARTDateGuardTests(unittest.TestCase):
    def test_prior_day_financial_headline_not_positive_growth(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,issuer,_=create_fixture(tmp)
            m,rows,docs=calculate(v18,issuer)
            self.assertEqual(m["schema"],SCHEMA)
            self.assertEqual(m["date_only_source_receipt_count"],5)
            self.assertEqual(m["strictly_preceding_receipts_captured"],3)
            self.assertEqual(m["same_day_receipts_excluded"],1)
            self.assertEqual(m["strong_sector_watch_prior_earnings_title_count"],1)
            a=next(r for r in rows if r["ticker"]=="010000")
            self.assertEqual(a["prior_30day_receipt_titles_earnings"],1)
            self.assertEqual(a["same_day_receipts_excluded_unknown_publication_time"],1)
            self.assertFalse(a["actual_earnings_direction_verified"])
            self.assertFalse(a["intraday_point_in_time_verified"])
            self.assertFalse(m["fundamental_growth_checked"])
            self.assertEqual(m["decision"],"CASH")
            self.assertTrue(all(x["trade_approved"] is False for x in docs))
            out=Path(tmp)/"output";write_outputs(out,m,rows,docs)
            self.assertIn("CASH",(out/"dart_date_only_v610_mobile.md").read_text())

    def test_same_day_new_price_news_cannot_be_used_as_prior_day_catalyst(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,issuer,_=create_fixture(tmp)
            _,rows,rr=calculate(v18,issuer)
            self.assertFalse(any(r["receipt_date"]==DAY for r in rr))
            self.assertFalse(any("공급계약체결(당일시각" in r["report_name"] for r in rr))

    def test_future_receipt_fails_even_if_dart_rows_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,issuer,path=create_fixture(tmp)
            with path.open(encoding="utf-8-sig",newline="") as f:
                rd=csv.DictReader(f);fields=rd.fieldnames;rr=list(rd)
            rr[0]["receipt_date"]="2026-10-26";write(path,fields,rr)
            with self.assertRaisesRegex(ValueError,"DART_FUTURE_RECEIPT"):
                calculate(v18,issuer)

    def test_duplicate_receipt_id_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,issuer,path=create_fixture(tmp)
            with path.open(encoding="utf-8-sig",newline="") as f:
                rd=csv.DictReader(f);fields=rd.fieldnames;rr=list(rd)
            rr[0]["receipt_no"]=rr[1]["receipt_no"];write(path,fields,rr)
            with self.assertRaisesRegex(ValueError,"DART_RECEIPT_NOT_REPRODUCIBLE"):
                calculate(v18,issuer)

    def test_no_intraday_publication_precision_forgery(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,issuer,path=create_fixture(tmp)
            with path.open(encoding="utf-8-sig",newline="") as f:
                rd=csv.DictReader(f);fields=rd.fieldnames;rr=list(rd)
            rr[0]["published_precision"]="MINUTE_VERIFIED"
            write(path,fields,rr)
            with self.assertRaisesRegex(ValueError,"DART_RECEIPT_NOT_REPRODUCIBLE"):
                calculate(v18,issuer)

    def test_cannot_fake_dart_timestamp_in_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,issuer,_=create_fixture(tmp)
            p=v18/"diagnostics/collection_status.json"
            s=json.loads(p.read_text())
            s["datasets"]["dart"]["exact_publication_time"]="AVAILABLE"
            p.write_text(json.dumps(s))
            with self.assertRaisesRegex(ValueError,"DART_ASOF_OR_PUBLICATION_TIME"):
                calculate(v18,issuer)

    def test_stock_count_edit_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,issuer,_=create_fixture(tmp)
            p=issuer/"issuer_entry_v610_status.json"
            s=json.loads(p.read_text())
            s["input_v68_candidates"]=123
            p.write_text(json.dumps(s))
            with self.assertRaisesRegex(ValueError,"V610_CANDIDATE_SET_NOT_COMPLETE"):
                calculate(v18,issuer)

    def test_disclosure_title_cannot_imply_earnings_amount(self):
        self.assertIn("EARNINGS_OR_FINANCIAL_TITLE",report_categories("잠정실적 발표"))
        self.assertIn("SHARE_BUYBACK_OR_CANCEL_TITLE",report_categories("자기주식취득결정"))
        self.assertIn("AMENDED_REPORT_TITLE",report_categories("[기재정정] 실적 안내"))
        self.assertNotIn("EARNINGS_OR_FINANCIAL_TITLE",report_categories("공급계약 공시"))

if __name__=="__main__":unittest.main()
