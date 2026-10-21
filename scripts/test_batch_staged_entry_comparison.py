import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from batch_staged_entry_comparison import second_support,compare,summary

class PairedTests(unittest.TestCase):
    def test_support_uses_only_signal_and_prior(self):
        bars=[{"low":100.} for _ in range(20)]
        bars[12]["low"]=102.
        bars[19]["low"]=104.
        bars[20-1]["low"]=103.
        self.assertEqual(second_support(bars,19,99,110),100.)
    def test_support_ignores_future_low(self):
        bars=[{"low":105.} for _ in range(21)]
        bars[20]["low"]=101.
        self.assertEqual(second_support(bars,19,99,110),105.)
    def test_support_rejects_below_stop(self):
        bars=[{"low":90.} for _ in range(20)]
        self.assertIsNone(second_support(bars,19,95,110))
    def test_no_signal_no_paired_rows(self):
        prices={"005930":[{"date":f"{i:03}","open":100.,"high":101.,
            "low":99.,"close":100.} for i in range(80)]}
        self.assertEqual(compare(prices,"999"),[])
    def test_empty_summary_is_not_success(self):
        x=summary([])
        self.assertEqual(x["paired_observations"],0)
        self.assertIsNone(x["strategies"]["B_60_40"]["mean_net_account_pct"])
        self.assertEqual(x["trade_approval"],"NO")
if __name__=="__main__":unittest.main()
