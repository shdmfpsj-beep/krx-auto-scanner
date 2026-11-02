import json,tempfile,unittest
from pathlib import Path
from c3_pipeline_readiness_v21 import inspect

class ReadinessTest(unittest.TestCase):
    def test_missing_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            report=inspect(d)
            self.assertFalse(report["forward_evaluation_ready"])
            self.assertEqual(report["buy_approvals"],0)
            self.assertIn("registry_v17",report["missing_or_invalid"])
    def test_header_only_registry_not_ready(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ("c3_preliminary.csv","c3_candidate_evidence_v1.csv"):
                (root/name).write_text("ticker\n",encoding="utf-8")
            (root/"c3_selection_evidence_v16.json").write_text('{"provisional_watch_top2":[]}',encoding="utf-8")
            (root/"c3_reference_calendar_v1.json").write_text('{"dates":[]}',encoding="utf-8")
            (root/"c3_selection_forward_registry_v17.csv").write_text("key,ticker\n",encoding="utf-8")
            self.assertFalse(inspect(root)["forward_evaluation_ready"])
if __name__=="__main__":unittest.main()
