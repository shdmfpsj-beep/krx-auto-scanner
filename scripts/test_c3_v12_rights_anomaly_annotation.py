import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_v12_rights_anomaly_annotation import annotate

def fixture():
    cases=[{"ticker":str(i).zfill(6),"date":"2026-10-21","status":"PRIMARY_RIGHTS_NOTICE_VERIFIED",
        "ticker_table_matches":True,"file_sha256_expected":"same","current_archive_sha256":"same",
        "parsed_reference_price_krw":1000,"actual_ex_date_closing_price":980,"raw_close_ratio":.5,
        "receipt_no":"20261020900001","close_vs_official_reference_pct":-2.0} for i in range(1,6)]
    evt=[{"ticker":str(i).zfill(6),"date":"2026-10-21","close_ratio":.5} for i in range(1,74)]
    return {"requested_primary_rights_notices":5,"cases":cases},{"events":evt,"price_anomalies":410}

class AnnotatedRightsTests(unittest.TestCase):
 def test_exact_five_original_ex_rights_only(self):
    a,b=fixture();r=annotate(a,b)
    self.assertEqual(r["first_party_rights_reference_and_ex_date_verified"],5)
    self.assertEqual(r["remaining_adjacent_anomalies_without_primary_rights_proof"],68)
    self.assertTrue(r["no_past_returns_or_entry_bands_rewritten"])
 def test_wrong_sha_blocks(self):
    a,b=fixture();a["cases"][0]["current_archive_sha256"]="different"
    self.assertEqual(annotate(a,b)["first_party_rights_reference_and_ex_date_verified"],4)
 def test_wrong_daily_close_ratio_blocks(self):
    a,b=fixture();a["cases"][0]["raw_close_ratio"]=.8
    self.assertEqual(annotate(a,b)["first_party_rights_reference_and_ex_date_verified"],4)
 def test_missing_original_rights_never_assumed(self):
    a,b=fixture();a["cases"][0]["status"]="UNVERIFIED_STRUCTURED_RIGHTS_FIELDS"
    self.assertEqual(annotate(a,b)["first_party_rights_reference_and_ex_date_verified"],4)
if __name__=="__main__":unittest.main()
