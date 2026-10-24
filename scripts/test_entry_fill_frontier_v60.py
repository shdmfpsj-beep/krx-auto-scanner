"""Offline risk-frontier regression: no forward leakage or false trading signals."""
import copy
import unittest
from datetime import date,timedelta
from unittest.mock import patch

from entry_fill_frontier_v60 import (
    VARIANTS, archived_signals, entry_levels, bounded_two_r_price,
    simulate_variants, summary, mobile, SCHEMA)
from entry_strategy_v58 import METHODS

ASOF=date(2026,10,23)
T="005930"

def dates(n=120):
    d=ASOF
    out=[]
    while len(out)<n:
        if d.weekday()<5:out.append(d)
        d-=timedelta(days=1)
    return out[::-1]

def candles():
    out=[]
    for i,d in enumerate(dates()):
        cl=100+i*.18
        out.append(dict(date=d,open=cl-.5,high=cl+2.5,
             low=cl-2.5,close=cl,volume=1200,source="pykrx"))
    return out

def pairs(when):
    base=dict(signal_asof=str(when),ticker=T,method=METHODS[2],
        signal_first_reference="115",signal_second_reference="110",
        stop_reference="105",target_reference="125",
        signal_close="118.9",trade_approved="False",
        regular_session_certified="False",hindsight_selected_ticker="True")
    return [{**base,"entry_variant":"FIRST"},
            {**base,"entry_variant":"SECOND"}]

class FrontierTests(unittest.TestCase):
    def test_five_price_policies_are_fixed_before_forward_bars(self):
        b=candles()
        i=100
        pre=b[:i+1]
        original=entry_levels(pre,115,110,105)
        future=copy.deepcopy(b)
        for x in future[i+1:]:
            x.update(open=500,high=1000,low=1,close=999)
        changed=entry_levels(future[:i+1],115,110,105)
        self.assertEqual(original,changed)
        self.assertEqual(tuple(original.keys()),VARIANTS)
        self.assertEqual(original["V58_FIRST"],115)
        self.assertEqual(original["V58_PIVOT_SECOND"],110)

    def test_archive_requires_exact_paired_variants(self):
        sig=date(2026,10,10)
        x=pairs(sig)
        self.assertEqual(len(archived_signals(x,ASOF)),1)
        with self.assertRaisesRegex(ValueError,"UNPAIRED"):
            archived_signals(x[:1],ASOF)
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            archived_signals(x+[x[0]],ASOF)

    def test_archived_signal_cannot_be_today_or_future(self):
        with self.assertRaisesRegex(ValueError,"FUTURE"):
            archived_signals(pairs(ASOF),ASOF)
        x=pairs(date(2026,10,22))
        x[0]["trade_approved"]="True"
        with self.assertRaisesRegex(ValueError,"UNSAFE"):
            archived_signals(x,ASOF)

    def test_invalid_control_geometry_is_preserved_not_selection_filtered(self):
        b=candles()
        sig=b[100]["date"]
        x=pairs(sig)
        for r in x:
            r["stop_reference"]="125" # now > first, must not silently drop
        c=[dict(ticker=T)]
        with patch("entry_fill_frontier_v60.signal_rows_for_historic_selected_universe",
                   return_value=(c,{T:b},[])):
            result,diag=simulate_variants(None,x,ASOF)
        self.assertEqual(diag["signals"],1)
        self.assertEqual(len(result),5)
        self.assertTrue(all(r["geometry_blocker"]=="INVALID_ARCHIVED_STOP_OR_FIRST"
                            for r in result))
        self.assertFalse(any(r["trade_approved"] for r in result))

    def test_no_trade_promotion_and_five_prices_single_signal(self):
        b=candles()
        x=pairs(b[100]["date"])
        c=[dict(ticker=T)]
        with patch("entry_fill_frontier_v60.signal_rows_for_historic_selected_universe",
                   return_value=(c,{T:b},[])):
            result,diag=simulate_variants(None,x,ASOF)
        self.assertEqual(diag["signals"],1)
        self.assertEqual(len(result),5)
        self.assertEqual([r["variant"] for r in result],list(VARIANTS))
        self.assertTrue(all(r["hindsight_universe"] for r in result))
        self.assertTrue(all(r["trade_approved"] is False for r in result))
        self.assertTrue(all(r["regular_session_certified"] is False for r in result))
        self.assertTrue(all(r["price_is_unconfirmed_support_proxy"]
            for r in result[2:]))
        self.assertFalse(any(r["geometry_2r_ok"] for r in result[2:]))

    def test_future_changes_outcome_only_not_candidate_entry(self):
        b=candles()
        sig=b[100]["date"]
        base=pairs(sig)
        c=[dict(ticker=T)]
        with patch("entry_fill_frontier_v60.signal_rows_for_historic_selected_universe",
                   return_value=(c,{T:b},[])):
            first,_=simulate_variants(None,base,ASOF)
        future=copy.deepcopy(b)
        for i in range(101,108):
            future[i].update(open=180,high=190,low=160,close=175)
        with patch("entry_fill_frontier_v60.signal_rows_for_historic_selected_universe",
                   return_value=(c,{T:future},[])):
            altered,_=simulate_variants(None,base,ASOF)
        for a,z in zip(first,altered):
            self.assertEqual(a["entry_reference"],z["entry_reference"])
            self.assertEqual(a["nearest_overhead_target"],z["nearest_overhead_target"])
            self.assertEqual(a["cost_adjusted_rr"],z["cost_adjusted_rr"])

    def test_r2_boundary_must_not_use_unobserved_future_target(self):
        b=candles()
        pre=b[:101]
        v=bounded_two_r_price(pre,115,105,5)
        fut=copy.deepcopy(b)
        fut[-1]["high"]=9999
        self.assertEqual(v,bounded_two_r_price(fut[:101],115,105,5))

    def test_summary_unfilled_payoff_is_not_investment_roi(self):
        b=candles()
        x=pairs(b[100]["date"])
        with patch("entry_fill_frontier_v60.signal_rows_for_historic_selected_universe",
                   return_value=([dict(ticker=T)],{T:b},[])):
            rs,diag=simulate_variants(None,x,ASOF)
        r=summary(rs,ASOF,diag,{})
        self.assertEqual(r["schema"],SCHEMA)
        self.assertEqual(r["research_rows"],5)
        self.assertEqual(r["research_signals"],1)
        self.assertTrue(r["signal_weighted_zeros_for_unfilled_are_not_pnl_on_deployed_capital"])
        self.assertFalse(r["winner_variant_not_selected_from_hindsight"] is False)
        self.assertFalse(r["trade_approved"])
        self.assertFalse(r["orders_enabled"])
        self.assertEqual(r["decision"],"CASH")
        self.assertIn("미체결",mobile(r))

if __name__=="__main__":
    unittest.main()
