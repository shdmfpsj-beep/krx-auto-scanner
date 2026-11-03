import unittest
from datetime import date,timedelta
from c3_confirmed_trend_break_v30 import confirmed_exit

def bars(closes):
    return [{"date":(date(2026,1,1)+timedelta(days=i)).isoformat(),
             "open":str(c),"high":str(c+1),"low":str(c-1),"close":str(c),
             "volume":"100"} for i,c in enumerate(closes)]

class V30Tests(unittest.TestCase):
    def test_structural_stop_close_then_next_open(self):
        data=bars([100]*70+[95,89,88,87])
        r=confirmed_exit(data,70,95,90)
        self.assertEqual(r["exit_reason"],"STRUCTURAL_CLOSE_BREAK_NEXT_OPEN")
        self.assertEqual(r["exit_date"],data[72]["date"])
    def test_horizon_and_censor(self):
        a=confirmed_exit(bars([100]*100),70,100,90,20)
        self.assertEqual(a["holding_sessions"],20)
        self.assertFalse(a["censored"])
        b=confirmed_exit(bars([100]*75),70,100,90,60)
        self.assertTrue(b["censored"])
    def test_next_open_is_not_signal_input(self):
        data=bars([100]*70+[95,89,88,87])
        a=confirmed_exit(data,70,95,90)
        data[72]["open"]="20"
        b=confirmed_exit(data,70,95,90)
        self.assertEqual(a["exit_date"],b["exit_date"])
        self.assertNotEqual(a["exit_price"],b["exit_price"])

if __name__=="__main__":unittest.main()
