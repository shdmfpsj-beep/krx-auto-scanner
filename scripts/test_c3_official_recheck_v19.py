"""Fail-closed KRX official date recheck tests, no network."""
import tempfile
import unittest
from c3_official_recheck_v19 import run

class RecheckTests(unittest.TestCase):
    def test_11_06_empty_returns_11_05_as_control_only_not_substitute(self):
        calls=[]
        def collector(day,where,key):
            calls.append(day)
            return dict(asof=day,status="OFFICIAL_RESPONSE_MISSING_OR_EMPTY_OUTBLOCK"
                        if day=="2026-11-06"
                        else "OFFICIAL_EOD_AVAILABLE_SESSION_SCOPE_UNCERTIFIED",
                        official_dataset_usable=(day=="2026-11-05"),
                        official_market_rows=0 if day=="2026-11-06" else 2769,
                        krx_eod_authenticated=(day=="2026-11-05"),
                        raw_response_sha256={})
        with tempfile.TemporaryDirectory() as tmp:
            x=run("2026-11-06",tmp,"secret",collect_fn=collector)
            self.assertEqual(calls,["2026-11-06","2026-11-05"])
            self.assertEqual(x["official_target_rows"],0)
            self.assertEqual(x["prior_day_control"]["rows"],2769)
            self.assertFalse(x["trading_approved"])
            self.assertTrue(x["target_prices_were_never_replaced_with_prior_control"])

    def test_available_official_eod_does_not_imply_15_30_session_verification(self):
        def collector(day,where,key):
            return dict(asof=day,status="OFFICIAL_EOD_AVAILABLE_SESSION_SCOPE_UNCERTIFIED",
                        official_dataset_usable=True,official_market_rows=2769,
                        krx_eod_authenticated=True,raw_response_sha256={})
        with tempfile.TemporaryDirectory() as tmp:
            x=run("2026-11-06",tmp,"secret",collect_fn=collector)
            self.assertEqual(x["official_target_rows"],2769)
            self.assertIsNone(x["prior_day_control"])
            self.assertFalse(x["independent_0900_1530_volume_certified"])
            self.assertFalse(x["trading_approved"])

    def test_no_api_key_is_not_claimed_as_completeness(self):
        def collector(day,where,key):
            self.assertEqual(key,"")
            return dict(asof=day,status="AUTH_KEY_NOT_CONNECTED",
                        official_dataset_usable=False,official_market_rows=0,
                        krx_eod_authenticated=False)
        with tempfile.TemporaryDirectory() as tmp:
            x=run("2026-11-06",tmp,"",collect_fn=collector)
            self.assertFalse(x["official_target_authenticated"])
            self.assertEqual(x["decision"],"CASH")

    def test_reject_wrong_response_asof(self):
        def collector(day,where,key):
            return dict(asof="2026-11-05",status="OFFICIAL_EOD_AVAILABLE_SESSION_SCOPE_UNCERTIFIED",
                        official_dataset_usable=True,official_market_rows=2769)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,"DATE_LOCK_MISMATCH"):
                run("2026-11-06",tmp,"x",collect_fn=collector)

if __name__=="__main__":unittest.main(verbosity=2)
