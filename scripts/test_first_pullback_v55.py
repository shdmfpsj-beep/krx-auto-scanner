"""Offline, deterministic safety checks for free first-pullback research."""
import unittest,copy
from datetime import date,timedelta
from first_pullback_v55 import wma,hma60,confirmed_turn,phase,down,up,inspect,analyze

def fixture(n=120):
    first=date(2026,1,1)
    rows=[]
    for i in range(n):
        close=100+0.14*i
        rows.append(dict(ticker="005930",date=(first+timedelta(days=i)).isoformat(),
            open=str(close-.4),high=str(close+1),low=str(close-1),
            close=str(close),volume="1000",data_source="pykrx"))
    return rows

def candidate(rows):
    return dict(ticker="005930",name="TEST",latest_date=rows[-1]["date"],
        close=rows[-1]["close"],data_source="pykrx",
        turnover_source="ESTIMATED_CLOSE_X_VOLUME",
        instrument_type="UNKNOWN")

class FirstPullbackTests(unittest.TestCase):
    def test_hma_does_not_peek_into_future_closes(self):
        prices=[100+i*.2 for i in range(150)]
        before=hma60(prices)
        after=hma60(prices+[100000,3,4])
        self.assertEqual(before,after[:len(prices)])
        self.assertIsNotNone(before[-1])

    def test_wma_warmup_and_order(self):
        self.assertEqual(wma([1.0,2.0,3.0],3),[None,None,14/6])
        with self.assertRaises(ValueError):wma([1.0],0)

    def test_tick_crossing_band_is_recomputed(self):
        self.assertEqual(down(5004.9),5000)
        self.assertEqual(up(4998),5000)
        self.assertEqual(down(200099),200000)

    def test_empty_history_never_guesses_stop_or_price(self):
        rows=fixture()
        s=inspect(candidate(rows),[],date.fromisoformat(rows[-1]["date"]))
        self.assertEqual(s["setup"],"DATA_PENDING")
        self.assertIsNone(s["daily_stop"])
        self.assertEqual(s["buy_approval"],"NO")

    def test_future_bar_and_duplicate_rejected(self):
        rows=fixture()
        d=date.fromisoformat(rows[-1]["date"])
        s=inspect(candidate(rows),rows+[{
            **rows[-1],"date":str(d+timedelta(days=1))}],d)
        self.assertEqual(s["setup"],"DATA_PENDING")
        self.assertIn("HISTORY_DATE_MISMATCH",s["warnings"])
        s2=inspect(candidate(rows),rows+[rows[-1]],d)
        self.assertIn("HISTORY_NOT_CHRONOLOGICAL",s2["warnings"])

    def test_c3_score_cannot_approve_trade(self):
        rows=fixture()
        d=date.fromisoformat(rows[-1]["date"])
        c=candidate(rows)
        s=inspect(c,rows,d,rank={"c3_preliminary_score":"100"})
        self.assertEqual(s["buy_approval"],"NO")
        self.assertIn("FINAL_80_SCORE_UNVERIFIED",s["warnings"])
        self.assertIn("COMMON_SHARE_TYPE_UNVERIFIED",s["warnings"])

    def test_known_cross_source_conflict_is_not_suppressed(self):
        rows=fixture()
        d=date.fromisoformat(rows[-1]["date"])
        s=inspect(candidate(rows),rows,d,conflicted={"005930"})
        self.assertIn("KNOWN_CROSS_SOURCE_CLOSE_CONFLICT",s["warnings"])
        self.assertEqual(s["buy_approval"],"NO")

    def test_hma_confirmation_uses_only_completed_closes(self):
        h=[None]*100
        for i in range(70,100):h[i]=120-i*.25
        h[96]=96;h[97]=95;h[98]=94;h[99]=95
        self.assertIsNone(confirmed_turn(h)) # one up slope is insufficient
        h[99]=96;h[98]=95;h[97]=94
        self.assertIsNotNone(confirmed_turn(h))

    def test_no_fake_mandatory_five_stock_top(self):
        rows=fixture()
        day=date.fromisoformat(rows[-1]["date"])
        status={"market_data_date":str(day),"scan_complete":True,
                "data_date_verified":True,"coverage_ratio":0.99}
        history=rows
        cs=[candidate(rows)]
        output,report=analyze(status,cs,history,[],day,{
            "asof":str(day),"status":"CROSS_SOURCE_CLOSE_CONFLICT",
            "overlap_tickers":81,"close_mismatches":59,
            "mismatch_examples":[{"ticker":"005930"}]})
        self.assertEqual(len(output),1)
        self.assertEqual(report["parity_mismatches"],59)
        self.assertEqual(report["watch_tickers"],[])
        self.assertFalse(report["trade_approved"])
        self.assertFalse(report["orders_enabled"])
        self.assertEqual(report["decision"],"CASH")

    def test_missing_parity_does_not_promote_research(self):
        rows=fixture()
        d=date.fromisoformat(rows[-1]["date"])
        _,r=analyze({"market_data_date":str(d),"scan_complete":True,
             "data_date_verified":True,"coverage_ratio":0.99},
             [candidate(rows)],rows,[],d,{})
        self.assertIn("PRICE_PARITY_DATE_OR_FILE_MISSING",r["source_errors"])
        self.assertEqual(r["watch_tickers"],[])
        self.assertEqual(r["decision"],"CASH")

if __name__=="__main__":unittest.main()
