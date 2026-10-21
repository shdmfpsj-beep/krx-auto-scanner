import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from kiwoom_five_day_bridge import evaluate

class OfflineBridgeTests(unittest.TestCase):
    def test_short_series_has_no_false_signal(self):
        rows=[{"ticker":"005930","Date":f"2026-10-{i:02d}",
               "Open":"100","High":"101","Low":"99","Close":"100","Volume":"10"}
              for i in range(1,12)]
        self.assertEqual(evaluate(rows,"2026-10-11"),[])
    def test_future_bars_not_used(self):
        rows=[{"ticker":"005930","Date":f"2026-10-{i:02d}",
               "Open":"100","High":"101","Low":"99","Close":"100","Volume":"10"}
              for i in range(1,12)]
        self.assertEqual(evaluate(rows,"2026-10-01"),[])
if __name__=="__main__":unittest.main()
