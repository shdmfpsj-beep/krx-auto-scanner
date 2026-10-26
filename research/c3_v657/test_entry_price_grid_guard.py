import unittest
from entry_price_grid_guard import (
  korea_cash_stock_price_grid_2023,price_grid_floor,frozen_D_research_prices)

class TestV657PriceGrid(unittest.TestCase):
 def trial(self,**kw):
  a=dict(ticker='005930',asof='2026-10-23',close=50100.0,
         original_structural_stop=45000.0,ATR14=3000.0,
         true_documented_overhead=58000.0,
         pre_D_known_support=49700.0,support_proven_asof='2026-10-23')
  a.update(kw);return frozen_D_research_prices(**a)
 def test_price_tiers(self):
  for price,expected in [(1999,1),(2000,5),(4999,5),(5000,10),
                         (20000,50),(49999,50),(50000,100),(200000,500),
                         (500000,1000)]:
   with self.subTest(price=price):self.assertEqual(korea_cash_stock_price_grid_2023(price),expected)
 def test_floor_valid(self):
  self.assertEqual(price_grid_floor(48876.1),48850)
 def test_floor_never_more_expensive(self):
  self.assertLessEqual(price_grid_floor(50133),50133)
 def test_d_close_bid(self):
  self.assertEqual(self.trial()['D_close_resting_limit_research'],50100)
 def test_atr_10(self):
  self.assertEqual(self.trial()['ATR10_resting_limit_research'],49800)
 def test_atr_25(self):
  self.assertEqual(self.trial()['ATR25_resting_limit_research'],49300)
 def test_near_chart_line(self):
  self.assertEqual(self.trial()['D_prior_support_resting_limit_research'],49700)
 def test_pit_future_support_rejected(self):
  with self.assertRaises(ValueError):
   self.trial(support_proven_asof='2026-10-26')
 def test_asof_missing_rejected(self):
  with self.assertRaises(ValueError):
   self.trial(support_proven_asof=None)
 def test_no_price_fabrication_when_resistance_missing(self):
  self.assertIsNone(self.trial(true_documented_overhead=None)['recorded_first_overhead_or_none'])
 def test_price_stop_integrity(self):
  with self.assertRaises(ValueError):
   self.trial(original_structural_stop=52000)
 def test_no_budget_input(self):
  with self.assertRaises(TypeError):
   self.trial(capital=1000000)
 def test_no_future_profit_input(self):
  with self.assertRaises(TypeError):
   self.trial(return_after_5days=100)
 def test_no_poc_from_daily_OHLC(self):
  self.assertFalse(self.trial()['support_IS_ACTUAL_volume_profile'])
 def test_orders_off(self):
  r=self.trial()
  self.assertFalse(r['trade_approved'])
  self.assertFalse(r['orders_enabled'])
  self.assertFalse(r['broker_fill_verified'])
 def test_too_low_bids_rejected_under_stop(self):
  self.assertIsNone(self.trial(ATR14=25000)['ATR25_resting_limit_research'])

if __name__=='__main__': unittest.main()
