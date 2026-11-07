"""Pure synthetic V6 counterexample tests; no external credentials or orders."""
import copy
import unittest
from c3_v6_fill_attribution import CAUSES, explain, summarize

PLAN = dict(ticker="000001",decision_date="2026-11-05",low=90,
            high=110,stop=85,resistance=140)
FROZEN = dict(status="PREOPEN_LIMIT_FROZEN",submitted=True,limit=100.)
NO_ORDER = dict(status="NO_ORDER_PRIOR_TREND_NOT_CONFIRMED",submitted=False)
def bar(o=120,l=101,h=122,c=119,volume=1000):
    return dict(date="2026-11-06",open=o,high=h,low=l,close=c,
                volume=volume,tradable=True)
def fill(when,price):
    return dict(filled=True,individual_fills=[dict(when=when,price=price)])
def nofill():return dict(filled=False,status="DAY_EXPIRED_NO_FILL")
def diag(plan=PLAN,frozen=FROZEN,model=None,b=None):
    return explain(plan,frozen,nofill() if model is None else model,
                   bar() if b is None else b,
                   expected_ticker="000001",expected_decision_date="2026-11-05")

class CausalFillAttribution(unittest.TestCase):
    def test_fixed_causes(self):
        self.assertEqual(len(CAUSES),8)

    def test_untouched_range_is_not_execution(self):
        x=diag()
        self.assertEqual(x["cause"],"NO_FILL_NEVER_REACHED_LIMIT")
        self.assertEqual(x["min_intraday_price_overshoot_pct"],1.0)

    def test_touch_without_trade_through_is_queue_unknown(self):
        x=diag(b=bar(o=120,l=100,c=115))
        self.assertEqual(x["cause"],"NO_FILL_TOUCH_QUEUE_UNPROVEN")
        self.assertFalse(x["queue_fill_verified"])

    def test_trade_through_fill_is_only_model_proxy(self):
        x=diag(model=fill("INTRADAY_LIMIT_ASSUMED",100),
               b=bar(o=120,l=99,c=117))
        self.assertEqual(x["cause"],"INTRADAY_TRADE_THROUGH_MODEL_ONLY")
        self.assertFalse(x["intraday_sequence_verified"])

    def test_auction_limit_fills_at_open_not_limit(self):
        x=diag(model=fill("AT_OPEN",97),b=bar(o=97,l=90,h=105,c=102))
        self.assertEqual(x["cause"],"AUCTION_FILLED")
        self.assertEqual(x["open_price"],97)

    def test_precommitted_auction_below_stop_cannot_be_canceled(self):
        x=diag(model=fill("AT_OPEN",80),b=bar(o=80,l=77,h=108,c=99))
        self.assertEqual(x["cause"],"AUCTION_GAP_AT_OR_BELOW_STOP")

    def test_no_plan_does_not_turn_into_winner_fill(self):
        x=diag(plan=None,frozen=dict(status="NO_ORIGINAL_SUPPORT_PLAN",submitted=False))
        self.assertEqual(x["cause"],"NO_ORIGINAL_SUPPORT_PLAN")

    def test_prior_veto_remains_prior_veto_even_if_open_rebounds(self):
        x=diag(frozen=NO_ORDER,b=bar(o=100,l=90,h=120,c=115))
        self.assertEqual(x["cause"],"PREOPEN_POLICY_REJECTED")
        self.assertEqual(x["rejection"],NO_ORDER["status"])

    def test_invalid_bar_denominator_not_silently_zero(self):
        x=diag(model=nofill(),b=bar(volume=0))
        self.assertEqual(x["cause"],"BAR_UNOBSERVABLE")

    def test_inconsistent_auction_fill_rejected(self):
        with self.assertRaisesRegex(ValueError,"PARITY"):
            diag(model=fill("INTRADAY_LIMIT_ASSUMED",100),
                 b=bar(o=97,l=95,h=108,c=102))

    def test_cannot_skip_a_trade_through_fill_when_model_claims_no_fill(self):
        with self.assertRaisesRegex(ValueError,"MISSED_VERIFIABLE"):
            diag(b=bar(o=120,l=99,c=116))

    def test_cannot_borrow_wrong_signal_identity(self):
        with self.assertRaisesRegex(ValueError,"IDENTITY_MISMATCH"):
            diag(plan=dict(PLAN,ticker="999999"))

    def test_source_objects_unmutated(self):
        p=copy.deepcopy(PLAN);f=copy.deepcopy(FROZEN);b=bar()
        before=copy.deepcopy(b)
        diag(b=b)
        self.assertEqual(PLAN,p);self.assertEqual(FROZEN,f)
        self.assertEqual(b,before)

    def test_accounting_attribution_not_strategy_performance(self):
        rows=[
            dict(next_open_reference_net_pct=7.,causes={
                "V2_HIGH":dict(cause="NO_FILL_NEVER_REACHED_LIMIT",filled=False,
                    min_intraday_price_overshoot_pct=3.),
                "V5":dict(cause="PREOPEN_POLICY_REJECTED",filled=False)}),
            dict(next_open_reference_net_pct=-3.,causes={
                "V2_HIGH":dict(cause="AUCTION_FILLED",filled=True),
                "V5":dict(cause="PREOPEN_POLICY_REJECTED",filled=False)}),
        ]
        r=summarize(rows)
        self.assertEqual(r["n"],2)
        self.assertEqual(r["policy_causes"]["V2_HIGH"]["missed_positive_reference_total"],1)
        self.assertEqual(r["policy_causes"]["V5"]["missed_positive_reference_total"],1)
        self.assertEqual(r["policy_causes"]["V5"]["avoided_negative_reference_total"],1)
        self.assertTrue(r["no_profit_claim"])
        self.assertEqual(r["transition_vs_control"]["V5"]["AUCTION_FILLED => PREOPEN_POLICY_REJECTED"],1)

if __name__=="__main__":
    unittest.main(verbosity=2)
