"""C3 stock-first historical-resistance discovery tests: no return backtest."""
import os,tempfile,unittest
import pandas as pd
from c3_full_history_leader_radar_v7 import full_pivots,select_band,run,net_r

SOURCE=os.getenv('C3_STOCK_FIRST_SOURCE_ZIP')
RANKED=os.getenv('C3_V5_RANKED_CSV')

class TestFullHistoryRadar(unittest.TestCase):
    def fixture(self):
        days=['2026-10-20','2026-10-21','2026-10-22','2026-10-23',
              '2026-10-26','2026-10-27','2026-10-28','2026-10-29','2026-10-30']
        high=[100,112,125,109,105,103,102,101,99]
        return pd.DataFrame(dict(date=days,open=[70]*9,high=high,
                 low=[65]*9,close=[75]*9,volume=[100]*9))

    def test_early_pivot_needs_two_later_completed_sessions(self):
        b=self.fixture()
        with self.assertRaisesRegex(ValueError,'HISTORY_MISSING'):
            full_pivots(b,'2026-10-29',75)

    def test_no_future_data_and_old_peak_removed_if_broken(self):
        b=self.fixture()
        b=pd.concat([b]*15,ignore_index=True)
        b.date=pd.date_range('2026-03-01',periods=len(b),freq='D').strftime('%Y-%m-%d')
        with self.assertRaisesRegex(ValueError,'HISTORY_MISSING'):
            full_pivots(b,'2026-10-30',75)

    def test_pivot_no_invented_target_when_all_time_high(self):
        b=pd.DataFrame(dict(date=pd.date_range('2026-06-01',periods=125,freq='D').strftime('%Y-%m-%d'),
                 open=range(100,225),high=range(102,227),
                 low=range(99,224),close=range(101,226),volume=[100]*125))
        p=full_pivots(b,str(b.date.iloc[-1]),225)
        self.assertEqual(p,[])

    def test_NICE_repricing_preserves_viable_band(self):
        row=dict(close=17320,structure_stop=16470,support=16600,atr14=576.43,
                 watch_low=16780,watch_high=17250,phase='SUSTAINED_EARLY_LEADER',
                 overhead_supply='UNKNOWN')
        band=select_band(dict(row,_first_supply='LOW_OBSERVED_SUPPLY'),18000)
        self.assertEqual((band['watch_low'],band['watch_high']),(16780,17070))
        self.assertEqual(band['band_status'],'PRACTICAL_PRICE_WATCH')
        self.assertGreaterEqual(net_r(17070,16470,18000),1.149)

    def test_missing_buy_zone_does_not_auto_approve_due_resistance(self):
        row=dict(close=23250,structure_stop=20600,support=21800,atr14=1010.71,
                 watch_low=float('nan'),watch_high=float('nan'),
                 phase='UNCONFIRMED_TREND',overhead_supply='UNKNOWN',
                 _first_supply='LOW_OBSERVED_SUPPLY')
        band=select_band(row,24250)
        self.assertIsNone(band['watch_low'])
        self.assertEqual(band['band_status'],'NO_PRACTICAL_GEOMETRY')

    @unittest.skipUnless(SOURCE and RANKED,'Original Oct30 scan and v5 ranked file needed')
    def test_actual_96_full_history_discovery_and_existing_top2(self):
        with tempfile.TemporaryDirectory() as temp:
            report=run(SOURCE,RANKED,temp)
        self.assertEqual(report['researched'],96)
        self.assertEqual(report['resistance_newly_recovered_count'],18)
        self.assertEqual([x['ticker'] for x in report['top2_preserved_until_new_completed_date']],['271560','026960'])
        self.assertEqual(len(report['recovered_early_leader_challengers']),1)
        nice=report['recovered_early_leader_challengers'][0]
        self.assertEqual(nice['ticker'],'030190')
        self.assertEqual((nice['first_historical_target_krw'],nice['second_historical_target_krw']),(18000,18140))
        self.assertEqual((nice['watch_low'],nice['watch_high']),(16780,17070))
        self.assertFalse(report['trade_approved'])
        self.assertFalse(report['orders_enabled'])
        self.assertTrue(report['no_backtests'])

if __name__=='__main__':unittest.main()
