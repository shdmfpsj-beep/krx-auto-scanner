import json,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from official_history_independent_audit import audit
class AuditTests(unittest.TestCase):
 def test_empty_is_cash(self):
  with tempfile.TemporaryDirectory() as t:
   r=audit(Path(t))
   self.assertEqual(r["observed_dates"],0)
   self.assertFalse(r["performance_publication_allowed"])
   self.assertEqual(r["decision"],"CASH")
 def test_unverified_evidence_cannot_self_certify(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/"evidence.json"
   p.write_text(json.dumps({"regular_1530_session_verified":{"verified":True,"independent_review":True,"source_uri":"https://example.com","source_sha256":"abc","asof":"2026-11-10"}}))
   r=audit(Path(t),p)
   self.assertFalse(r["quality_gates"]["regular_1530_session_verified"])
 def test_missing_manifest_not_counted(self):
  with tempfile.TemporaryDirectory() as t:
   (Path(t)/"2026-11-10").mkdir()
   r=audit(Path(t))
   self.assertEqual(r["missing_manifest_folders"],["2026-11-10"])
if __name__=="__main__":unittest.main()
