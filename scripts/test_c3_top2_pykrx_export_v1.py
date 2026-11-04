import unittest
from datetime import datetime,date,timedelta
from c3_top2_pykrx_export_v1 import collect,history_start,routing_probe

P=[dict(ticker="271560"),dict(ticker="026960")]
class Frame:
    empty=False
    def iterrows(self):
        yield datetime(2026,11,2),{"시가":110,"고가":120,"저가":105,"종가":115,"거래량":100}
class ExportTests(unittest.TestCase):
    def test_history_starts_before_selection(self):
        plans=[dict(ticker="271560",selection_date="2026-10-30"),
               dict(ticker="026960",selection_date="2026-10-30")]
        self.assertEqual(history_start(plans),date(2026,10,30)-timedelta(days=120))
    def test_short_history_request_rejected(self):
        with self.assertRaisesRegex(ValueError,"INSUFFICIENT_REQUESTED_HISTORY"):
            history_start([dict(selection_date="2026-10-30")],20)
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

    def test_bad_later_row_discards_entire_ticker_response(self):
        class Partial(Frame):
            def iterrows(self):
                yield from super().iterrows()
                yield datetime(2026,11,3),{"시가":110,"고가":120,"저가":105,"종가":115,"거래량":float('inf')}
        rows,days,failures=collect(P,lambda *a,**kw:Partial(),"2026-11-01","2026-11-04")
        self.assertEqual(rows,[])
        self.assertEqual(days,[])
        self.assertEqual(len(failures),2)

    def test_provider_cannot_return_prices_outside_requested_window(self):
        rows,days,failures=collect(P,lambda *a,**kw:Frame(),"2026-11-03","2026-11-04")
        self.assertEqual(rows,[])
        self.assertEqual(len(failures),2)

    def test_runtime_routing_audit_records_installed_source_without_certifying(self):
        from unittest.mock import patch
        source='def fetch(adjusted=True):\n    if adjusted:\n        df = naver.get_market_ohlcv_by_date()\n'
        with patch('c3_top2_pykrx_export_v1.inspect.getsource',return_value=source):
            r=routing_probe(lambda:None)
        self.assertEqual(r['upstream'],'NAVER_VIA_PYKRX_ADJUSTED')
        self.assertEqual(len(r['source_sha256']),64)
        self.assertTrue(r['inspection_is_not_session_certification'])

    def test_uninspectable_runtime_stays_unverified(self):
        self.assertEqual(routing_probe(len)['upstream'],'PYKRX_UPSTREAM_UNVERIFIED')

if __name__=="__main__":
    unittest.main()
