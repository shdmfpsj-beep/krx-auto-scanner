import unittest
from c3_top2_progress_status_v1 import build,markdown

def entry(t):
    return dict(ticker=t,observed_sessions=2,expected_sessions=5,
        observation_complete=False,
        pullback=dict(opportunity_days=1),
        breakout_retest=dict(opportunity_days=0),
        breakout_without_pullback=dict(opportunity_days=1),
        future_close_observations={"pullback":[{"complete":False},{"complete":False},{"complete":False}]})

class ProgressTests(unittest.TestCase):
    def test_unverified_status_and_counts(self):
        report=build({"plans":[entry("271560"),entry("026960")]},
                     {"results":[{"ticker":"271560","max_provider_close_gap_pct":0.53},
                                 {"ticker":"026960","max_provider_close_gap_pct":0.54}]})
        self.assertIsNone(report["progress_percentage"])
        self.assertFalse(report["trade_approved"])
        self.assertEqual(report["results"][0]["forward_horizons_complete"],0)
        self.assertIn("CASH",markdown(report))
    def test_duplicate_ticker_fails(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_TOP2_TICKER"):
            build({"plans":[entry("271560"),entry("271560")]},
                  {"results":[{"ticker":"271560"},{"ticker":"026960"}]})
    def test_nan_gap_fails(self):
        with self.assertRaisesRegex(ValueError,"INVALID_PROVIDER_GAP"):
            build({"plans":[entry("271560"),entry("026960")]},
                  {"results":[{"ticker":"271560","max_provider_close_gap_pct":float("nan")},
                              {"ticker":"026960","max_provider_close_gap_pct":0.5}]})
    def test_missing_ticker_fails(self):
        with self.assertRaisesRegex(ValueError,"TICKER_MISMATCH"):
            build({"plans":[entry("271560"),entry("026960")]},
                  {"results":[{"ticker":"271560"},{"ticker":"000000"}]})
if __name__=="__main__":unittest.main()
