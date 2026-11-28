"""C3 large portrait chart: source-integrity and mobile readability tests.

Never infer regular-session-only certification, a BUY, or promised returns.
"""
import gzip,io,json,os,struct,tempfile,unittest,zipfile
from pathlib import Path
import pandas as pd
from c3_top2_large_portrait_v2 import source_data,choose,run

SOURCE=os.getenv("C3_STOCK_FIRST_SOURCE_ZIP")
RANKED=os.getenv("C3_V5_RANKED_CSV")

def png_dimensions(path):
    with open(path,"rb") as f:header=f.read(24)
    if header[:8]!=b"\x89PNG\r\n\x1a\n":raise ValueError("NOT_PNG")
    return struct.unpack(">II",header[16:24])

class TestLargePortrait(unittest.TestCase):
    def test_ranked_top2_uses_order_not_hardcoded_names(self):
        x=pd.DataFrame([
          dict(ticker="123456",priority_class="PRIORITY_PULLBACK",
               watch_low=100,watch_high=200,first_obstacle_krw=500),
          dict(ticker="987654",priority_class="SECONDARY_WATCH",
               watch_low=100,watch_high=200,first_obstacle_krw=500),
          dict(ticker="271560",priority_class="LOW_PRIORITY",
               watch_low=100,watch_high=200,first_obstacle_krw=500)])
        self.assertEqual([v["ticker"] for v in choose(x)],["123456","987654"])

    def test_missing_ranked_stocks_refuses_two_charts(self):
        x=pd.DataFrame([
          dict(ticker="271560",priority_class="PRIORITY_PULLBACK",
               watch_low=100,watch_high=200,first_obstacle_krw=500)])
        with self.assertRaisesRegex(ValueError,"FEWER_THAN_TWO"):
            choose(x)

    @unittest.skipUnless(SOURCE and RANKED,"Original dated scan and v5 ranked data required")
    def test_real_top2_large_png_and_price_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            x=run(SOURCE,RANKED,d,bars=35,external_close_map={
                "271560":114800,"026960":28450})
            self.assertEqual(x["asof"],"2026-10-30")
            self.assertEqual([z["ticker"] for z in x["candidates"]],["271560","026960"])
            self.assertEqual([z["source_close"] for z in x["candidates"]],[114200,28400])
            self.assertEqual([z["reference_regular_close"] for z in x["candidates"]],[114800,28450])
            self.assertEqual([z["t1"] for z in x["candidates"]],[131500,29550])
            self.assertEqual([z["t2"] for z in x["candidates"]],[141700,30550])
            self.assertTrue(all(z["regular_close_match"] is False for z in x["candidates"]))
            for z in x["candidates"]:
                image=Path(d)/z["file"]
                self.assertEqual(png_dimensions(image),(1751,2618))
                self.assertGreater(image.stat().st_size,30000)
                self.assertFalse(z["trade_approved"])
            self.assertFalse(x["regular_only_source_certified"])
            self.assertFalse(x["buy_approved"])
            self.assertFalse(x["orders_enabled"])

    @unittest.skipUnless(SOURCE and RANKED,"Original dated scan and v5 ranked data required")
    def test_reject_ranked_date_not_equal_to_archive_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=pd.read_csv(RANKED,dtype={"ticker":str})
            f.loc[0,"asof"]="2026-10-29"
            target=Path(tmp)/"altered_rank.csv";f.to_csv(target,index=False)
            with self.assertRaisesRegex(ValueError,"RANK_DATE"):
                source_data(SOURCE,target)

if __name__=="__main__":unittest.main()
