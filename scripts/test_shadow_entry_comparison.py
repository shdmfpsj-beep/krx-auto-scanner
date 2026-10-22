#!/usr/bin/env python3
"""Tests for prospective next-open vs pullback entry comparisons."""
import unittest
from shadow_entry_comparison import assess_limit,compare,aggregate,save
from shadow_trade_audit import ROUNDTRIP_COST_PCT

SIG=dict(signal_date="2026-10-22",ticker="005930",sector_id="SEMICON",
         signal_close=100,signal_atr14=10,stop_reference=90,
         no_chase_reference=106,prior_high=125,
         research_proxy_index=90,plan_version="next_open_5d_v1")
DAYS=["2026-10-23","2026-10-26","2026-10-27","2026-10-28","2026-10-29",
      "2026-10-30","2026-11-02"]
def bar(d,op=100,hi=105,lo=98,cl=101):
    return dict(date=d,open=op,high=hi,low=lo,close=cl)

class EntryABTests(unittest.TestCase):
    def test_limit_only_touched_on_second_day(self):
        bars=[bar(DAYS[0],lo=98),bar(DAYS[1],lo=96,hi=106),
              bar(DAYS[2],hi=113,lo=96)]
        r=assess_limit(SIG,bars,DAYS)
        self.assertEqual(r["status"],"CLOSED")
        self.assertEqual(r["fill_session"],2)
        self.assertEqual(r["exit_reason"],"TARGET_2R")
        self.assertAlmostEqual(r["next_entry_reference"],96.5)
    def test_pessimistic_stop_when_both_hit_on_entry_bar(self):
        r=assess_limit(SIG,[bar(DAYS[0],hi=120,lo=85)],DAYS)
        self.assertEqual(r["status"],"CLOSED")
        self.assertEqual(r["exit_reason"],"STOP_FIRST_AMBIGUOUS_INTRABAR")
        self.assertLess(r["net_return_pct"],0)
    def test_limit_order_not_filled_when_price_escapes_for_two_days(self):
        r=assess_limit(SIG,[bar(DAYS[0],lo=99),bar(DAYS[1],lo=97)],DAYS)
        self.assertEqual(r["status"],"SKIP_LIMIT_NOT_TOUCHED")
    def test_future_during_unfinished_entry_window_is_not_skip(self):
        r=assess_limit(SIG,[bar(DAYS[0],lo=99)],[DAYS[0]])
        self.assertEqual(r["status"],"PENDING_LIMIT_WINDOW")
    def test_old_trade_archive_missing_next_day_price_blocks_new_fill(self):
        r=assess_limit(SIG,[bar(DAYS[1],lo=96)],DAYS)
        self.assertEqual(r["status"],"MISSING_LIMIT_WINDOW_SESSION_PRICE")
    def test_archive_has_future_market_days_but_missing_hold_candle(self):
        r=assess_limit(SIG,[bar(DAYS[0],lo=96)],DAYS)
        self.assertEqual(r["status"],"MISSING_HOLDING_SESSION_PRICE")
    def test_broken_support_gap_does_not_assume_good_limit_entry(self):
        r=assess_limit(SIG,[bar(DAYS[0],op=85,lo=80,hi=100)],DAYS)
        self.assertEqual(r["status"],"SKIP_BROKEN_SUPPORT_AT_OPEN")
    def test_limit_below_stop_is_no_trade(self):
        r=assess_limit({**SIG,"stop_reference":98},[bar(DAYS[0])],DAYS)
        self.assertEqual(r["status"],"SKIP_LIMIT_BELOW_STOP")
    def test_partial_held_trade_is_not_counted_win_or_loss(self):
        r=assess_limit(SIG,[bar(DAYS[0],lo=96,hi=100)],[DAYS[0]])
        self.assertEqual(r["status"],"OPEN_NEEDS_FUTURE_DAILY_BARS")
    def test_cost_applied_to_target_trade(self):
        # Day 1's high might precede an intraday low/limit fill.
        # Count 2R on a later candle, not an ambiguous entry candle.
        r=assess_limit(SIG,[bar(DAYS[0],lo=96,hi=115),
                            bar(DAYS[1],lo=97,hi=115)],DAYS)
        self.assertEqual(r["status"],"CLOSED")
        self.assertEqual(r["hold_sessions"],2)
        self.assertAlmostEqual(r["net_return_pct"],
                               100*((96.5+2*6.5)/96.5-1)-ROUNDTRIP_COST_PCT,places=3)
    def test_intraday_touch_high_before_entry_cannot_claim_same_day_profit(self):
        only=[bar(DAYS[0],op=100,hi=115,lo=96)]
        out=assess_limit(SIG,only,[DAYS[0]])
        self.assertEqual(out["status"],"OPEN_NEEDS_FUTURE_DAILY_BARS")
    def test_limit_filled_at_open_can_reach_target_same_day(self):
        bar_at_open=bar(DAYS[0],op=96,hi=114,lo=94)
        result=assess_limit(SIG,[bar_at_open],[DAYS[0]])
        self.assertEqual(result["status"],"CLOSED")
        self.assertEqual(result["exit_reason"],"TARGET_2R")

    def test_missing_calendar_is_unknown_not_skip(self):
        self.assertEqual(assess_limit(SIG,[],[])["status"],"NO_MARKET_CALENDAR")
    def test_comparison_keeps_original_signal_ticker_and_no_auto_buy(self):
        prices={"005930":[bar(DAYS[0],lo=96,hi=115),bar(DAYS[1],lo=97,hi=115)]}
        rows=compare([SIG],prices,DAYS)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["ticker"],"005930")
        self.assertEqual(rows[0]["pullback_limit"]["status"],"CLOSED")
        self.assertEqual(rows[0]["next_open"]["status"],"MISSING_INTERMEDIATE_SESSION_PRICE")
        self.assertFalse(rows[0]["pullback_limit"].get("trade_approved",False))
    def test_nonfills_reduce_signal_level_mean(self):
        values=[dict(pullback_limit={"status":"CLOSED","net_return_pct":10,"net_r":2}),
                dict(pullback_limit={"status":"SKIP_LIMIT_NOT_TOUCHED"})]
        s=aggregate(values,"pullback_limit")
        self.assertEqual(s["closed"],1)
        self.assertEqual(s["mean_net_pct_filled"],10)
        self.assertEqual(s["mean_net_pct_per_decided_signal"],5)
        self.assertTrue(s["mode_not_validated_as_profitable"])
    def test_invalid_version_cannot_join_experiment(self):
        self.assertEqual(compare([{**SIG,"plan_version":"unknown"}],{},DAYS),[])
    def test_date_locked_signal_no_intraday_lookahead(self):
        r=assess_limit(SIG,[bar("2026-10-22",lo=80,hi=150)],DAYS)
        self.assertEqual(r["status"],"MISSING_LIMIT_WINDOW_SESSION_PRICE")

if __name__=="__main__":
    unittest.main()
