import unittest

from c3_loss_diagnostics_v2 import preconditions,decompose_stop


class LossDiagnosticsTests(unittest.TestCase):
    def test_components_reconcile_with_gap_and_cost(self):
        record=dict(entry=dict(price=100),structure_stop=90,
            exits={"20":{"CLOSE_HOLD":dict(exit_price=85,exit_date="2026-05-06",
                exit_reason="CLOSE_STOP_NEXT_OPEN",hypothetical_net_pct=-15.6)}})
        result=decompose_stop(record,[dict(date="2026-05-05",close=88)])
        self.assertAlmostEqual(result["structural_distance"],-10)
        self.assertAlmostEqual(result["close_breach_overshoot"],-2)
        self.assertAlmostEqual(result["next_open_gap"],-3)
        self.assertAlmostEqual(result["costs"],-.6)
        self.assertAlmostEqual(sum(result[k] for k in ("structural_distance","close_breach_overshoot","next_open_gap","costs")),-15.6)

    def test_time_exit_does_not_invent_stop_components(self):
        record=dict(entry=dict(price=100),structure_stop=90,
            exits={"20":{"CLOSE_HOLD":dict(exit_price=110,exit_date="2026-05-06",
                exit_reason="HORIZON_CLOSE",hypothetical_net_pct=9.3)}})
        result=decompose_stop(record,[])
        self.assertIsNone(result["structural_distance"])
        self.assertAlmostEqual(result["costs"],-.7)

    def test_ex_ante_features_ignore_future_bars(self):
        rows=[dict(date=f"2026-03-{i:02}",open=100,high=102,low=98,close=100,volume=1000) for i in range(1,29)]
        plan=dict(decision_date="2026-03-28",watch_high=100,structure_stop=90,resistance1=110,atr14=4,
            geometry=dict(support=98,ma20=99),context=dict(market_regime="UP"))
        original=preconditions(plan,rows)
        future=dict(date="2026-04-01",open=1,high=1000000,low=1,close=1000000,volume=100000000)
        self.assertEqual(original,preconditions(plan,rows+[future]))
        self.assertIsNone(original["flags"]["SECTOR_RELATIVE_STRENGTH_WEAK"])

    def test_missing_decision_cannot_use_next_bar(self):
        with self.assertRaisesRegex(ValueError,"DECISION_BAR_MISSING"):
            preconditions(dict(decision_date="2026-03-28"),[dict(date="2026-03-29")])


if __name__=="__main__":unittest.main()
