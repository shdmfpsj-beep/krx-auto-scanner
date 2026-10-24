"""Offline deterministic resistance evidence and non-promotion tests."""
import copy
import unittest
from datetime import date,timedelta
from unittest.mock import patch
from resistance_tiers_v61 import (
    highs_confirmed, tier_levels, build, summarize, VERSION)
from entry_strategy_v58 import METHODS

ASOF=date(2026,10,23)
T="005930"

def market(n=120):
    days=[]
    d=ASOF
    while len(days)<n:
        if d.weekday()<5:days.append(d)
        d-=timedelta(days=1)
    days.reverse()
    bars=[]
    for i,d in enumerate(days):
        bars.append(dict(date=d,open=100.,high=103.,
            low=98.,close=100.,volume=1000.,source="pykrx"))
    return bars

def paired(when,first=99.5,second=99.0,stop=95.0):
    base=dict(ticker=T,method=METHODS[2],
        signal_asof=str(when),signal_first_reference=str(first),
        signal_second_reference=str(second),
        stop_reference=str(stop),target_reference="110.0",
        signal_close="100.0",trade_approved="False",
        regular_session_certified="False",
        hindsight_selected_ticker="True",
        legacy_first_entry_target="110.0")
    return [{**base,"entry_variant":"FIRST"},
            {**base,"entry_variant":"SECOND"}]

def v60(when,first=99.5,second=99.0,stop=95.0):
    return [dict(ticker=T,method=METHODS[2],signal_asof=str(when),
        variant=k,entry_reference=str(entry),stop_reference=str(stop),
        nearest_overhead_target="103.0",
        regular_session_certified="False",trade_approved="False")
        for k,entry in (("V58_FIRST",first),("V58_PIVOT_SECOND",second))]

class ResistanceV61Tests(unittest.TestCase):
    def test_pivot_requires_two_prior_and_two_subsequent_completed_bars(self):
        b=market(105)
        b[95]["high"]=115
        pivots=highs_confirmed(b)
        self.assertTrue(any(i==95 for i,_,_,_ in pivots))
        b[96]["high"]=116
        pivots=highs_confirmed(b)
        self.assertFalse(any(i==95 for i,_,_,_ in pivots))

    def test_signal_and_previous_candle_are_not_confirmed_pivot_highs(self):
        b=market()
        b[-1]["high"]=150
        b[-2]["high"]=140
        b[-3]["high"]=130
        pivots=highs_confirmed(b)
        self.assertFalse(any(i>=len(b)-3 for i,_,_,_ in pivots))

    def test_nearest_wick_lower_than_confirmed_swing_not_executable_upgrade(self):
        b=market()
        b[-18]["high"]=115
        evidence=tier_levels(b,99.5)
        self.assertEqual(evidence["near"],103)
        self.assertEqual(evidence["pivot"],115)
        self.assertGreater(evidence["pivot"],evidence["near"])
        self.assertGreaterEqual(evidence["near_touches"],1)

    def test_two_separated_confirmed_pivots_create_cluster(self):
        b=market()
        b[-30]["high"]=116
        b[-17]["high"]=115.8
        evidence=tier_levels(b,99.5)
        self.assertEqual(evidence["cluster_count"],2)
        self.assertEqual(evidence["cluster"],115)
        self.assertEqual(len(evidence["cluster_dates"]),2)
        self.assertIsNotNone(evidence["cluster_volume_ratio"])

    def test_single_unconfirmed_high_does_not_create_pivot_or_cluster(self):
        b=market()
        b[-2]["high"]=150
        e=tier_levels(b,99.5)
        self.assertEqual(e["near"],103)
        self.assertIsNone(e["pivot"])
        self.assertIsNone(e["cluster"])

    def test_tick_floor_of_nearest_high_to_entry_is_valid_hard_barrier(self):
        b=market()
        for bar in b:
            bar["high"]=103.8
        e=tier_levels(b,103)
        self.assertEqual(e["near"],103)
        self.assertIsNone(e["pivot"])
        self.assertEqual(e["near_touches"],60)
        self.assertFalse(e["near"]>103)

    def test_no_future_leakage_in_reference_levels(self):
        b=market()
        b[-18]["high"]=114
        cutoff=b[:-7]
        first=tier_levels(cutoff,99.5)
        after=copy.deepcopy(b)
        for x in after[-7:]:
            x["high"]=900
            x["low"]=1
            x["close"]=500
        second=tier_levels(after[:-7],99.5)
        self.assertEqual(first,second)

    def test_rows_do_not_upgrade_pivot_rr_if_nearest_risk_blocks(self):
        b=market()
        b[96]["high"]=115
        # historical signal index 100, leaves 19 subsequent sessions
        when=b[100]["date"]
        controls=paired(when)
        candidates=[dict(ticker=T,name="TEST")]
        with patch("resistance_tiers_v61.signal_rows_for_historic_selected_universe",
                   return_value=(candidates,{T:b},[])):
            res,diagnostic=build(None,controls,v60(when),ASOF)
        self.assertEqual(len(res),2)
        self.assertEqual(diagnostic["signals"],1)
        self.assertTrue(all(x["confirmed_pivot_resistance"]==115 for x in res))
        self.assertTrue(all(x["nearest_wick_reference"]==103 for x in res))
        self.assertTrue(all(x["optimistic_pivot_2r_only"] for x in res))
        self.assertTrue(all(not x["conservative_2r_pass"] for x in res))
        self.assertTrue(all(x["trade_approved"] is False for x in res))
        self.assertTrue(all(x["orders_enabled"] is False for x in res))
        totals=summarize(res,diagnostic,ASOF)
        self.assertEqual(totals["pivot_only_2r_rows"],2)
        self.assertEqual(totals["nearest_2r_rows"],0)
        self.assertEqual(totals["decision"],"CASH")

    def test_v59_v60_price_mismatch_rejected(self):
        b=market()
        when=b[100]["date"]
        mismatched=v60(when)
        mismatched[1]["stop_reference"]="94"
        with patch("resistance_tiers_v61.signal_rows_for_historic_selected_universe",
                   return_value=([dict(ticker=T)],{T:b},[])):
            with self.assertRaisesRegex(ValueError,"V59_V60_PRICE_OR_STOP_DISAGREE"):
                build(None,paired(when),mismatched,ASOF)

    def test_incomplete_baseline_rejected_not_silently_drop_case(self):
        b=market()
        when=b[100]["date"]
        with patch("resistance_tiers_v61.signal_rows_for_historic_selected_universe",
                   return_value=([dict(ticker=T)],{T:b},[])):
            with self.assertRaisesRegex(ValueError,"V60_BASELINE_FIRST_SECOND_NOT_COMPLETE"):
                build(None,paired(when),v60(when)[:1],ASOF)

    def test_baseline_nearby_wick_cannot_be_overwritten_by_pivot(self):
        b=market()
        when=b[100]["date"]
        x=v60(when)
        x[1]["nearest_overhead_target"]="115"
        with patch("resistance_tiers_v61.signal_rows_for_historic_selected_universe",
                   return_value=([dict(ticker=T)],{T:b},[])):
            with self.assertRaisesRegex(ValueError,"V60_BASELINE_NEAREST_FRICTION_MISMATCH"):
                build(None,paired(when),x,ASOF)

if __name__=="__main__":
    unittest.main()
