"""Price-only C3 v4 checks. No historical performance backtesting."""
import os,tempfile,unittest
from c3_stock_first_v4 import quote,tick,net_r,ceiling_by_r,design_entries,analyze
import pandas as pd

SOURCE=os.getenv('C3_STOCK_FIRST_SOURCE_ZIP')

class TestV4(unittest.TestCase):
    def test_krx_ticks_at_band_edges(self):
        for p in (1999.2,2000.3,4999.7,19999.6,49999.2,199999.1,499999.6,500000.1):
            lo,hi=quote(p,'down'),quote(p,'up')
            self.assertLessEqual(lo,p);self.assertGreaterEqual(hi,p)
            self.assertEqual(lo%tick(lo),0);self.assertEqual(hi%tick(hi),0)

    def test_first_obstacle_not_forced_to_2r(self):
        self.assertLess(net_r(27950,26900,29550),2)
        self.assertGreaterEqual(net_r(27950,26900,29550),1.149)
        self.assertGreaterEqual(ceiling_by_r(29550,26900,1.15),27950)

    def test_dongseo_pullback_and_no_chase(self):
        row=dict(close=28400,atr14=892.86,stop=26900,support=27100,
                 first_resistance=29550,second_resistance=None,
                 r20_pct=11.59,r60_pct=11.37,rvol20=.82)
        b=pd.DataFrame({'high':[26000]*19+[29550]+[28000],
            'low':[25500]*21,'close':[25900]*21,'volume':[100000]*21,
            'date':[f'2026-10-{i+1:02d}' for i in range(21)]})
        p=design_entries(row,b)
        self.assertEqual((p['pullback_low'],p['pullback_high']),(27600,27950))
        self.assertIsNone(p['breakout_trigger'])
        self.assertFalse(p['buy_approved'])
        self.assertFalse(p['orders_enabled'])
        self.assertIn(p['overhead_supply'],('LOW_CONFIRMED_SELL_PRESSURE','MODERATE_SUPPLY','HIGH_SUPPLY'))

    def test_orion_breakout_needs_future_confirmation(self):
        row=dict(close=114200,atr14=3564.29,stop=109600,support=110300,
                 first_resistance=131500,second_resistance=141700,
                 r20_pct=6.73,r60_pct=-13.35,rvol20=.57)
        b=pd.DataFrame({'high':[111000]*19+[115200]+[114200],
            'low':[100000]*21,'close':[110000]*21,'volume':[100000]*21,
            'date':[f'2026-10-{i+1:02d}' for i in range(21)]})
        p=design_entries(row,b)
        self.assertEqual(p['breakout_trigger'],115700)
        self.assertIn('FUTURE_COMPLETED_CLOSE',p['breakout_rule'])
        self.assertTrue(p['breakouts_are_not_today_orders'])

    @unittest.skipUnless(SOURCE,'Original dated scan source required')
    def test_original_oct30_stock_first_screen(self):
        with tempfile.TemporaryDirectory() as d:
            z,_=analyze(SOURCE,d)
        self.assertEqual(z['source_run_id'],'41051723762')
        self.assertEqual(z['price_stage_total'],457)
        self.assertEqual(z['researched'],96)
        self.assertTrue(-30<z['market_median_20d_pct']<30)
        self.assertEqual([i['ticker'] for i in z['top2']],['026960','271560'])
        self.assertFalse(z['trade_approved'])
        self.assertFalse(z['orders_enabled'])
        self.assertTrue(z['no_backtest_requested'])
        self.assertEqual(z['readiness_counts']['C_SHARP_REBOUND_NOT_CONFIRMED'],3)
        self.assertEqual(z['top2'][1]['breakout_trigger'],115300)
        for row in z['top2']:
            self.assertLess(row['stop'],row['pullback_low'])
            self.assertLessEqual(row['pullback_low'],row['pullback_high'])
            self.assertFalse(row['investor_flow_verified'])

if __name__=='__main__':unittest.main()
