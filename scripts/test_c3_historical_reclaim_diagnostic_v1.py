"""Test historical lookahead guard, adverse stop ordering and bias flags."""
import os,tempfile,unittest
import numpy as np
from c3_historical_reclaim_diagnostic_v1 import (pivot_floor,
    first_overhead_high,model_return,run)

SRC=os.getenv('C3_REPLAY_ARTIFACT_PATH')
class TestHistorical(unittest.TestCase):
    def test_floor_requires_two_completed_following_bars(self):
        low=np.array([105,104,103,100,95,100,102,104,103,101],float)
        days=np.array([f'2026-01-{i+1:02d}' for i in range(len(low))])
        self.assertIsNone(pivot_floor(low,days,4))
        self.assertIsNone(pivot_floor(low,days,5))
        self.assertEqual(pivot_floor(low,days,6),(95.,'2026-01-07'))

    def test_old_high_broken_by_new_high_is_not_ceiling(self):
        high=np.array([102,105,106,110,120,111,112,115,125,120,118,117],float)
        self.assertIsNone(first_overhead_high(high,110.,8))
        self.assertEqual(first_overhead_high(high,110.,10),125.)

    def test_same_bar_target_and_stop_resolves_to_stop(self):
        r=model_return(np.array([100.]),np.array([130.]),np.array([85.]),
            np.array([124.]),0,100.,90.,120.,1)
        self.assertEqual(r['exit_reason'],'STOP_FIRST_IF_BOTH')
        self.assertTrue(r['stop_hit'])
        self.assertLess(r['net_pct'],0)

    def test_gap_through_stop_exits_at_worse_open(self):
        r=model_return(np.array([83.]),np.array([104.]),np.array([80.]),
            np.array([100.]),0,100.,90.,120.,1)
        self.assertEqual(r['exit_reason'],'GAP_STOP_AT_OPEN')
        self.assertAlmostEqual(r['net_pct'],-17.65,places=3)

    @unittest.skipUnless(SRC,'Frozen original Oct30 artifact not supplied')
    def test_real_historic_study_is_diagnostic_not_approval(self):
        with tempfile.TemporaryDirectory() as dest:
            out=run(SRC,dest)
        self.assertEqual(out['source_run_id'],'41051723762')
        self.assertIn('LOOKAHEAD_UNIVERSE_BIAS',out['major_bias'])
        self.assertFalse(out['strategy_profitability_proven'])
        self.assertFalse(out['trade_approved'])
        self.assertFalse(out['orders_enabled'])
        self.assertEqual(out['diagnostics']['loose_paper_d2_eligible'],156)
        self.assertEqual(out['diagnostics']['moderate_paper_d2_eligible'],20)
        self.assertEqual(out['diagnostics']['strict_paper_d2_eligible'],9)
        by={x['policy']:x for x in out['results']
            if x['partition']=='ALL' and x['hold']==5}
        self.assertLess(by['CONTACT_ONLY']['mean_net_return_pct'],0)
        self.assertLess(by['MODERATE_RECOVERY']['mean_net_return_pct'],0)
        self.assertLess(by['STRICT_RECOVERY']['simulated_cases'],10)

if __name__=='__main__':unittest.main()
