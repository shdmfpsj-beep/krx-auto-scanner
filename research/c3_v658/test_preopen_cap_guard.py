import unittest
from preopen_cap_guard import FrozenD,preopen_research_caps,floor_cash_tick

class TestPreOpenCaps(unittest.TestCase):
    def d(self,**kw):
        x=dict(ticker="005930",signal_date="2026-10-23",
               close=50000.,atr14=2000.,original_daily_structure_stop=46000.,
               first_recorded_overhead=56000.,overhead_proven_date="2026-10-23")
        x.update(kw)
        return FrozenD(**x)
    def test_pre_D_close(self):
        self.assertEqual(preopen_research_caps(self.d())["cap_limit_research_only"]["D_CLOSE"],50000)
    def test_cap10(self):
        self.assertEqual(preopen_research_caps(self.d())["cap_limit_research_only"]["CAP10"],50200)
    def test_cap25(self):
        self.assertEqual(preopen_research_caps(self.d())["cap_limit_research_only"]["CAP25"],50500)
    def test_cap50(self):
        self.assertEqual(preopen_research_caps(self.d())["cap_limit_research_only"]["CAP50"],51000)
    def test_first_overhead_caps_blocked(self):
        self.assertIsNone(preopen_research_caps(self.d(first_recorded_overhead=50500))["cap_limit_research_only"]["CAP25"])
    def test_future_hurdle_not_allowed(self):
        with self.assertRaises(ValueError):
            preopen_research_caps(self.d(overhead_proven_date="2026-10-26"))
    def test_unknown_hurdle_stays_unknown(self):
        x=preopen_research_caps(self.d(first_recorded_overhead=None,overhead_proven_date=None))
        self.assertFalse(x["overhead_known"])
        self.assertIsNone(x["second_target"])
        self.assertFalse(x["live_buy_approved"])
    def test_invalid_stop(self):
        with self.assertRaises(ValueError):
            preopen_research_caps(self.d(original_daily_structure_stop=52000))
    def test_invalid_ticker(self):
        with self.assertRaises(ValueError):
            preopen_research_caps(self.d(ticker="00593"))
    def test_2023_grid_boundary(self):
        self.assertEqual(floor_cash_tick(49999),49950)
    def test_no_account_cash_budget(self):
        with self.assertRaises(TypeError):
            FrozenD("005930","2026-10-23",50000,2000,46000,56000,"2026-10-23",account_cash=1000000)
    def test_orders_off(self):
        x=preopen_research_caps(self.d())
        self.assertFalse(x["orders_enabled"])
        self.assertFalse(x["market_KRX_only_verified"])
        self.assertEqual(x["broker_fills"],0)

if __name__=="__main__":unittest.main()
