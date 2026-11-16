import unittest
from c3_early_stage_v1 import classify
class EarlyStageTest(unittest.TestCase):
 def setUp(self):
  self.r=dict(ticker='211270',name='fixture',close=100,liquidity_pass=True,history_rows=119,own_rs20=10,rs_accel5=2,
   observation_audit=dict(price=dict(asof='2026-11-16',atr14=5,ma={'20':96,'60':90},returns_pct={'20':15,'5':5},ma20_extension_atr=.8)),
   financial=dict(statement=dict(published_on='2026-08-14',equity_krw=100,assets_krw=200,liabilities_krw=100,operating_profit_krw=-5,previous_comparable_operating_profit_krw=-20)))
 def test_early(self):self.assertEqual(classify(self.r)['stage'],'EARLY_TREND_CANDIDATE')
 def test_early_burst_wait(self):
  self.r['observation_audit']['price']['returns_pct']['20']=40
  self.assertEqual(classify(self.r)['stage'],'EARLY_BURST_WAIT')
 def test_no_chase(self):
  self.r['observation_audit']['price']['ma20_extension_atr']=3
  self.assertEqual(classify(self.r)['stage'],'EXTENDED_OR_LATE')
 def test_financial_missing_hold(self):
  self.r['financial']['statement'].pop('equity_krw')
  self.assertEqual(classify(self.r)['stage'],'FINANCIAL_HOLD')
 def test_future_report_hold(self):
  self.r['financial']['statement']['published_on']='2026-11-17'
  self.assertEqual(classify(self.r)['stage'],'FUTURE_DISCLOSURE_HOLD')
 def test_no_buy_approval(self):self.assertFalse(classify(self.r)['buy_approved'])
if __name__=='__main__':unittest.main()
