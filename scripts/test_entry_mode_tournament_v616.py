#!/usr/bin/env python3
"""Risk audit for as-of, stop-first and nonexecuting v6.16 policy comparisons."""
import unittest
from entry_mode_tournament_v616 import (
    MODES,SCHEMA,FIELDS,strategy_levels,simulate,summarize,
)

def signal(kind="FRESH_20D_BREAKOUT"):
    return dict(asof="2026-10-01",ticker="000001",name="TEST",
       method=kind,classification="C_SIGNAL_NOT_READY_RISK_OR_HEADROOM",
       asof_close="110",first_limit_study="108",
       structure_stop_study="101.0",atr14="3.0",sma20="106",
       prior20_high="108.7",relative_volume20="1.5",
       nearby_confirmed_overhead="120",discovery_index_only="82.3")

def future():
    return [dict(Date=d,Open=str(o),High=str(h),Low=str(l),Close=str(c))
       for d,o,h,l,c in [
         ("2026-10-02",110,112,107,109),
         ("2026-10-06",110,112,108,109),
         ("2026-10-07",109,112,108,111),
         ("2026-10-08",112,114,110,113),
         ("2026-10-12",113,115,111,114)]]

class ModeAuditTests(unittest.TestCase):
    def test_multiple_entry_mode_levels_precomputed_without_future(self):
        modes={r["mode"]:r for r in strategy_levels(signal())}
        self.assertTrue({"ORIGINAL_LIMIT","NEAR_CLOSE_LIMIT",
             "BREAKOUT_RETEST_LIMIT","NEXT_OPEN_GAP_CONDITION"}.issubset(modes))
        self.assertTrue(all(x["live_trade_approved"] is False and
              x["orders_enabled"] is False for x in modes.values()))
        self.assertEqual(set(modes).difference(MODES),set())
    def test_ma20_support_is_only_for_pullback_family(self):
        self.assertIn("MA20_SUPPORT_LIMIT",
          [r["mode"] for r in strategy_levels(signal("FIRST_MA20_RESUME"))])
        self.assertNotIn("BREAKOUT_RETEST_LIMIT",
          [r["mode"] for r in strategy_levels(signal("FIRST_MA20_RESUME"))])
    def test_no_confirmed_pivot_or_excess_risk_never_generates_plan(self):
        z=signal();z["structure_stop_study"]=""
        self.assertEqual(strategy_levels(z),[])
        z=signal();z["structure_stop_study"]="55"
        self.assertEqual(strategy_levels(z),[])
    def test_valid_five_day_limit_price_touch_not_broker_execution(self):
        p=next(r for r in strategy_levels(signal()) if r["mode"]=="ORIGINAL_LIMIT")
        q=simulate(p,future())
        self.assertIs(q["future5_complete"],True)
        self.assertTrue(q["next_day_limit_touch_not_broker_fill"])
        self.assertIs(q["actual_broker_execution_verified"],False)
        self.assertIs(q["orders_enabled"],False)
    def test_first_bar_stop_priority_always_over_same_bar_target(self):
        p=next(r for r in strategy_levels(signal()) if r["mode"]=="ORIGINAL_LIMIT")
        f=future();f[0]["Low"]="99";f[0]["High"]="145"
        q=simulate(p,f)
        self.assertEqual(q["shadow_outcome"],"STOP_FIRST_AMBIGUOUS_PRICE_PATH")
        self.assertLess(q["shadow_net_pct"],0)
    def test_partial_future_does_not_count_pnl(self):
        p=next(r for r in strategy_levels(signal()) if r["mode"]=="ORIGINAL_LIMIT")
        q=simulate(p,future()[:4])
        self.assertFalse(q["future5_complete"])
        self.assertEqual(q["shadow_net_pct"],"")
    def test_open_gap_requires_precommitted_ceiling_and_retests_no_open_trick(self):
        p=next(r for r in strategy_levels(signal()) if r["mode"]=="NEXT_OPEN_GAP_CONDITION")
        too_high=future();too_high[0]["Open"]="120"
        q=simulate(p,too_high)
        self.assertEqual(q["shadow_outcome"],"MISSED_FIRST_SESSION_ENTRY")
        self.assertFalse(q["next_day_limit_touch_not_broker_fill"])
        ok=future()
        q=simulate(p,ok)
        self.assertTrue(q["next_day_limit_touch_not_broker_fill"])
        self.assertEqual(q["shadow_entry_reference"],110.0)
    def test_nonoverlap_mode_one_slot_and_no_buy_promotion(self):
        a=next(r for r in strategy_levels(signal()) if r["mode"]=="ORIGINAL_LIMIT")
        a=simulate(a,future())
        b=dict(a,asof="2026-10-02",ticker="000002")
        r,slots=summarize([a,b],["2026-10-01","2026-10-02","2026-10-06"])
        self.assertEqual(len(slots["ORIGINAL_LIMIT"]),1)
        self.assertEqual(next(x for x in r if x["mode"]=="ORIGINAL_LIMIT")["approved_live_buys"],0)
        self.assertEqual(SCHEMA,"C3_V616_PREDECLARED_ENTRY_TOURNAMENT_READ_ONLY")
        self.assertIn("shadow_net_pct",FIELDS)

if __name__=="__main__":unittest.main()
