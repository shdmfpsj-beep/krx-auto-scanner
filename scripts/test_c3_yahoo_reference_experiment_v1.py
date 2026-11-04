import unittest
from c3_yahoo_reference_experiment_v1 import normalize

class YahooReferenceTests(unittest.TestCase):
    def test_empty_frame_fails(self):
        class Empty:
            empty=True
        with self.assertRaisesRegex(ValueError,"EMPTY_YAHOO_RESPONSE"):
            normalize(Empty(),"271560")
    def test_invalid_ohlc_fails(self):
        class Frame:
            empty=False
            def iterrows(self):
                from datetime import date
                yield date(2026,11,3),{"Open":110,"High":100,"Low":90,"Close":105,"Volume":100}
        with self.assertRaisesRegex(ValueError,"INVALID_YAHOO_OHLC"):
            normalize(Frame(),"271560")
    def test_valid_row(self):
        class Frame:
            empty=False
            def iterrows(self):
                from datetime import date
                yield date(2026,11,3),{"Open":100,"High":110,"Low":90,"Close":105,"Volume":100}
        rows=normalize(Frame(),"271560")
        self.assertEqual(rows[0]["ticker"],"271560")
        self.assertEqual(rows[0]["date"],"2026-11-03")

if __name__=="__main__":
    unittest.main()
