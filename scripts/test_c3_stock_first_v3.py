"""C3 v3 stock-first selector unit tests: no portfolio or historical P/L backtests."""
import os,tempfile,unittest
from pathlib import Path
import numpy as np
import pandas as pd
from c3_stock_first_v3 import (floor,first_resistances,price_grid_down,
    run,source,SCHEMA)

ARCHIVE=os.getenv('C3_STOCK_FIRST_SOURCE_ZIP')

class TestStockFirst(unittest.TestCase):
    def test_pivot_cannot_be_used_before_two_later_closes(self):
        for n in [5,6,7]:
            lows=[110,108,105,100,92,99,101][:n]
            bars=pd.DataFrame({'low':lows,'date':[f'2026-10-{i+10:02d}' for i in range(n)]})
            pivot=floor(bars)
            if n<7:self.assertIsNone(pivot)
            else:self.assertEqual((pivot[0],pivot[1],pivot[2]),(92.,'2026-10-14','2026-10-16'))

    def test_quote_grid_uses_valid_price_steps(self):
        self.assertEqual(price_grid_down(27621),27600)
        self.assertEqual(price_grid_down(112987),112900)
        self.assertEqual(price_grid_down(5894),5890)

    def test_near_high_pivot_not_created_without_five_complete_bars(self):
        bars=pd.DataFrame({'high':[110,112,115,125,120,118,116,115,114,113],
           'date':[f'2026-10-{i+10:02d}' for i in range(10)]})
        r=first_resistances(bars,100)
        self.assertTrue(r)
        self.assertEqual(r[0][0],125)

    @unittest.skipUnless(ARCHIVE,'Original frozen full-market artifact required')
    def test_actual_20261030_snapshot_selects_two_without_trading(self):
        scan,obs,hist,sector,name,evidence=source(ARCHIVE)
        self.assertEqual(scan['market_data_date'],'2026-10-30')
        with tempfile.TemporaryDirectory() as tmp:
            summary=run(ARCHIVE,tmp)
        self.assertEqual(summary['schema'],SCHEMA)
        self.assertEqual(summary['premovement_stage_cases'],457)
        self.assertEqual(summary['structured_candidates'],96)
        self.assertEqual([x['ticker'] for x in summary['new_research_top2']],
                         ['026960','271560'])
        self.assertFalse(summary['trade_approved'])
        self.assertFalse(summary['orders_enabled'])
        self.assertTrue(summary['no_performance_backtest'])
        for x in summary['new_research_top2']:
            self.assertEqual(x['entry_status'],'ACTIONABLE_RESEARCH_ZONE')
            self.assertGreaterEqual(x['first_resistance_net_R'],2)
            self.assertLess(x['stop_krw'],x['buy_low_krw'])
            self.assertLessEqual(x['buy_low_krw'],x['buy_high_krw'])
            self.assertFalse(x['regular_only_verified'])
            self.assertFalse(x['trade_approved'])

if __name__=='__main__':unittest.main()
