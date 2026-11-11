import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parent))
from c3_pr87_date_evidence_join import audit

class AsOfJoinTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        folder=self.root/"2026-08-03"
        folder.mkdir()
        sh={}
        for market,ticker in (("KOSPI","0015N0"),("KOSDAQ","000001")):
            file=folder/(market+"_official.csv")
            with file.open("w",newline="",encoding="utf-8-sig") as f:
                w=csv.DictWriter(f,fieldnames=["ticker","name","valid_daily_bar"])
                w.writeheader()
                w.writerow({"ticker":ticker,"name":"테스트종목","valid_daily_bar":"True"})
            sh[market]=hashlib.sha256(file.read_bytes()).hexdigest()
        (folder/"krx_v65_collect_status.json").write_text(json.dumps({"asof":"2026-08-03",
            "official_dataset_usable":True,"market_file_sha256":sh}))
    def tearDown(self):self.tmp.cleanup()

    def _cohort(self,ticker="000001"):
        return {"events":[{"ticker":ticker,"date":"2026-08-03"}]}

    def test_date_join_not_pit(self):
        f=[{"ticker":"000001","available_date":"2026-07-31","filing_date":"2026-07-30",
            "receipt_no":"20260730000123","validation_status":"PROVISIONAL_API_SNAPSHOT_NOT_PIT_VERIFIED"}]
        r=audit(self._cohort(),self.root,f,{"strict_pit_approved":False})
        self.assertEqual(r["source_counts"]["provisional_financial_date_matches"],1)
        self.assertEqual(r["events"][0]["financial"]["status"],"DATE_JOIN_ONLY_NOT_ORIGINAL_PIT")
        self.assertFalse(r["trading_approved"])
        self.assertEqual(r["decision"],"CASH")

    def test_future_filing_rejected(self):
        f=[{"ticker":"000001","available_date":"2026-08-04","filing_date":"2026-08-03"}]
        r=audit(self._cohort(),self.root,f)
        self.assertEqual(r["events"][0]["financial"]["status"],"BLOCKED_NO_PRIOR_FILING")

    def test_alpha_six_char_is_not_mistaken_for_preferred(self):
        r=audit(self._cohort("0015N0"),self.root)
        self.assertEqual(r["source_counts"]["alphanumeric_6char_tickers"],1)
        self.assertEqual(r["events"][0]["source"],"KRX_EOD_HASH_VERIFIED_1530_UNCERTIFIED")
        self.assertEqual(r["events"][0]["share_type"],"UNVERIFIED_NO_ISSUE_CLASSIFICATION")

    def test_operating_date_match_is_not_live_approval(self):
        r=audit(self._cohort(),self.root,paper={"positions":{"x":{"plan":{
            "ticker":"000001","selection_date":"2026-08-03"}}}})
        self.assertEqual(r["source_counts"]["same_ticker_date_operational_records"],1)
        self.assertFalse(r["events"][0]["may_approve_trading"])

    def test_hash_tamper_blocks_source(self):
        with (self.root/"2026-08-03"/"KOSDAQ_official.csv").open("a") as f:f.write("tamper")
        r=audit(self._cohort(),self.root)
        self.assertEqual(r["events"][0]["source"],"BLOCKED_NO_VALID_SOURCE_ROW")

if __name__=="__main__":unittest.main()
