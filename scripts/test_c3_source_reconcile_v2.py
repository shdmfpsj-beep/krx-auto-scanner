import unittest
from c3_source_reconcile_v2 import compare


class ReconciliationTests(unittest.TestCase):
    def test_different_close_is_exposed_not_called_split(self):
        a=dict(open=100,high=110,low=90,close=100,volume=1000)
        b=dict(a,close=101)
        result=compare({("A","2026-05-01"):a},{("A","2026-05-01"):b})
        self.assertEqual(result["compared"],1)
        self.assertIn("CLOSE_ONLY_PROVIDER_OR_SESSION_DIFFERENCE_UNRESOLVED",result["categories"])
        self.assertEqual(result["differences"][0]["changed_fields"],["close"])

    def test_missing_source_dates_remain_counted(self):
        row=dict(open=100,high=110,low=90,close=100,volume=1000)
        result=compare({("A","2026-05-01"):row},{("A","2026-05-02"):row})
        self.assertEqual(result["compared"],0);self.assertEqual(result["left_only"],1)
        self.assertEqual(result["right_only"],1)


if __name__=="__main__":unittest.main()
