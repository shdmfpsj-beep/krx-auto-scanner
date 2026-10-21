import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from kiwoom_ten_day_pipeline import merge,rank

def bar(t,day,c):
    return {"ticker":t,"Date":day,"Open":str(c),"High":str(c+1),
            "Low":str(c-1),"Close":str(c),"Volume":"100"}

class TenSessionPipelineTests(unittest.TestCase):
    def setUp(self):
        self.dates=[f"2026-10-{d:02d}" for d in range(1,12)]
        self.a=[bar("005930",d,100+i) for i,d in enumerate(self.dates)]
        self.b=[bar("000660",d,100+2*i) for i,d in enumerate(self.dates)]
    def test_dedup_and_future_rejection(self):
        future=bar("005930","2026-10-12",999)
        updated=bar("005930",self.dates[-1],115)
        rows=merge(self.a,self.b+[updated,future],"2026-10-11")
        self.assertEqual(len(rows),22)
        self.assertEqual(next(r for r in rows if r["ticker"]=="005930" and r["Date"]==self.dates[-1])["Close"],"115")
    def test_rank_and_incomplete_exclusion(self):
        ranked,info=rank(self.a+self.b[:-1],"2026-10-11")
        self.assertEqual([r["ticker"] for r in ranked],["005930"])
        self.assertEqual(info["excluded_incomplete"],1)
        self.assertFalse(info["universe_verified_full_krx"])
        self.assertEqual(ranked[0]["trade_approval"],"NO")
    def test_no_future_data(self):
        ranked,info=rank(self.a+self.b,"2026-10-10")
        self.assertEqual(info["reason"],"INSUFFICIENT_SESSIONS")
        self.assertEqual(ranked,[])
    def test_insufficient_sessions(self):
        ranked,info=rank(self.a[:4],"2026-10-11")
        self.assertEqual(info["reason"],"INSUFFICIENT_SESSIONS")
        self.assertFalse(ranked)
    def test_bad_ohlc_excluded(self):
        bad=bar("111111","2026-10-11",100)
        bad["Low"]="110"
        ranked,info=rank(self.a+[bad],"2026-10-11")
        self.assertEqual(info["input_tickers"],1)

if __name__=="__main__":unittest.main()
