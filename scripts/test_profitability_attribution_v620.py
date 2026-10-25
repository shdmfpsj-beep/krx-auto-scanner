#!/usr/bin/env python3
"""v6.20 test offline profitability diagnostics without lookahead or BUY."""
import unittest
from profitability_attribution_v620 import (
 SCHEMA,COHORTS,MODES,qualifies,day_cluster_ci,strict_reference,summarize,COST_PCT
)

def study(mode="ORIGINAL_LIMIT",touch=True):
 return dict(asof="2026-10-01",ticker="000001",name="TEST",pattern="FIRST_MA20_RESUME",
  mode=mode,risk_mode="GREEN_RESEARCH_ONLY",relative_volume20="1.4",
  structure_risk_pct="4.4",overhead_net_R="2.2",
  entry_limit_reference="108",stop_reference="103",asof_close="110",
  condition_ceiling_reference="111",next_day_limit_touch_not_broker_fill=
  "True" if touch else "False",shadow_net_pct="2.0",
  shadow_exit_date="2026-10-08",shadow_outcome="FIVE_DAY_CLOSE_PROXY")
def nextbars(op="110",low="107",high="115"):
 return [dict(Date=d,Open=o,Low=l,High=h,Close=c) for d,o,l,h,c in [
  ("2026-10-02",op,low,high,"111"),
  ("2026-10-05","110","105","114","112"),
  ("2026-10-06","111","109","114","112"),
  ("2026-10-07","112","109","115","113"),
  ("2026-10-08","113","110","116","115")]]
def market():
 return {"2026-10-02":dict(Date="2026-10-02",Open="100",Close="100"),
 "2026-10-08":dict(Date="2026-10-08",Open="99",Close="98")}

class ProfitAudit(unittest.TestCase):
 def test_predeclared_no_weights_fitted(self):
  self.assertEqual(len(COHORTS),11)
  self.assertEqual(len(MODES),5)
  self.assertEqual(SCHEMA,"C3_V620_PROFITABILITY_ATTRIBUTION_NO_BUY")
 def test_stop_five_session_and_cost_adjust(self):
  r=strict_reference(study(),nextbars(),market(),signal_atr=3)
  self.assertTrue(r["strict_price_contact_only"])
  self.assertEqual(r["strict_shadow_net_pct_0p65_cost"],1.85)
  self.assertEqual(r["strict_contact_status"],"STUDY_PRICE_CONTACT_NOT_BROKER_FILL")
  self.assertGreater(r["market_relative_proxy_net_pp"],1)
 def test_gap_down_below_limit_is_not_a_fill(self):
  r=strict_reference(study(),nextbars(op="106",low="103",high="110"),market(),3)
  self.assertFalse(r["strict_price_contact_only"])
  self.assertEqual(r["strict_contact_status"],"CANCEL_GAP_THROUGH_RESTING_LIMIT")
  self.assertEqual(r["strict_shadow_net_pct_0p65_cost"],"")
 def test_large_up_gap_cancel_no_chase(self):
  r=strict_reference(study(),nextbars(op="115",low="106",high="116"),market(),3)
  self.assertEqual(r["strict_contact_status"],"CANCEL_OPEN_TOO_HIGH_NO_CHASE")
 def test_stop_in_intraday_candle_is_ambiguous_not_winning_certainty(self):
  r=strict_reference(study(),nextbars(op="110",low="101",high="115"),market(),3)
  self.assertEqual(r["strict_contact_status"],"STUDY_TOUCH_WITH_AMBIGUOUS_SAME_DAY_STOP_FIRST")
 def test_parent_touch_mismatch_never_imputed(self):
  r=strict_reference(study(touch=False),nextbars(),market(),3)
  self.assertEqual(r["strict_contact_status"],"PARENT_STUDY_TOUCH_CONFLICT")
  self.assertFalse(r["strict_price_contact_only"])
 def test_incomplete_forward_period_is_censored_not_zero(self):
  r=strict_reference(study(),nextbars()[:4],market(),3)
  self.assertFalse(r["five_future_sessions_complete"])
  self.assertEqual(r["strict_shadow_net_pct_0p65_cost"],"")
 def test_signal_classification_is_from_asof_not_outcome(self):
  s=study();s["strict_shadow_net_pct_0p65_cost"]=-7
  self.assertTrue(qualifies(s,"GREEN_AND_MA20_RESUME"))
  self.assertTrue(qualifies(s,"REL_VOLUME_GE1P2"))
  self.assertTrue(qualifies(s,"OVERHEAD_NET_R_GE2"))
  self.assertTrue(qualifies(s,"STRUCTURE_RISK_LE6"))
  s["risk_mode"]="RED_MARKET_RISK_OFF"
  self.assertFalse(qualifies(s,"GREEN_AND_MA20_RESUME"))
 def test_no_confidence_interval_from_few_dates(self):
  z=[dict(asof="2026-10-01",strict_shadow_net_pct_0p65_cost=10.0) for i in range(18)]
  self.assertEqual(day_cluster_ci(z),(None,None))
 def test_shadow_research_may_be_positive_but_never_buy(self):
  case=dict(study(),strict_price_contact_only=True,
    five_future_sessions_complete=True,parent_touch_only=True,
    strict_shadow_net_pct_0p65_cost=1.5,market_relative_proxy_net_pp=2.3)
  rows=summarize([case])
  selected=[r for r in rows if r["cohort"]=="ALL" and r["entry_mode"]=="ORIGINAL_LIMIT"][0]
  self.assertEqual(selected["pnl_mean_net_pct"],1.5)
  self.assertEqual(selected["live_approved_buys"],0)
 def test_original_atr_required_not_synthetic(self):
  with self.assertRaises(ValueError):
   strict_reference(study(),nextbars(),market(),None)
 def test_macrobear_proxy_not_transform_absolute_loss_into_gain(self):
  case=dict(study(),strict_price_contact_only=True,
    five_future_sessions_complete=True,parent_touch_only=True,
    strict_shadow_net_pct_0p65_cost=-1.5,market_relative_proxy_net_pp=9)
  row=next(x for x in summarize([case]) if x["cohort"]=="ALL" and x["entry_mode"]=="ORIGINAL_LIMIT")
  self.assertEqual(row["pnl_mean_net_pct"],-1.5)
  self.assertEqual(row["net_market_relative_mean_pp"],9)

if __name__=="__main__":unittest.main()
