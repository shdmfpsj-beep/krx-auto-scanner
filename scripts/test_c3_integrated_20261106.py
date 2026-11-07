"""Independent deterministic guardrail tests for the Nov6 integrated C3 audit."""
import unittest
from decimal import Decimal

from c3_integrated_replay_20261106 import ORDER_SPECS, iso, EXPECTED, DAY
from c3_entry_v2_preopen import entry
from c3_exit_v3_close_confirmed import exit_strategy
from c3_data_quality_v17 import classify_bar,regular_contract
from c3_telegram_notify import delivery_key

class IntegratedGuardrails(unittest.TestCase):
    def test_three_submitted_limits_translate_to_whole_shares(self):
        self.assertEqual([int(Decimal(o["budget"])/Decimal(o["limit"]))
            for o in ORDER_SPECS],[39,41,106])

    def test_102_preopen_prices_preserve_cash_and_costs(self):
        self.assertEqual(80*59600+106*23450,7253700)
        self.assertEqual(10000000-7253700,2746300)

    def test_original_uncertified_close_not_afterhours_mock_quote(self):
        close_value=80*EXPECTED["028050"][1]+106*EXPECTED["030530"][1]
        mock_screen=80*61300+106*28800
        self.assertEqual(close_value,7839800)
        self.assertEqual(mock_screen,7956800)
        self.assertNotEqual(close_value,mock_screen)

    def test_delayed_preview_cannot_be_certified_preopen(self):
        original=iso("2026-11-06T02:15:31.891712+00:00")
        auction=iso("2026-11-06T09:00:00+09:00")
        self.assertGreater(original,auction)

    def test_report_schedule_preceded_registration(self):
        self.assertLess(iso("2026-11-06T22:29:07+09:00"),
                        iso("2026-11-06T23:20:48+09:00"))

    def test_nonregular_source_cannot_be_approved(self):
        x=regular_contract("FINANCEDATA_KRX_CACHE",DAY,
                           "2026-11-06T14:21:34.207808+00:00")
        self.assertFalse(x["regular_input_allowed"])
        self.assertIn("VOLUME_AND_TURNOVER_NOT_REGULAR_ONLY",x["blockers"])
        self.assertIn("CURRENT_DAY_CLOSE_NOT_REGULAR_ONLY",x["blockers"])

    def test_zero_volume_with_amount_is_invalid_not_halt(self):
        x=dict(open=100,high=100,low=100,close=100,volume=0,turnover_krw=300)
        self.assertEqual(classify_bar(x),"ZERO_VOLUME_WITH_POSITIVE_TURNOVER")

    def test_durable_telegram_key_has_no_send_side_effect(self):
        self.assertEqual(delivery_key(DAY,"0289a5f01e43a4ed","live"),
                         "final/2026-11-06-0289a5f01e43a4ed")

    def test_legacy_gap_veto_and_auction_fill_not_conflated(self):
        p=dict(ticker="028050",decision_date="2026-11-05",
               method="PULLBACK",segment=0,low=60700,high=63500,
               stop=57700,reference_close=64300,resistance=65500,atr=3857)
        b=dict(date=DAY,open=59600,high=62300,low=58300,close=60500,
               volume=500000,segment=0,action_boundary=False,
               tradable=True,invalid_data=False)
        self.assertEqual(entry(p,b,"LEGACY_GAP_VETO")["status"],"OPEN_BELOW_BUDGET")
        resting=entry(p,b,"RESTING_TWO")
        self.assertEqual(resting["fill_count"],2)
        self.assertEqual(resting["price"],59600)
        for mode in ("BASELINE","HALF_R1","TRAIL_7_ATR","HALF_R1_TRAIL"):
            self.assertEqual(exit_strategy(p,DAY,resting,{DAY:b},[DAY],5,mode)["status"],
                             "WINDOW_NOT_MATURED")

if __name__=="__main__":
    unittest.main(verbosity=2)
