import csv,json,tempfile,unittest
from pathlib import Path
from c3_provider_gap_entry_impact_v1 import assess

class GapEntryImpactTests(unittest.TestCase):
    def test_gap_flags_and_no_trading(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"plans.csv"
            with path.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["ticker","name","source_close","structure_stop","watch_low","watch_high"])
                w.writeheader()
                w.writerow({"ticker":"271560","name":"test","source_close":100,"structure_stop":95,"watch_low":98,"watch_high":98.2})
            result=assess(path,{"gap_summary":{"271560":{"max_abs_gap_pct":0.5,"mean_abs_gap_pct":0.2}}})
            row=result["results"][0]
            self.assertTrue(row["gap_exceeds_watch_band"])
            self.assertTrue(row["gap_exceeds_10pct_of_stop_distance"])
            self.assertFalse(result["trade_approved"])
            self.assertFalse(row["entry_price_certified"])
    def test_missing_data_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"plans.csv"
            path.write_text("ticker,name,source_close,structure_stop,watch_low,watch_high\n271560,test,100,95,98,99\n")
            with self.assertRaisesRegex(ValueError,"MISSING_PROVIDER_GAP"):
                assess(path,{"gap_summary":{}})
if __name__=="__main__":unittest.main()
