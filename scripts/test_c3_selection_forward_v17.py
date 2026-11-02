import json,tempfile,unittest
from pathlib import Path
from c3_selection_forward_v17 import register

class ForwardRegistryTest(unittest.TestCase):
    def test_idempotent_with_one_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"source.json"
            output=Path(d)/"ledger.csv"
            source.write_text(json.dumps({"provisional_watch_top2":[
                {"ticker":"000001","price_date":"2026-11-02"}]}),encoding="utf-8")
            self.assertEqual(register(str(source),str(output),"run1","1"),"REGISTERED")
            original=output.read_bytes()
            self.assertEqual(register(str(source),str(output),"run1","1"),"ALREADY_REGISTERED")
            self.assertEqual(original,output.read_bytes())
    def test_empty_candidate_has_no_trade(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"source.json"
            output=Path(d)/"ledger.csv"
            source.write_text('{"provisional_watch_top2":[]}',encoding="utf-8")
            self.assertEqual(register(str(source),str(output),"run2","1"),"REGISTERED")
            self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()),1)
if __name__=="__main__":unittest.main()
