import unittest
from practical_entry_quotes_v619 import (
 tick,krx_round,quote_set,next_session_touch,
 completed_retest_signal,confirmed_d2_open,risk_capacity,SCHEMA
)

class PracticalV619Tests(unittest.TestCase):
 def test_krx_order_grid_price_bands(self):
  for price,down,up in ((1999.9,1999,2000),(2001,2000,2005),
   (4999,4995,5000),(5008,5000,5010),(19999,19990,20000),
   (20123,20100,20150),(49999,49950,50000),
   (50099,50000,50100),(199999,199900,200000),
   (200499,200000,200500),(500999,500000,501000)):
   self.assertEqual(krx_round(price),down)
   self.assertEqual(krx_round(price,'up'),up)
 def test_invalid_prices_do_not_yield_order_prices(self):
  for x in (0,-2,float('nan'),float('inf')):
   with self.assertRaises(ValueError):tick(x)
 def test_stop_precedes_first_and_alternative_is_not_averaging(self):
  a=quote_set(11000,360,10700,10300,10900,12800)
  self.assertEqual(len(a),2)
  self.assertTrue(all(x['day_structure_stop_krw']<x['proposed_limit_krw'] for x in a))
  self.assertTrue(all(x['one_slot_second_not_add_on'] for x in a))
  self.assertTrue(all(not x['trade_approved'] for x in a))
 def test_missing_verified_overhead_does_not_pass_by_inventing_target(self):
  a=quote_set(11000,360,10700,10300,10900,None)
  self.assertTrue(all(x['verified_overhead_net_R'] is None for x in a))
  self.assertTrue(all(x['research_tier']=='WATCH_PRICE_ONLY_NO_VERIFIED_2R' for x in a))
 def test_overheated_no_structure_cannot_make_plan(self):
  with self.assertRaises(ValueError):quote_set(11000,1500,10700,10000,10900)
  with self.assertRaises(ValueError):quote_set(11000,300,10000,11500,10900)
 def test_tick_compliant_quote_and_live_false(self):
  x=quote_set(55000,700,54000,50500,54400)[0]
  self.assertEqual(x['proposed_limit_krw']%100,0)
  self.assertFalse(x['asof_regular_session_certified'])
  self.assertFalse(x['orders_enabled'])
  self.assertEqual(x['schema'],SCHEMA)
 def test_limit_gap_through_is_not_a_fill(self):
  p=quote_set(11000,360,10700,10300,10900)[0]
  e=p['proposed_limit_krw']
  self.assertEqual(next_session_touch(p,11000,360,e-10,e+100,e-200),
   'CANCEL_GAP_THROUGH_RESTING_LIMIT')
 def test_limit_far_gap_up_is_cancelled(self):
  p=quote_set(11000,360,10700,10300,10900)[0]
  self.assertEqual(next_session_touch(p,11000,360,12000,12100,10800),
   'CANCEL_OPEN_TOO_HIGH_NO_CHASE')
 def test_limit_intraday_touch_is_only_price_contact(self):
  p=quote_set(11000,360,10700,10300,10900)[0]
  self.assertEqual(next_session_touch(p,11000,360,11000,11100,10750),
   'STUDY_PRICE_CONTACT_NOT_BROKER_FILL')
 def test_stop_same_day_not_promoted_to_profitable_buy(self):
  p=quote_set(11000,360,10700,10300,10900)[0]
  self.assertEqual(next_session_touch(p,11000,360,11000,11200,10200),
   'STUDY_TOUCH_WITH_AMBIGUOUS_SAME_DAY_STOP_FIRST')
 def test_confirm_after_day1_close_only_then_day2_open_bracket(self):
  self.assertTrue(completed_retest_signal(10800,11010,10800,10980,10900,360,10300))
  self.assertEqual(confirmed_d2_open(10980,360,11000,10300),11000)
  self.assertIsNone(confirmed_d2_open(10980,360,12000,10300))
 def test_bearish_day1_retest_is_not_confirmation(self):
  self.assertFalse(completed_retest_signal(11100,11200,10800,10900,10900,360,10300))
 def test_cash_unverified_makes_no_share_quantity(self):
  self.assertIsNone(risk_capacity(269230,11000,10300,verified_cash=False))
  self.assertEqual(risk_capacity(269230,11000,10300,verified_cash=True),3)
 def test_gap_stop_invalidates_open(self):
  p=quote_set(11000,360,10700,10300,10900)[0]
  self.assertEqual(next_session_touch(p,11000,360,10200,10800,9900),
   'CANCEL_OPEN_BELOW_STRUCTURE_STOP')

if __name__=="__main__":unittest.main()
