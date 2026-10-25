import unittest
from datetime import date,timedelta
from market_month_lag_guard_v628 import market_context,SCHEMA,GATES

def history():
    d=date(2025,8,1);r=[];i=0
    while d<=date(2026,2,4):
        if d.weekday()<5:
            r.append(dict(date=d.isoformat(),close=100+i*.2))
            i+=1
        d+=timedelta(days=1)
    return r

class TestMonthlyLagV628(unittest.TestCase):
 def test_gate_count(self):
  self.assertEqual(len(GATES),6)
 def test_december_completed_before_january(self):
  q=market_context(history(),"2026-01-30")
  self.assertEqual(q['schema'],SCHEMA)
  self.assertEqual(q['last_completed_month'],"2025-12")
  self.assertLess(q['market_observation_asof'],"2026-01-01")
 def test_not_use_current_month_as_finished(self):
  q=market_context(history(),"2026-02-03")
  self.assertEqual(q['last_completed_month'],"2026-01")
  self.assertLess(q['market_observation_asof'],"2026-02-01")
 def test_mutate_future_cannot_change_today_gate(self):
  original=market_context(history(),"2026-01-16")
  data=history()
  for x in data:
   if x['date']>"2026-01-16":x['close']*=10000
  revised=market_context(data,"2026-01-16")
  self.assertEqual(original,revised)
 def test_missing_current_close_is_unknown_daily_not_false_buy(self):
  q=market_context([x for x in history() if x['date']<="2026-01-29"],"2026-01-30")
  self.assertTrue(all(v is None for v in q['daily_completed_signal_gates'].values()))
  self.assertFalse(q['trade_approved'])
 def test_positively_trending_data_not_buy(self):
  q=market_context(history(),"2026-01-30")
  self.assertTrue(q['previous_month_gates']['PREVIOUS_MONTH_POSITIVE'])
  self.assertTrue(q['daily_completed_signal_gates']['SIGNAL_DAY_ABOVE_MA20'])
  self.assertFalse(q['orders_enabled'])
 def test_duplicate_day_fails(self):
  q=history()
  q.insert(100,dict(q[99]))
  with self.assertRaises(ValueError):market_context(q,"2026-01-30")
 def test_wrong_price_fails(self):
  q=history();q[40]['close']=-100
  with self.assertRaises(ValueError):market_context(q,"2026-01-30")
 def test_missing_previous_month_is_error(self):
  q=[x for x in history() if not x['date'].startswith("2025-12")]
  with self.assertRaises(ValueError):market_context(q,"2026-01-30")
 def test_short_history_fails_not_an_approval(self):
  q=[x for x in history() if x['date']>="2025-11-01"]
  with self.assertRaises(ValueError):market_context(q,"2026-01-30")

if __name__=='__main__':unittest.main()
