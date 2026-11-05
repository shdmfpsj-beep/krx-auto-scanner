import unittest
from c3_practical_report_v3 import current_decision


class CurrentDecisionTests(unittest.TestCase):
    def inputs(self):
        return (dict(asof="2026-11-03",full_market_universe=2768,official_common_120day_50e8_liquid=295,
                     official_common_120day_liquid_5d_positive_FI=134,regular_1530_session_certified=False,
                     confirmed_research_trigger_rows=0),dict(asof="2026-11-03"))

    def test_new_run_does_not_turn_stale_data_into_current_quotes(self):
        b,i=self.inputs();r=current_decision(b,i,"2026-11-04")
        self.assertEqual(r["decision"],"CASH");self.assertIn("SELECTION_DATA_NOT_AT_REQUESTED_COMPLETED_DATE",r["blockers"])
        self.assertIsNone(r["top2"][0]["first_buy"]);self.assertIsNone(r["top2"][1]["structural_stop"])

    def test_same_day_without_validated_edge_is_still_cash(self):
        b,i=self.inputs();r=current_decision(b,i,"2026-11-03")
        self.assertIn("NO_VALIDATED_PROFITABLE_TOP2_MODEL",r["blockers"])
        self.assertIsNone(r["score_out_of_100"]);self.assertFalse(r["orders_enabled"])

    def test_source_dates_cannot_be_mixed(self):
        b,i=self.inputs();i["asof"]="2026-11-02"
        with self.assertRaisesRegex(ValueError,"ASOF_JOIN_MISMATCH"):current_decision(b,i,"2026-11-04")

    def test_unknown_fundamentals_are_not_healthy(self):
        b,i=self.inputs();r=current_decision(b,i,"2026-11-03")
        self.assertIn("EARNINGS_AND_CATALYST_UNVERIFIED",r["blockers"])
        self.assertFalse(r["historical_investor_flow_effect_verified"])


if __name__=="__main__":unittest.main()
