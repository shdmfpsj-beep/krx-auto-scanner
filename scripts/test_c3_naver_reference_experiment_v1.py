import unittest
from c3_naver_reference_experiment_v1 import normalize

class FakeFrame:
    def __init__(self,rows):
        self.rows=rows
        self.empty=not bool(rows)
        self.columns=("Open","High","Low","Close","Volume")
    def iterrows(self):
        for day,row in self.rows:
            yield day,row
class FakeDay:
    def strftime(self,fmt):
        return "2026-11-03"
class NaverAdapterTests(unittest.TestCase):
    def test_valid_normalization(self):
        rows=normalize("271560",FakeFrame([(FakeDay(),dict(Open=100,High=105,Low=99,Close=103,Volume=10))]))
        self.assertEqual(rows[0]["ticker"],"271560")
        self.assertEqual(rows[0]["close"],103)
    def test_invalid_low_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"INVALID_NAVER_OHLCV"):
            normalize("271560",FakeFrame([(FakeDay(),dict(Open=100,High=105,Low=101,Close=103,Volume=10))]))
    def test_empty_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"EMPTY_NAVER_REFERENCE"):
            normalize("271560",FakeFrame([]))
if __name__=="__main__":
    unittest.main()
