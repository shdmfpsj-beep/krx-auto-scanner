import unittest
from c3_price_basis_v2 import classify_prices,prefix_comparison

B=dict(date='2026-03-31',open=100,high=110,low=90,close=105,volume=100)
class PriceBasisTests(unittest.TestCase):
    def test_close_only_disagreement_cannot_be_called_a_split(self):
        self.assertEqual(classify_prices(dict(B,close=104),B),'CLOSE_ONLY_PROVIDER_OR_SESSION_DIFFERENCE_UNRESOLVED')
    def test_scale_change_is_only_a_candidate_without_corporate_action_evidence(self):
        adjusted={k:(v/2 if k in ('open','high','low','close') else v) for k,v in B.items()}
        self.assertEqual(classify_prices(adjusted,B),'UNIFORM_OHLC_SCALE_CANDIDATE_NOT_CONFIRMED_ACTION')
    def test_same_retrieval_prefix_match_does_not_certify_historical_vintage(self):
        r=prefix_comparison([B],[B,dict(B,date='2026-04-01')],'2026-03-31')
        self.assertEqual(r['changed_prefix_days'],[])
        self.assertFalse(r['point_in_time_historical_vintage_certified'])
    def test_missing_prefix_is_not_an_equal_history(self):
        self.assertEqual(prefix_comparison([B],[],'2026-03-31')['missing_prefix_dates'],['2026-03-31'])
    def test_revised_past_price_is_exposed(self):
        r=prefix_comparison([B],[dict(B,close=104)],'2026-03-31')
        self.assertEqual(r['changed_prefix_days'],[dict(date='2026-03-31',fields=['close'])])
if __name__=='__main__':unittest.main()
