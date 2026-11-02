import unittest
from datetime import datetime,timezone,timedelta
from c3_intraday_watch_v1 import evaluate
KST=timezone(timedelta(hours=9))
PLANS=[{"ticker":"271560","name":"오리온","watch_low":"110900","watch_high":"113700","structure_stop":"109600"}]
NOW=datetime(2026,11,2,10,10,tzinfo=KST)
class Safety(unittest.TestCase):
 def test_naive_time_rejected(self):
  q={"ticker":"271560","price":112000,"observed_at":"2026-11-02T10:09:00","source":"verified_provider"}
  self.assertEqual(evaluate(PLANS,[q],NOW)["alerts"][0]["status"],"NO_VERIFIED_QUOTE")
 def test_zoned_time_accepted(self):
  q={"ticker":"271560","price":112000,"observed_at":"2026-11-02T10:09:00+09:00","source":"verified_provider"}
  self.assertEqual(evaluate(PLANS,[q],NOW)["alerts"][0]["status"],"WATCH_ZONE")
if __name__=="__main__":unittest.main()
