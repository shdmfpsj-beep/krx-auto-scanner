import unittest
from c3_top2_provisional_report_v1 import validate_export

P=[{"ticker":"271560"},{"ticker":"026960"}]
D={("271560","2026-11-02"):{"close":1},("026960","2026-11-02"):{"close":1}}
M={"provider":"pykrx","price_adjustment":"ADJUSTED","rows":2,
   "tickers":["271560","026960"],"end":"2026-11-03","failures":{}}

class ExportIntegrityTests(unittest.TestCase):
    def test_valid_consistent(self):
        self.assertTrue(validate_export(P,D,M))
    def test_missing_ticker(self):
        with self.assertRaisesRegex(ValueError,"MISSING_OR_UNEXPECTED_TICKER"):
            validate_export(P,{list(D)[0]:{}},{**M,"rows":1,"tickers":["271560"]})
    def test_wrong_count(self):
        with self.assertRaisesRegex(ValueError,"MANIFEST_ROW_COUNT_MISMATCH"):
            validate_export(P,D,{**M,"rows":3})
    def test_collector_failure(self):
        with self.assertRaisesRegex(ValueError,"COLLECTOR_FAILURES"):
            validate_export(P,D,{**M,"failures":{"271560":"EMPTY_RESPONSE"}})
    def test_future_price(self):
        with self.assertRaisesRegex(ValueError,"PRICE_AFTER_MANIFEST_END"):
            validate_export(P,D,{**M,"end":"2026-11-01"})
    def test_wrong_provider(self):
        with self.assertRaisesRegex(ValueError,"UNEXPECTED_SOURCE_METADATA"):
            validate_export(P,D,{**M,"provider":"unknown"})
    def test_duplicate_plans(self):
        with self.assertRaisesRegex(ValueError,"EXPECTED_TWO_UNIQUE_PLANS"):
            validate_export([P[0],P[0]],D,M)

if __name__=="__main__":
    unittest.main()
