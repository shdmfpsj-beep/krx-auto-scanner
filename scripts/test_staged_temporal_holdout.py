import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from staged_temporal_holdout import analyze

class HoldoutTests(unittest.TestCase):
    def test_temporal_split_no_future_training(self):
        rows=[{"signal_date":"2026-07-31","A_100_0_net_account_pct":"10",
               "B_60_40_net_account_pct":"8"},
              {"signal_date":"2026-08-01","A_100_0_net_account_pct":"-2",
               "B_60_40_net_account_pct":"-1"}]
        r=analyze(rows,min_holdout=2)
        self.assertEqual((r["train_n"],r["holdout_n"]),(1,1))
        self.assertEqual(r["holdout_deltas_vs_full_pctpt"]["B_60_40"],1)
        self.assertFalse(r["holdout_sample_sufficient"])
        self.assertEqual(r["trade_approval"],"NO")
    def test_empty_not_approved(self):
        r=analyze([])
        self.assertIsNone(r["holdout"]["A_100_0"]["mean_net_account_pct"])
        self.assertFalse(r["holdout_sample_sufficient"])
if __name__=="__main__":unittest.main()
