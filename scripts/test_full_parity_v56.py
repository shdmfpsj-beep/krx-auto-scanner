"""Offline tests: full, date-locked mismatch roster and non-tradable result."""
import csv
import tempfile
import unittest
from pathlib import Path
from full_parity_v56 import inspect

DAY = "2026-10-23"


def make_csv(path, fields, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)


class FullParityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.scan = root/"recovery"
        self.evidence = root/"v18"

    def inputs(self, n=20, changed=None, ghost=False, date=DAY):
        changed = set(range(n)) if changed is None else set(changed)
        tickers = [f"{i+100000:06d}" for i in range(n)]
        recovery = [dict(ticker=t, date=DAY, open="100", high="110",
                         low="90", close="100", data_source="pykrx")
                    for t in tickers]
        if ghost:
            recovery.append(dict(ticker="950190", date=DAY, open="100",
                         high="110", low="90", close="100", data_source="pykrx"))
        make_csv(self.scan/"candidate_daily_history_v52.csv",
                 ["ticker","date","open","high","low","close","data_source"],
                 recovery)
        prices = [dict(ticker=t, Date=date, Open=100, High=110,
                       Low=90, Close=101 if i in changed else 100)
                  for i,t in enumerate(tickers)]
        cols = ["ticker","Date","Open","High","Low","Close"]
        make_csv(self.evidence/f"market/daily_prices/KOSPI/{DAY}.csv",
                 cols,prices)
        make_csv(self.evidence/f"market/daily_prices/KOSDAQ/{DAY}.csv",
                 cols,[dict(ticker="005930",Date=date,Open=100,High=110,Low=90,Close=100)])
        return tickers

    def test_all_20_conflicts_not_only_first_15(self):
        ts = self.inputs(n=20)
        res = inspect(self.scan,self.evidence,DAY)
        self.assertEqual(res["source_status"],"CROSS_SOURCE_CLOSE_CONFLICT")
        self.assertEqual(res["overlap_tickers"],20)
        self.assertEqual(res["close_mismatches"],20)
        self.assertEqual(res["mismatch_tickers"],ts)
        self.assertEqual(len(res["comparison_rows"]),20)
        self.assertTrue(res["mismatch_tickers_complete"])
        self.assertFalse(res["regular_only_session_certified"])
        self.assertFalse(res["independent_provider_verified"])
        self.assertFalse(res["trade_approved"])
        self.assertEqual(res["decision"],"CASH")

    def test_partial_conflict_roster_and_unpaired_candidates(self):
        ts=self.inputs(n=20,changed={1,19},ghost=True)
        res=inspect(self.scan,self.evidence,DAY)
        self.assertEqual(res["mismatch_tickers"],[ts[1],ts[19]])
        self.assertEqual(res["close_mismatches"],2)
        self.assertEqual(res["exact_close_matches"],18)
        self.assertEqual(res["unpaired_recovery_tickers"],["950190"])
        self.assertTrue(res["mismatch_tickers_complete"])

    def test_identical_pykrx_derived_feed_still_not_certified(self):
        self.inputs(n=2,changed=[])
        res=inspect(self.scan,self.evidence,DAY)
        self.assertEqual(res["source_status"],"CANDIDATE_CLOSES_MATCH_RESEARCH_ONLY")
        self.assertEqual(res["close_mismatches"],0)
        self.assertFalse(res["regular_only_session_certified"])
        self.assertFalse(res["trade_approved"])

    def test_missing_market_not_successful_empty_parity(self):
        self.inputs(n=2)
        (self.evidence/f"market/daily_prices/KOSDAQ/{DAY}.csv").unlink()
        res=inspect(self.scan,self.evidence,DAY)
        self.assertEqual(res["source_status"],"V18_MARKET_FILE_MISSING_OR_AMBIGUOUS")
        self.assertFalse(res["mismatch_tickers_complete"])
        self.assertIsNone(res["close_mismatches"])

    def test_v18_row_date_mismatch_fails_no_overlap(self):
        self.inputs(n=2,date="2026-10-22")
        res=inspect(self.scan,self.evidence,DAY)
        self.assertEqual(res["source_status"],"NO_VALID_OVERLAP")
        self.assertGreaterEqual(res["invalid_rows"],2)
        self.assertFalse(res["mismatch_tickers_complete"])

    def test_invalid_zero_ohlc_candidate_is_named_and_never_assumed_matched(self):
        self.inputs(n=2,changed=[])
        p=self.scan/"candidate_daily_history_v52.csv"
        with p.open("a",encoding="utf-8") as handle:
            handle.write("050090,2026-10-23,0,0,0,696,pykrx\n")
        res=inspect(self.scan,self.evidence,DAY)
        self.assertIn("050090",res["invalid_recovery_tickers"])
        self.assertNotIn("050090",res["unpaired_recovery_tickers"])
        self.assertEqual(res["recovery_valid_tickers"],2)
        self.assertEqual(res["source_status"],"CANDIDATE_CLOSES_MATCH_RESEARCH_ONLY")
        self.assertFalse(res["regular_only_session_certified"])
        self.assertEqual(res["decision"],"CASH")

    def test_duplicate_recovery_prevents_partial_roster(self):
        self.inputs(n=2)
        p=self.scan/"candidate_daily_history_v52.csv"
        with p.open("a",encoding="utf-8") as handle:
            handle.write("100000,2026-10-23,100,110,90,100,pykrx\n")
        res=inspect(self.scan,self.evidence,DAY)
        self.assertEqual(res["source_status"],"DUPLICATE_DATED_TICKER")
        self.assertIn("100000",res["duplicate_tickers"])
        self.assertFalse(res["mismatch_tickers_complete"])

if __name__ == "__main__":
    unittest.main()
