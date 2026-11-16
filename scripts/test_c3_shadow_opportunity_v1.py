import unittest
from c3_shadow_opportunity_v1 import classify
class ShadowTests(unittest.TestCase):
    def setUp(self):
        self.row=dict(ticker='123456',name='fixture',close=105.,financial=dict(required_metrics_complete=True,observed_positive=True),momentum_pass=True,liquidity_pass=True,entry_window=dict(status='WAIT_PULLBACK',asof='2026-11-16'),observation_audit=dict(price=dict(atr14=10.,ma={'5':104.,'10':101.,'20':98.,'60':90.})))
    def test_near_is_watch_not_buy(self):
        x=classify(self.row);self.assertEqual(x['status'],'WATCH_NEW_SUPPORT_CONFIRMATION');self.assertFalse(x['buy_approved']);self.assertIsNone(x['stop'])
    def test_financial_failure(self):
        self.row['financial']['observed_positive']=False;self.assertEqual(classify(self.row)['status'],'NO_SHADOW_SETUP')
    def test_extension_rejected(self):
        self.row['close']=130.;self.assertEqual(classify(self.row)['reason'],'MA20_EXTENSION_TOO_LARGE')
    def test_trend_rejected(self):
        self.row['observation_audit']['price']['ma']['60']=100.;self.assertEqual(classify(self.row)['reason'],'TREND_NOT_CONFIRMED')
    def test_existing_active_untouched(self):
        self.row['entry_window']['status']='NEAR_ENTRY';self.assertEqual(classify(self.row)['status'],'NO_SHADOW_SETUP')
if __name__=='__main__':unittest.main()
