"""Paired daily-close stop diagnostic tests, no broker fills."""
import os,tempfile,unittest
import numpy as np
from c3_close_stop_comparison_v1 import closing_stop_return,run

SRC=os.getenv('C3_REPLAY_ARTIFACT_PATH')
OUT=os.getenv('C3_REPLAY_OUTPUT_DIR')

class TestCloseBasedStop(unittest.TestCase):
    def test_close_below_stop_exits_next_open_not_intraday_low(self):
        r=closing_stop_return(
          np.array([100.,82.]),np.array([110.,90.]),
          np.array([80.,78.]),np.array([89.,83.]),
          0,100.,90.,120.,2)
        self.assertEqual(r['close_stop_exit_reason'],'CLOSE_STOP_NEXT_OPEN_GAP')
        self.assertAlmostEqual(r['close_stop_net_pct'],-18.65,places=3)

    def test_intraday_stop_touch_is_ignored_if_close_holds(self):
        r=closing_stop_return(np.array([100.]),np.array([105.]),
          np.array([88.]),np.array([101.]),0,100.,90.,120.,1)
        self.assertEqual(r['close_stop_exit_reason'],'TIME_EXIT')
        self.assertAlmostEqual(r['close_stop_net_pct'],.35,places=3)

    def test_target_and_closing_stop_same_bar_uses_adverse_exit(self):
        r=closing_stop_return(np.array([100.,85.]),
          np.array([130.,100.]),np.array([85.,80.]),
          np.array([88.,93.]),0,100.,90.,120.,2)
        self.assertEqual(r['close_stop_exit_reason'],'CLOSE_STOP_NEXT_OPEN_GAP')
        self.assertLess(r['close_stop_net_pct'],0)

    def test_halted_zero_ohlcv_refused(self):
        with self.assertRaisesRegex(ValueError,'UNTRADEABLE_ZERO_OHLC'):
            closing_stop_return(np.array([100.,0.]),np.array([101.,0.]),
              np.array([95.,0.]),np.array([98.,100.]),0,100.,90.,120.,2)

    @unittest.skipUnless(SRC and OUT,'Requires original immutable scan plus preceding diagnostic')
    def test_corrected_historical_stops_are_paired(self):
        with tempfile.TemporaryDirectory() as directory:
            r=run(SRC,OUT+'/c3_historical_reclaim_diagnostic_v1.csv',
                  OUT+'/c3_historical_reclaim_diagnostic_v1_status.json',
                  directory)
        self.assertTrue(r['hindsight_selected_universe_bias'])
        self.assertFalse(r['trade_approved'])
        self.assertFalse(r['orders_enabled'])
        self.assertEqual(r['actual_fills'],0)
        cases={x['policy']:x for x in r['results']
               if x['partition']=='ALL' and x['hold']==5}
        self.assertEqual(cases['CONTACT_ONLY']['paired_cases'],154)
        self.assertAlmostEqual(cases['CONTACT_ONLY']['close_stop_mean_pct'],-.165,places=3)
        self.assertEqual(cases['STRICT_RECOVERY']['paired_cases'],9)
        self.assertLess(cases['STRICT_RECOVERY']['close_stop_mean_pct'],0)

if __name__=='__main__':unittest.main()
