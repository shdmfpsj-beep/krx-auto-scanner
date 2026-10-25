import unittest
from profit_selection_bias_audit_v634 import audit,six_try_illustration,RANKS,EXIT

def samples():
    ranked=[dict(model="NEAR60_RISK8",exit_mode=EXIT,
       rank=r,pct=4.329 if r=="BALANCED_LEADER" else -1.0) for r in RANKS]
    randoms=[dict(model="NEAR60_RISK8",exit_mode=EXIT,
       seed=str(i),pct=5.0 if i<35 else 1.0) for i in range(200)]
    return ranked,randoms

class ResearchBiasV634(unittest.TestCase):
    def test_near60_35_of_200(self):
        a,b=samples();x=audit(a,b)
        self.assertEqual(x["retrospective_uniform_random_ge_best"],35)
        self.assertAlmostEqual(x["single_try_empirical_tail"],.175)
        self.assertAlmostEqual(x["six_independent_draws_illustration"],.6847002028808595)
    def test_no_order_authority_even_if_past_winner(self):
        a,b=samples();x=audit(a,b)
        self.assertFalse(x["trade_approved"]);self.assertFalse(x["orders_enabled"])
        self.assertTrue(x["true_corrected_pvalue_not_calculated"])
    def test_one_draw_identity(self):
        self.assertAlmostEqual(six_try_illustration(.175,1),.175)
    def test_invalid_probability_rejected(self):
        with self.assertRaises(ValueError):six_try_illustration(1.1,6)
    def test_no_rank_removed_after_result(self):
        a,b=samples()
        with self.assertRaises(ValueError):audit(a[:-1],b)
    def test_duplicate_seed_rejected(self):
        a,b=samples();b[-1]["seed"]="0"
        with self.assertRaises(ValueError):audit(a,b)
    def test_short_placebo_rejected(self):
        a,b=samples()
        with self.assertRaises(ValueError):audit(a,b[:-1])

if __name__=="__main__":unittest.main()
