import unittest
from c3_provider_difference_diagnostic_v1 import summarize

class ProviderDifferenceDiagnosticTests(unittest.TestCase):
    def test_per_field_counts(self):
        payload={"results":[
            {"ticker":"271560","date":"2026-11-02","result":"MATCH","fields":[]},
            {"ticker":"271560","date":"2026-11-03","result":"MISMATCH","fields":["close","volume"]},
            {"ticker":"026960","date":"2026-11-03","result":"MISSING_REFERENCE","fields":[]},
        ]}
        result=summarize(payload)
        a=result["tickers"]["271560"]
        self.assertEqual((a["rows"],a["matches"],a["mismatches"]),(2,1,1))
        self.assertEqual(a["field_mismatches"],{"close":1,"volume":1})
        self.assertEqual(result["tickers"]["026960"]["missing"],1)
        self.assertFalse(result["trade_approved"])
        self.assertFalse(result["regular_only_certified"])

if __name__=="__main__":
    unittest.main()
