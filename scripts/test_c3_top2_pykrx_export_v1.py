import unittest
from datetime import datetime
from c3_top2_pykrx_export_v1 import collect

P=[dict(ticker="271560"),dict(ticker="026960")]
class Frame:
    empty=False
    def iterrows(self):
        yield datetime(2026,11,2),{"시가":110,"고가":120,"저가":105,"종가":115,"거래량":100}
class ExportTests(unittest.TestCase):
    def test_two_ticker_export(self):
        rows,days,failures=collect(P,lambda *a,**kw:Frame(),"2026-11-01","2026-11-04")
        self.assertEqual(len(rows),2)
        self.assertEqual(days,["2026-11-02"])
        self.assertFalse(failures)
    def test_empty_provider_failure(self):
        class Empty: empty=True
        rows,days,failures=collect(P,lambda *a,**kw:Empty(),"2026-11-01","2026-11-04")
        self.assertEqual(len(failures),2)
    def test_duplicate_ticker_rejected(self):
        with self.assertRaises(ValueError):
            collect([P[0],P[0]],lambda *a,**kw:Frame(),"2026-11-01","2026-11-04")
    def test_bad_ohlc_rejected(self):
        class Bad:
            empty=False
            def iterrows(self):
                yield datetime(2026,11,2),{"시가":110,"고가":100,"저가":105,"종가":115,"거래량":100}
        rows,days,failures=collect(P,lambda *a,**kw:Bad(),"2026-11-01","2026-11-04")
        self.assertEqual(len(failures),2)
    def test_fetch_adjusted_explicit(self):
        calls=[]
        def fetch(*a,**kw):
            calls.append(kw)
            return Frame()
        collect(P,fetch,"2026-11-01","2026-11-04")
        self.assertTrue(all(c["adjusted"] is True for c in calls))

if __name__=="__main__":
    unittest.main()
