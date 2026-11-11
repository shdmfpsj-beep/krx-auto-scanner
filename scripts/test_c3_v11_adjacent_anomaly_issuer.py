import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_v11_adjacent_anomaly_issuer import num,paired_compare

def row(parval,shares):
    return {"PARVAL":str(parval),"LIST_SHRS":str(shares)}

class CorporateEvidenceTests(unittest.TestCase):
 def test_price_jump_without_share_or_par_change_is_not_certified_ca(self):
    self.assertEqual(paired_compare(row(500,100000),row(500,100000)),
        "NO_PARVAL_OR_SHARES_CHANGE_OBSERVED")
 def test_par_value_change_is_not_action_certification(self):
    self.assertEqual(paired_compare(row(5000,100000),row(500,100000)),
        "PARVAL_CHANGED_UNVERIFIED_CAUSE")
 def test_shares_change_is_only_metadata(self):
    self.assertEqual(paired_compare(row(500,100000),row(500,200000)),
        "SHARES_CHANGED_UNVERIFIED_CAUSE")
 def test_both_changed(self):
    self.assertEqual(paired_compare(row(5000,100000),row(500,200000)),
        "BOTH_PARVAL_AND_SHARES_CHANGED_UNVERIFIED_CAUSE")
 def test_missing_issuer_is_blocked(self):
    self.assertEqual(paired_compare(None,row(500,100)),
        "BLOCKED_MISSING_ISSUER_ON_ONE_DATE")
 def test_missing_metadata_is_unverified(self):
    self.assertEqual(paired_compare(row(500,100),row("",100)),
        "UNVERIFIED_NUMERIC_METADATA_MISSING")
 def test_non_numeric_not_inferred(self):
    self.assertIsNone(num("N/A"))
    self.assertEqual(num("1,000"),1000)
if __name__=="__main__":unittest.main()
