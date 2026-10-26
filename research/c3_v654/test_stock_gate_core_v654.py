import unittest
from stock_gate_core_v654 import SignalD,historical_research_gate

def sample(**kw):
    d=dict(ticker="006110",asof="2026-10-23",d_close=60000,d_stop=54000,
        ret5=5.0,breadth20=.60,recorded_resistance=None)
    d.update(kw)
    return SignalD(**d)

class TestC3Guard(unittest.TestCase):
 def test_good_research_trend_not_buy(self):
  x=historical_research_gate(sample())
  self.assertTrue(x["research_strong_market_stock"])
  self.assertFalse(x["stock_buy_approved"]);self.assertFalse(x["orders_enabled"])
 def test_stock_ret5_nonpos_reject(self):
  self.assertFalse(historical_research_gate(sample(ret5=0))["research_strong_market_stock"])
 def test_weak_breadth_reject(self):
  self.assertFalse(historical_research_gate(sample(breadth20=.499))["research_strong_market_stock"])
 def test_threshold_research_only(self):
  self.assertTrue(historical_research_gate(sample(breadth20=.5))["research_strong_market_stock"])
 def test_no_recorded_target_means_no_R(self):
  x=historical_research_gate(sample());self.assertIsNone(x["recorded_overhead_R"])
  self.assertFalse(x["overhead_verified_R2"])
 def test_close_resistance_fails_2R(self):
  self.assertFalse(historical_research_gate(sample(recorded_resistance=62000))["overhead_verified_R2"])
 def test_distant_overhead_still_not_approved(self):
  x=historical_research_gate(sample(recorded_resistance=90000))
  self.assertTrue(x["overhead_verified_R2"]);self.assertFalse(x["stock_buy_approved"])
 def test_no_future_outcome_possible(self):
  with self.assertRaises(TypeError):sample(future_return_5=999)
 def test_no_position_size_input(self):
  with self.assertRaises(TypeError):sample(account_capital=100000000)
 def test_invalid_ticker(self):
  with self.assertRaises(ValueError):historical_research_gate(sample(ticker="6110"))
 def test_structure_invalid(self):
  with self.assertRaises(ValueError):historical_research_gate(sample(d_stop=61000))
 def test_breadth_invalid(self):
  with self.assertRaises(ValueError):historical_research_gate(sample(breadth20=1.2))
 def test_source_not_certified(self):
  self.assertFalse(historical_research_gate(sample())["complete_original_KRX_regular_price_verified"])
 def test_issuer_not_certified(self):
  self.assertFalse(historical_research_gate(sample())["contemporaneous_issuer_and_sector_verified"])

if __name__=="__main__":unittest.main()
