import unittest
from datetime import datetime,timezone,timedelta
from c3_intraday_watch_v1 import evaluate
KST=timezone(timedelta(hours=9))
P=[{"ticker":"271560","name":"오리온","watch_low":"110900","watch_high":"113700","structure_stop":"109600"}]
def now(hour=10):return datetime(2026,11,2,hour,0,tzinfo=KST)
def quote(price=112000,minute=0,source="verified_provider"):
 return {"ticker":"271560","price":price,"observed_at":datetime(2026,11,2,10,minute,tzinfo=KST).isoformat(),"source":source}
class TestWatch(unittest.TestCase):
 def test_zone_not_fill(self):
  r=evaluate(P,[quote()],now());self.assertEqual(r["alerts"][0]["status"],"WATCH_ZONE");self.assertFalse(r["alerts"][0]["paper_filled"])
 def test_stale_block(self):
  self.assertEqual(evaluate(P,[quote()],now(11))["alerts"][0]["status"],"NO_VERIFIED_QUOTE")
 def test_unverified_block(self):
  self.assertEqual(evaluate(P,[quote(source="unknown")],now())["alerts"][0]["status"],"NO_VERIFIED_QUOTE")
 def test_stop_intraday_not_close(self):
  a=evaluate(P,[quote(109000)],now())["alerts"][0];self.assertEqual(a["risk_note"],"INTRADAY_BELOW_STOP_NOT_A_CLOSE_STOP");self.assertFalse(a["paper_filled"])
 def test_afterhours(self):
  self.assertEqual(evaluate(P,[quote()],now(16))["status"],"OUTSIDE_REGULAR_SESSION")
if __name__=="__main__":unittest.main()
