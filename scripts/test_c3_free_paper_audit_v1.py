import json,tempfile,unittest
from pathlib import Path
from c3_free_paper_audit_v1 import audit
class AuditTests(unittest.TestCase):
 def test_waiting_without_evidence(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"ledger.json"
   p.write_text(json.dumps({"positions":{"p1":{"plan":{"ticker":"271560","name":"오리온"},"status":"WAITING","sessions_observed":0},"p2":{"plan":{"ticker":"026960","name":"동서"},"status":"WAITING","sessions_observed":0}}}),encoding="utf8")
   x=audit(p)
   self.assertTrue(x["all_waiting_without_observations"])
   self.assertFalse(x["positions"][0]["has_forward_evidence"])
   self.assertFalse(x["positions"][0]["realized_performance_verified"])
 def test_observation_does_not_prove_profit(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"ledger.json"
   p.write_text(json.dumps({"positions":{"p":{"plan":{"ticker":"271560"},"status":"WAITING","sessions_observed":2,"last_observed_date":"2026-11-03"}}}),encoding="utf8")
   x=audit(p)
   self.assertFalse(x["all_waiting_without_observations"])
   self.assertTrue(x["positions"][0]["has_forward_evidence"])
   self.assertFalse(x["positions"][0]["realized_performance_verified"])
if __name__=="__main__":unittest.main()
