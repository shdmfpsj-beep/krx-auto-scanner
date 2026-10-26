import unittest
from extension_guard import CompletedD5,research_extension_decision

def q(**kw):
    p=dict(ticker="005930",signal_day="2026-10-12",decision_day="2026-10-19",
           five_day_status="TIME_CLOSE_PROXY",observed_net_return_5d_pct=3.4,
           completed_D5_close=100,completed_D5_MA20=95)
    p.update(kw)
    return CompletedD5(**p)

class TestD5ReadOnly(unittest.TestCase):
    def test_positive_survivor(self):
        self.assertTrue(research_extension_decision(q())["hypothesis_profit_extension12"])
    def test_negative_survivor_not_extended(self):
        self.assertFalse(research_extension_decision(q(observed_net_return_5d_pct=-1))["hypothesis_profit_extension12"])
    def test_stopped_before_D5_cannot_extend(self):
        self.assertFalse(research_extension_decision(q(five_day_status="STOP_PRICE_PROXY"))["hypothesis_profit_extension12"])
    def test_target_before_D5_cannot_extend(self):
        self.assertFalse(research_extension_decision(q(five_day_status="TARGET_TOUCH_PROXY"))["hypothesis_profit_extension12"])
    def test_ma20_additional_gate(self):
        a=research_extension_decision(q(completed_D5_close=90))
        self.assertTrue(a["hypothesis_profit_extension12"])
        self.assertFalse(a["hypothesis_profit_and_MA20_extension12"])
    def test_date_no_future(self):
        with self.assertRaises(ValueError):research_extension_decision(q(decision_day="2026-10-11"))
    def test_d5_date_validation(self):
        with self.assertRaises(ValueError):research_extension_decision(q(decision_day="2026-02-31"))
    def test_no_fabricated_broker_fill(self):
        self.assertFalse(research_extension_decision(q())["actual_broker_fill_verified"])
    def test_research_not_autoorders(self):
        r=research_extension_decision(q())
        self.assertFalse(r["trade_approved"]);self.assertFalse(r["orders_enabled"])
    def test_no_account_risk_in_inputs(self):
        with self.assertRaises(TypeError):q(capital_won=1000000)
    def test_future_profit_cannot_influence_decision(self):
        with self.assertRaises(TypeError):q(return_12d_pct=999)
    def test_invalid_status(self):
        with self.assertRaises(ValueError):research_extension_decision(q(five_day_status="FILLED_AFTER_WATCH"))
    def test_missing_price(self):
        with self.assertRaises(ValueError):research_extension_decision(q(completed_D5_MA20=float("nan")))
if __name__=="__main__":unittest.main()
