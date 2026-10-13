import csv, tempfile, unittest, sys, io
from pathlib import Path
from datetime import date, timedelta
sys.path.insert(0,str(Path(__file__).parent))
import hma2026_v12 as m

class HMA2026Tests(unittest.TestCase):
 def makebars(self,n=300,start=date(2025,1,2),jump=0):
  d=start;rows=[]
  while len(rows)<n:
   if d.weekday()<5:
    val=100+len(rows)*0.12 + jump
    rows.append(dict(Date=d.isoformat(),Open=val,High=val+1,Low=val-1,Close=val+.2,Volume=10000))
   d+=timedelta(days=1)
  return rows
 def test_user_examples_count(self):self.assertEqual(len(m.USER_FOUR),4)
 def test_lookahead_features_closed_at_signal(self):
  b=[{'date':r['Date'],'open':r['Open'],'high':r['High'],'low':r['Low'],'close':r['Close'],'volume':r['Volume']} for r in self.makebars(300)]
  a=m.money_features(b,250)
  b[251]['close']=100_000; b[251]['volume']=50_000_000
  self.assertEqual(a,m.money_features(b,250))
 def test_turnover_ratio_positive(self):
  b=[{'date':r['Date'],'open':r['Open'],'high':r['High'],'low':r['Low'],'close':r['Close'],'volume':r['Volume']} for r in self.makebars()]
  f=m.money_features(b,50)
  self.assertGreater(f['tv_ratio_10_vs_prior20'],0)
 def test_staleness_rejected_without_inventing_october_prices(self):
  r=self.makebars(310);status,_=m.validate_rows(r,'2025-01-01','2026-10-14')
  self.assertEqual(status,'STALE_MORE_THAN_7_CAL_DAYS')
 def test_short_history_rejected(self):
  status,_=m.validate_rows(self.makebars(64),'2025-01-01','2026-10-14')
  self.assertEqual(status,'INSUFFICIENT_220_BARS')
 def test_pre_aug_2025_required(self):
  r=self.makebars(240,date(2025,9,1));s,_=m.validate_rows(r,'2025-01-01','2026-10-14');self.assertIn(s,('MISSING_PRE_2025_AUG','STALE_MORE_THAN_7_CAL_DAYS'))
 def test_recent_oct_2026_required(self):
  r=self.makebars(250);s,_=m.validate_rows(r,'2025-01-01','2026-10-14');self.assertEqual(s,'STALE_MORE_THAN_7_CAL_DAYS')
 def test_duplicate_dates_invalid(self):
  r=self.makebars(460); r[250]['Date']=r[249]['Date'];s,_=m.validate_rows(r,'2025-01-01','2026-10-14');self.assertIn(s,('INVALID_OHLCV','STALE_MORE_THAN_7_CAL_DAYS'))
 def test_large_data_gap_detected(self):
  r=self.makebars(460);r=r[:200]+r[250:];self.assertTrue(m.has_big_gaps(r))
 def test_turnover_not_net_buy(self):
  r=self.makebars(400);f=m.money_features([{'date':e['Date'],'open':e['Open'],'high':e['High'],'low':e['Low'],'close':e['Close'],'volume':e['Volume']} for e in r],50)
  self.assertNotIn('net_buy',f)
 def test_sector_sample_not_pit(self):
  b=[{'date':'2026-09-10','open':100,'high':105,'low':98,'close':104,'volume':100}]
  z=m.market_calendar_daily_flow({'005930':b},{'005930':{'sector_snapshot':'semiconductor'}})
  self.assertEqual(z[0]['sector_historical_pit_verified'],'False')
 def test_prepare_forced_4_and_unmapped_skipped(self):
  with tempfile.TemporaryDirectory() as td:
   td=Path(td);z=td/'old';z.mkdir();(z/'000001.csv').write_text('Date,Open,High,Low,Close,Volume\n',encoding='utf-8')
   mp=td/'sector.csv'
   with mp.open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=['ticker','name','market','sector']);w.writeheader();w.writerow(dict(ticker='000001',name='A',market='KOSPI',sector='x'))
   obj=type('Args',(),dict(source=str(z),mapping=str(mp),outdir=str(td/'out'),universe_mode='v36'))()
   manifest=m.prepare(obj);self.assertEqual(len(manifest),5)
   self.assertTrue(all(x['sector_historical_pit_verified']=='False' for x in manifest))
 def test_hma_wma_formula(self):
  import hma60_first_pullback_v11 as hm
  vals=[100.0+i*.1 for i in range(180)]
  out=hm.hma(vals)
  self.assertIsNone(out[64]);self.assertIsNotNone(out[-1])
 def test_source_does_not_merge_old_short_prices(self):
  text=Path(m.__file__).read_text();self.assertNotIn('merged.update',text)
 def test_no_invented_numeric_for_zero_denominator(self):
  bars=[{'date':(date(2025,1,1)+timedelta(days=i)).isoformat(),'close':100.,'open':100.,'high':101.,'low':99.,'volume':0.} for i in range(50)]
  f=m.money_features(bars,45)
  self.assertIsNone(f['tv_ratio_10_vs_prior20'])
 def test_price_gaps_in_study_censor(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);(p/'prices').mkdir();
   csvfile=p/'manifest.csv';m.save_csv(csvfile,[dict(ticker='036930',name='A',market='KOSDAQ',sector_snapshot='전기전자',snapshot_date='2026-10-08')],['ticker','name','market','sector_snapshot','snapshot_date'])
   args=type('Args',(),dict(manifest=str(csvfile),prices=str(p/'prices'),outdir=str(p/'out'),asof='2026-10-13',min_turnover=0,max_hold=60,cost_bps=35,min_valid=50))()
   audit=m.study(args);self.assertEqual(audit['status'],'DATA_PENDING');self.assertEqual(audit['full_asof_2026_history'],0)

if __name__=='__main__':unittest.main()
