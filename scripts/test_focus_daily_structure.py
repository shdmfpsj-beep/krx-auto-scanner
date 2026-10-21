#!/usr/bin/env python3
"""Tests prove a valid historical stop can exist without a BUY trigger."""
import unittest
from datetime import date,timedelta
from focus_daily_structure import normalize,calculate,run,save,pivot,FOCUS

ASOF=date(2026,10,22)
def bars(n=90,asof=ASOF):
    # Synthetic completed day-by-day bars, no future observations.
    start=asof-timedelta(days=n-1)
    data=[]
    for i in range(n):
        close=1000.0
        low=990.0 if i!=n-12 else 920.0
        high=1010.0 if i!=n-35 else 1400.0
        data.append(dict(date=(start+timedelta(days=i)).isoformat(),
             open=1000,high=high,low=low,close=close,volume=10000))
    return data

def calculate_fixture(rows=None,asof=ASOF):
    if rows is None:rows=bars(asof=asof)
    b,error=normalize("005930",rows)
    if error:raise ValueError(error)
    return calculate("005930","삼성전자",b,"FinanceDataReader",[],asof)

class FocusStructureTests(unittest.TestCase):
    def test_valid_pivot_stop_computed_independent_of_buy(self):
        out=calculate_fixture()
        self.assertEqual(out["pivot_date"],bars()[-12]["date"])
        self.assertGreater(out["historical_stop_reference"],0)
        self.assertLess(out["historical_stop_reference"],out["close"])
        self.assertFalse(out["trade_state"]!="CASH_NO_BUY_APPROVAL")
        self.assertEqual(out["data_source"],"FinanceDataReader")
    def test_no_recent_pivot_does_not_make_fake_stop(self):
        src=bars()
        src[-12]["low"]=990.0
        out=calculate_fixture(src)
        self.assertEqual(out["historical_stop_reference"],"")
        self.assertEqual(out["structure_state"],"NO_HELD_CONFIRMED_PIVOT")
    def test_risk_rejected_still_shows_historic_structure(self):
        src=bars()
        src[-12]["low"]=700.0
        out=calculate_fixture(src)
        self.assertEqual(out["structure_state"],"STOP_DISTANCE_UNSUITABLE")
        self.assertGreater(out["historical_stop_reference"],0)
        self.assertEqual(out["entry1_research_range"],"")
    def test_no_prior_upside_preserves_stop_but_no_buy(self):
        src=bars()
        src[-35]["high"]=1010.0
        out=calculate_fixture(src)
        self.assertEqual(out["structure_state"],"LOW_FORWARD_REWARD_RISK")
        self.assertGreater(out["historical_stop_reference"],0)
        self.assertEqual(out["trade_state"],"CASH_NO_BUY_APPROVAL")
    def test_old_quote_is_not_marked_fresh(self):
        out=calculate_fixture(rows=bars(),asof=ASOF+timedelta(days=10))
        self.assertEqual(out["historical_stop_reference"],"")
        self.assertEqual(out["structure_state"],"STALE_DAILY_CLOSE")
    def test_future_quote_cannot_be_reused(self):
        src=bars()
        b,error=normalize("005930",src)
        self.assertIsNone(error)
        out=calculate("005930","삼성전자",b,"FDR",[],ASOF-timedelta(days=1))
        self.assertEqual(out["structure_state"],"STALE_DAILY_CLOSE")
        self.assertEqual(out["historical_stop_reference"],"")
    def test_missing_market_history_produces_reason(self):
        out=calculate("005930","삼성전자",[],"NONE",["FDR_EMPTY","PYKRX_EMPTY"],ASOF)
        self.assertEqual(out["historical_stop_reference"],"")
        self.assertIn("FDR_EMPTY",out["data_problems"])
    def test_out_of_order_or_invalid_ohlc_not_used(self):
        src=bars()
        src[-1]["low"]=1500.0
        _,reason=normalize("005930",src)
        self.assertEqual(reason,"INVALID_OHLC")
        other=bars()
        other[-1]["date"]=other[-2]["date"]
        _,why=normalize("005930",other)
        self.assertEqual(why,"DUPLICATE_OR_UNSORTED_DATE")
    def test_no_network_fixture_run_uses_all_names(self):
        def fake_fetch(t,asof):
            d,why=normalize(t,bars(asof=asof))
            return d,"fixture",[]
        result=run(ASOF,fetch=fake_fetch,names={"005930":"삼성전자","000660":"SK하이닉스"})
        self.assertEqual(len(result),2)
        self.assertTrue(all(x["trade_state"]=="CASH_NO_BUY_APPROVAL" for x in result))
    def test_universe_covers_screenshot_top5_and_core(self):
        self.assertTrue({"005930","000660","010120","267260","373220",
                       "004490","042700","005380"}.issubset(FOCUS))

if __name__=="__main__":
    unittest.main()
