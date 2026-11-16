import unittest
from c3_chart_first_turnaround_v1 import classify
class ChartFirstTests(unittest.TestCase):
 def setUp(self):
  self.r=dict(ticker='123456',name='fixture',close=105,liquidity_pass=True,history_rows=119,own_rs20=10,rs_accel5=2,
   entry_window=dict(status='WAIT_PULLBACK',research_fit_eligible=False),
   observation_audit=dict(price=dict(atr14=10,ma={'5':104,'10':101,'20':98,'60':90},latest_rvol_vs_prior20=1.3)),
   financial=dict(statement=dict(published_on='2026-08-14',equity_krw=100,assets_krw=200,liabilities_krw=100,
    revenue_krw=110,previous_comparable_revenue_krw=100,operating_profit_krw=-5,previous_comparable_operating_profit_krw=-20)))
 def test_turnaround_loss_can_be_watch(self):
  x=classify(self.r,'2026-11-16');self.assertEqual(x['status'],'CHART_FIRST_WATCH');self.assertTrue(x['turnaround_loss_making']);self.assertFalse(x['buy_approved']);self.assertIsNone(x['stop'])
 def test_future_disclosure_rejected(self):
  self.r['financial']['statement']['published_on']='2026-11-17';self.assertEqual(classify(self.r,'2026-11-16')['reason'],'FUTURE_FINANCIAL_REPORT')
 def test_negative_equity_held(self):
  self.r['financial']['statement']['equity_krw']=-1;self.assertEqual(classify(self.r,'2026-11-16')['status'],'RESEARCH_HOLD')
 def test_excessive_debt_excluded(self):
  self.r['financial']['statement']['liabilities_krw']=400;self.assertEqual(classify(self.r,'2026-11-16')['reason'],'HIGH_LEVERAGE')
 def test_bad_chart_excluded(self):
  self.r['own_rs20']=-2;self.assertEqual(classify(self.r,'2026-11-16')['reason'],'CHART_TREND_FAIL')
if __name__=='__main__':unittest.main()
