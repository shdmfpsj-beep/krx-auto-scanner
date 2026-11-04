import unittest
from c3_top2_progress_status_v1 import build,markdown

def entry(t):
    return dict(ticker=t,observed_sessions=2,expected_sessions=5,
        observation_complete=False,
        pullback=dict(opportunity_days=1),
        breakout_retest=dict(opportunity_days=0),
        breakout_without_pullback=dict(opportunity_days=1),
        future_close_observations={"pullback":[dict(horizon_sessions=n,observed_sessions=1,complete=False,observation_close_return_pct=None,strategy_return_pct=None,verified_fill=False) for n in (5,10,20)]})

class ProgressTests(unittest.TestCase):
    def test_unverified_status_and_counts(self):
        report=build({"plans":[entry("271560"),entry("026960")]},
                     {"results":[{"ticker":"271560","max_provider_close_gap_pct":0.53},
                                 {"ticker":"026960","max_provider_close_gap_pct":0.54}]})
        self.assertIsNone(report["progress_percentage"])
        self.assertFalse(report["trade_approved"])
        self.assertEqual(report["readiness_gate"],"BLOCKED")
        self.assertIn("FORWARD_HORIZONS_INCOMPLETE",report["readiness_blockers"])
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
    def test_unverified_strategy_return_fails(self):
        a=entry("271560")
        a["future_close_observations"]["pullback"][0]["strategy_return_pct"]=4.5
        with self.assertRaisesRegex(ValueError,"UNVERIFIED_TRADE_CLAIM"):
            build({"plans":[a,entry("026960")]},
                  {"results":[{"ticker":"271560","max_provider_close_gap_pct":0.53},
                              {"ticker":"026960","max_provider_close_gap_pct":0.54}]})
    def test_missing_ticker_fails(self):
        with self.assertRaisesRegex(ValueError,"TICKER_MISMATCH"):
            build({"plans":[entry("271560"),entry("026960")]},
                  {"results":[{"ticker":"271560"},{"ticker":"000000"}]})
if __name__=="__main__":unittest.main()
