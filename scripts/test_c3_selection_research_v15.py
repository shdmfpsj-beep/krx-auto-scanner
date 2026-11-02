import unittest
from c3_selection_research_v15 import build

class SelectionTests(unittest.TestCase):
    def test_excludes_named_biotech_and_no_buy(self):
        rows=[
          {"ticker":"111111","name":"가상바이오","c3_preliminary_score":"90","extension_vs_ma20_pct":"1","rvol20":"2","latest_date":"2026-11-02","setup":"BREAKOUT"},
          {"ticker":"222222","name":"가상산업","c3_preliminary_score":"70","extension_vs_ma20_pct":"2","rvol20":"1","latest_date":"2026-11-02","setup":"REVERSAL_PROXY"}]
        result=build(rows)
        self.assertEqual(result["name_excluded"],1)
        self.assertEqual(result["provisional_watch_top2"][0]["ticker"],"222222")
        self.assertEqual(result["buy_approvals"],0)
        self.assertIsNone(result["provisional_watch_top2"][0]["entry_range"])
    def test_missing_metrics_does_not_create_buy(self):
        result=build([{"ticker":"333333","name":"가상산업","c3_preliminary_score":"n/a"}])
        self.assertEqual(result["research_pool_count"],0)
        self.assertEqual(result["decision"],"CASH")

if __name__=="__main__":unittest.main()
