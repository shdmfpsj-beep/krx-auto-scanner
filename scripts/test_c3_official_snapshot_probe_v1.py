import tempfile
import unittest
from c3_official_snapshot_probe_v1 import compare_snapshot,run

BAR=dict(open=100,high=110,low=99,close=105,volume=100)


class OfficialSnapshotTests(unittest.TestCase):
    def test_only_exact_dates_can_be_compared(self):
        p={("TEST","2026-11-03"):BAR,("TEST","2026-11-04"):BAR}
        r=compare_snapshot(p,{"TEST":("KOSPI",BAR)},"2026-11-04")
        self.assertEqual(r["compared_rows"],1)
        self.assertEqual(r["result_counts"],{"MATCH":1})
        self.assertFalse(r["regular_only_certified"])

    def test_official_missing_is_not_a_price_match(self):
        r=compare_snapshot({("TEST","2026-11-04"):BAR},{},"2026-11-04")
        self.assertEqual(r["result_counts"],{"OFFICIAL_REFERENCE_MISSING":1})

    def test_zero_comparisons_cannot_claim_agreement(self):
        r=compare_snapshot({}, {"TEST":("KOSPI",BAR)},"2026-11-04")
        self.assertEqual(r["compared_rows"],0)
        self.assertEqual(r["result_counts"],{})

    def test_field_disagreement_is_retained(self):
        r=compare_snapshot({("TEST","2026-11-04"):BAR},
                           {"TEST":("KOSPI",dict(BAR,volume=90))},"2026-11-04")
        self.assertEqual(r["results"][0]["fields"],["volume"])

    def test_unavailable_connection_returns_blocked_evidence_without_secrets(self):
        def fake(day,folder,auth_key=None):
            self.assertIsNone(auth_key)
            return dict(status="AUTH_KEY_NOT_CONNECTED",krx_eod_authenticated=False,
                        official_market_rows=0,official_dataset_usable=False)
        with tempfile.TemporaryDirectory() as t:
            r=run(["2026-11-04"],{},t,collector=fake)
        self.assertFalse(r["dates"][0]["authenticated"])
        self.assertFalse(r["api_key_recorded"])
        self.assertFalse(r["orders_enabled"])

    def test_duplicate_dates_rejected_before_any_request(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError,"DUPLICATE"):
                run(["2026-11-04","2026-11-04"],{},t)


if __name__=="__main__":
    unittest.main()
