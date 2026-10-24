"""Offline safeguards for zero-cost research diagnostics."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from krx_price_integrity_v84 import inspect

ASOF = "2026-10-23"


class PriceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.out = self.base / "reports"
        self.out.mkdir()
        self.refs = self.base / "references.json"
        self.refs.write_text("{}", encoding="utf-8")
        self.write_csv("candidates.csv", ["ticker", "latest_date", "close"], [
            {"ticker": "005930", "latest_date": ASOF, "close": "1000"}])
        for f in ("c3_preliminary.csv", "k100_preliminary.csv"):
            self.write_csv(f, ["ticker", "latest_date", "close_reference", "trade_approval"], [
                {"ticker": "005930", "latest_date": ASOF,
                 "close_reference": "1000", "trade_approval": "NO"}])

    def write_csv(self, name, fields, values):
        with (self.out / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(values)

    def audit(self, asof=ASOF):
        return inspect(self.out, self.refs, asof, 0.5)

    def test_matching_same_feed_never_approves_trades(self):
        r = self.audit()
        self.assertEqual(r["status"], "INTERNAL_CONSISTENT_EXTERNAL_UNVERIFIED")
        self.assertEqual(r["internal_comparisons"], 2)
        self.assertFalse(r["regular_session_scope_verified"])
        self.assertFalse(r["independent_price_provider_verified"])
        self.assertFalse(r["trade_approved"])
        self.assertEqual(r["decision"], "CASH")

    def test_internal_mismatch_is_detected(self):
        self.write_csv("k100_preliminary.csv",
                       ["ticker", "latest_date", "close_reference", "trade_approval"],
                       [{"ticker": "005930", "latest_date": ASOF,
                         "close_reference": "1100", "trade_approval": "NO"}])
        r = self.audit()
        self.assertEqual(r["status"], "INTERNAL_CLOSE_CONFLICT")
        self.assertEqual(r["internal_close_conflict_count"], 1)
        self.assertFalse(r["trade_approved"])

    def test_external_manual_reference_conflict_is_not_hidden(self):
        self.refs.write_text(json.dumps({
            ASOF: {"005930": {"close": 1200, "sources": ["https://example.org/source"]}}
        }), encoding="utf-8")
        r = self.audit()
        self.assertEqual(r["status"], "DATED_REFERENCE_CLOSE_CONFLICT")
        self.assertEqual(r["dated_reference_conflict_count"], 1)
        self.assertFalse(r["independent_price_provider_verified"])

    def test_stale_input_is_not_verified(self):
        r = self.audit("2026-10-22")
        self.assertEqual(r["status"], "DATA_MISSING_OR_ASOF_UNVERIFIED")
        self.assertIn("ASOF_MISMATCH", r["data_errors"])

    def test_unexpected_trade_flag_forces_review(self):
        self.write_csv("c3_preliminary.csv",
                       ["ticker", "latest_date", "close_reference", "trade_approval"],
                       [{"ticker": "005930", "latest_date": ASOF,
                         "close_reference": "1000", "trade_approval": "YES"}])
        r = self.audit()
        self.assertEqual(r["status"], "DATA_MISSING_OR_ASOF_UNVERIFIED")
        self.assertIn("UNEXPECTED_TRADE_APPROVAL_FLAG", r["data_errors"])
        self.assertFalse(r["trade_approved"])


if __name__ == "__main__":
    unittest.main()
