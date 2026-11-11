import csv,io,json,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_v13_finite_14_original_financial_audit import (
  digest,match_literal_amount,safe_doc_text,evaluate,fetch_original)

class Finite14Tests(unittest.TestCase):
  def test_amount_matching_is_diagnostic_only(self):
    raw="매출액 1,234,000 원 영업이익 30,000"
    self.assertTrue(match_literal_amount(raw,1234000))
    self.assertFalse(match_literal_amount(raw,1235001))
  def test_negative_amount_and_thousand_unit(self):
    self.assertTrue(match_literal_amount("결산 -1,500 매출액", -1500000))
  def test_html_document_zip_safe(self):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:z.writestr("REPORT.xml",b"<table><tr><td>Hello 5,000</td></tr></table>")
    out,n=safe_doc_text(buf.getvalue())
    self.assertEqual(n,1);self.assertIn("Hello 5,000",out)
  def test_traversal_and_nonzip_rejected(self):
    with self.assertRaisesRegex(ValueError,"ORIGINAL_NOT_VALID_ZIP"):
      safe_doc_text(b"hello")
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:z.writestr("../unsafe.xml","harm")
    with self.assertRaisesRegex(ValueError,"UNSAFE_ARCHIVE_PATH"):
      safe_doc_text(buf.getvalue())
  def test_no_key_is_blocked(self):
    data,status=fetch_original("20260513000773","")
    self.assertIsNone(data);self.assertEqual(status,"BLOCKED_NO_OPENDART_KEY")
  def test_14_exact_finite_records_fail_closed(self):
    with tempfile.TemporaryDirectory() as tmp:
      root=Path(tmp);(root/"reports").mkdir()
      fields=["receipt_no","ticker","filing_date","available_date","fs_div",
              "report_year","report_code","revenue_amount_krw","op_profit_amount_krw",
              "liabilities_amount_krw","equity_amount_krw"]
      with (root/"reports/v91_financial_pit_provisional.csv").open("w",newline="") as out:
        w=csv.DictWriter(out,fieldnames=fields);w.writeheader()
        pit=[];prior=[]
        for i in range(14):
          date="2026-05-13";no="20260513"+str(i).zfill(6)
          w.writerow(dict(receipt_no=no,ticker=str(i).zfill(6),
              filing_date=date,available_date="2026-05-14",fs_div="CFS",
              report_year="2026",report_code="11013",revenue_amount_krw="1000",
              op_profit_amount_krw="100",liabilities_amount_krw="500",equity_amount_krw="500"))
          pit.append(dict(receipt_no=no,ticker=str(i).zfill(6),filing_date=date,
              selection_date="2026-06-01",old_available_date="2026-05-14",
              classification="MATCHES_FIRST_FROZEN_KRX_SESSION"))
          prior.append(dict(receipt_no=no,kind="FINANCIAL_PROVISIONAL_DATE_LINK",
              original_archive_sha256=digest(b"old")))
      x=evaluate(root,{"events":pit},{"receipts":prior},"")
      self.assertEqual(x["total_classified"],14)
      self.assertEqual(x["statuses"]["BLOCKED"],14)
      self.assertEqual(x["statuses"]["VERIFIED"],0)
      self.assertFalse(x["production_changed"])
if __name__=="__main__":unittest.main()
