import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
from staged_entry_comparison import compare,summarize
from staged_entry_research import SPLITS

def row(t,d,open_=105,low=103,high=108,close=106):
    return {"ticker":t,"Date":f"2026-01-{d:02d}" if d<=31 else f"2026-02-{d-31:02d}",
            "Open":str(open_),"High":str(high),"Low":str(low),
            "Close":str(close),"Volume":"100"}

class ComparisonTests(unittest.TestCase):
    def test_empty_summary_is_not_fake_success(self):
        s=summarize([],"2026-10-21")
        self.assertEqual(s["signals"],0)
        self.assertIsNone(s["strategies"]["B_60_40"]["mean_net_account_pct"])
        self.assertEqual(s["trade_approval"],"NO")
    def test_no_future_bars_used(self):
        rows=[row("005930",i) for i in range(1,20)]
        self.assertEqual(compare(rows,"2026-01-10"),[])
    def test_all_four_share_same_signal(self):
        # 75 valid sequential dates over March/April, no market-data dependency.
        from datetime import date,timedelta
        rows=[]
        for i in range(75):
            d=(date(2026,1,1)+timedelta(days=i)).isoformat()
            rows.append({"ticker":"005930","Date":d,"Open":"105",
                         "High":"108","Low":"103","Close":"106","Volume":"100"})
        with patch("staged_entry_comparison.setup",return_value="BREAKOUT_20D"),patch(
            "staged_entry_comparison.pivot_stop",return_value=100.),patch(
            "staged_entry_research.setup",return_value="BREAKOUT_20D"),patch(
            "staged_entry_research.pivot_stop",return_value=100.):
            results=compare(rows,"2026-03-16")
        self.assertEqual(len(results),4)
        self.assertEqual(set(r["strategy"] for r in results),set(SPLITS))
        self.assertEqual(len(set(r["signal_date"] for r in results)),1)
if __name__=="__main__":unittest.main()
