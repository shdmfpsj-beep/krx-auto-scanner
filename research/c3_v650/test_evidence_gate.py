import unittest
from evidence_gate import price_conflicts,old_plan_status

def bars():
    return [
      {"ticker":"006110","session":"2026-10-20","provider":"Investing",
       "close":83800,"url":"https://kr.investing.com"},
      {"ticker":"006110","session":"2026-10-20","provider":"StockPulse",
       "close":82400,"url":"https://sangsoo.synology.me"},
      {"ticker":"006110","session":"2026-10-23","provider":"Investing",
       "close":67500,"url":"https://kr.investing.com"},
      {"ticker":"006110","session":"2026-10-23","provider":"StockPulse",
       "close":67400,"url":"https://sangsoo.synology.me"}]

def audit(items=None,quote=59800,when="2026-10-26T14:06:36+09:00"):
    return old_plan_status("006110","2026-10-19",72000,
                           bars() if items is None else items,when,quote)

class C3V650ResearchTests(unittest.TestCase):
    def test_two_sessions_disagree(self):
        self.assertEqual(len([x for x in price_conflicts(bars())
                              if x["precise_levels_quarantined"]]),2)
    def test_small_100won_difference_still_flags(self):
        self.assertEqual(price_conflicts(bars())[-1]["spread_krw"],100)
    def test_material_larger_spread(self):
        self.assertTrue(price_conflicts(bars())[0]["material_gt_half_percent"])
    def test_old_hypothesis_broken(self):
        self.assertEqual(audit()["archived_plan_status"],"ARCHIVED_PLAN_BROKEN")
    def test_no_trade_even_when_broken(self):
        self.assertFalse(audit()["orders_enabled"])
        self.assertFalse(audit()["trade_approved"])
    def test_never_reuse_historical_entry(self):
        self.assertIsNone(audit()["current_entry"])
        self.assertIsNone(audit()["current_targets"])
    def test_one_provider_not_certifying_old_breach(self):
        b=[x for x in bars() if x["provider"]=="Investing"]
        self.assertEqual(audit(b)["archived_plan_status"],"INTRADAY_UNCONFIRMED_BREAK")
    def test_intraday_is_not_official(self):
        self.assertFalse(audit()["price_origin_certified"])
    def test_no_fake_volume_profile(self):
        self.assertFalse(audit()["verified_poc"])
    def test_wrong_ticker_reject(self):
        b=bars()
        b[0]=dict(b[0],ticker="005930")
        with self.assertRaises(ValueError):audit(b)
    def test_future_bar_reject(self):
        b=bars()
        b[0]=dict(b[0],session="2026-10-27")
        with self.assertRaises(ValueError):audit(b)
    def test_naive_clock_reject(self):
        with self.assertRaises(ValueError):audit(when="2026-10-26T14:06:36")
    def test_no_budget_fields(self):
        self.assertNotIn("account_risk_budget",audit())
    def test_stale_but_above_stop(self):
        self.assertEqual(audit([],quote=83000)["archived_plan_status"],
                         "FRESH_ANALYSIS_REQUIRED")

if __name__=="__main__":unittest.main()
