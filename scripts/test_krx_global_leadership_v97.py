import csv
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from krx_global_leadership_v97 import (
    us_close_kst, cutoff_kst, us_asof, parse_ohlc, factor, verified_map,
    future_returns, write_csv, execute, ETFS)

class V97Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()

    def test_us_summer_time_kst(self):
        self.assertEqual(us_close_kst(date(2024,7,1)).hour,5)
        self.assertEqual(us_close_kst(date(2024,1,2)).hour,6)
        self.assertEqual(us_close_kst(date(2024,7,1)).date(), date(2024,7,2))

    def test_korea_morning_uses_last_us_close(self):
        bars=[{'day':date(2024,7,1)}, {'day':date(2024,7,2)}]
        self.assertEqual(us_asof(bars,date(2024,7,2)),0)
        self.assertEqual(us_asof(bars,date(2024,7,3)),1)

    def test_cannot_use_same_us_session_on_kr_day(self):
        bars=[{'day':date(2024,7,2)}, {'day':date(2024,7,3)}]
        self.assertEqual(us_asof(bars,date(2024,7,3),at='15:00'),0)

    def test_us_weekend_monday(self):
        bars=[{'day':date(2024,7,5)}]
        self.assertEqual(us_asof(bars,date(2024,7,8)),0)
        self.assertIsNone(us_asof(bars,date(2024,7,12)))

    def test_missing_us_history_is_missing(self):
        self.assertIsNone(us_asof([],date(2024,7,2)))
        self.assertIsNone(factor([],{},date(2024,7,2)))

    def test_verified_map_blocks_future_membership(self):
        row={'ticker':'083450','global_theme':'SMH','valid_from':'2022-01-01','valid_to':'','available_date':'2024-07-10','source':'historical archive','verified':'true'}
        self.assertIsNone(verified_map([row],'083450',date(2024,7,5)))
        self.assertEqual(verified_map([row],'083450',date(2024,7,12))['global_theme'],'SMH')

    def test_unverified_not_accepted(self):
        row={'ticker':'083450','global_theme':'SOXX','valid_from':'2022-01-01','available_date':'2022-01-01','source':'guessed','verified':'false'}
        self.assertIsNone(verified_map([row],'083450',date(2024,1,1)))

    def test_malformed_mapping_not_accepted(self):
        row={'ticker':'083450','global_theme':'UNKNOWN','valid_from':'2022-01-01','available_date':'2022-01-01','source':'reference','verified':'true'}
        self.assertIsNone(verified_map([row],'083450',date(2024,1,1)))

    def test_horizon_next_open(self):
        d=date(2024,1,2)
        bars=[{'day':d,'open':100,'close':100}]+[{'day':d+timedelta(days=i),'open':100,'close':100+i} for i in range(1,23)]
        ret,entry=future_returns(bars,d,cost_pct=0.35)
        self.assertEqual(entry,'2024-01-03')
        self.assertAlmostEqual(ret['5'],4.65)
        self.assertAlmostEqual(ret['10'],9.65)
        self.assertAlmostEqual(ret['20'],19.65)

    def test_insufficient_horizon_is_not_return(self):
        d=date(2024,1,2)
        ret,entry=future_returns([{'day':d+timedelta(days=1),'open':100,'close':101}],d)
        self.assertIsNone(ret['5'])

    def test_invalid_ohlc_rejected(self):
        p=self.d/'x.csv'
        write_csv(p,[{'Date':'2024-01-02','Open':100,'High':98,'Low':90,'Close':101,'Volume':100}],['Date','Open','High','Low','Close','Volume'])
        self.assertEqual(parse_ohlc(p),[])

    def test_factor_requires_21_matching_sessions(self):
        start=date(2024,7,1)
        bars=[{'day':start+timedelta(days=i),'close':100+i*2} for i in range(45)]
        spy={b['day']:100+i for i,b in enumerate(bars)}
        # Korea date in Aug sees all US sessions through previous day
        f=factor(bars,spy,date(2024,8,16))
        self.assertIsNotNone(f)
        self.assertGreater(f['excess5_pp'],0)
        self.assertTrue(f['strong'])

    def test_with_no_global_data_no_approved_link(self):
        start=date(2024,6,3)
        prices=[{'Date':(start+timedelta(days=i)).isoformat(),'Open':100+i,'High':102+i,'Low':99+i,'Close':101+i,'Volume':1000} for i in range(31)]
        krx=self.d/'krx';krx.mkdir()
        write_csv(krx/'083450.csv',prices,['Date','Open','High','Low','Close','Volume'])
        signal=self.d/'signals.csv'
        write_csv(signal,[{'ticker':'083450','signal_date':'2024-06-05','signal_score':'80','selection_status':'MISSING_ASOF_SECTOR'}],['ticker','signal_date','signal_score','selection_status'])
        mapping=self.d/'map.csv';mapping.write_text('ticker,global_theme,valid_from,valid_to,available_date,source,verified\n')
        args=type('A',(),{'outdir':str(self.d/'out'),'global_cache':str(self.d/'global'),'start':'2023-01-01','end':'2024-07-10','provider':'none','signals':str(signal),'mapping':str(mapping),'krx_cache':str(krx),'cutoff':'08:35','round_trip_cost_pct':0.35})()
        result=execute(args)
        self.assertEqual(result['strict_global_link_signal_count'],0)
        self.assertEqual(result['strict_signal_gate'],'NOT_READY_NO_VERIFIED_SECTOR_LINKS')
        audit=list(csv.DictReader((self.d/'out'/'v97_signal_global_audit.csv').open(encoding='utf-8-sig')))
        self.assertEqual(audit[0]['global_status'],'MISSING_SECTOR_MAP')

    def test_approved_map_does_not_infer_without_etf(self):
        start=date(2024,6,3)
        prices=[{'Date':(start+timedelta(days=i)).isoformat(),'Open':100+i,'High':102+i,'Low':99+i,'Close':101+i,'Volume':1000} for i in range(40)]
        krx=self.d/'krx';krx.mkdir()
        write_csv(krx/'083450.csv',prices,['Date','Open','High','Low','Close','Volume'])
        signal=self.d/'signals.csv'
        write_csv(signal,[{'ticker':'083450','signal_date':'2024-06-05','signal_score':'80','selection_status':'MISSING_ASOF_SECTOR'}],['ticker','signal_date','signal_score','selection_status'])
        mapping=self.d/'map.csv'
        write_csv(mapping,[{'ticker':'083450','global_theme':'SMH','valid_from':'2023-01-01','valid_to':'','available_date':'2023-01-01','source':'historical trace','verified':'true'}],['ticker','global_theme','valid_from','valid_to','available_date','source','verified'])
        args=type('A',(),{'outdir':str(self.d/'out'),'global_cache':str(self.d/'global'),'start':'2023-01-01','end':'2024-07-10','provider':'none','signals':str(signal),'mapping':str(mapping),'krx_cache':str(krx),'cutoff':'08:35','round_trip_cost_pct':0.35})()
        result=execute(args)
        self.assertEqual(result['strict_global_link_signal_count'],0)
        audit=list(csv.DictReader((self.d/'out'/'v97_signal_global_audit.csv').open(encoding='utf-8-sig')))
        self.assertEqual(audit[0]['global_status'],'MISSING_GLOBAL')


    def test_synthetic_global_feed_works_as_of_real_us_close(self):
        start=date(2024,4,1)
        us_days=[start+timedelta(days=i) for i in range(100) if (start+timedelta(days=i)).weekday()<5]
        global_dir=self.d/'glob';global_dir.mkdir()
        for symbol in ETFS:
            feed=[]
            for i,d in enumerate(us_days):
                close=100+i*0.3 if symbol=='SPY' else 100+i*1.4
                feed.append({'Date':d.isoformat(),'Open':close,'High':close+2,'Low':close-2,'Close':close,'Volume':100000})
            write_csv(global_dir/(symbol+'.csv'),feed,['Date','Open','High','Low','Close','Volume'])
        krx_dir=self.d/'krx';krx_dir.mkdir()
        d=date(2024,6,12)
        korea_days=[start+timedelta(days=i) for i in range(100) if (start+timedelta(days=i)).weekday()<5]
        feed=[{'Date':dt.isoformat(),'Open':1000+i,'High':1005+i,'Low':995+i,'Close':1000+i,'Volume':100000} for i,dt in enumerate(korea_days)]
        write_csv(krx_dir/'083450.csv',feed,['Date','Open','High','Low','Close','Volume'])
        signals=self.d/'sig.csv'
        write_csv(signals,[{'ticker':'083450','signal_date':d.isoformat(),'selection_status':'MISSING_ASOF_SECTOR'}],['ticker','signal_date','selection_status'])
        m=self.d/'map.csv'
        write_csv(m,[{'ticker':'083450','global_theme':'SMH','valid_from':'2023-01-01','valid_to':'','available_date':'2023-01-01','source':'synthetic verified fixture','verified':'true'}],['ticker','global_theme','valid_from','valid_to','available_date','source','verified'])
        args=type('A',(),{'outdir':str(self.d/'out'),'global_cache':str(global_dir),'start':'2023-01-01','end':'2024-07-09','provider':'none','signals':str(signals),'mapping':str(m),'krx_cache':str(krx_dir),'cutoff':'08:35','round_trip_cost_pct':0.35})()
        status=execute(args)
        self.assertEqual(status['strict_global_link_signal_count'],1)
        rows=list(csv.DictReader((self.d/'out'/'v97_signal_global_audit.csv').open(encoding='utf-8-sig')))
        self.assertEqual(rows[0]['global_status'],'STRONG')
        self.assertEqual(rows[0]['macro_regime'],'GLOBAL_BREADTH_ON')
        # Wednesday Korea morning: Tuesday US 16:00 local close available 05 KST.
        self.assertEqual(rows[0]['us_session'],'2024-06-11')
        self.assertEqual(rows[0]['macro_up'],'6')
        self.assertNotEqual(rows[0]['net5_pct'],'')

if __name__=='__main__':unittest.main(verbosity=2)
