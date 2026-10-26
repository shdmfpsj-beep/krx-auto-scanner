import unittest
from chart_headroom_guard import KnownDChart,headroom,prospective_retest_timing

class ChartPriceOnly(unittest.TestCase):
    def test_D_known_low_headroom(self):
        x=headroom(KnownDChart("006110","2026-10-23",60000,54000,66000))
        self.assertLess(x["recorded_hurdle_R"],2)
        self.assertFalse(x["is_current_Buy"])
    def test_higher_resistance_may_clear_2R_without_buy(self):
        x=headroom(KnownDChart("006110","2026-10-23",60000,54000,100000))
        self.assertGreater(x["recorded_hurdle_R"],2)
        self.assertFalse(x["orders_enabled"])
    def test_missing_overhead_not_assigned_zero(self):
        x=headroom(KnownDChart("006110","2026-10-23",60000,54000,None))
        self.assertIsNone(x["recorded_hurdle_R"])
        self.assertEqual(x["status"],"OVERHEAD_MISSING_NOT_ZERO_UPSIDE")
    def test_ceiling_is_math_not_verified_support(self):
        x=headroom(KnownDChart("006110","2026-10-23",60000,54000,66000))
        self.assertFalse(x["ceiling_is_verified_support"])
    def test_first_resistance_not_proof_of_next(self):
        x=headroom(KnownDChart("006110","2026-10-23",60000,54000,66000))
        self.assertFalse(x["next_overhead_above_first_known"])
    def test_stock_stop_must_be_under_price(self):
        with self.assertRaises(ValueError):
            headroom(KnownDChart("006110","2026-10-23",60000,62000,66000))
    def test_first_resistance_above_price(self):
        with self.assertRaises(ValueError):
            headroom(KnownDChart("006110","2026-10-23",60000,54000,59000))
    def test_no_account_1pct_input(self):
        with self.assertRaises(TypeError):
            KnownDChart("006110","2026-10-23",60000,54000,66000,account_risk=0.01)
    def test_no_next_session_lookahead(self):
        with self.assertRaises(ValueError):
            prospective_retest_timing("2026-10-23","2026-10-24","2026-10-24","2026-10-27")
    def test_valid_later_session_is_still_not_actual_fill(self):
        x=prospective_retest_timing("2026-10-23","2026-10-26","2026-10-27","2026-10-28")
        self.assertFalse(x["broker_fill_verified"])
        self.assertFalse(x["trade_approved"])
    def test_no_retroactive_signal_day_event(self):
        with self.assertRaises(ValueError):
            prospective_retest_timing("2026-10-23","2026-10-23","2026-10-26","2026-10-27")
    def test_no_retest_open_before_close(self):
        with self.assertRaises(ValueError):
            prospective_retest_timing("2026-10-23","2026-10-26","2026-10-27","2026-10-27")

if __name__=="__main__":unittest.main()
