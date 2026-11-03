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
        return compare(self.a, self.b, "PYKRX", "INDEPENDENT_KRX_EXPORT",
                       reference_regular_only=regular)

    def test_identical_reference_is_provisional_match(self):
        x = self.check()
        self.assertEqual(x["result_counts"]["MATCH"], 1)
        self.assertTrue(x["regular_only_certified"])

    def test_close_mismatch_fails(self):
        x = self.check(dict(BASE, close=116500))
        self.assertFalse(x["regular_only_certified"])
        self.assertEqual(x["results"][0]["fields"], ["close"])

    def test_volume_mismatch_fails(self):
        x = self.check(dict(BASE, volume=299999))
        self.assertFalse(x["regular_only_certified"])

    def test_uncertified_reference_fails(self):
        self.assertFalse(self.check(regular=False)["regular_only_certified"])

    def test_same_provider_rejected(self):
        self.write(self.a, BASE)
        self.write(self.b, BASE)
        with self.assertRaisesRegex(ValueError, "NON_INDEPENDENT_PROVIDER"):
            compare(self.a, self.b, "PYKRX", "pykrx", True)

    def test_missing_reference_fails(self):
        self.write(self.a, BASE)
        self.write(self.b, dict(BASE, date="2026-11-02"))
        x = compare(self.a, self.b, "PYKRX", "KRX_EXPORT", True)
        self.assertFalse(x["regular_only_certified"])
        self.assertEqual(x["results"][0]["result"], "MISSING_REFERENCE")

if __name__ == "__main__":
    unittest.main()
