import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from unittest.mock import patch
from kiwoom_execution_audit import outcome,evaluate

def bars(next_open=100,second_open=100,second_low=98,second_high=102):
    data=[{"date":f"day{i}","open":100.0,"high":103.0,"low":97.0,"close":100.0}
          for i in range(75)]
    data[66].update(open=next_open,high=max(next_open,106),low=min(next_open,101))
    data[67].update(open=second_open,low=second_low,high=second_high)
    return data

class ExecutionTests(unittest.TestCase):
    def test_next_open_not_signal_close(self):
        data=bars(next_open=105)
        with patch("kiwoom_execution_audit.setup",return_value="BREAKOUT_20D"),patch(
            "kiwoom_execution_audit.pivot_stop",return_value=100):
            r=outcome(data,65)
        self.assertEqual(r["entry"],105)
    def test_stop_gap_uses_worse_open(self):
        data=bars(next_open=105,second_open=90,second_low=89,second_high=100)
        with patch("kiwoom_execution_audit.setup",return_value="BREAKOUT_20D"),patch(
            "kiwoom_execution_audit.pivot_stop",return_value=100):
            r=outcome(data,65)
        self.assertEqual(r["status"],"STOP_GAP_OPEN")
        self.assertLess(r["net_pct"],-10)
    def test_both_intraday_ambiguous(self):
        data=bars(next_open=105,second_open=105,second_low=99,second_high=116)
        with patch("kiwoom_execution_audit.setup",return_value="BREAKOUT_20D"),patch(
            "kiwoom_execution_audit.pivot_stop",return_value=100):
            r=outcome(data,65)
        self.assertEqual(r["status"],"AMBIGUOUS_SAME_BAR")
        self.assertIsNone(r["net_pct"])
    def test_no_entry_below_stop(self):
        data=bars(next_open=99)
        with patch("kiwoom_execution_audit.setup",return_value="BREAKOUT_20D"),patch(
            "kiwoom_execution_audit.pivot_stop",return_value=100):
            r=outcome(data,65)
        self.assertEqual(r["status"],"ENTRY_OPEN_BELOW_STOP")
    def test_empty_data(self):
        self.assertEqual(evaluate([],"2026-10-21"),[])
if __name__=="__main__":unittest.main()
