#!/usr/bin/env python3
"""v6.18 U.S./macro risk decisions never create brokerage BUY orders."""
import io,unittest,tempfile,csv
from pathlib import Path
from datetime import date
from unittest.mock import patch
from global_macro_risk_v618 import (
    SCHEMA,fred_parse,latest_fred,fred_change,etf_context,classify,collect,FRED_SERIES
)
def etf(ret1=0,ret5=0,above=True):
    return dict(us_session="2026-10-23",close=100,ma20=99 if above else 101,
        ret1_pct=ret1,ret5_pct=ret5,above_ma20=above,
        us_close_kst="2026-10-24T05:00:00+09:00")

class GlobalMacroTests(unittest.TestCase):
    def test_fred_csv_normalization_and_missing_period_not_zero(self):
        b=b"DATE,VIXCLS\n2026-10-22,.\n2026-10-23,25.3\n"
        self.assertEqual(fred_parse(b,"VIXCLS"),[(date(2026,10,23),25.3)])
        with self.assertRaisesRegex(ValueError,"SCHEMA"):
            fred_parse(b,"DGS10")
        with self.assertRaisesRegex(ValueError,"UNSORTED"):
            fred_parse(b"DATE,VIXCLS\n2026-10-23,20\n2026-10-22,21\n","VIXCLS")
    def test_fred_stale_and_future_observation_excluded(self):
        p=[(date(2026,10,17),20.),(date(2026,10,23),23.1),(date(2026,10,26),40.)]
        self.assertEqual(latest_fred(p,date(2026,10,23),5)["value"],23.1)
        self.assertEqual(latest_fred(p,date(2026,10,25),5)["date"],"2026-10-23")
        self.assertIsNone(latest_fred(p,date(2026,11,6),5))
        self.assertLess(fred_change(p,date(2026,10,25))["delta7"],4)
    def test_global_broad_crash_is_red_even_if_chips_green(self):
        r=classify({"SPY":etf(-2.2,-3),"SMH":etf(1,5)}, {})
        self.assertEqual(r["regime"],"GLOBAL_DATA_INCOMPLETE_RESEARCH_ONLY")
        self.assertEqual(r["group_classifications"]["US_BROAD"],"RED")
        # With adequate independent VIX coverage, broad crash blocks "GREEN"
        r=classify({"SPY":etf(-2.2,-3),"SMH":etf(1,5)},{"VIXCLS":{"value":20}})
        self.assertEqual(r["regime"],"GLOBAL_RISK_OFF_RESEARCH_ONLY")
    def test_semiconductor_shock_cannot_claim_whole_market_green(self):
        e={"SPY":etf(0.4,2),"SMH":etf(-4.6,-9)}
        r=classify(e,{"VIXCLS":{"value":21}})
        self.assertEqual(r["regime"],"GLOBAL_CAUTION_RESEARCH_ONLY")
        self.assertFalse(r["confirmed_industry_stock_mapping"])
    def test_volatility_and_credit_spike_combine_to_riskoff(self):
        r=classify({"SPY":etf(.3,1)},{
           "VIXCLS":{"value":34},
           "BAMLH0A0HYM2":{"value":4.4,"delta7":.6}})
        self.assertEqual(r["regime"],"GLOBAL_RISK_OFF_RESEARCH_ONLY")
        self.assertEqual(r["red_factors"],2)
    def test_fx_and_oil_are_directionally_distinct(self):
        r=classify({"SPY":etf(.2,1),"SMH":etf(.3,3)},{
            "DEXKOUS":{"value":1450,"pct7":4},
            "DCOILWTICO":{"value":116,"pct7":12},
            "VIXCLS":{"value":18}})
        self.assertEqual(r["regime"],"GLOBAL_CAUTION_RESEARCH_ONLY")
        self.assertEqual(r["group_classifications"]["WTI"],"AMBER")
    def test_overseas_macro_missing_must_not_impute_zero_or_green(self):
        r=classify({"SPY":etf(.2,2)}, {})
        self.assertEqual(r["regime"],"GLOBAL_DATA_INCOMPLETE_RESEARCH_ONLY")
        self.assertTrue(r["positive_signal_never_authorizes_buy"])
    def test_etf_cutoff_rejects_future_us_same_calendar_session(self):
        with tempfile.TemporaryDirectory() as p:
            dest=Path(p)/"SPY.csv"
            with dest.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["Date","Open","High","Low","Close","Volume"])
                w.writeheader()
                from datetime import timedelta
                for i in range(28):
                    d=date(2026,9,23)+timedelta(days=i)
                    w.writerow(dict(Date=d.isoformat(),Open=100+i,High=101+i,
                        Low=99+i,Close=100+i,Volume=1000))
            a=etf_context(dest,date(2026,10,20),"08:35")
            self.assertEqual(a["us_session"],"2026-10-19")
    def test_collect_no_network_all_sources_absent_stays_watch_c3_cash(self):
        with tempfile.TemporaryDirectory() as root:
            with patch("global_macro_risk_v618.ensure_history",return_value=[]),patch(
                  "global_macro_risk_v618.fred_fetch",return_value=([],"MISSING_TEST")):
                out=collect(date(2026,10,25),"08:35",Path(root),False)
            self.assertEqual(out["regime"],"GLOBAL_DATA_INCOMPLETE_RESEARCH_ONLY")
            self.assertEqual(len(out["stale_or_missing_factors"]),len(FRED_SERIES))
            self.assertEqual(out["trade_action"],"CASH_UNTIL_DOMESTIC_PRICE_RISK_ACCOUNT_GATES")
            self.assertIs(out["trade_approved"],False)
            self.assertIs(out["orders_enabled"],False)
            self.assertEqual(out["schema"],SCHEMA)

if __name__=="__main__":unittest.main()
