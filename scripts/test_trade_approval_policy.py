"""Regression: 79 reject, 80/85 conditional review, missing gates reject."""
import unittest
from trade_approval_policy import (
    BUY_REVIEW_SCORE_MIN, MANDATORY_EVIDENCE, evaluate_review
)


class TradeApprovalPolicyTests(unittest.TestCase):
    def evidence(self):
        return {**{k: True for k in MANDATORY_EVIDENCE},
                "account": "K100", "c3_existing_position": False}

    def test_threshold_is_80_of_100(self):
        self.assertEqual(BUY_REVIEW_SCORE_MIN, 80)
        self.assertEqual(evaluate_review(79, self.evidence(), cost_adjusted_rr=2.5)["decision"], "CASH")
        for score in (80, 85, 100):
            x = evaluate_review(score, self.evidence(), cost_adjusted_rr=2.5)
            self.assertTrue(x["manual_review_eligible"])
            self.assertEqual(x["scoring_scale"], 100)
            self.assertFalse(x["trade_approved"])
            self.assertFalse(x["orders_enabled"])

    def test_unverified_score_must_not_approve(self):
        for value in (None, 79.99, "90", True, float("nan"), -1, 101):
            self.assertEqual(evaluate_review(value, self.evidence(), cost_adjusted_rr=2.5)["decision"], "CASH")

    def test_research_score_80_without_independent_evidence_not_approved(self):
        x = evaluate_review(80, {}, cost_adjusted_rr=3.0)
        self.assertEqual(x["decision"], "CASH")
        self.assertGreaterEqual(len(x["blockers"]), len(MANDATORY_EVIDENCE))

    def test_one_missing_gate_blocks_even_perfect_score(self):
        for key in MANDATORY_EVIDENCE:
            check = self.evidence()
            check[key] = False
            self.assertEqual(evaluate_review(100, check, cost_adjusted_rr=4)["decision"], "CASH", key)

    def test_missing_foreign_institution_data_is_optional(self):
        check = self.evidence()
        check["foreign_institution_flows_verified"] = False
        x = evaluate_review(80, check, cost_adjusted_rr=2.5)
        self.assertEqual(x["foreign_institution_flow_confirmation"], "OPTIONAL_NOT_VERIFIED")
        self.assertTrue(x["manual_review_eligible"])
        self.assertFalse(x["trade_approved"])
        self.assertNotIn("EVIDENCE_UNVERIFIED:foreign_institution_flows_verified", x["blockers"])
        check["sector_money_flow_verified"] = False
        self.assertEqual(evaluate_review(90, check, cost_adjusted_rr=2.5)["decision"], "CASH")

    def test_rr_and_c3_position_safety(self):
        for rr in (None, "3.0", 1.99, float("inf"), True):
            self.assertEqual(evaluate_review(85, self.evidence(), cost_adjusted_rr=rr)["decision"], "CASH")
        check = self.evidence()
        check.update({"account": "C3", "c3_existing_position": True})
        x = evaluate_review(100, check, cost_adjusted_rr=3)
        self.assertEqual(x["decision"], "CASH")
        self.assertIn("C3_ONE_POSITION_ALREADY_HELD", x["blockers"])


if __name__ == "__main__":
    unittest.main()
