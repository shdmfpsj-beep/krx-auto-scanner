import unittest,sys,math,datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import hma60_first_pullback_v11 as model
import bottom_upturn_v10 as base

class Hma60ResearchTests(unittest.TestCase):
 def test_wma_finite(self):self.assertAlmostEqual(model.wma([1.,2.,3.],3)[-1],14/6)
 def test_wma_warmup(self):self.assertEqual(model.wma([1.,2.,3.],3)[:2],[None,None])
 def test_wma_bad_period(self):
  with self.assertRaises(ValueError):model.wma([1.,2.],0)
 def test_hma_warmup(self):
  h=model.hma([float(i+30) for i in range(70)])
  self.assertTrue(all(a is None for a in h[:65]));self.assertIsNotNone(h[65])
 def test_hma_identity_linear(self):
  # Hull MA is low-lag and on an exact linear close sequence its lag is finite.
  y=[100.+i*.20 for i in range(90)];h=model.hma(y)
  self.assertAlmostEqual(h[89]-h[88],.20,places=8)
 def test_hma_no_future_peek(self):
  price=[100.+math.sin(i/7)*4+i*.1 for i in range(105)]
  a=model.hma(price);b=model.hma(price+[1000,1,10])
  self.assertEqual(a,b[:len(a)])
 def test_turn_no_forced_signals_on_flat_data(self):
  bars=self.make_bars();h=model.hma([b['close'] for b in bars]);self.assertEqual(list(model.turn_dates(bars,h)),[])
 def test_turn_slope_confirmation(self):
  b=self.make_bars();h=[90.0]*len(b)
  for i in range(80,100):h[i]=100-(i-80)*.3
  h[100]=94.5;h[101]=94.2;h[102]=94.4;h[103]=94.6
  self.assertIn(103,list(model.turn_dates(b,h)))
 def test_turn_reject_no_prior_downtrend(self):
  b=self.make_bars();h=[100.0]*len(b);h[100]=99.9;h[101]=100;h[102]=100.1
  self.assertNotIn(102,list(model.turn_dates(b,h)))
 def test_example_match_first_pullback(self):
  b,h=self.example();x=model.recognize_first_pullback(b,h,95)
  self.assertIsNotNone(x,x);self.assertEqual(x['entry_idx'],100)
  self.assertEqual(x['signal_date'],b[99]['date']);self.assertTrue(.025<=x['risk_pct']/100<=.05)
 def test_future_changes_do_not_change_entry(self):
  b,h=self.example();a=model.recognize_first_pullback(b,h,95)
  b2=[x.copy() for x in b]
  for r in b2[101:]:r['close']*=1.7;r['open']*=1.7;r['high']*=1.7;r['low']*=1.7
  self.assertEqual(a,model.recognize_first_pullback(b2,h,95))
 def test_rebound_not_yet_confirmed(self):
  b,h=self.example();b[99]['close']=103.;self.assertIsNone(model.recognize_first_pullback(b,h,95))
 def test_gap_up_rejected(self):
  b,h=self.example();b[100]['open']=110.;self.assertIsNone(model.recognize_first_pullback(b,h,95))
 def test_gap_down_rejected(self):
  b,h=self.example();b[100]['open']=95.;self.assertIsNone(model.recognize_first_pullback(b,h,95))
 def test_failed_first_pullback_if_heavy_volume(self):
  b,h=self.example();b[98]['volume']=5000
  self.assertIsNone(model.recognize_first_pullback(b,h,95))
 def test_hma_loss_censoring(self):
  b,h=self.example();e=model.recognize_first_pullback(b,h,95)
  self.assertEqual(base.run_exit(b[:100],e,'A_10_ALL')['status'],'CENSORED_NO_60_BARS')
 def test_stop_and_profit_same_bar_is_stop(self):
  b,h=self.example();e=model.recognize_first_pullback(b,h,95)
  b[100]['low']=e['stop']*.99;b[100]['high']=e['entry_price']*1.23
  r=base.run_exit(b,e,'A_10_ALL');self.assertEqual(r['exit_reason'],'STOP')
 def test_b_exit_partially_open_is_censored(self):
  b,h=self.example();e=model.recognize_first_pullback(b,h,95)
  b[100]['high']=e['entry_price']*1.11
  # no future bars, only TP half completed, rest not assumed to have returned
  b=b[:101];r=base.run_exit(b,e,'B_10_HALF_20_TRAIL');self.assertEqual(r['status'],'CENSORED_REMAINDER_OPEN')
 def test_chronological_signal_selection_not_turn_order(self):
  from unittest.mock import patch
  b=self.make_bars()
  older={'turn_date':'2024-04-01','entry_idx':106,'entry_date':b[106]['date']}
  newer={'turn_date':'2024-04-03','entry_idx':103,'entry_date':b[103]['date']}
  with patch.object(model,'turn_dates',return_value=iter([90,92])):
   with patch.object(model,'recognize_first_pullback',side_effect=[older,newer]):
    picks,_,_=model.hma_entries(b,0)
  self.assertEqual(len(picks),1)
  self.assertEqual(picks[0]['entry_idx'],103)
 def test_entry_bar_later_highs_cannot_change_signal(self):
  b,h=self.example();a=model.recognize_first_pullback(b,h,95)
  b[100]['high']=10000.;b[100]['close']=9999.;b[100]['low']=.1
  self.assertEqual(a,model.recognize_first_pullback(b,h,95))
 def test_watchlist_not_a_success_cohort(self):
  self.assertEqual(model.HMA_PERIOD,60)
  self.assertEqual(model.VARIANTS,base.VARIANTS)
 def make_bars(self):
  start=datetime.date(2024,1,1)
  return [dict(date=str(start+datetime.timedelta(days=i)),open=100.,high=101.,low=99.,close=100.,volume=1000.) for i in range(125)]
 def example(self):
  b=self.make_bars()
  h=[95.+i*.03 for i in range(125)]
  b[95].update(close=100.,open=99.,high=101.,low=98.)
  b[97].update(close=105.,open=100.,high=106.,low=99.5,volume=2500.)
  b[98].update(close=104.,open=105.,high=105.,low=101.5,volume=1100.)
  b[99].update(close=105.5,open=103.5,high=106.5,low=103.5,volume=1600.)
  b[100].update(open=105.,high=108.,low=104.,close=107.)
  return b,h

if __name__=='__main__':unittest.main()
