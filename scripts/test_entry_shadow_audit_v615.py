#!/usr/bin/env python3
"""Five-session outcome audit fails safely on OHLC fill ambiguity."""
import unittest
from entry_shadow_audit_v615 import scenario,SCHEMA

def e():
    return dict(asof="2026-10-02",ticker="000001",name="테스트",
       method="FRESH_20D_BREAKOUT",classification="A_CONDITIONAL_GEOMETRY_1P5R_RESEARCH",
       first_limit_study="100",structure_stop_study="95",
       nearby_confirmed_overhead="110",
       scenario_target_2R_not_verified="120")

def bars():
    return [dict(Date="2026-10-"+day,Open=str(op),Low=str(lo),
       High=str(hi),Close=str(cl))
       for day,op,lo,hi,cl in [
        ("06",101,99,106,103),("07",104,103,109,107),
        ("08",105,104,108,107),("12",105,103,107,106),
        ("13",105,102,106,105)]]

class ShadowTests(unittest.TestCase):
    def test_five_day_incomplete_never_makes_pnl(self):
        r=scenario(e(),bars()[:4])
        self.assertEqual(r["shadow_outcome"],"FIVE_SESSIONS_NOT_OBSERVED")
        self.assertEqual(r["shadow_net_pct_0p5_cost"],"")
        self.assertIs(r["trade_approved"],False)
    def test_first_day_no_touch_never_assumes_bought(self):
        f=bars();f[0]["Low"]="100.1"
        r=scenario(e(),f)
        self.assertEqual(r["shadow_outcome"],"NO_FIRST_SESSION_LIMIT_TOUCH")
        self.assertEqual(r["shadow_net_pct_0p5_cost"],"")
        self.assertIs(r["broker_fill_proven"],False)
    def test_same_day_loss_conservative(self):
        f=bars();f[0]["Low"]="94";f[0]["High"]="112"
        r=scenario(e(),f)
        self.assertEqual(r["shadow_outcome"],"STOP_FIRST_CONSERVATIVE_OHLC")
        self.assertLess(r["shadow_net_pct_0p5_cost"],0)
        self.assertIs(r["same_day_path_uncertain"],True)
    def test_below_stop_open_not_marked_as_verified_buy(self):
        f=bars();f[0]["Open"]="93";f[0]["Low"]="92"
        r=scenario(e(),f)
        self.assertEqual(r["shadow_outcome"],"GAP_BELOW_STOP_TOUCH_NO_EXECUTION_PROOF")
        self.assertEqual(r["shadow_net_pct_0p5_cost"],"")
    def test_fifth_day_mark_to_market_is_not_proven_profitability(self):
        r=scenario(e(),bars())
        self.assertEqual(r["shadow_outcome"],"HELD_FIVE_DAY_MARK_TO_MARKET")
        self.assertAlmostEqual(r["shadow_net_pct_0p5_cost"],4.5,places=3)
        self.assertIs(r["profitability_proven"],False)
        self.assertIs(r["orders_enabled"],False)
    def test_later_target_is_still_proxy_not_real_execution(self):
        f=bars();f[1]["High"]="111"
        r=scenario(e(),f)
        self.assertEqual(r["shadow_outcome"],"TARGET_AFTER_FIRST_DAY_PROXY")
        self.assertAlmostEqual(r["shadow_net_pct_0p5_cost"],9.5)
        self.assertIs(r["broker_fill_proven"],False)
        self.assertEqual(SCHEMA,"C3_V615_FIVE_SESSION_SHADOW_AUDIT")

if __name__=="__main__":unittest.main()
