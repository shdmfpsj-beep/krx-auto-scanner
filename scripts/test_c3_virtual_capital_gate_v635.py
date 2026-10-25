import unittest,math
from c3_virtual_capital_gate_v635 import (paper_whole_share_qty,
 virtual_budget_status,RESEARCH_START_KRW,SCHEMA)

class TestOneMillionC3ResearchGate(unittest.TestCase):
 def test_start_is_1m(self):self.assertEqual(RESEARCH_START_KRW,1_000_000)
 def test_stop_risk_10000_not_price_pct(self):
  self.assertEqual(paper_whole_share_qty(1_000_000,1_000_000,50_000,46_000),2)
 def test_paper_virtual_no_actual_account_changes(self):
  s=virtual_budget_status(50000,46000)
  self.assertEqual(s["schema"],SCHEMA)
  self.assertFalse(s["actual_account_deposit"])
  self.assertFalse(s["trade_approved"])
  self.assertFalse(s["orders_enabled"])
 def test_risk_budget_includes_roundtrip_friction(self):
  s=virtual_budget_status(50000,46000)
  self.assertEqual(s["planned_stop_damage_krw"],8650)
  self.assertLessEqual(s["planned_stop_damage_krw"],s["initial_risk_budget_krw"])
 def test_real_cash_below_1share_will_not_use_virtual_1m(self):
  self.assertEqual(paper_whole_share_qty(1_000_000,10_000,50_000,46_000),0)
 def test_large_stop_exceeds_risk(self):
  self.assertEqual(paper_whole_share_qty(1_000_000,1_000_000,50_000,38_000),0)
 def test_reject_nonfinite_invalid_and_nonsense(self):
  self.assertEqual(paper_whole_share_qty(float('nan'),1e6,50000,46000),0)
  self.assertEqual(paper_whole_share_qty(1e6,1e6,50000,50000),0)
 def test_higher_cost_reduces_not_increases_qty(self):
  a=paper_whole_share_qty(1e6,1e6,50000,46000,friction_fraction=.0065)
  b=paper_whole_share_qty(1e6,1e6,50000,46000,friction_fraction=.0095)
  self.assertLessEqual(b,a)
 def test_gap_risk_not_guaranteed_stop_price(self):
  s=virtual_budget_status(50000,46000)
  self.assertTrue(s["gap_or_unfilled_slippage_may_exceed_budget"])

if __name__=='__main__':unittest.main()
