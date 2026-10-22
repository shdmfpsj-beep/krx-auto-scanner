import csv,tempfile,unittest
from pathlib import Path
from krx_source_price_parity import run

DAY="2026-10-22"
def write(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as stream:
        w=csv.DictWriter(stream,fieldnames=fields);w.writeheader();w.writerows(rows)
def recovery(root,close=100,high=110,low=90):
    write(root/"candidate_daily_history_v52.csv",
        ["ticker","date","open","high","low","close","data_source"],[
        dict(ticker="005930",date=DAY,open=99,high=high,low=low,close=close,data_source="pykrx")])
def v18(root,close=100,high=110,low=90):
    write(root/"market/daily_prices/KOSPI"/(DAY+".csv"),
          ["ticker","Open","High","Low","Close"],[
          dict(ticker="005930",Open=99,High=high,Low=low,Close=close)])
    write(root/"market/daily_prices/KOSDAQ"/(DAY+".csv"),
          ["ticker","Open","High","Low","Close"],[
          dict(ticker="035420",Open=100,High=105,Low=95,Close=100)])
class TestParity(unittest.TestCase):
    def test_same_closes_are_research_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);recovery(root/"r");v18(root/"s")
            x=run(root/"r",root/"s",DAY)
            self.assertEqual(x["status"],"CANDIDATE_CLOSES_MATCH_RESEARCH_ONLY")
            self.assertEqual(x["overlap_tickers"],1)
            self.assertEqual(x["close_mismatches"],0)
            self.assertFalse(x["independent_provider_verified"])
            self.assertFalse(x["trade_approved"])
    def test_changed_close_unchanged_range_is_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);recovery(root/"r");v18(root/"s",close=105)
            x=run(root/"r",root/"s",DAY)
            self.assertEqual(x["status"],"CROSS_SOURCE_CLOSE_CONFLICT")
            self.assertEqual(x["changed_close_unchanged_highlow_count"],1)
            self.assertEqual(x["mismatch_examples"][0]["v18_close"],105)
            self.assertEqual(x["decision"],"CASH")
    def test_different_market_dates_no_fake_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);recovery(root/"r");v18(root/"s")
            x=run(root/"r",root/"s","2026-10-21")
            self.assertNotEqual(x["status"],"CANDIDATE_CLOSES_MATCH_RESEARCH_ONLY")
            self.assertEqual(x["overlap_tickers"],0)
    def test_missing_kosdaq_is_missing_not_zero_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);recovery(root/"r");v18(root/"s")
            (root/"s/market/daily_prices/KOSDAQ"/(DAY+".csv")).unlink()
            x=run(root/"r",root/"s",DAY)
            self.assertEqual(x["status"],"V18_DAILY_MARKET_SOURCE_MISSING")
            self.assertIn("KOSDAQ",x["market_files_missing"])
    def test_bad_recovery_price_cannot_become_trusted_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);recovery(root/"r",close=120);v18(root/"s")
            x=run(root/"r",root/"s",DAY)
            self.assertEqual(x["recovery_invalid_candidate_bars"],1)
            self.assertEqual(x["overlap_tickers"],0)
            self.assertEqual(x["status"],"NO_OVERLAPPING_VALID_DAILY_BARS")
if __name__=="__main__":unittest.main()
