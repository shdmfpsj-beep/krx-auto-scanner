"""Small extracted exchange-wide daily-file integrity tests (not price certification)."""
from __future__ import annotations
import copy,csv,json,tempfile,unittest
from pathlib import Path
from market_slice_v63 import extract,day_market,date_value,sha,SCHEMA

DAY="2026-10-23"
CLOCK="2026-10-23T12:50:00+00:00"

def fixture(parent):
    root=Path(parent)/"report"
    (root/"diagnostics").mkdir(parents=True)
    (root/"diagnostics/collection_status.json").write_text(
        json.dumps(dict(asof=DAY,orders_enabled=False,
                        datasets=dict(krx_preflight=dict(status="OK",asof=DAY)))))
    for market,start in (("KOSPI",0),("KOSDAQ",5000)):
        path=root/"market"/"daily_prices"/market
        path.mkdir(parents=True)
        with (path/(DAY+".csv")).open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=[
                "ticker","Date","Open","High","Low","Close","Volume","TurnoverKRW"])
            w.writeheader()
            for i in range(110):
                w.writerow(dict(ticker=str(i+start).zfill(6),Date=DAY,Open=100,
                    High=105,Low=98,Close=102,Volume=1000,TurnoverKRW=102000))
    return root

class SliceV63Tests(unittest.TestCase):
    def test_extract_both_markets_and_check_every_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            source=fixture(d);out=Path(d)/"out"
            meta=extract(source,out,"39948306433",CLOCK)
            self.assertEqual(meta["schema"],SCHEMA)
            self.assertEqual(meta["market_counts"],{"KOSPI":110,"KOSDAQ":110})
            self.assertEqual(meta["total_covered_tickers"],220)
            self.assertEqual(meta["regular_only_verified"],False)
            for m in ("KOSPI","KOSDAQ"):
                self.assertEqual(meta["sha256"][m],sha(out/DAY/(m+".csv")))
            self.assertFalse(meta["trade_approved"])

    def test_malformed_date_or_missing_market_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            source=fixture(d)
            (source/"market/daily_prices/KOSDAQ"/(DAY+".csv")).unlink()
            with self.assertRaisesRegex(ValueError,"MARKET_FILE_MISSING"):
                extract(source,Path(d)/"out","12345678",CLOCK)
        with self.assertRaises(ValueError):date_value("2026-10-45")

    def test_unapproved_trade_flags_cannot_become_valid_source(self):
        with tempfile.TemporaryDirectory() as d:
            source=fixture(d)
            f=source/"diagnostics/collection_status.json"
            q=json.loads(f.read_text());q["orders_enabled"]=True
            f.write_text(json.dumps(q))
            with self.assertRaisesRegex(ValueError,"V18_SOURCE_NOT_COMPLETED"):
                extract(source,Path(d)/"out","12345678",CLOCK)

    def test_date_mismatch_or_duplicate_ticker_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            source=fixture(d)
            f=source/"market/daily_prices/KOSPI"/(DAY+".csv")
            data=f.read_text(encoding="utf-8-sig").replace(
                "2026-10-23","2026-10-22",1)
            f.write_text(data)
            with self.assertRaisesRegex(ValueError,"MARKET_DUPLICATE_TICKER_OR_DATE"):
                extract(source,Path(d)/"out","12345678",CLOCK)
        with tempfile.TemporaryDirectory() as d:
            source=fixture(d)
            f=source/"market/daily_prices/KOSPI"/(DAY+".csv")
            lines=f.read_text(encoding="utf-8-sig").splitlines()
            lines[-1]=lines[-2]
            f.write_text("\n".join(lines)+"\n",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"MARKET_DUPLICATE_TICKER_OR_DATE"):
                extract(source,Path(d)/"out","12345678",CLOCK)

    def test_source_clock_can_never_predate_session(self):
        with tempfile.TemporaryDirectory() as d:
            source=fixture(d)
            with self.assertRaisesRegex(ValueError,"COLLECTION_TIME_BEFORE_MARKET"):
                extract(source,Path(d)/"out","12345678","2026-10-22T12:00:00Z")

    def test_market_tick_appearing_twice_across_exchanges_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            source=fixture(d)
            f=source/"market/daily_prices/KOSDAQ"/(DAY+".csv")
            txt=f.read_text(encoding="utf-8-sig")
            txt=txt.replace("005000","000000",1)
            f.write_text(txt,encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"SAME_TICKER_IN_KOSPI_AND_KOSDAQ"):
                extract(source,Path(d)/"out","12345678",CLOCK)
if __name__=="__main__":unittest.main()
