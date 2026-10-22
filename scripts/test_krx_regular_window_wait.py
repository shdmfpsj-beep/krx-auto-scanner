import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from krx_regular_window_wait import seconds_until_capture

KST=ZoneInfo("Asia/Seoul")
def t(h,m,s=0,day=23):
    return datetime(2026,10,day,h,m,s,tzinfo=KST)

class WaitWindowTests(unittest.TestCase):
    def test_prewarms_then_waits_until_market_close_observation(self):
        self.assertEqual(seconds_until_capture(t(15,25)),495)
        self.assertEqual(seconds_until_capture(t(15,33,15)),0)
        self.assertEqual(seconds_until_capture(t(15,35)),0)
    def test_late_worker_cannot_backdate_or_claim_regular(self):
        self.assertIsNone(seconds_until_capture(t(15,40)))
        self.assertIsNone(seconds_until_capture(t(16,0)))
        self.assertIsNone(seconds_until_capture(t(12,0,day=24)))
    def test_requires_timezone_aware_time(self):
        with self.assertRaisesRegex(ValueError,"TZ_AWARE"):
            seconds_until_capture(datetime(2026,10,23,15,35))

if __name__=="__main__":unittest.main()
