import unittest
from c3_krx_fresh_v1 import scan

def sample(n=90):
    out=[]
    for i in range(n):
        close=100+i*.35
        out.append(dict(ticker="005930",name="TEST",asof=f"2026-{(i//28)+1:02d}-{(i%28)+1:02d}",open=close-1,high=close+2,low=close-2,close=close,volume=100000))
    return out

class KRXFreshTests(unittest.TestCase):
    def test_history_requirement(self):
        self.assertIsNone(scan(sample(79)))
    def test_sane_history(self):
        x=scan(sample())
        self.assertEqual(x["ticker"],"005930")
        self.assertGreater(x["stop"],0)
        self.assertGreaterEqual(x["rr"],2)
    def test_duplicate_day_rejected(self):
        rows=sample();rows[-1]["asof"]=rows[-2]["asof"]
        self.assertIsNone(scan(rows))
    def test_zero_close_rejected(self):
        rows=sample();rows[-1]["close"]=0
        self.assertIsNone(scan(rows))

if __name__=="__main__":unittest.main()
