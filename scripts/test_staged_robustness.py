import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from staged_robustness import analyze

class RobustnessTests(unittest.TestCase):
    def test_paired_delta_and_fills(self):
        rows=[]
        for month,full,split,filled in [("01",1,2,True),("02",3,1,False)]:
            rows.append({"signal_date":"2026-"+month+"-12",
                "A_100_0_net_account_pct":str(full),
                "B_60_40_net_account_pct":str(split),
                "B_60_40_second_filled":str(filled)})
        r=analyze(rows)["strategies"]["B_60_40"]
        self.assertEqual(r["mean_delta_vs_full_pctpt"],-.5)
        self.assertEqual(r["filled_mean_delta_pctpt"],1)
        self.assertEqual(r["unfilled_mean_delta_pctpt"],-2)
        self.assertEqual(r["outperformed_full_count"],1)
    def test_empty_does_not_claim_performance(self):
        r=analyze([])
        self.assertIsNone(r["strategies"]["C_50_50"]["mean_delta_vs_full_pctpt"])
        self.assertEqual(r["trade_approval"],"NO")
if __name__=="__main__":unittest.main()
