"""D+1 audit chronology and frozen observed result tests."""
import os,unittest,tempfile
import pandas as pd
from c3_registered_next_session_shadow_v1 import run,confirmed_floor

class TestDplusOne(unittest.TestCase):
    def test_floor_needs_two_following_sessions(self):
        df=pd.DataFrame(dict(date=[f'2026-10-{d:02d}' for d in range(1,12)],
                             low=[100,100,100,100,99,95,97,99,100,100,100]))
        self.assertIsNone(confirmed_floor(df.iloc[:7].copy()))
        self.assertEqual(confirmed_floor(df.iloc[:8].copy())[0],95.0)

    @unittest.skipUnless(os.getenv('C3_REPLAY_ARTIFACT_PATH'),'Frozen artifact not supplied')
    def test_registered_cohort_observed_after_freeze(self):
        with tempfile.TemporaryDirectory() as t:
            r=run(os.environ['C3_REPLAY_ARTIFACT_PATH'],t)
        self.assertEqual((r['baseline'],r['next_observed_session']),('2026-10-29','2026-10-30'))
        self.assertEqual((r['tested'],r['zone_contacts_including_stop_ambiguity'],
                          r['stop_ambiguous'],r['completed_recovery_signals']),(36,23,4,0))
        self.assertEqual(r['broker_fills'],0)
        self.assertFalse(r['trade_approved'])
        self.assertTrue(r['next_session_prices_never_used_to_set_entry'])

if __name__=='__main__':unittest.main()
