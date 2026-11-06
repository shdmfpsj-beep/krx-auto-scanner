"""Synthetic, not market-data, tests for C3 independent price comparison."""
import csv
import tempfile
import unittest
from pathlib import Path
from c3_price_concordance_v1 import compare

BASE = dict(ticker="271560", date="2026-11-03", open=115000,
            high=118000, low=114000, close=116600, volume=300000)

class ConcordanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.a = Path(self.temp.name) / "a.csv"
        self.b = Path(self.temp.name) / "b.csv"

    def write(self, path, row):
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(BASE))
            w.writeheader()
            w.writerow(row)

    def check(self, reference=None, regular=True):
        self.write(self.a, BASE)
        self.write(self.b, reference or BASE)
        return compare(self.a, self.b, "PYKRX", "SEPARATE_TEST_FEED",
                       reference_regular_only=regular)

    def test_identical_reference_is_provisional_match(self):
        x = self.check()
        self.assertEqual(x["result_counts"]["MATCH"], 1)
        self.assertTrue(x["regular_only_concordance_passed"])
        self.assertFalse(x["regular_only_certified"])

    def test_close_mismatch_fails(self):
        x = self.check(dict(BASE, close=116500))
        self.assertFalse(x["regular_only_concordance_passed"])
        self.assertEqual(x["results"][0]["fields"], ["close"])

    def test_volume_mismatch_fails(self):
        x = self.check(dict(BASE, volume=299999))
        self.assertFalse(x["regular_only_concordance_passed"])

    def test_uncertified_reference_fails(self):
        self.assertFalse(self.check(regular=False)["regular_only_certified"])

    def test_same_provider_rejected(self):
        self.write(self.a, BASE)
        self.write(self.b, BASE)
        with self.assertRaisesRegex(ValueError, "NON_INDEPENDENT_PROVIDER"):
            compare(self.a, self.b, "PYKRX", "pykrx", True)

    def test_krx_alias_is_not_independent(self):
        self.write(self.a, BASE)
        self.write(self.b, BASE)
        with self.assertRaisesRegex(ValueError, "NON_INDEPENDENT_PROVIDER"):
            compare(self.a, self.b, "pykrx", "KRX", True)

    def test_naver_wrapper_is_not_independent_of_pykrx(self):
        self.write(self.a, BASE)
        self.write(self.b, BASE)
        for vendor in ("NAVER","FinanceDataReader_NAVER","fdr:naver"):
            with self.subTest(vendor=vendor):
                with self.assertRaisesRegex(ValueError,"NON_INDEPENDENT_PROVIDER"):
                    compare(self.a,self.b,"pykrx",vendor,True)

    def test_shared_upstream_observation_never_passes_independence_gate(self):
        self.write(self.a, BASE)
        self.write(self.b, BASE)
        r=compare(self.a,self.b,"pykrx_adjusted","FinanceDataReader_NAVER",True,
                  observation_only=True)
        self.assertEqual(r["result_counts"],{"MATCH":1})
        self.assertTrue(r["source_lineage_overlap"])
        self.assertFalse(r["regular_only_concordance_passed"])
        self.assertFalse(r["regular_only_certified"])

    def test_nonfinite_price_rejected(self):
        self.write(self.a, dict(BASE, close="nan"))
        self.write(self.b, BASE)
        with self.assertRaisesRegex(ValueError, "INVALID_NONFINITE"):
            compare(self.a, self.b, "PYKRX", "SEPARATE_TEST_FEED", True)

    def test_reference_only_date_reported(self):
        self.write(self.a, BASE)
        self.write(self.b, dict(BASE, date="2026-11-02"))
        x = compare(self.a, self.b, "PYKRX", "SEPARATE_TEST_FEED", True)
        self.assertIn("REFERENCE_ONLY", x["result_counts"])

    def test_blank_ticker_rejected(self):
        self.write(self.a, dict(BASE, ticker=" "))
        self.write(self.b, BASE)
        with self.assertRaisesRegex(ValueError, "EMPTY_TICKER_OR_DATE"):
            compare(self.a, self.b, "PYKRX", "SEPARATE_TEST_FEED", True)

    def test_blank_provider_rejected(self):
        self.write(self.a, BASE)
        self.write(self.b, BASE)
        with self.assertRaisesRegex(ValueError, "PROVIDER_PROVENANCE_REQUIRED"):
            compare(self.a, self.b, "  ", "SEPARATE_TEST_FEED", True)

    def test_missing_reference_fails(self):
        self.write(self.a, BASE)
        self.write(self.b, dict(BASE, date="2026-11-02"))
        x = compare(self.a, self.b, "PYKRX", "SEPARATE_TEST_FEED", True)
        self.assertFalse(x["regular_only_concordance_passed"])
        self.assertIn("MISSING_REFERENCE", [row["result"] for row in x["results"]])

if __name__ == "__main__":
    unittest.main()
