"""No-profitability checks for C3 mobile candle charts (dated research only)."""
import os,tempfile,unittest
from pathlib import Path
import pandas as pd
from c3_top2_candle_chart_v1 import assert_study_levels,run,SCHEMA

SOURCE=os.getenv('C3_STOCK_FIRST_SOURCE_ZIP')
RANK=os.getenv('C3_V5_RANKED_CSV')

class TestC3Top2Charts(unittest.TestCase):
    def test_price_overlay_cannot_forge_last_close(self):
        bars=pd.DataFrame(dict(date=['2026-10-29','2026-10-30'],
            open=[112800,113700],high=[114200,115200],
            low=[111100,111900],close=[113200,114200],volume=[63966,56828]))
        row=dict(asof='2026-10-30',close=114201,watch_low=110900,
            watch_high=113700,structure_stop=109600,
            first_obstacle_krw=131500)
        with self.assertRaisesRegex(ValueError,'QUOTE_NOT_EQUAL_TO_ORIGINAL_OHLCV'):
            assert_study_levels(row,bars)
        row['close']=114200
        p=assert_study_levels(row,bars)
        self.assertEqual(p['structure_stop'],109600)

    def test_invalid_stop_above_entry_rejected(self):
        bars=pd.DataFrame(dict(date=['2026-10-30'],open=[113700],
            high=[115200],low=[111900],close=[114200],volume=[56828]))
        row=dict(asof='2026-10-30',close=114200,watch_low=110900,
            watch_high=113700,structure_stop=113800,
            first_obstacle_krw=131500)
        with self.assertRaisesRegex(ValueError,'UNUSABLE_STOP_ENTRY_RESISTANCE'):
            assert_study_levels(row,bars)

    def test_halt_zero_bar_rejected(self):
        bars=pd.DataFrame(dict(date=['2026-10-30'],open=[0],high=[0],
            low=[0],close=[114200],volume=[0]))
        row=dict(asof='2026-10-30',close=114200,watch_low=110900,
            watch_high=113700,structure_stop=109600,first_obstacle_krw=131500)
        with self.assertRaisesRegex(ValueError,'INVALID_OR_HALTED_OHLCV'):
            assert_study_levels(row,bars)

    @unittest.skipUnless(SOURCE and RANK,'Original Oct30 archive and v5 ranked research required')
    def test_top2_mobile_charts_are_real_45_candles_and_no_buy(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest=run(SOURCE,RANK,tmp)
            files=[Path(tmp)/x['chart_file'] for x in manifest['charts']]
            self.assertEqual(len(files),2)
            self.assertTrue(all(p.exists() and p.stat().st_size>5000 for p in files))
            self.assertEqual([x['ticker'] for x in manifest['charts']],['271560','026960'])
            self.assertEqual([x['last_close'] for x in manifest['charts']],[114200,28400])
            self.assertTrue(all(x['candle_count']==45 for x in manifest['charts']))
            self.assertFalse(manifest['trade_approved'])
            self.assertFalse(manifest['orders_enabled'])

if __name__=='__main__':
    unittest.main()
