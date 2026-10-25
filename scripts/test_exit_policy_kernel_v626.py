import unittest
from exit_policy_kernel_v626 import exit_sim,published_before_next_open,MODES

def b(op=100,high=104,low=99,close=101,d="2026-10-26"):
 return {"Date":d,"Open":op,"High":high,"Low":low,"Close":close}

class ExitPolicyV626(unittest.TestCase):
 def test_7_frozen_exits(self):self.assertEqual(len(MODES),7)
 def test_stop_first_even_high_reached(self):
  x=exit_sim([b(high=121,low=90)]*5,100,95,"STOP_TARGET10PCT")
  self.assertEqual(x["reason"],"STOP_FIRST")
 def test_open_gap_below_stop(self):
  x=exit_sim([b(op=91,high=102,low=90,close=96)]*5,100,95,"STOP_TRAIL7")
  self.assertEqual(x["net_pct"],-9.65)
 def test_target_contact_never_actual_fill(self):
  x=exit_sim([b(high=111)]*5,100,95,"STOP_TARGET10PCT")
  self.assertEqual(x["reason"],"PROXY_TARGET_TOUCH")
  self.assertFalse(x["broker_fill_verified"])
 def test_partial_then_stop(self):
  x=exit_sim([b(high=111,low=99)]+[b(op=105,high=108,low=95,close=104)]*4,
     100,95,"STOP_PARTIAL10_TRAIL7")
  self.assertTrue(x["partial_happened"])
  self.assertEqual(x["reason"],"STOP_FIRST")
 def test_target_after_stop_forbidden_on_same_bar(self):
  x=exit_sim([b(high=115,low=93)]*5,100,95,"STOP_PARTIAL10_TRAIL7")
  self.assertFalse(x["partial_happened"])
 def test_earliest_public_event_preopen(self):
  pub="2026-08-19T16:11:48+09:00"
  self.assertTrue(published_before_next_open(pub,"2026-08-20",
       "2026-08-28",["2026-08-20","2026-08-28"]))
  self.assertFalse(published_before_next_open(pub,"2026-08-19",
       "2026-08-28",["2026-08-19","2026-08-28"]))
 def test_all_real_trade_gates_off(self):
  x=exit_sim([b()]*5,100,95,"STOP_TARGET2R")
  self.assertFalse(x["orders_enabled"]);self.assertFalse(x["trade_approved"])
 def test_must_have_five_complete_bars(self):
  with self.assertRaises(ValueError):exit_sim([b()]*4,100,95,"STOP_TRAIL7")
 def test_exit_must_be_preregistered(self):
  with self.assertRaises(ValueError):exit_sim([b()]*5,100,95,"SECRET_OPTIMIZED_EXIT")

if __name__=="__main__":unittest.main()
