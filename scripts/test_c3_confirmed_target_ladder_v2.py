"""C3 target1/target2 chronological source tests (no historical P/L backtest)."""
import os,tempfile,unittest
import pandas as pd
from c3_confirmed_target_ladder_v2 import historic_overhead,target_ladder
from c3_top2_candle_chart_v1 import load,run

SOURCE=os.getenv('C3_STOCK_FIRST_SOURCE_ZIP')
RANK=os.getenv('C3_V5_RANKED_CSV')

class TestFourLevelResearchChart(unittest.TestCase):
    def test_two_later_complete_bars_required(self):
        dates=['2026-10-26','2026-10-27','2026-10-28','2026-10-29','2026-10-30']
        highs=[10,11,15,9,8]
        self.assertEqual(historic_overhead(highs,dates,'2026-10-29'),[])
        x=historic_overhead(highs,dates,'2026-10-30')
        self.assertEqual((x[0]['level'],x[0]['confirmed_at']),(15,'2026-10-30'))

    def test_later_break_invalidates_old_peak(self):
        dates=['2026-10-20','2026-10-21','2026-10-22','2026-10-23',
               '2026-10-26','2026-10-27','2026-10-28']
        highs=[10,11,15,9,8,16,13]
        self.assertFalse(any(x['level']==15 for x in historic_overhead(highs,dates,'2026-10-28')))

    def test_source_close_mismatch_rejected(self):
        b=pd.DataFrame(dict(date=['2026-10-26','2026-10-27','2026-10-28',
                          '2026-10-29','2026-10-30','2026-11-02','2026-11-03'],
                          high=[10,11,15,9,8,7,6],close=[9]*7))
        with self.assertRaisesRegex(ValueError,'SOURCE_CLOSE_MISMATCH'):
            target_ladder(b,asof='2026-10-30',close=11,
                          entry_low=2,entry_high=3,stop=1,first_observed=15)

    @unittest.skipUnless(SOURCE and RANK,'Original dated scan and v5 ranking required')
    def test_actual_top2_target2_dates_and_four_level_charts(self):
        _,history,ranked,_=load(SOURCE,RANK)
        for ticker,first,second,date in (
            ('271560',131500,141700,'2026-08-11'),
            ('026960',29550,30550,'2026-02-23')):
            b=history[history.ticker==ticker]
            row=ranked[ranked.ticker==ticker].iloc[0]
            z=target_ladder(b,asof='2026-10-30',close=row['close'],
                  entry_low=row['watch_low'],entry_high=row['watch_high'],
                  stop=row['structure_stop'],first_observed=row['first_obstacle_krw'])
            self.assertEqual(z['first_target']['price_krw'],first)
            self.assertEqual(z['second_target']['price_krw'],second)
            self.assertEqual(z['second_target']['pivot_date'],date)
            self.assertFalse(z['buy_approved'])
            self.assertFalse(z['orders_enabled'])
        with tempfile.TemporaryDirectory() as output:
            data=run(SOURCE,RANK,output)
            self.assertEqual([r['second_historical_resistance'] for r in data['charts']],
                             [141700,30550])
            self.assertFalse(data['trade_approved'])
            self.assertFalse(data['orders_enabled'])

if __name__=='__main__':unittest.main()
