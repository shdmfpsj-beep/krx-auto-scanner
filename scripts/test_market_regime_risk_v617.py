#!/usr/bin/env python3
import unittest,tempfile,csv
from datetime import date,timedelta
from pathlib import Path
from market_regime_risk_v617 import classify,market_asof,SCHEMA

class RiskGateAudit(unittest.TestCase):
    def test_green_still_research_not_trade(self):
        flag,why=classify(110,100,1.2,2.5,-.4)
        self.assertEqual(flag,"GREEN_RESEARCH_ONLY")
        self.assertIn("ABOVE_20MA",why)
    def test_below_ma20_always_red(self):
        self.assertEqual(classify(99,100,2,6,4)[0],"RED_MARKET_RISK_OFF")
    def test_three_day_crash_red_even_if_above_ma20(self):
        self.assertEqual(classify(101,100,0,-3.1,0)[0],"RED_MARKET_RISK_OFF")
    def test_daily_crash_red_even_if_ma20_looks_strong(self):
        self.assertEqual(classify(110,100,-3.2,2,4)[0],"RED_MARKET_RISK_OFF")
    def test_amber_for_negative_daily_momentum(self):
        self.assertEqual(classify(110,100,-1,1,1)[0],"AMBER_CONFIRMATION_WAIT")
    def test_missing_market_data_is_not_green(self):
        self.assertEqual(classify(None,100,1,1,1)[0],"RED_UNVERIFIED_DATA")
        self.assertEqual(classify(110,0,1,1,1)[0],"RED_UNVERIFIED_DATA")
    def test_market_source_requires_20261023_current_and_chronological(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/"market/etf_prices/069500.csv"
            target.parent.mkdir(parents=True)
            start=date(2026,6,15)
            with target.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["Date","Close"])
                w.writeheader()
                for i in range((date(2026,10,23)-start).days+1):
                    v=start+timedelta(days=i)
                    w.writerow(dict(Date=v.isoformat(),Close=10000+i))
            rs,h=market_asof(Path(d),"2026-10-23")
            self.assertEqual(rs["2026-10-23"]["risk_mode"],"GREEN_RESEARCH_ONLY")
            self.assertTrue(h)
            with self.assertRaisesRegex(ValueError,"STALE"):
                market_asof(Path(d),"2026-10-24")
    def test_schema_read_only(self):
        self.assertEqual(SCHEMA,"C3_V617_MARKET_CRASH_GATE_AUDIT_READ_ONLY")

if __name__=="__main__":unittest.main()
