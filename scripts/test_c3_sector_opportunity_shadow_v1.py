"""Deterministic smoke tests for research-only sector/opportunity logic."""
import unittest
from c3_sector_opportunity_shadow_v1 import entry_modes,sector_snapshot,run
class SectorOpportunityTests(unittest.TestCase):
 def test_sector_snapshot_not_called_flow(self):
  s=sector_snapshot([dict(ticker='111111',open=100,close=105,turnover_krw=1000)],[dict(ticker='111111',sector='TEST')])
  self.assertEqual(s['TEST']['status'],'ONE_DAY_CROSS_SECTION_ONLY_NOT_FUND_FLOW')
  self.assertEqual(s['TEST']['investor_net_flow'],'UNAVAILABLE')
 def test_short_history_never_fabricates_entry(self):
  self.assertEqual(entry_modes([dict(date='2026-11-16',open=100,high=102,low=99,close=101,volume=10)],101,2),[])
 def test_empty_diagnostics_cannot_approve(self):
  x=run(dict(asof='2026-11-16',rows=[]),dict(asof='2026-11-16',rows=[]))
  self.assertEqual(x['verified_top2'],[])
  self.assertEqual(x['stage_gate'],'HOLD')
  self.assertFalse(x['buy_approved'])
  self.assertEqual(x['telegram_requests'],0)
 def test_future_date_mismatch_fails(self):
  with self.assertRaises(AssertionError):
   run(dict(asof='2026-11-16',rows=[]),dict(asof='2026-11-17',rows=[]))
if __name__=='__main__':unittest.main()
