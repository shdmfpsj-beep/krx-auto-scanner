#!/usr/bin/env python3
import unittest
from corporate_action_guard_v625 import event_risk,suspicious_gap,verified_total_cash_return

D="2026-08-26T15:30:00+09:00"
D1="2026-08-27T08:35:00+09:00"
DAYS=["2026-08-27","2026-08-28","2026-08-31","2026-09-01","2026-09-02"]
CORAMCO=dict(ticker="417310",type="SPECIAL_DIVIDEND",ex_date="2026-08-28",
 public_ts_kst="2026-08-26T17:07:53+09:00",
 primary_source_ref="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260826800685")

class TestCorporateAction(unittest.TestCase):
 def test_preopen_knows_afterclose_filing_but_day_signal_does_not(self):
  r=event_risk("417310",D,D1,DAYS,[CORAMCO],True)
  self.assertEqual(r["status"],"CANCEL_UNADJUSTED_CORPORATE_ACTION")
  self.assertEqual(r["known_at_signal"],[])
  self.assertEqual(len(r["known_at_preopen"]),1)
  self.assertFalse(r["trade_approved"])
 def test_future_filing_cannot_be_used_to_cancel_before_published(self):
  e=dict(CORAMCO,public_ts_kst="2026-08-27T17:07:53+09:00")
  r=event_risk("417310",D,D1,DAYS,[e],True)
  self.assertEqual(r["status"],"NO_DISCLOSED_ACTION_IN_VERIFIED_INVENTORY")
 def test_unknown_inventory_not_promoted_to_green(self):
  r=event_risk("005930",D,D1,DAYS,[],False)
  self.assertEqual(r["status"],"UNKNOWN_CORPORATE_ACTION_COVERAGE")
 def test_other_ticker_event_not_falsely_matched(self):
  r=event_risk("005930",D,D1,DAYS,[CORAMCO],True)
  self.assertEqual(r["status"],"NO_DISCLOSED_ACTION_IN_VERIFIED_INVENTORY")
  self.assertFalse(r["trade_approved"])
 def test_exdate_outside_holding_window_not_blocked(self):
  r=event_risk("417310",D,D1,["2026-08-27"],[CORAMCO],True)
  self.assertEqual(r["status"],"NO_DISCLOSED_ACTION_IN_VERIFIED_INVENTORY")
 def test_no_naive_timestamp_accepted(self):
  with self.assertRaises(ValueError):event_risk("417310",D,"2026-08-27T08:35",DAYS,[CORAMCO],True)
 def test_missing_primary_source_rejected(self):
  with self.assertRaises(ValueError):event_risk("417310",D,D1,DAYS,[dict(CORAMCO,primary_source_ref="")],True)
 def test_large_gap_not_claimed_verified_trading_loss(self):
  r=suspicious_gap(10930,2290)
  self.assertTrue(r["corporate_action_investigation_required"])
  self.assertTrue(r["no_hindsight_trade_cancellation"])
 def test_dividend_must_have_verified_entitlement(self):
  self.assertIsNone(verified_total_cash_return(10970,2290,8900,False))
  self.assertEqual(verified_total_cash_return(10970,2290,8900,True),
     round(100*((2290+8900)/10970-1)-.65,3))

if __name__=="__main__":unittest.main()
