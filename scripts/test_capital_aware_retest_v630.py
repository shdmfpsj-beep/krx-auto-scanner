#!/usr/bin/env python3
import math,unittest
from capital_aware_retest_v630 import (
 affordable_shares,research_capacity,hypothetical_close_entry_pnl,SCHEMA)

class C3V630Safety(unittest.TestCase):
 def test_one_pct_risk_and_friction(self):
  self.assertEqual(affordable_shares(269230,10000,9000,1),2)
 def test_two_pct_doubles_some_opportunities(self):
  self.assertEqual(affordable_shares(269230,10000,9000,2),5)
 def test_cash_does_not_authorize_one_expensive_share(self):
  self.assertEqual(affordable_shares(269230,300000,270000,1),0)
 def test_high_structural_loss_exceeds_account_budget(self):
  self.assertEqual(affordable_shares(269230,50000,40000,1),0)
 def test_invalid_or_nan_never_returns_shares(self):
  self.assertEqual(affordable_shares(float('nan'),10000,9000,1),0)
  self.assertEqual(affordable_shares(269230,10000,10000,1),0)
  self.assertEqual(affordable_shares(269230,10000,9000,0),0)
 def test_research_only_even_when_snapshots_verified(self):
  x=research_capacity(269230,10000,9000,1,True)
  self.assertEqual(x["schema"],SCHEMA)
  self.assertFalse(x["trade_approved"])
  self.assertFalse(x["orders_enabled"])
  self.assertFalse(x["confirmed_broker_fill"])
 def test_risk_limit_and_notional(self):
  x=research_capacity(269230,10000,9000,1)
  self.assertEqual(x["research_qty"],2)
  self.assertEqual(x["expected_entry_notional_krw"],20000)
  self.assertLessEqual(x["modeled_stop_budget_krw"],269230*.01)
 def test_cash_return_is_on_order_shares_not_entire_equity(self):
  x=hypothetical_close_entry_pnl(269230,10000,9000,10,1)
  self.assertEqual(x["shares"],2)
  self.assertEqual(x["modeled_pnl_krw"],2000)
  self.assertEqual(x["new_cash"],271230)
 def test_zero_shares_cash_is_kept_without_retro_substitution(self):
  x=hypothetical_close_entry_pnl(269230,50000,40000,10,1)
  self.assertEqual(x["shares"],0)
  self.assertEqual(x["new_cash"],269230)
 def test_nan_model_outcome_must_be_rejected(self):
  with self.assertRaises(ValueError):
   hypothetical_close_entry_pnl(269230,10000,9000,float('nan'),1)

if __name__=="__main__":unittest.main()
