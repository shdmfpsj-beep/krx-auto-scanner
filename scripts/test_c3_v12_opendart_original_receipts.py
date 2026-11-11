import io,json,sys,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_v12_opendart_original_receipts import analyze_document,exact_receipts
class OriginalDocTests(unittest.TestCase):
 def test_error_xml_not_raw_filing(self):
    d=analyze_document(b"<result><status>014</status><message>no file</message></result>")
    self.assertEqual(d["status"],"OPEN_DART_STATUS_014")
    self.assertFalse(d["zip_authenticated"])
 def test_real_zip_does_not_certify_earnings(self):
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w") as z:z.writestr("document.xml","<DOCUMENT>매출액 1,000</DOCUMENT>")
    d=analyze_document(b.getvalue())
    self.assertTrue(d["zip_authenticated"])
    self.assertFalse(d["original_primary_document_numeric_PIT_verified"])
    self.assertFalse(d["actual_corporate_action_effective_price_verified"])
 def test_empty_zip_fail_closed(self):
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w"):pass
    self.assertEqual(analyze_document(b.getvalue())["status"],"BLOCKED_EMPTY_OR_INVALID_FILE")
 def test_exact14digit_receipts_and_corporate_title(self):
    a={"events":[{"ticker":"001000","financial":{"receipt_no":"20260513000773","filing_date":"2026-05-13"}}]}
    b={"events":[{"ticker":"475460","label":"PRIOR_ACTION_TITLE_UNVERIFIED_CAUSE","prior_30_day_titles":[
       {"receipt_no":"20260915900714","receipt_date":"2026-09-15","report_name":"권리락 (무상증자)"}]}]}
    x=exact_receipts(a,b)
    self.assertEqual(len(x),2)
    self.assertEqual(x["20260915900714"]["kind"],"CORPORATE_OR_RIGHTS_DART_TITLE_ONLY")
 def test_no_unsourced_filing_number(self):
    a={"events":[{"ticker":"001000","financial":{"receipt_no":"none"}}]}
    b={"events":[{"ticker":"001000","label":"NO_MATCHING_PRIOR_TITLE_IN_SNAPSHOT","prior_30_day_titles":[]}]}
    self.assertEqual(exact_receipts(a,b),{})
if __name__=="__main__":unittest.main()
