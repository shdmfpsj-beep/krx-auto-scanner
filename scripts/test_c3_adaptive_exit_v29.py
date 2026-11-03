import unittest
from datetime import date,timedelta
from c3_adaptive_exit_v29 import adaptive_exit

def rows(closes):
    return [{"date":(date(2026,1,1)+timedelta(days=i)).isoformat(),
             "open":str(c),"high":str(c+1),"low":str(c-1),"close":str(c)}
            for i,c in enumerate(closes)]

class AdaptiveExitTests(unittest.TestCase):
    def test_next_open_on_close_stop(self):
        bars=rows([100]*70+[108,110,105,99,98,97])
        out=adaptive_exit(bars,70,100,90)
        self.assertTrue(out["profit_lock_activated"])
        self.assertEqual(out["exit_reason"],"CLOSE_STOP_NEXT_OPEN")
        self.assertGreater(out["holding_sessions"],0)

    def test_horizon_and_censor(self):
        full=adaptive_exit(rows([100]*100),70,100,90,20)
        self.assertFalse(full["censored"])
        self.assertEqual(full["holding_sessions"],20)
        short=adaptive_exit(rows([100]*75),70,100,90,60)
        self.assertTrue(short["censored"])

    def test_no_lookahead_from_next_open(self):
        base=rows([100]*70+[108,110,105,99,98,97])
        first=adaptive_exit(base,70,100,90)
        # Change the open of the exit bar only; decision date must stay fixed.
        ix=next(i for i,r in enumerate(base) if r["date"]==first["exit_date"])
        base[ix]["open"]="50"
        second=adaptive_exit(base,70,100,90)
        self.assertEqual(first["exit_date"],second["exit_date"])
        self.assertNotEqual(first["exit_price"],second["exit_price"])

if __name__=="__main__":unittest.main()
