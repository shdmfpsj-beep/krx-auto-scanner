import sys,unittest,tempfile,json,csv
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from official_krx_120d_replay import weekdays,history
class HistoryTests(unittest.TestCase):
 def test_weekdays(self):
  d=weekdays("2026-11-11",120)
  self.assertEqual(len(d),120)
  self.assertEqual(len(set(d)),120)
  self.assertTrue(all(__import__("datetime").date.fromisoformat(x).weekday()<5 for x in d))
 def test_missing_is_not_success(self):
  with tempfile.TemporaryDirectory() as tmp:
   rows,missing=history(Path(tmp),["2026-11-10"])
   self.assertEqual(rows,[]);self.assertEqual(missing,["2026-11-10"])
 def test_one_market_file_does_not_certify(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);d=root/"2026-11-10";d.mkdir()
   (d/"krx_v65_collect_status.json").write_text(json.dumps({"official_dataset_usable":False,"asof":"2026-11-10"}))
   rows,missing=history(root,["2026-11-10"])
   self.assertEqual(rows,[]);self.assertEqual(len(missing),1)
if __name__=="__main__":unittest.main()
