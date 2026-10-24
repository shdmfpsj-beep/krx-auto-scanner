"""Offline tests: pre-signal wick evidence, truly separated future reactions."""
import copy
import unittest
from datetime import date,timedelta
from unittest.mock import patch

from wick_barrier_reliability_v62 import (
    pre_signal_rejections,classify_barrier,future_reactions,
    frozen_inputs_valid,analyze,aggregate,SCHEMA,LABELS,HORIZON)
from resistance_tiers_v61 import tier_levels
from entry_strategy_v58 import METHODS

ASOF=date(2026,10,23)
TICKER="005930"

def bars(n=120):
    dates=[]
    d=ASOF
    while len(dates)<n:
        if d.weekday()<5:dates.append(d)
        d-=timedelta(days=1)
    dates.reverse()
    return [dict(date=d,open=100.0,high=103.0,low=98.0,
                 close=100.0,volume=1000,source="pykrx") for d in dates]

def archived(b):
    day=b[100]["date"].isoformat()
    out=[]
    for entry,variant in ((100,"V58_FIRST"),(99,"V58_PIVOT_SECOND")):
        t=tier_levels(b[:101],entry)
        out.append(dict(ticker=TICKER,name="TEST",method=METHODS[2],
            signal_asof=day,variant=variant,entry_reference=str(entry),
            daily_pivot_stop="95",nearest_wick_reference=str(t["near"]),
            confirmed_pivot_resistance="",
            clustered_pivot_resistance="",trade_approved="False",
            orders_enabled="False",regular_price_certified="False"))
    status=dict(schema="C3_K100_RESISTANCE_EVIDENCE_V61",asof=str(ASOF),
        absolute_nearest_wick_is_hard_barrier_for_buy_approval=True,
        actual_regular_session_provider_verified=False,
        original_research_signals=1,evaluated_entry_rows=2,
        trade_approved=False,orders_enabled=False)
    return status,out

class ReliabilityV62Tests(unittest.TestCase):
    def test_lookback_does_not_use_current_signal_or_forward(self):
        b=bars()
        pre=b[:101]
        reference=tier_levels(pre,100)
        dates,crossed=pre_signal_rejections(pre,reference["near"],reference["atr"])
        edited=copy.deepcopy(b)
        for x in edited[101:]:
            x.update(open=400,close=400,high=450,low=390)
        new=tier_levels(edited[:101],100)
        new_dates,new_crossed=pre_signal_rejections(
            edited[:101],new["near"],new["atr"])
        self.assertEqual((dates,crossed),(new_dates,new_crossed))
        self.assertEqual(reference,new)

    def test_two_rejections_must_be_separated_by_three_completed_bars(self):
        b=bars()
        for bar in b:bar["close"]=102.9
        pre=b[:101]
        b[50]["close"]=100
        b[51]["close"]=100
        b[54]["close"]=100
        t=tier_levels(pre,100)
        days,over=pre_signal_rejections(pre,t["near"],t["atr"])
        self.assertEqual(len(days),2)
        self.assertEqual(over,0)
        self.assertEqual(classify_barrier(t["near"],100,0,len(days)),
                         "REPEATED_PRE_SIGNAL_REJECTION")

    def test_close_break_has_separate_pre_signal_class(self):
        b=bars()
        for bar in b:bar.update(high=110,close=108,low=98)
        near=103
        days,prior=pre_signal_rejections(b[:101],near,4)
        self.assertEqual(days,[])
        self.assertGreater(prior,0)
        self.assertEqual(classify_barrier(near,100,prior,0),
                         "HISTORIC_CLOSE_THROUGH_BARRIER")

    def test_no_barrier_and_at_entry_are_explicit_not_a_proven_target(self):
        self.assertEqual(classify_barrier(None,100,0,0),LABELS[0])
        self.assertEqual(classify_barrier(100,100,0,8),LABELS[1])
        self.assertEqual(future_reactions(bars()[101:106],None,2)[
            "forward_any_close_break"],False)

    def test_future_high_without_close_confirmation_is_not_a_break(self):
        b=bars()[101:106]
        b[0].update(high=120,close=100,low=98)
        z=future_reactions(b,103,5)
        self.assertTrue(z["forward_any_touch"])
        self.assertFalse(z["forward_any_close_break"])
        self.assertTrue(z["forward_any_rejection"])
        self.assertFalse(z["forward_two_consecutive_close_break"])

    def test_two_consecutive_future_closes_above_buffer(self):
        b=bars()[101:106]
        b[1].update(high=112,close=110)
        b[2].update(high=114,close=111)
        z=future_reactions(b,103,5)
        self.assertTrue(z["forward_any_touch"])
        self.assertTrue(z["forward_any_close_break"])
        self.assertTrue(z["forward_two_consecutive_close_break"])
        self.assertEqual(z["forward_first_close_break_day"],b[1]["date"].isoformat())

    def test_truncated_forward_horizon_is_not_negative_outcome(self):
        with self.assertRaisesRegex(ValueError,"FORWARD_FIVE_SESSION_WINDOW_MISSING"):
            future_reactions(bars()[101:104],103,5)

    def test_reject_duplicate_or_missing_second_or_wrong_date(self):
        b=bars();meta,r=archived(b)
        self.assertTrue(frozen_inputs_valid(meta,r,ASOF))
        with self.assertRaisesRegex(ValueError,"V61_DATE_OR_FULL_EVIDENCE_UNVERIFIED"):
            frozen_inputs_valid(meta,r[:1],ASOF)
        dup=copy.deepcopy(r)
        dup[1]["variant"]=dup[0]["variant"]
        with self.assertRaisesRegex(ValueError,"V61_DUPLICATE_OR_UNSAFE_TRADE_ROW"):
            frozen_inputs_valid(meta,dup,ASOF)
        late=copy.deepcopy(r);late[1]["signal_asof"]=str(ASOF)
        with self.assertRaisesRegex(ValueError,"V61_FUTURE_OR_ASOF_SIGNAL"):
            frozen_inputs_valid(meta,late,ASOF)

    def test_fail_closed_on_source_order_approval(self):
        b=bars();meta,r=archived(b)
        meta["trade_approved"]=True
        with self.assertRaises(ValueError):frozen_inputs_valid(meta,r,ASOF)
        meta["trade_approved"]=False;r[0]["orders_enabled"]="True"
        with self.assertRaisesRegex(ValueError,"V61_DUPLICATE_OR_UNSAFE_TRADE_ROW"):
            frozen_inputs_valid(meta,r,ASOF)

    def test_exact_asof_tier_price_mismatch_prevents_wrong_replay(self):
        b=bars();meta,rows=archived(b)
        rows[0]["nearest_wick_reference"]="999"
        with patch("wick_barrier_reliability_v62.signal_rows_for_historic_selected_universe",
                   return_value=([dict(ticker=TICKER)],{TICKER:b},[])):
            with self.assertRaisesRegex(ValueError,"V61_DAILY_PRICE_TIER_DRIFT_near"):
                analyze(None,meta,rows,ASOF)

    def test_full_two_variant_replay_no_buy_and_no_fake_probability(self):
        b=bars();meta,rows=archived(b)
        with patch("wick_barrier_reliability_v62.signal_rows_for_historic_selected_universe",
                   return_value=([dict(ticker=TICKER)],{TICKER:b},[])):
            result,issues=analyze(None,meta,rows,ASOF)
        self.assertEqual(len(result),2)
        self.assertTrue(all(x["forward_bar_count"]==5 for x in result))
        self.assertTrue(all(x["historically_selected_universe"] for x in result))
        self.assertTrue(all(x["trade_approved"] is False for x in result))
        self.assertTrue(all(x["orders_enabled"] is False for x in result))
        report=aggregate(result,ASOF,issues)
        self.assertEqual(report["schema"],SCHEMA)
        self.assertEqual(report["input_rows"],2)
        self.assertFalse(report["validated_win_probability_available"])
        self.assertFalse(report["exact_regular_session_source_verified"])
        self.assertEqual(report["decision"],"CASH")

    def test_signal_close_reclaim_is_reported_but_does_not_override_barrier(self):
        b=bars()
        meta,raw=archived(b)
        b[100].update(open=100,high=109,low=98,close=108)
        with patch("wick_barrier_reliability_v62.signal_rows_for_historic_selected_universe",
                   return_value=([dict(ticker=TICKER)],{TICKER:b},[])):
            cases,_=analyze(None,meta,raw,ASOF)
        self.assertEqual(len(cases),2)
        for item in cases:
            self.assertTrue(item["nearby_barrier_below_signal_close"])
            self.assertTrue(item["signal_close_confirms_barrier_reclaim"])
            self.assertGreater(item["signal_close_over_near_atr"],.25)
            self.assertFalse(item["barrier_status_is_proven_resistance"])
            self.assertFalse(item["trade_approved"])

    def test_report_counts_separate_first_vs_second_without_claimed_win_rate(self):
        b=bars();meta,raw=archived(b)
        with patch("wick_barrier_reliability_v62.signal_rows_for_historic_selected_universe",
                   return_value=([dict(ticker=TICKER)],{TICKER:b},[])):
            records,errors=analyze(None,meta,raw,ASOF)
        report=aggregate(records,ASOF,errors)
        self.assertEqual(report["by_entry_variant"]["V58_FIRST"]["rows"],1)
        self.assertEqual(report["by_entry_variant"]["V58_PIVOT_SECOND"]["rows"],1)
        self.assertEqual(sum(x["rows"] for x in report["categories"].values()),2)
        self.assertTrue(report["signal_close_reclaim_is_diagnostic_not_trading_permission"])
        self.assertFalse(report["validated_win_probability_available"])
        self.assertEqual(report["decision"],"CASH")

    def test_break_above_level_is_not_fresh_when_signal_already_above(self):
        b=bars();meta,raw=archived(b)
        b[100].update(high=110,close=108)
        b[101].update(high=115,close=110)
        b[102].update(high=115,close=110)
        with patch("wick_barrier_reliability_v62.signal_rows_for_historic_selected_universe",
                   return_value=([dict(ticker=TICKER)],{TICKER:b},[])):
            outcome,_=analyze(None,meta,raw,ASOF)
        self.assertTrue(outcome[0]["signal_close_confirms_barrier_reclaim"])
        self.assertTrue(outcome[0]["forward_any_close_break"])
        self.assertFalse(outcome[0]["forward_new_close_break_after_signal_below"])
        self.assertTrue(outcome[0]["forward_above_after_signal_already_reclaimed"])

    def test_fresh_break_when_signal_close_starts_below_level(self):
        b=bars();meta,raw=archived(b)
        b[101].update(high=114,close=111)
        with patch("wick_barrier_reliability_v62.signal_rows_for_historic_selected_universe",
                   return_value=([dict(ticker=TICKER)],{TICKER:b},[])):
            outcome,_=analyze(None,meta,raw,ASOF)
        self.assertFalse(outcome[0]["signal_close_confirms_barrier_reclaim"])
        self.assertTrue(outcome[0]["forward_new_close_break_after_signal_below"])
        self.assertFalse(outcome[0]["forward_above_after_signal_already_reclaimed"])
        report=aggregate(outcome,ASOF,[])
        self.assertTrue(report["post_signal_first_breaks_separate_from_already_reclaimed_price"])

    def test_forward_outcomes_mutation_does_not_change_pre_signal_labels(self):
        b=bars();meta,rows=archived(b)
        with patch("wick_barrier_reliability_v62.signal_rows_for_historic_selected_universe",
                   return_value=([dict(ticker=TICKER)],{TICKER:b},[])):
            old,_=analyze(None,meta,rows,ASOF)
        changed=copy.deepcopy(b)
        changed[102].update(high=125,close=120)
        changed[103].update(high=125,close=120)
        with patch("wick_barrier_reliability_v62.signal_rows_for_historic_selected_universe",
                   return_value=([dict(ticker=TICKER)],{TICKER:changed},[])):
            new,_=analyze(None,meta,rows,ASOF)
        for before,after in zip(old,new):
            self.assertEqual(before["pre_signal_barrier_label"],
                             after["pre_signal_barrier_label"])
            self.assertEqual(before["prior_independent_rejection_count"],
                             after["prior_independent_rejection_count"])
            self.assertEqual(before["nearest_barrier"],after["nearest_barrier"])
            self.assertFalse(before["forward_two_consecutive_close_break"])
            self.assertTrue(after["forward_two_consecutive_close_break"])
            self.assertFalse(after["trade_approved"])

if __name__=="__main__":
    unittest.main()
