#!/usr/bin/env python3
"""Fail-closed daily entry geometry tests including risk and anti-chase."""
import unittest
from entry_setup_audit import build,level_range,down_tick,up_tick,check_row

DAY="2026-10-22"
STOCK=dict(ticker="005930",name="삼성전자",sector_id="SEMICON",
  independent_stop_status="HISTORICAL_DAILY_REFERENCE_ONLY",
  independently_collected_daily_stop_reference="185000")
ROW=dict(ticker="005930",name="삼성전자",latest_complete_date=DAY,
  data_source="V18_KRX_CACHED",bar_count="80",close="220000",
  atr14="4000",pivot_date="2026-10-12",pivot_low="200000",
  historical_stop_reference="198000",entry1_research_range="218,500~220,000",
  entry2_support_research_range="210,000~213,000",
  prior_60d_high="290000",no_chase_reference="222000",
  structure_state="RESEARCH_GEOMETRY_CANDIDATE",data_problems="")
def input_report(stock=None,row=None,asof=DAY):
    return dict(asof=asof,stock_research_top5=[
      STOCK if stock is None else stock],
      focus_daily_structure_research=[
      ROW if row is None else row],focus_close_conflict_tickers=[])

class EntryTests(unittest.TestCase):
    def test_verified_real_bar_geometry_produces_meaningful_prices(self):
        r=build(input_report())
        x=r["candidates"][0]
        self.assertTrue(x["technical_research_pass"])
        self.assertEqual(x["first_entry_krw"],[218500,220000])
        self.assertEqual(x["second_entry_support_krw"],[210000,213000])
        self.assertEqual(x["stop_krw"],198000)
        self.assertEqual(x["resistance_krw"],290000)
        self.assertAlmostEqual(x["forward_rr_at_first_ceiling"],3.18,places=2)
        self.assertEqual(x["target_2r_krw"],264000)
        self.assertFalse(x["real_buy_approved"])
        self.assertEqual(r["decision"],"CASH")
    def test_very_close_stop_is_structural_quality_failure(self):
        row={**ROW,"historical_stop_reference":"217000",
             "pivot_low":"218000"}
        x=build(input_report(row=row))["candidates"][0]
        self.assertEqual(x["code"],"STOP_DISTANCE_OUTSIDE_2_TO_12_PCT")
        self.assertFalse(x["technical_research_pass"])
    def test_very_distant_stop_is_structural_quality_failure(self):
        row={**ROW,"historical_stop_reference":"165000",
             "pivot_low":"168000"}
        self.assertEqual(build(input_report(row=row))["candidates"][0]["code"],
                         "STOP_DISTANCE_OUTSIDE_2_TO_12_PCT")
    def test_no_2r_to_old_resistance_is_rejected(self):
        row={**ROW,"prior_60d_high":"245000"}
        x=build(input_report(row=row))["candidates"][0]
        self.assertEqual(x["code"],"FORWARD_REWARD_RISK_BELOW_2R")
        self.assertEqual(x["forward_rr_at_first_ceiling"],1.14)
    def test_no_chase_ceiling_overrun(self):
        row={**ROW,"no_chase_reference":"219000"}
        x=build(input_report(row=row))["candidates"][0]
        self.assertEqual(x["code"],"CHASE_OR_ENTRY_GEOMETRY_INVALID")
    def test_price_feed_conflict_blocks_all_prices(self):
        r=input_report()
        r["focus_close_conflict_tickers"]=["005930"]
        x=build(r)["candidates"][0]
        self.assertEqual(x["code"],"CROSS_SOURCE_PRICE_CONFLICT")
        self.assertIsNone(x["first_entry_krw"])
        self.assertIsNone(x["stop_krw"])
    def test_older_bar_is_not_usable(self):
        row={**ROW,"latest_complete_date":"2026-10-21"}
        self.assertEqual(build(input_report(row=row))["candidates"][0]["code"],
                         "BAR_OR_PIVOT_DATE_MISMATCH")
    def test_future_pivot_is_never_a_research_stop(self):
        row={**ROW,"pivot_date":"2026-10-23"}
        self.assertEqual(build(input_report(row=row))["candidates"][0]["code"],
                         "BAR_OR_PIVOT_DATE_MISMATCH")
    def test_insufficient_65_bar_history_not_accepted(self):
        row={**ROW,"bar_count":"44"}
        self.assertEqual(build(input_report(row=row))["candidates"][0]["code"],
                         "NO_65_VERIFIED_OHLC_BARS")
    def test_source_research_pivot_stop_must_be_valid(self):
        row={**ROW,"pivot_low":"180000"}
        self.assertEqual(build(input_report(row=row))["candidates"][0]["code"],
                         "UNVERIFIED_DAILY_STOP_PIVOT_ATR")
    def test_unconfirmed_independent_price_blocks_old_stock_references(self):
        stock={**STOCK,"independent_stop_status":"NO_HELD_CONFIRMED_PIVOT"}
        self.assertEqual(build(input_report(stock=stock))["candidates"][0]["code"],
                         "INDEPENDENT_PIVOT_NOT_ACCEPTED")
    def test_missing_second_support_does_not_invent_second_buy_price(self):
        row={**ROW,"entry2_support_research_range":""}
        x=build(input_report(row=row))["candidates"][0]
        self.assertTrue(x["technical_research_pass"])
        self.assertIsNone(x["second_entry_support_krw"])
    def test_bad_range_parser_rejects_inverted_and_unknown(self):
        self.assertIsNone(level_range("220000~210000"))
        self.assertIsNone(level_range("보류"))
        self.assertIsNone(level_range("220000"))
        self.assertEqual(level_range("200,000~210,000"),(200000,210000))
    def test_krx_tier_tick_rounding(self):
        self.assertEqual(down_tick(190999),190900)
        self.assertEqual(up_tick(220001),220500)
        self.assertEqual(down_tick(49599),49550)
        self.assertEqual(up_tick(49999),50000)
    def test_unverifiable_entry_is_no_signal_not_zero(self):
        row={**ROW,"entry1_research_range":""}
        x=build(input_report(row=row))["candidates"][0]
        self.assertEqual(x["code"],"NO_VALID_FIRST_ENTRY_RANGE")
        self.assertIsNone(x["forward_rr_at_first_ceiling"])
    def test_unseen_future_prices_are_not_accessed(self):
        r=build(input_report(asof="2026-10-21"))
        self.assertEqual(r["technical_geometry_pass_count"],0)
        self.assertEqual(r["prospective_trades_created"],0)
    def test_data_problems_disable_setup_even_with_plausible_numbers(self):
        row={**ROW,"data_problems":"OHLC_DUPLICATE"}
        self.assertEqual(build(input_report(row=row))["candidates"][0]["code"],
                         "SOURCE_OHLC_DATA_ISSUE")
    def test_empty_report_is_clear_cash_not_fake_approvals(self):
        r=build({"asof":DAY,"stock_research_top5":[]})
        self.assertEqual(r["stock_count"],0)
        self.assertEqual(r["decision"],"CASH")
        self.assertFalse(r["trade_approved"])
        self.assertEqual(r["prospective_trades_created"],0)

if __name__=="__main__":unittest.main()
