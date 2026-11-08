"""Diagnostics: missed winners, CASH denominators and conditional performance.

The metrics tests are deliberately synthetic and have no connection to any
actual investment account, orders, market subscriptions or alerts.
"""
import unittest
from c3_v5_continuation_study_20261107 import (
    aggregate,continuation_cohorts,net_price_reference,mean_or_none)

def stat(fill,ret=0,submitted=True):
    return dict(submitted=submitted,filled=fill,
        prior_status="PREOPEN_LIMIT_FROZEN" if submitted else "NO_ORDER_PRIOR_TREND_NOT_CONFIRMED",
        cash_opportunity_pct=ret if fill else 0.,
        completed_net_pct=ret if fill else None,
        entry_status="MODEL_ENTRY_RESEARCH_ONLY" if fill else "NO_ENTRY",
        at_open=fill,model_intraday_limit_fill_assumed=False,
        unsafe_gap_at_or_below_stop=False,same_session_low_touch_stop=False,
        exit_reason="HORIZON_NEXT_OPEN" if fill else None)

def row(day,strong,up,market_outperf,ref,old,new):
    return dict(ticker="SYNTH",decision_date=day,
        continuation_up=up,continuation_outperformed_market=market_outperf,
        stock_excess_close_pct=5. if market_outperf else -2.,
        independent_next_open_reference_net_pct=ref,
        prior_strength=dict(strong=strong,missing=False),
        output={"V2_HIGH":old,"V5_TREND_GATE_HIGH":new})

class MetricsContract(unittest.TestCase):
    def setUp(self):
        self.rows=[
            row("2026-05-07",True,True,True,3.,
                stat(True,8.),stat(False,submitted=False)),
            row("2026-05-08",False,False,False,-4.,
                stat(True,-6.),stat(False,submitted=False)),
            row("2026-05-11",True,True,True,5.,
                stat(False),stat(False,submitted=False)),
        ]

    def test_cash_denominator_includes_all_three_opportunities(self):
        new=aggregate(self.rows,"V5_TREND_GATE_HIGH")
        self.assertEqual(new["evaluated_preclose_B_picks"],3)
        self.assertEqual(new["filled"],0)
        self.assertEqual(new["preclose_rejected"],3)
        self.assertEqual(new["mean_cash_adjusted_return_per_original_selection_pct"],0)
        self.assertIsNone(new["mean_completed_trade_net_pct"])
        self.assertIsNone(new["completed_win_rate_pct"])

    def test_missing_winner_counts_are_not_filled_strategy_returns(self):
        x=aggregate(self.rows,"V5_TREND_GATE_HIGH")
        self.assertEqual(x["missed_next_open_reference_profitable_count"],2)
        self.assertEqual(x["captured_next_open_reference_profitable_count"],0)
        self.assertEqual(x["avoided_negative_reference_count"],1)
        self.assertEqual(x["missed_positive_decision_close_continuations"],2)

    def test_same_signal_paired_differences_not_unpaired_trade_means(self):
        x=aggregate(self.rows,"V5_TREND_GATE_HIGH")
        self.assertAlmostEqual(x["paired_mean_delta_vs_V2_pp"],(-8+6+0)/3,places=6)
        self.assertEqual(x["paired_improved_count"],1)
        self.assertEqual(x["paired_worsened_count"],1)
        self.assertEqual(x["paired_unchanged_count"],1)
        self.assertEqual(x["same_day_cluster_count"],3)

    def test_labelled_continuation_does_not_become_magic_order_fill(self):
        y=continuation_cohorts(self.rows)
        self.assertEqual(y["PRIOR_STRONG"]["continuation_positive_count"],2)
        self.assertEqual(y["PRIOR_STRONG"]["control_V2_high_fills"],1)
        self.assertEqual(y["PRIOR_NOT_STRONG"]["continuation_positive_count"],0)
        self.assertEqual(y["PRIOR_NOT_STRONG"]["control_V2_high_fills"],1)

    def test_reference_no_trading_fees_are_not_free(self):
        self.assertLess(net_price_reference(100,100),0)
        self.assertIsNone(mean_or_none([]))

if __name__=="__main__":
    unittest.main(verbosity=2)
