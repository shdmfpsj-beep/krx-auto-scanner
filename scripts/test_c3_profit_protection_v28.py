import unittest
from datetime import date,timedelta
from c3_profit_protection_v28 import exit_model

class ProfitProtectionTests(unittest.TestCase):
    def make_rows(self, closes):
        rows=[]
        for i,c in enumerate(closes):
            rows.append({"date":(date(2026,1,1)+timedelta(days=i)).isoformat(),
                         "open":str(c),"high":str(c+1),"low":str(c-1),"close":str(c)})
        return rows

    def test_profit_lock_activates_only_after_close_gain(self):
        rows=self.make_rows([100]*70+[108,110,107,104,103,102,101,100])
        result=exit_model(rows,70,100,90,"profit_lock",60)
        self.assertTrue(result["profit_lock_activated"])
        self.assertEqual(result["exit_reason"],"CLOSE_STOP_NEXT_OPEN")
        self.assertEqual(result["exit_date"],rows[75]["date"])

    def test_censored_when_insufficient_future_bars(self):
        rows=self.make_rows([100]*75)
        result=exit_model(rows,70,100,90,"atr_trend",60)
        self.assertTrue(result["censored"])

    def test_horizon_exit_when_data_sufficient(self):
        rows=self.make_rows([100]*95)
        result=exit_model(rows,70,100,90,"atr_trend",20)
        self.assertFalse(result["censored"])
        self.assertEqual(result["holding_sessions"],20)

if __name__=="__main__":
    unittest.main()
