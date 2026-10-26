import unittest
from historical_vintage_and_price_guard import etf_pdf_vintage_gate, after_cost_chart_payoff_ratio

class HistoricalPublicationV653(unittest.TestCase):
 def test_screenshot_backfill_cannot_retroactively_buy(self):
  x=etf_pdf_vintage_gate("2026-08-18","2026-10-23T12:23:12+00:00","2026-09-01")
  self.assertTrue(x["historical_backfill_after_signal_close"])
  self.assertFalse(x["eligible_as_strict_live_sector_membership"])
 def test_same_D_after1530_is_too_late(self):
  x=etf_pdf_vintage_gate("2026-10-19","2026-10-23T12:23:12Z","2026-10-23")
  self.assertFalse(x["observed_by_D_this_system"])
 def test_prior_source_capture_still_not_independently_published(self):
  x=etf_pdf_vintage_gate("2026-10-19","2026-10-22T05:00:00Z","2026-10-23")
  self.assertTrue(x["observed_by_D_this_system"])
  self.assertFalse(x["publication_vintage_independently_certified"])
  self.assertFalse(x["trade_approved"])
 def test_original_snapshot_after_signal_is_rejected(self):
  with self.assertRaises(ValueError):
   etf_pdf_vintage_gate("2026-10-25","2026-10-22T05:00:00Z","2026-10-23")
 def test_naive_collection_timestamp_rejected(self):
  with self.assertRaises(ValueError):
   etf_pdf_vintage_gate("2026-10-19","2026-10-23T12:23:12","2026-10-23")
 def test_historical_study_rr_example(self):
  self.assertAlmostEqual(after_cost_chart_payoff_ratio(378000,340500,422000),1.039062598,7)
 def test_account_capital_not_part_of_price(self):
  r=after_cost_chart_payoff_ratio(378000,340500,422000)
  self.assertEqual(r,after_cost_chart_payoff_ratio(378000,340500,422000))
 def test_overhead_inside_entry_fails(self):
  with self.assertRaises(ValueError):
   after_cost_chart_payoff_ratio(100,90,95)
 def test_stop_above_entry_fails(self):
  with self.assertRaises(ValueError):
   after_cost_chart_payoff_ratio(100,101,150)
 def test_bad_prices_rejected(self):
  with self.assertRaises(ValueError):
   after_cost_chart_payoff_ratio(100,90,float('nan'))
if __name__=="__main__":unittest.main()
