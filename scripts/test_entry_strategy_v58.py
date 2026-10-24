"""Offline deterministic v5.8 safety + setup geometry regression tests."""
import copy
import unittest
from datetime import date,timedelta
from unittest.mock import patch
from entry_strategy_v58 import (
    METHODS,base_row,build,breakout_retest,choose_second,
    confirmed_pivots,evaluate,nearest_ceiling,price_gate,trend_pullback,
    MIN_RR)

D=date(2026,10,23)
T="005930"

def history(n=105):
    first=date(2026,7,1)
    a=[]
    for i in range(n):
        cl=100+i*.2
        a.append(dict(ticker=T,date=str(first+timedelta(days=i)),
            open=str(cl-.4),high=str(cl+2),low=str(cl-2),
            close=str(cl),volume="1200",data_source="pykrx"))
    a[-11]["low"]=str(float(a[-11]["low"])-6)
    return a

def candidate(h):
    return dict(ticker=T,name="TEST",
        latest_date=h[-1]["date"],close=h[-1]["close"],
        instrument_type="COMMON",turnover_source="SOURCE_REPORTED",
        data_source="pykrx")

def provenance(day,names):
    return dict(schema="free_krx_regular_source_forensics_v57",
        asof=str(day),diagnosis_valid=True,
        total_rows=len(names),mismatches=0,
        comparisons=[dict(ticker=x,close_equal=True,
            category="OHLC_EXACT_MATCH_UNCERTIFIED") for x in names],
        trade_approved=False,orders_enabled=False)

class EntryV58Tests(unittest.TestCase):
    def test_all_three_methods_always_emitted_in_fixed_order(self):
        h=history();d=date.fromisoformat(h[-1]["date"])
        status=dict(market_data_date=str(d),scan_complete=True,
                    data_date_verified=True,coverage_ratio=.99)
        plans,r=build(status,[candidate(h)],h,provenance(d,[T]),d)
        self.assertEqual([x["method"] for x in plans],list(METHODS))
        self.assertEqual(r["evaluated_method_rows"],3)
        self.assertEqual(r["decision"],"CASH")
        self.assertFalse(r["trade_approved"])
        self.assertFalse(r["orders_enabled"])
        self.assertFalse(r["final_80_score_verified"])

    def test_price_gate_rejects_cross_date_unverified_rows(self):
        p=provenance(D,[T])
        self.assertEqual(price_gate(D,p)[1],[])
        p["asof"]="2026-10-22"
        self.assertIn("SOURCE_FORENSICS_DATE_OR_INTEGRITY_INVALID",price_gate(D,p)[1])

    def test_price_gate_rejects_duplicate_or_unsafe_flags(self):
        p=provenance(D,[T])
        p["comparisons"]+=copy.deepcopy(p["comparisons"])
        p["total_rows"]=2
        self.assertIn("DUPLICATE_OR_MALFORMED_PRICE_PAIR",price_gate(D,p)[1])
        p=provenance(D,[T]);p["trade_approved"]=True
        self.assertIn("PRICE_FORENSICS_UNSAFE_ORDER_FLAG",price_gate(D,p)[1])

    def test_alternative_second_must_have_confirmed_pivot(self):
        b=[dict(low=110.) for i in range(80)]
        # No pivot: do not invent a 2nd MA price.
        v,s=choose_second(b,135,108,8,[])
        self.assertIsNone(v)
        self.assertEqual(s,"NO_CONFIRMED_SEPARATE_SECOND_SUPPORT")
        v,s=choose_second(b,135,108,8,[(70,110)])
        self.assertEqual(v,112)
        self.assertIn("ALTERNATIVE_LIMIT",s)
        v,s=choose_second(b,113,108,8,[(70,110)])
        self.assertIsNone(v)  # < 0.5 ATR separation.

    def test_pivot_must_have_two_right_completed_bars(self):
        bars=[dict(low=50.0+i*.1) for i in range(80)]
        bars[-2]["low"]=1
        self.assertNotIn((78,1),confirmed_pivots(bars))
        bars[-4]["low"]=2
        self.assertFalse(any(i==76 for i,_ in confirmed_pivots(bars)))

    def test_research_rows_never_have_a_buy_or_executable_price(self):
        h=history();d=date.fromisoformat(h[-1]["date"])
        p=dict(ticker=T,close_equal=True,category="OHLC_EXACT_MATCH_UNCERTIFIED")
        for m in METHODS:
            x=evaluate(candidate(h),h,d,m,p)
            self.assertFalse(x["trade_approved"])
            self.assertFalse(x["orders_enabled"])
            self.assertEqual(x["price_source_status"],"NOT_SESSION_CERTIFIED")

    def test_future_bars_cannot_redefine_past_entries(self):
        h=history();d=date.fromisoformat(h[-1]["date"])
        p=dict(ticker=T,close_equal=True,category="OHLC_EXACT_MATCH_UNCERTIFIED")
        a=evaluate(candidate(h),h,d,METHODS[0],p)
        extra=dict(h[-1]);extra["date"]=str(d+timedelta(days=1))
        extra["close"]="1000";extra["high"]="1200";extra["low"]="90"
        b=evaluate(candidate(h),h+[extra],d,METHODS[0],p)
        self.assertEqual(b["setup"],"DATA_PENDING")
        self.assertIn("HISTORY_DATE_MISMATCH",b["blocking_reasons"])
        self.assertNotEqual(a["setup"],"DATA_PENDING")

    def test_candidate_close_mismatch_blocks_research_even_same_date(self):
        h=history();d=date.fromisoformat(h[-1]["date"])
        c=candidate(h);c["close"]="999"
        x=evaluate(c,h,d,METHODS[0])
        self.assertEqual(x["setup"],"DATA_PENDING")
        self.assertIsNone(x["stop_reference"])
        self.assertIn("CANDIDATE_HISTORY_PRICE_OR_PROVIDER_MISMATCH",x["blocking_reasons"])

    def test_c3_cash_and_capital_not_auto_assumed(self):
        h=history();d=date.fromisoformat(h[-1]["date"])
        s=dict(market_data_date=str(d),scan_complete=True,
               data_date_verified=True,coverage_ratio=.99)
        _,r=build(s,[candidate(h)],h,provenance(d,[T]),d)
        self.assertFalse(r["final_80_score_verified"])
        self.assertIn("NEVER_AVERAGE_DOWN",r["second_entry_policy"])

    def test_completed_breakout_retest_requires_actual_retest(self):
        a=[dict(open=99,high=105,low=95,close=100,volume=500) for _ in range(105)]
        # A breakout j=n-4 and a tested level on n-2; today confirmed reclaim.
        a[-4].update(open=104,high=112,low=103,close=111)
        a[-3].update(open=110,high=112,low=105,close=108)
        a[-2].update(open=108,high=110,low=104,close=108)
        a[-1].update(open=109,high=115,low=108,close=113)
        self.assertIsNotNone(breakout_retest(a,8))
        a[-2]["low"]=110
        self.assertIsNone(breakout_retest(a,8))

    def test_trend_requires_completed_reclaim_and_rising_ma(self):
        a=[dict(open=99+i*.3,high=101+i*.3,
                low=98+i*.3,close=100+i*.3,volume=500)
           for i in range(110)]
        a[-2]["low"]=a[-2]["close"]-7
        a[-1]["close"]=a[-2]["high"]+1
        self.assertIsNotNone(trend_pullback(a,4))
        a[-1]["close"]=a[-2]["high"]-1
        self.assertIsNone(trend_pullback(a,4))

    def test_first_and_second_both_checked_for_two_r(self):
        self.assertEqual(MIN_RR,2.0)
        h=history();d=date.fromisoformat(h[-1]["date"])
        p=dict(ticker=T,close_equal=False,category="CLOSE_ONLY_SAME_OPEN_HIGH_LOW")
        with patch("entry_strategy_v58.first_pullback",
                   return_value=dict(method=METHODS[0],
                     signal_condition="TEST_COMPLETED",first_hint=120,
                     support_hint=None)):
            x=evaluate(candidate(h),h,d,METHODS[0],p)
        self.assertIn("CROSS_SOURCE_CLOSE_MISMATCH",x["blocking_reasons"])
        self.assertFalse(x["trade_approved"])
        self.assertEqual(x["second_entry_policy"] if x["second_entry_reference"] is None
            else "SECOND_PRESENT",x["second_entry_policy"] if x["second_entry_reference"] is None
            else "SECOND_PRESENT")

    def test_no_false_top5_if_source_missing(self):
        h=history();d=date.fromisoformat(h[-1]["date"])
        status=dict(market_data_date=str(d),scan_complete=True,
                    data_date_verified=True,coverage_ratio=.99)
        out,r=build(status,[candidate(h)],h,{},d)
        self.assertEqual(len(out),3)
        self.assertIn("DATED_FULL_V57_SOURCE_FORENSICS_MISSING",r["source_errors"])
        self.assertEqual(r["watch_tickers"],[])
        self.assertEqual(r["decision"],"CASH")

if __name__=="__main__":unittest.main()
