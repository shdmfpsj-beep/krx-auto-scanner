import unittest
from c3_final_top2_research_v1 import evaluate_one,evaluate
class FinalTop2(unittest.TestCase):
 def setUp(self):
  self.b=[dict(date='2026-%02d-%02d'%(1+i//20,1+i%20),high=100,low=95,close=98) for i in range(201)]
  self.r=dict(ticker='X',name='TEST',close=98,liquidity_pass=True,own_rs20=3,rs_accel5=2,
    observation_audit=dict(price=dict(asof=self.b[-1]['date'],atr14=3,ma={'20':96,'60':95})),
    financial=dict(statement=dict(published_on='2026-01-01',equity_krw=100,assets_krw=200,liabilities_krw=100)))
 def test_missing_history_holds(self):self.assertEqual(evaluate_one(self.r)['stage'],'DATA_HOLD')
 def test_long_run_rejected(self):
  for b in self.b[:100]:b.update(close=35,high=36,low=34)
  self.assertEqual(evaluate_one(self.r,self.b)['stage'],'MATURE_RUN')
 def test_future_financial_holds(self):
  self.r['financial']['statement']['published_on']='2027-01-01'
  self.assertEqual(evaluate_one(self.r,self.b)['stage'],'FINANCIAL_HOLD')
 def test_no_fabricated_resistance(self):
  z=evaluate_one(self.r,self.b);self.assertIsNone(z['entry_range'])
 def test_unapproved(self):
  z=evaluate(dict(asof='2026-11-16',rows=[self.r]),{'X':self.b});self.assertFalse(z['buy_approved']);self.assertEqual(z['telegram_requests'],0)
if __name__=='__main__':unittest.main()
